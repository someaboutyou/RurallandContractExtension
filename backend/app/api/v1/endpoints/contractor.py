from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.contractor import ContractorCreate, ContractorRead, ContractorUpdate
from app.schemas.pagination import PageResponse
from app.schemas.response import ApiResponse
from app.services.contractor_service import contractor_service

router = APIRouter()


@router.get("", response_model=ApiResponse[PageResponse[ContractorRead]])
def list_contractors(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None),
    type_code: str | None = Query(default=None, alias="typeCode"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {
        "data": contractor_service.list_contractors(
            db,
            page=page,
            page_size=page_size,
            current_user=current_user,
            keyword=keyword,
            type_code=type_code,
        )
    }


@router.get("/{contractor_code}", response_model=ApiResponse[ContractorRead])
def get_contractor(
    contractor_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {"data": contractor_service.get_contractor(db, contractor_code, current_user)}


@router.post("", response_model=ApiResponse[ContractorRead], status_code=status.HTTP_201_CREATED)
def create_contractor(
    payload: ContractorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": contractor_service.create_contractor(db, payload.model_dump(), current_user)}


@router.put("/{contractor_code}", response_model=ApiResponse[ContractorRead])
def update_contractor(
    contractor_code: str,
    payload: ContractorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": contractor_service.update_contractor(db, contractor_code, payload.model_dump(), current_user)}


@router.delete("/{contractor_code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contractor(
    contractor_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    contractor_service.delete_contractor(db, contractor_code, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
