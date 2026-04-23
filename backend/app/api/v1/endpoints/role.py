from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.schemas.response import ApiResponse
from app.schemas.role import RoleCreate, RoleRead, RoleUpdate
from app.services.role_service import role_service

router = APIRouter()


@router.get("", response_model=ApiResponse[list[RoleRead]])
def list_roles(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.view")),
):
    return {"data": role_service.list_roles(db)}


@router.post("", response_model=ApiResponse[RoleRead], status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.manage")),
):
    return {"data": role_service.create_role(db, payload.model_dump())}


@router.put("/{role_id}", response_model=ApiResponse[RoleRead])
def update_role(
    role_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.manage")),
):
    return {"data": role_service.update_role(db, role_id, payload.model_dump())}


@router.delete("/{role_id}", response_model=ApiResponse[dict[str, bool]])
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.manage")),
):
    role_service.delete_role(db, role_id)
    return {"data": {"success": True}}
