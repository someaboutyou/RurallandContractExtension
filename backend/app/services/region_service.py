import re
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.issuer import Issuer
from app.models.fbf import Fbf
from app.models.region import Region
from app.models.user import User
from app.models.user_region_permission import UserRegionPermission
from app.repositories.region_repository import region_repository


class RegionService:
    def list_regions(self, db: Session, current_user: User, level: str | None = None) -> list[dict]:
        tenant_code = self._visible_tenant_code(current_user)
        records = region_repository.list_regions(db, level=level, tenant_code=tenant_code)
        if level != "group":
            records = [item for item in records if item.level != "group"]
        records = self._filter_records_by_permission(records, current_user)
        return [self._serialize(item) for item in records]

    def list_tree(
        self,
        db: Session,
        current_user: User,
        level: str | None = None,
        include_groups: bool = False,
    ) -> list[dict]:
        tenant_code = self._visible_tenant_code(current_user)
        records = region_repository.list_regions(db, level=None, tenant_code=tenant_code)
        if not include_groups and level != "group":
            records = [item for item in records if item.level != "group"]
        records = self._filter_records_by_permission(records, current_user)
        if level:
            allowed_levels = self._levels_until(level)
            records = [item for item in records if item.level in allowed_levels]
        by_parent: dict[int | None, list[Region]] = {}
        for item in records:
            by_parent.setdefault(item.parent_id, []).append(item)

        visible_ids = {item.id for item in records}
        roots = [item for item in records if item.parent_id not in visible_ids]

        def build(item: Region) -> dict:
            node = self._serialize(item)
            node["children"] = [build(child) for child in by_parent.get(item.id, [])]
            return node

        return [build(item) for item in roots]

    def list_children(
        self,
        db: Session,
        current_user: User,
        parent_id: int | None = None,
        include_groups: bool = False,
    ) -> list[dict]:
        tenant_code = self._visible_tenant_code(current_user)
        if parent_id is None:
            records = region_repository.list_regions(db, level=None, tenant_code=tenant_code)
            if not include_groups:
                records = [item for item in records if item.level != "group"]
            records = self._filter_records_by_permission(records, current_user)
            visible_ids = {item.id for item in records}
            records = [item for item in records if item.parent_id not in visible_ids]
        else:
            records = region_repository.list_children(db, parent_id=parent_id, tenant_code=tenant_code, include_groups=include_groups)
            records = self._filter_records_by_permission(records, current_user)
        assigned_by_code = self._assigned_user_by_region_code(db, [item.code for item in records if item.level == "group"])
        return [
            self._serialize(
                item,
                leaf=self._is_leaf_for_lazy(db, item, tenant_code, include_groups),
                assigned_user_id=assigned_by_code.get(item.code),
            )
            for item in records
        ]

    def search_regions(
        self,
        db: Session,
        current_user: User,
        keyword: str,
        include_groups: bool = False,
        limit: int = 50,
    ) -> list[dict]:
        keyword = keyword.strip()
        if not keyword:
            return self.list_children(db, current_user=current_user, parent_id=None, include_groups=include_groups)
        tenant_code = self._visible_tenant_code(current_user)
        records = region_repository.search_regions(
            db,
            keyword=keyword,
            tenant_code=tenant_code,
            include_groups=include_groups,
            limit=limit,
        )
        records = self._filter_records_by_permission(records, current_user)
        assigned_by_code = self._assigned_user_by_region_code(db, [item.code for item in records if item.level == "group"])
        return [
            self._serialize(
                item,
                leaf=self._is_leaf_for_lazy(db, item, tenant_code, include_groups),
                assigned_user_id=assigned_by_code.get(item.code),
            )
            for item in records[:limit]
        ]

    def create_region(self, db: Session, payload: dict) -> dict:
        self._validate_payload(db, payload)
        parent = db.get(Region, payload.get("parentId")) if payload.get("parentId") else None
        item = Region(
            name=payload["name"].strip(),
            code=payload["code"].strip(),
            level=payload["level"],
            parent_id=parent.id if parent else None,
            tenant_code=self._derive_tenant_code(payload["code"], payload["level"]),
            full_name=self._build_full_name(parent, payload["name"].strip()),
            status=payload.get("status") or "active",
            sort_order=payload.get("sortOrder") or 0,
            remark=payload.get("remark"),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return self._serialize(item)

    def update_region(self, db: Session, region_id: int, payload: dict) -> dict:
        item = self._get_or_404(db, region_id)
        self._validate_payload(db, payload, exclude_id=region_id)
        if payload.get("parentId") == region_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="父级区域不能选择自身")
        if payload.get("parentId") and self._is_descendant(db, payload["parentId"], region_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="父级区域不能选择当前区域的下级")
        parent = db.get(Region, payload.get("parentId")) if payload.get("parentId") else None
        item.name = payload["name"].strip()
        item.code = payload["code"].strip()
        item.level = payload["level"]
        item.parent_id = parent.id if parent else None
        item.tenant_code = self._derive_tenant_code(item.code, item.level)
        item.full_name = self._build_full_name(parent, item.name)
        item.status = payload.get("status") or "active"
        item.sort_order = payload.get("sortOrder") or 0
        item.remark = payload.get("remark")
        db.commit()
        self._refresh_descendant_full_names(db, item)
        db.refresh(item)
        return self._serialize(item)

    def delete_region(self, db: Session, region_id: int) -> None:
        item = self._get_or_404(db, region_id)
        child_count = db.scalar(select(func.count(Region.id)).where(Region.parent_id == region_id)) or 0
        if child_count:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="存在下级区域，不能删除")
        user_count = db.scalar(select(func.count(User.id)).where(User.region_id == region_id)) or 0
        issuer_count = db.scalar(select(func.count(Issuer.id)).where(Issuer.region_id == region_id)) or 0
        if user_count or issuer_count:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="区域已被用户或发包方引用，不能删除，可改为停用")
        db.delete(item)
        db.commit()

    def _visible_tenant_code(self, current_user: User) -> str | None:
        return None if current_user.role.data_scope == "all" else current_user.tenant_code

    def _serialize(self, item: Region, leaf: bool | None = None, assigned_user_id: int | None = None) -> dict:
        data = {
            "id": item.id,
            "name": item.name,
            "code": item.code,
            "level": item.level,
            "tenantCode": item.tenant_code,
            "fullName": item.full_name,
            "parentId": item.parent_id,
            "status": item.status,
            "sortOrder": item.sort_order,
            "remark": item.remark,
            "createdAt": item.created_at,
            "updatedAt": item.updated_at,
            "leaf": item.level == "group" if leaf is None else leaf,
        }
        if assigned_user_id is not None:
            data["assignedUserId"] = assigned_user_id
        return data

    def _group_nodes(self, db: Session, village: Region, tenant_code: str | None, current_user: User) -> list[dict]:
        stmt = (
            select(Fbf.fbfbm, Fbf.fbfmc)
            .where(Fbf.fbfbm.startswith(village.code))
            .order_by(Fbf.fbfbm.asc())
        )
        if tenant_code:
            stmt = stmt.where(Fbf.tenant_code == tenant_code)
        if current_user.role.data_scope != "all":
            permissions = [
                permission.region_code
                for permission in getattr(current_user, "region_permissions", [])
                if permission.region_code
            ]
            if not permissions:
                permissions = [current_user.region.code] if current_user.region else []
            rows = [
                row
                for row in db.execute(stmt.execution_options(skip_tenant_scope=True)).all()
                if any(row.fbfbm.startswith(code) or code.startswith(row.fbfbm) for code in permissions)
            ]
        else:
            rows = db.execute(stmt.execution_options(skip_tenant_scope=True)).all()
        assignments = {
            row.region_code: row
            for row in db.scalars(
                select(UserRegionPermission)
                .where(UserRegionPermission.level == "group")
                .where(UserRegionPermission.region_code.startswith(village.code))
            ).all()
        }
        return [
            {
                "id": -index,
                "name": name or code,
                "code": code,
                "level": "group",
                "tenantCode": code[:6],
                "fullName": f"{village.full_name} / {name or code}",
                "parentId": village.id,
                "status": "active",
                "sortOrder": index,
                "remark": None,
                "assignedUserId": assignments[code].user_id if code in assignments else None,
                "children": [],
            }
            for index, (code, name) in enumerate(rows, start=1)
        ]

    def _filter_records_by_permission(self, records: list[Region], current_user: User) -> list[Region]:
        if current_user.role.data_scope == "all":
            return records
        permissions = [
            permission.region_code
            for permission in getattr(current_user, "region_permissions", [])
            if permission.region_code
        ]
        if not permissions and current_user.region:
            permissions = [current_user.region.code]
        if not permissions:
            return []
        return [
            item
            for item in records
            if any(item.code.startswith(code) or code.startswith(item.code) for code in permissions)
        ]

    def _get_or_404(self, db: Session, region_id: int) -> Region:
        item = db.get(Region, region_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="区域不存在")
        return item

    def _validate_payload(self, db: Session, payload: dict, exclude_id: int | None = None) -> None:
        code = payload["code"].strip()
        level = payload["level"]
        if level not in {"province", "county", "town", "village", "group"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="区域级别不合法")
        expected_lengths = {"county": 6, "town": 9, "village": 12, "group": 14}
        if level in expected_lengths and len(code) != expected_lengths[level]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{self._level_label(level)}代码必须为 {expected_lengths[level]} 位")
        existed = db.scalar(select(Region).where(Region.code == code))
        if existed is not None and existed.id != exclude_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="区域代码已存在")
        parent = db.get(Region, payload.get("parentId")) if payload.get("parentId") else None
        if level == "province" and parent is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="省级区域不能选择父级")
        expected_parent = {"county": "province", "town": "county", "village": "town", "group": "village"}.get(level)
        if expected_parent and (parent is None or parent.level != expected_parent):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{self._level_label(level)}必须选择{self._level_label(expected_parent)}父级")
        if parent and level in {"county", "town", "village", "group"} and not code.startswith(parent.code):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="区域代码必须以前级区域代码开头")

    def _derive_tenant_code(self, code: str, level: str) -> str | None:
        return code[:6] if level in {"county", "town", "village", "group"} and len(code) >= 6 else None

    def _build_full_name(self, parent: Region | None, name: str) -> str:
        return f"{parent.full_name} / {name}" if parent else name

    def _refresh_descendant_full_names(self, db: Session, item: Region) -> None:
        children = db.scalars(select(Region).where(Region.parent_id == item.id).order_by(Region.sort_order, Region.code)).all()
        for child in children:
            child.full_name = self._build_full_name(item, child.name)
            child.tenant_code = self._derive_tenant_code(child.code, child.level)
            self._refresh_descendant_full_names(db, child)
        db.commit()

    def _is_descendant(self, db: Session, possible_child_id: int, parent_id: int) -> bool:
        current = db.get(Region, possible_child_id)
        while current is not None:
            if current.parent_id == parent_id:
                return True
            current = db.get(Region, current.parent_id) if current.parent_id else None
        return False

    def _levels_until(self, level: str) -> set[str]:
        order = ["province", "county", "town", "village", "group"]
        if level not in order:
            return set(order)
        return set(order[: order.index(level) + 1])

    def _level_label(self, level: str) -> str:
        return {"province": "省级", "county": "县级", "town": "镇级", "village": "村级"}.get(level, level)

    def _is_leaf_for_lazy(self, db: Session, item: Region, tenant_code: str | None, include_groups: bool) -> bool:
        if item.level == "group":
            return True
        if item.level == "village" and not include_groups:
            return True
        stmt = select(func.count(Region.id)).where(Region.parent_id == item.id)
        if tenant_code:
            stmt = stmt.where(Region.tenant_code == tenant_code)
        if not include_groups:
            stmt = stmt.where(Region.level != "group")
        return (db.scalar(stmt) or 0) == 0

    def _assigned_user_by_region_code(self, db: Session, region_codes: list[str]) -> dict[str, int]:
        if not region_codes:
            return {}
        rows = db.scalars(
            select(UserRegionPermission)
            .where(UserRegionPermission.level == "group")
            .where(UserRegionPermission.region_code.in_(region_codes))
        ).all()
        return {row.region_code: row.user_id for row in rows}



    def derive_regions_from_fbf(self, db: Session, current_user: User) -> dict:
        """从 fbf 表中派生出镇、村、组行政区域数据。"""
        # 检查权限
        from app.api.deps import has_permission
        if not has_permission(current_user, "regions.manage"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要区域管理权限")
        
        # 获取所有不同的 region_code 和对应的 fbfmc
        rows = db.execute(
            select(Fbf.region_code, Fbf.fbfmc)
            .where(Fbf.region_code.isnot(None))
            .distinct()
        ).fetchall()
        
        if not rows:
            return {"created": 0, "message": "没有找到区域数据"}
        
        created_count = 0
        # 缓存已存在的区域代码
        existing_codes = set()
        for region in db.execute(select(Region.code)).scalars():
            existing_codes.add(region)
        
        # 处理每个区域代码
        for region_code, fbfmc in rows:
            if region_code in existing_codes:
                continue
            
            # 解析区域代码，确定级别
            code_len = len(region_code)
            if code_len == 14:
                level = "group"
                parent_code_len = 12
            elif code_len == 12:
                level = "village"
                parent_code_len = 9
            elif code_len == 9:
                level = "town"
                parent_code_len = 6
            elif code_len == 6:
                level = "county"
                parent_code_len = None
            else:
                continue  # 忽略无效代码
            
            # 提取父级代码
            parent_code = region_code[:parent_code_len] if parent_code_len else None
            
            # 解析名称
            name = self._parse_region_name(fbfmc, level)
            
            # 确保父级区域存在
            if parent_code and parent_code not in existing_codes:
                self._ensure_parent_region(db, parent_code, existing_codes)
            
            # 创建区域记录
            parent_id = None
            if parent_code:
                parent = db.execute(select(Region).where(Region.code == parent_code)).scalar()
                if parent:
                    parent_id = parent.id
            
            region = Region(
                name=name,
                code=region_code,
                level=level,
                parent_id=parent_id,
                tenant_code=self._derive_tenant_code(region_code, level),
                full_name=self._build_full_name_from_code(db, region_code, name),
                status="active",
                sort_order=0
            )
            db.add(region)
            existing_codes.add(region_code)
            created_count += 1
        
        db.commit()
        return {"created": created_count, "message": f"成功创建 {created_count} 个区域记录"}
    
    def _parse_region_name(self, fbfmc: str, level: str) -> str:
        """从 fbfmc 中解析出指定级别的名称。"""
        # 简单实现：根据级别返回相应部分
        # 假设格式为 "县名镇名村名组名"
        # 这里先返回整个 fbfmc，后续可以优化
        return fbfmc
    
    def _ensure_parent_region(self, db: Session, parent_code: str, existing_codes: set) -> None:
        """确保父级区域存在，如果不存在则创建。"""
        if parent_code in existing_codes:
            return
        
        # 递归创建父级
        code_len = len(parent_code)
        if code_len == 12:
            level = "village"
            parent_code_len = 9
        elif code_len == 9:
            level = "town"
            parent_code_len = 6
        elif code_len == 6:
            level = "county"
            parent_code_len = None
        else:
            return
        
        parent_code_of_parent = parent_code[:parent_code_len] if parent_code_len else None
        if parent_code_of_parent and parent_code_of_parent not in existing_codes:
            self._ensure_parent_region(db, parent_code_of_parent, existing_codes)
        
        # 创建父级记录
        parent_id = None
        if parent_code_of_parent:
            parent = db.execute(select(Region).where(Region.code == parent_code_of_parent)).scalar()
            if parent:
                parent_id = parent.id
        
        region = Region(
            name=parent_code,  # 暂时使用代码作为名称
            code=parent_code,
            level=level,
            parent_id=parent_id,
            tenant_code=self._derive_tenant_code(parent_code, level),
            full_name=self._build_full_name_from_code(db, parent_code, parent_code),
            status="active",
            sort_order=0
        )
        db.add(region)
        existing_codes.add(parent_code)
    
    def _build_full_name_from_code(self, db: Session, code: str, name: str) -> str:
        """根据代码构建完整名称。"""
        # 获取父级完整名称
        parent_code = None
        if len(code) == 14:
            parent_code = code[:12]
        elif len(code) == 12:
            parent_code = code[:9]
        elif len(code) == 9:
            parent_code = code[:6]
        
        if parent_code:
            parent = db.execute(select(Region).where(Region.code == parent_code)).scalar()
            if parent:
                return f"{parent.full_name} / {name}"
        return name

    def sync_regions_from_fbf(self, db: Session, current_user: User, overwrite: bool = False) -> dict:
        """从 fbf 表同步区域数据到 regions 表。overwrite=True 时覆盖已有记录的名称。"""
        from app.api.deps import has_permission
        if not has_permission(current_user, "regions.manage"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要区域管理权限")
        
        group_rows = db.execute(
            select(Fbf.fbfbm, func.min(Fbf.fbfmc))
            .where(func.length(Fbf.fbfbm) >= 12)
            .group_by(Fbf.fbfbm)
            .order_by(Fbf.fbfbm)
        ).all()
        if not group_rows:
            return {"created": 0, "updated": 0, "message": "fbf 表中没有找到业务数据"}
        
        def _parse_name(fbfmc, level):
            if level == "county":
                m = re.search(r"^(.*?县)", fbfmc)
                return m.group(1) if m else fbfmc
            elif level == "town":
                s = re.sub(r"^.*?县", "", fbfmc)
                m = re.search(r"^(.*?(?:镇|乡|开发区))", s)
                return m.group(1) if m else s
            elif level == "village":
                s = re.sub(r"^.*?(?:镇|乡|开发区)", "", fbfmc)
                m = re.search(r"^(.*?(?:村|居|社区))", s)
                return m.group(1) if m else s
            elif level == "group":
                s = re.sub(r"^.*?(?:村|居|社区)", "", fbfmc)
                m = re.search(r"([一二三四五六七八九十百零\d]+组)", s)
                return m.group(1) if m else s.strip()
            return fbfmc
        
        created = 0
        updated = 0
        
        # 确保省级占位存在
        province_code = "auto-province"
        province = db.scalar(select(Region).where(Region.code == province_code))
        if province is None:
            province = Region(
                name="导入数据省级占位", code=province_code, level="province",
                full_name="导入数据省级占位", parent_id=None, tenant_code=None,
            )
            db.add(province)
            db.flush()
            created += 1
        
        for raw_group_code, raw_group_name in group_rows:
            if not raw_group_code:
                continue
            group_code = raw_group_code[:14] if len(raw_group_code) >= 14 else None
            village_code = raw_group_code[:12]
            county_code = village_code[:6]
            town_code = village_code[:9]
            
            # 县级 —— 直接从 raw_group_name（fbfmc）解析各级名称
            # 不再按 Fbf.region_code 查询，因为该字段存的是14位 fbfbm 而非截断后的区域代码子串
            county_name = _parse_name(raw_group_name, "county") if raw_group_name else f"{county_code} 县域"
            county = db.scalar(select(Region).where(Region.code == county_code))
            if county is None:
                county = Region(
                    name=county_name, code=county_code, level="county",
                    full_name=f"导入数据 / {county_name}", parent_id=province.id, tenant_code=county_code,
                )
                db.add(county)
                db.flush()
                created += 1
            elif overwrite:
                county.name = county_name
                county.full_name = f"导入数据 / {county_name}"
                updated += 1

            # 镇级
            town_name = _parse_name(raw_group_name, "town") if raw_group_name else f"{town_code} 镇级区域"
            town = db.scalar(select(Region).where(Region.code == town_code))
            if town is None:
                town = Region(
                    name=town_name, code=town_code, level="town",
                    full_name=f"{county.full_name} / {town_name}", parent_id=county.id, tenant_code=county_code,
                )
                db.add(town)
                db.flush()
                created += 1
            elif overwrite:
                town.name = town_name
                town.full_name = f"{county.full_name} / {town_name}"
                updated += 1

            # 村级
            village_name = _parse_name(raw_group_name, "village") if raw_group_name else f"{village_code} 村级区域"
            village = db.scalar(select(Region).where(Region.code == village_code))
            if village is None:
                village = Region(
                    name=village_name, code=village_code, level="village",
                    full_name=f"{town.full_name} / {village_name}", parent_id=town.id, tenant_code=county_code,
                )
                db.add(village)
                db.flush()
                created += 1
            elif overwrite:
                village.name = village_name
                village.full_name = f"{town.full_name} / {village_name}"
                updated += 1
            # 组级
            if group_code:
                group = db.scalar(select(Region).where(Region.code == group_code))
                group_name = _parse_name(raw_group_name, "group") if raw_group_name else f"{group_code} 组级区域"
                if group is None:
                    group = Region(
                        name=group_name, code=group_code, level="group",
                        full_name=f"{village.full_name} / {group_name}", parent_id=village.id, tenant_code=county_code,
                    )
                    db.add(group)
                    created += 1
                elif overwrite:
                    group.name = group_name
                    group.full_name = f"{village.full_name} / {group_name}"
                    updated += 1
        
        db.commit()
        return {"created": created, "updated": updated, "message": f"同步完成：新增 {created} 个，更新 {updated} 个区域记录"}


region_service = RegionService()







