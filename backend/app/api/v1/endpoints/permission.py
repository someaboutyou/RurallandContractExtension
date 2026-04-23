from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.schemas.permission import PermissionRead
from app.schemas.response import ApiResponse
from app.services.permission_service import permission_service

router = APIRouter()


@router.get("", response_model=ApiResponse[list[PermissionRead]])
def list_permissions(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.view")),
):
    return {"data": permission_service.list_permissions(db)}
