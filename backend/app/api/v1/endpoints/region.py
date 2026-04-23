from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.schemas.region import RegionOption
from app.schemas.response import ApiResponse
from app.services.region_service import region_service

router = APIRouter()


@router.get("", response_model=ApiResponse[list[RegionOption]])
def list_regions(
    level: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: object = Depends(get_current_user),
):
    return {"data": region_service.list_regions(db, current_user=current_user, level=level)}
