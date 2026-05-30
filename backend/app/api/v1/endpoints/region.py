from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_permission
from app.schemas.region import RegionCreate, RegionOption, RegionRead, RegionTreeNode, RegionUpdate
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


@router.get("/tree", response_model=ApiResponse[list[RegionTreeNode]])
def list_region_tree(
    level: str | None = Query(default=None),
    include_groups: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: object = Depends(get_current_user),
):
    return {"data": region_service.list_tree(db, current_user=current_user, level=level, include_groups=include_groups)}


@router.get("/children", response_model=ApiResponse[list[RegionTreeNode]])
def list_region_children(
    parent_id: int | None = Query(default=None, alias="parentId"),
    include_groups: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: object = Depends(get_current_user),
):
    return {"data": region_service.list_children(db, current_user=current_user, parent_id=parent_id, include_groups=include_groups)}


@router.get("/search", response_model=ApiResponse[list[RegionTreeNode]])
def search_regions(
    keyword: str = Query(default=""),
    include_groups: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: object = Depends(get_current_user),
):
    return {"data": region_service.search_regions(db, current_user=current_user, keyword=keyword, include_groups=include_groups, limit=limit)}


@router.post("", response_model=ApiResponse[RegionRead], status_code=status.HTTP_201_CREATED)
def create_region(
    payload: RegionCreate,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_permission("regions.manage")),
):
    return {"data": region_service.create_region(db, payload.model_dump())}


@router.put("/{region_id}", response_model=ApiResponse[RegionRead])
def update_region(
    region_id: int,
    payload: RegionUpdate,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_permission("regions.manage")),
):
    return {"data": region_service.update_region(db, region_id, payload.model_dump())}


@router.delete("/{region_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_region(
    region_id: int,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_permission("regions.manage")),
):
    region_service.delete_region(db, region_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
