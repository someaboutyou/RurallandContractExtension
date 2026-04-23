from collections.abc import Generator

import jwt
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.auth import TokenDep
from app.models.user import User
from app.services.auth_service import auth_service


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(token: TokenDep, db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录状态无效",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        subject = payload.get("sub")
        if subject is None:
            raise credentials_error
        user_id = int(subject)
    except (jwt.InvalidTokenError, ValueError):
        raise credentials_error
    return auth_service.get_current_user(db, user_id)


def require_platform_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role.code != "platform_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅平台管理员可执行此操作",
        )
    return current_user


def has_permission(current_user: User, permission_code: str) -> bool:
    return any(item.code == permission_code for item in current_user.role.permissions)


def require_permission(permission_code: str):
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user, permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前用户无权执行此操作",
            )
        return current_user

    return dependency
