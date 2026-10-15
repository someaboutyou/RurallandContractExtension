from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.schemas.pagination import PageResponse
from app.schemas.response import ApiResponse
from app.schemas.user import UserCreate, UserPasswordReset, UserRead, UserUpdate
from app.services.user_service import user_service

router = APIRouter()


@router.get("", response_model=ApiResponse[PageResponse[UserRead]])
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    role_id: int | None = Query(default=None),
    tenant_code: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.view")),
):
    # ⛔ 审计 M3：非平台管理员强制只返回本租户用户（见 user_service.list_users）
    items, total = user_service.list_users(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        role_id=role_id,
        tenant_code=tenant_code,
        status_filter=status_filter,
        current_user=current_user,
    )
    return {"data": {"items": items, "total": total, "page": page, "pageSize": page_size}}


@router.post("", response_model=ApiResponse[UserRead], status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.manage")),
):
    return {"data": user_service.create_user(db, payload.model_dump(), current_user)}


@router.put("/{user_id}", response_model=ApiResponse[UserRead])
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.manage")),
):
    return {"data": user_service.update_user(db, user_id, payload.model_dump(), current_user)}


@router.post("/{user_id}/reset-password", response_model=ApiResponse[dict[str, bool]])
def reset_password(
    user_id: int,
    payload: UserPasswordReset,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.manage")),
):
    # ⛔ 审计 M3：重置密码 = 潜在提权链入口，禁止非平台管理员动平台管理员账号
    user_service.reset_password(db, user_id, payload.password, current_user)
    return {"data": {"success": True}}


@router.delete("/{user_id}", response_model=ApiResponse[dict[str, bool]])
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.manage")),
):
    user_service.delete_user(db, user_id, operator_id=current_user.id, operator=current_user)
    return {"data": {"success": True}}
