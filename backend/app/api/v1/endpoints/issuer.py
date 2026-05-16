from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.issuer import IssuerContractorRead, IssuerCreate, IssuerRead, IssuerUpdate
from app.schemas.land_parcel import LandParcelItem
from app.schemas.pagination import PageResponse
from app.schemas.response import ApiResponse
from app.services.issuer_service import issuer_service
from app.services.land_parcel_service import land_parcel_service

router = APIRouter()


@router.get("", response_model=ApiResponse[PageResponse[IssuerRead]])
def list_issuers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None),
    region_code: str | None = Query(default=None, alias="regionCode"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.view")),
):
    return {
        "data": issuer_service.list_issuers(
            db,
            page=page,
            page_size=page_size,
            current_user=current_user,
            keyword=keyword,
            region_code=region_code,
        )
    }


@router.post("", response_model=ApiResponse[IssuerRead], status_code=status.HTTP_201_CREATED)
def create_issuer(
    payload: IssuerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.manage")),
):
    return {"data": issuer_service.create_issuer(db, payload.model_dump(), current_user)}


@router.put("/{issuer_code}", response_model=ApiResponse[IssuerRead])
def update_issuer(
    issuer_code: str,
    payload: IssuerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.manage")),
):
    return {"data": issuer_service.update_issuer(db, issuer_code, payload.model_dump(), current_user)}


@router.get("/{issuer_code}/contractors", response_model=ApiResponse[list[IssuerContractorRead]])
def list_issuer_contractors(
    issuer_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.view")),
):
    return {"data": issuer_service.list_contractors(db, issuer_code, current_user)}


@router.get("/{issuer_code}/parcels", response_model=ApiResponse[list[LandParcelItem]])
def list_issuer_parcels(
    issuer_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.view")),
):
    return {"data": land_parcel_service.get_parcels_for_issuer(db, issuer_code, current_user)}


@router.delete("/{issuer_code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_issuer(
    issuer_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.manage")),
):
    issuer_service.delete_issuer(db, issuer_code, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
