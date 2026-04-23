from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User
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
        region = self._get_region_or_404(db, payload["regionId"])

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
        return self.serialize_user(user_repository.add_user(db, user))

    def update_user(self, db: Session, user_id: int, payload: dict) -> dict:
        user = self._get_user_or_404(db, user_id)
        self._validate_status(payload["status"])
        self._ensure_username_unique(db, payload["username"], exclude_id=user_id)
        role = self._get_role_or_404(db, payload["roleId"])
        region = self._get_region_or_404(db, payload["regionId"])

        user.username = payload["username"].strip()
        user.real_name = payload["realName"].strip()
        user.mobile = self._normalize_optional(payload.get("mobile"))
        user.status = payload["status"]
        user.tenant_code = region.tenant_code
        user.role_id = role.id
        user.region_id = region.id
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


user_service = UserService()
