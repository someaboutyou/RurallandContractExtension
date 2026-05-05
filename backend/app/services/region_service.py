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
            if include_groups and item.level == "village":
                node["children"].extend(self._group_nodes(db, item, tenant_code, current_user))
            return node

        return [build(item) for item in roots]

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

    def _serialize(self, item: Region) -> dict:
        return {
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
        }

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
        if level not in {"province", "county", "town", "village"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="区域级别不合法")
        expected_lengths = {"county": 6, "town": 9, "village": 12}
        if level in expected_lengths and len(code) != expected_lengths[level]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{self._level_label(level)}代码必须为 {expected_lengths[level]} 位")
        existed = db.scalar(select(Region).where(Region.code == code))
        if existed is not None and existed.id != exclude_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="区域代码已存在")
        parent = db.get(Region, payload.get("parentId")) if payload.get("parentId") else None
        if level == "province" and parent is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="省级区域不能选择父级")
        expected_parent = {"county": "province", "town": "county", "village": "town"}.get(level)
        if expected_parent and (parent is None or parent.level != expected_parent):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{self._level_label(level)}必须选择{self._level_label(expected_parent)}父级")
        if parent and level in {"county", "town", "village"} and not code.startswith(parent.code):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="区域代码必须以前级区域代码开头")

    def _derive_tenant_code(self, code: str, level: str) -> str | None:
        return code[:6] if level in {"county", "town", "village"} and len(code) >= 6 else None

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
        order = ["province", "county", "town", "village"]
        if level not in order:
            return set(order)
        return set(order[: order.index(level) + 1])

    def _level_label(self, level: str) -> str:
        return {"province": "省级", "county": "县级", "town": "镇级", "village": "村级"}.get(level, level)


region_service = RegionService()
