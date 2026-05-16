from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_permission
from app.schemas.dictionary import DictionaryItemCreate, DictionaryItemRead, DictionaryItemUpdate, DictionaryOption
from app.schemas.response import ApiResponse
from app.services.dictionary_service import dictionary_service

router = APIRouter()


@router.get("", response_model=ApiResponse[list[DictionaryItemRead]])
def list_dictionary_items(
    dictType: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    _: object = Depends(require_permission("dictionaries.view")),
):
    return {"data": dictionary_service.list_items(db, dict_type=dictType, keyword=keyword, enabled=enabled)}


@router.get("/options/{dict_type}", response_model=ApiResponse[list[DictionaryOption]])
def get_dictionary_options(
    dict_type: str,
    db: Session = Depends(get_db),
    current_user: object = Depends(get_current_user),
):
    return {"data": dictionary_service.get_options(db, dict_type)}


@router.post("", response_model=ApiResponse[DictionaryItemRead], status_code=status.HTTP_201_CREATED)
def create_dictionary_item(
    payload: DictionaryItemCreate,
    db: Session = Depends(get_db),
    _: object = Depends(require_permission("dictionaries.manage")),
):
    return {"data": dictionary_service.create_item(db, payload.model_dump())}


@router.put("/{item_id}", response_model=ApiResponse[DictionaryItemRead])
def update_dictionary_item(
    item_id: int,
    payload: DictionaryItemUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(require_permission("dictionaries.manage")),
):
    return {"data": dictionary_service.update_item(db, item_id, payload.model_dump())}


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dictionary_item(
    item_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_permission("dictionaries.manage")),
):
    dictionary_service.delete_item(db, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
