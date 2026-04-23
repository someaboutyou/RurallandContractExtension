from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.schemas.auth import CurrentUser, LoginRequest, TokenPayload
from app.schemas.response import ApiResponse
from app.services.auth_service import auth_service

router = APIRouter()


@router.post("/login", response_model=ApiResponse[TokenPayload])
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    return {"data": auth_service.login(db, payload.username, payload.password)}


@router.get("/me", response_model=ApiResponse[CurrentUser])
def get_me(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return {"data": auth_service.serialize_current_user(current_user)}
