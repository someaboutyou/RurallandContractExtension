from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.schemas.land_parcel import LandParcelItem
from app.schemas.response import ApiResponse
from app.services.land_parcel_service import land_parcel_service

router = APIRouter()


@router.get(
    "/{contractor_code}/parcels",
    response_model=ApiResponse[list[LandParcelItem]],
)
def get_contractor_parcels(
    contractor_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {
        "data": land_parcel_service.get_parcels_for_contractor(
            db, contractor_code, current_user
        )
    }
