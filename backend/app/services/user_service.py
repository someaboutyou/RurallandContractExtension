from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User
from app.models.user_region_permission import UserRegionPermission
from app.repositories.region_repository import region_repository
from app.repositories.role_repository import role_repository
from app.repositories.user_repository import user_repository

VALID_USER_STATUS = {"active", "disabled"}


class UserService:
    def list_users(
        self,
        db: Session,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        role_id: int | None = None,
        tenant_code: str | None = None,
        status_filter: str | None = None,
    ) -> tuple[list[dict], int]:
        records, total = user_repository.list_users(
            db,
            page=page,
            page_size=page_size,
            keyword=keyword,
            role_id=role_id,
            tenant_code=tenant_code,
            status=status_filter,
        )
        return [self.serialize_user(item) for item in records], total

    def create_user(self, db: Session, payload: dict) -> dict:
        self._validate_status(payload["status"])
        self._ensure_username_unique(db, payload["username"])
        role = self._get_role_or_404(db, payload["roleId"])
        region_permissions = self._build_region_permissions(db, payload.get("regionCodes") or [])
        region = self._get_home_region_from_permissions(db, region_permissions)

        user = User(
            username=payload["username"].strip(),
            real_name=payload["realName"].strip(),
            password_hash=hash_password(payload["password"]),
            mobile=self._normalize_optional(payload.get("mobile")),
            status=payload["status"],
            tenant_code=region.tenant_code,
            role_id=role.id,
            region_id=region.id,
        )
        user.region_permissions = region_permissions
        return self.serialize_user(user_repository.add_user(db, user))

    def update_user(self, db: Session, user_id: int, payload: dict) -> dict:
        user = self._get_user_or_404(db, user_id)
        self._validate_status(payload["status"])
        self._ensure_username_unique(db, payload["username"], exclude_id=user_id)
        role = self._get_role_or_404(db, payload["roleId"])
        region_permissions = self._build_region_permissions(db, payload.get("regionCodes") or [], user=user)
        region = self._get_home_region_from_permissions(db, region_permissions)

        user.username = payload["username"].strip()
        user.real_name = payload["realName"].strip()
        user.mobile = self._normalize_optional(payload.get("mobile"))
        user.status = payload["status"]
        user.tenant_code = region.tenant_code
        user.role_id = role.id
        user.region_id = region.id
        user.region_permissions = region_permissions
        return self.serialize_user(user_repository.update_user(db, user))

    def reset_password(self, db: Session, user_id: int, password: str) -> None:
        user = self._get_user_or_404(db, user_id)
        user.password_hash = hash_password(password)
        user_repository.update_user(db, user)

    def delete_user(self, db: Session, user_id: int, *, operator_id: int) -> None:
        user = self._get_user_or_404(db, user_id)
        if user.id == operator_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除当前登录账号")
        user_repository.delete_user(db, user)

    def serialize_user(self, item: User) -> dict:
        return {
            "id": item.id,
            "username": item.username,
            "realName": item.real_name,
            "mobile": item.mobile,
            "tenantCode": item.tenant.code if item.tenant else item.tenant_code,
            "tenantName": item.tenant.name if item.tenant else None,
            "roleId": item.role.id,
            "role": item.role.name,
            "roleCode": item.role.code,
            "dataScope": item.role.data_scope,
            "regionId": item.region.id,
            "region": item.region.full_name,
            "regionPermissions": [
                {
                    "tenantCode": permission.tenant_code,
                    "regionCode": permission.region_code,
                    "level": permission.level,
                }
                for permission in sorted(item.region_permissions, key=lambda value: value.region_code)
            ],
            "status": item.status,
        }

    def _get_user_or_404(self, db: Session, user_id: int) -> User:
        user = user_repository.get_user(db, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        return user

    def _get_role_or_404(self, db: Session, role_id: int):
        role = role_repository.get_role(db, role_id)
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
        return role

    def _get_region_or_404(self, db: Session, region_id: int):
        region = region_repository.get_region(db, region_id)
        if region is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行政区域不存在")
        return region

    def _ensure_username_unique(self, db: Session, username: str, *, exclude_id: int | None = None) -> None:
        existed = user_repository.get_user_by_username(db, username.strip())
        if existed and existed.id != exclude_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="登录账号已存在")

    def _validate_status(self, value: str) -> None:
        if value not in VALID_USER_STATUS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户状态不合法")

    def _normalize_optional(self, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    def _build_region_permissions(
        self,
        db: Session,
        region_codes: list[str],
        *,
        user: User | None = None,
    ) -> list[UserRegionPermission]:
        normalized_codes = []
        for code in region_codes:
            normalized = self._normalize_region_code(code)
            if normalized and normalized not in normalized_codes:
                normalized_codes.append(normalized)
        if not normalized_codes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少需要配置一个数据权限区域")
        tenant_codes = {code[:6] for code in normalized_codes}
        if len(tenant_codes) > 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="数据权限区域必须属于同一个租户")

        permissions: list[UserRegionPermission] = []
        existing_by_code = {
            item.region_code: item
            for item in (user.region_permissions if user is not None else [])
        }
        for code in normalized_codes:
            self._ensure_region_code_exists(db, code)
            self._ensure_group_not_assigned(db, code, user=user)
            permission = existing_by_code.get(code)
            if permission is None:
                permission = UserRegionPermission(
                    tenant_code=code[:6],
                    region_code=code,
                    level=self._level_by_code(code),
                )
            else:
                permission.tenant_code = code[:6]
                permission.level = self._level_by_code(code)
            permissions.append(permission)
        return permissions

    def _ensure_group_not_assigned(self, db: Session, code: str, *, user: User | None = None) -> None:
        if len(code) != 14:
            return
        stmt = (
            select(UserRegionPermission)
            .where(UserRegionPermission.level == "group")
            .where(UserRegionPermission.region_code == code)
        )
        if user is not None:
            stmt = stmt.where(UserRegionPermission.user_id != user.id)
        existed = db.scalar(stmt)
        if existed is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"组级区域已分配给其他用户：{code}")

    def _get_home_region_from_permissions(self, db: Session, permissions: list[UserRegionPermission]):
        first_code = permissions[0].region_code if permissions else None
        if not first_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少需要配置一个数据权限区域")
        lookup_code = first_code[:12] if len(first_code) >= 12 else first_code
        region = region_repository.get_region_by_code(db, lookup_code)
        if region is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"数据权限区域不存在：{first_code}")
        return region

    def _ensure_region_code_exists(self, db: Session, code: str) -> None:
        lookup_code = code[:12] if len(code) >= 12 else code
        region = region_repository.get_region_by_code(db, lookup_code)
        if region is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"数据权限区域不存在：{code}")

    def _normalize_region_code(self, code: str | None) -> str | None:
        if code is None:
            return None
        text = code.strip()
        if len(text) >= 14:
            return text[:14]
        if len(text) >= 12:
            return text[:12]
        if len(text) >= 9:
            return text[:9]
        return text[:6] if len(text) >= 6 else text

    def _level_by_code(self, code: str) -> str:
        return {6: "county", 9: "town", 12: "village", 14: "group"}.get(len(code), "custom")


user_service = UserService()
