from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.schemas.response import ApiResponse
from app.services.dashboard_service import dashboard_service

router = APIRouter()


@router.get("/summary", response_model=ApiResponse[DashboardSummary])
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard.view")),
):
    return {"data": dashboard_service.get_summary(db, current_user)}
