from collections.abc import Generator

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal, set_current_user
from app.models.auth import TokenDep
from app.models.user import User
from app.services.auth_service import auth_service

# auto_error=False：授权上传的 bootstrap 闸门需要"没有 token"也能进依赖
_optional_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


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
    user = auth_service.get_current_user(db, user_id)
    set_current_user(db, user)
    return user


def require_platform_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role.code != "platform_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅平台管理员可执行此操作",
        )
    return current_user


def require_license_upload_permission(
    db: Session = Depends(get_db),
    token: str | None = Depends(_optional_oauth2),
) -> None:
    """授权文件上传 / 热重载的鉴权闸门（bootstrap 死锁修复，2026-10-20）。

    背景：授权失效时前端弹的是根组件级模态（不可关闭），登录页被挡住；
    若上传一律要求登录，就成了"要上传先登录、要登录先授权"的死锁。

    口径（按**请求时刻**的授权状态分流）：
    - 授权当前**失效**：允许匿名上传。系统本就不可用，无私钥伪造不出有效
      授权文件，匿名上传构不成提权——这是唯一能走出死锁的通道。
    - 授权当前**有效**：仅平台管理员。防止匿名传垃圾文件把好授权顶掉。
    """
    from app.core.license import LicenseStatus, license_validator

    if license_validator.validate().status != LicenseStatus.VALID:
        return

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态无效",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        subject = payload.get("sub")
        user_id = int(subject) if subject is not None else None
    except (jwt.InvalidTokenError, ValueError):
        user_id = None
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态无效",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = auth_service.get_current_user(db, user_id)
    set_current_user(db, user)
    if user.role.code != "platform_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅平台管理员可执行此操作",
        )


def has_permission(current_user: User, permission_code: str) -> bool:
    return any(item.code == permission_code for item in current_user.role.permissions)


def has_any_permission(current_user: User, permission_codes: list[str] | tuple[str, ...]) -> bool:
    current_codes = {item.code for item in current_user.role.permissions}
    return any(code in current_codes for code in permission_codes)


def require_permission(permission_code: str):
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user, permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前用户无权执行此操作",
            )
        return current_user

    return dependency


def require_any_permission(permission_codes: list[str] | tuple[str, ...]):
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if not has_any_permission(current_user, permission_codes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前用户无权执行此操作",
            )
        return current_user

    return dependency
