from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.login_throttle import LOCK_SECONDS, check_locked, record_failure, reset
from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.repositories.auth_repository import auth_repository

logger = logging.getLogger(__name__)


class AuthService:
    def login(self, db: Session, username: str, password: str, client_ip: str = "") -> dict:
        # ⛔ 登录失败锁定（审计 M4）：先查锁再验证，锁定期内一律 429，
        # 防止对任意用户名在线爆破。
        remaining = check_locked(username, client_ip)
        if remaining > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"登录失败次数过多，账号已临时锁定，请 {remaining} 秒后重试",
            )
        user = auth_repository.get_user_by_username(db, username)
        if user is None or not verify_password(password, user.password_hash):
            left = record_failure(username, client_ip)
            logger.warning("登录失败 username=%s ip=%s 剩余尝试次数=%s", username, client_ip, left)
            if left <= 0:
                detail = f"连续登录失败次数过多，账号已锁定 {LOCK_SECONDS // 60} 分钟"
            else:
                detail = "用户名或密码错误"
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=detail,
            )
        if user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="用户已被禁用",
            )

        # 登录成功：清除失败计数（只清「用户名+IP」这一条，不影响其他来源）
        reset(username, client_ip)
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
