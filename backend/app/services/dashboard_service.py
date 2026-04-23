from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.dashboard_repository import dashboard_repository


class DashboardService:
    def get_summary(self, db: Session, current_user: User) -> dict:
        summary = dashboard_repository.get_summary(db, current_user)
        return {**summary, "workflowEnabled": False, "gisEnabled": False}


dashboard_service = DashboardService()
