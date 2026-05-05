from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.repositories.auth_repository import auth_repository


class AuthService:
    def login(self, db: Session, username: str, password: str) -> dict:
        user = auth_repository.get_user_by_username(db, username)
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )
        if user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="用户已被禁用",
            )

        token = create_access_token(str(user.id))
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": settings.jwt_access_token_expire_minutes * 60,
        }

    def get_current_user(self, db: Session, user_id: int) -> User:
        user = auth_repository.get_user_by_id(db, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="登录状态无效",
            )
        return user

    def serialize_current_user(self, user: User) -> dict:
        return {
            "id": user.id,
            "username": user.username,
            "realName": user.real_name,
            "tenantCode": user.tenant.code if user.tenant else user.tenant_code,
            "tenantName": user.tenant.name if user.tenant else None,
            "role": user.role.name,
            "roleCode": user.role.code,
            "dataScope": user.role.data_scope,
            "regionCode": user.region.code,
            "region": user.region.full_name,
            "regionPermissions": [
                {
                    "tenantCode": item.tenant_code,
                    "regionCode": item.region_code,
                    "level": item.level,
                }
                for item in sorted(user.region_permissions, key=lambda value: value.region_code)
            ],
            "status": user.status,
            "permissions": sorted(item.code for item in user.role.permissions),
        }


auth_service = AuthService()
