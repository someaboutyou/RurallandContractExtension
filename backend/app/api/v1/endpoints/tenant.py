from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.schemas.response import ApiResponse
from app.schemas.tenant import TenantRead
from app.services.tenant_service import tenant_service

router = APIRouter()


@router.get("", response_model=ApiResponse[list[TenantRead]])
def list_tenants(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("users.view")),
):
    return {"data": tenant_service.list_tenants(db)}
