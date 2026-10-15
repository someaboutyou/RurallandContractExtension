from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.schemas.auth import CurrentUser, LoginRequest, TokenPayload
from app.schemas.response import ApiResponse
from app.services.auth_service import auth_service

router = APIRouter()


@router.post("/login", response_model=ApiResponse[TokenPayload])
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    # 来源 IP 用于登录失败锁定（审计 M4）；反向代理场景取 X-Forwarded-For 首段
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else ""
    return {"data": auth_service.login(db, payload.username, payload.password, client_ip)}


@router.get("/me", response_model=ApiResponse[CurrentUser])
def get_me(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return {"data": auth_service.serialize_current_user(current_user)}
