from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.fbf import Fbf
from app.models.region import Region
from app.models.request_case import RequestCase
from app.models.user import User
from app.services.data_access_service import data_access_service


class DashboardRepository:
    def get_summary(self, db: Session, current_user: User) -> dict:
        user_count_stmt = select(func.count(User.id)).join(Region, Region.id == User.region_id)
        issuer_count_stmt = select(func.count(Fbf.fbfbm))
        request_count_stmt = select(func.count(RequestCase.id))
        todo_count_stmt = select(func.count(RequestCase.id)).where(RequestCase.status != "已办结")

        if current_user.role.data_scope != "all":
            region_prefix = data_access_service.get_region_scope_prefix(current_user)
            if region_prefix:
                user_count_stmt = user_count_stmt.where(Region.code.like(f"{region_prefix}%"))
                issuer_count_stmt = issuer_count_stmt.where(Fbf.fbfbm.like(f"{region_prefix}%"))
            request_filters = data_access_service.build_request_case_filters(current_user)
            request_count_stmt = request_count_stmt.where(*request_filters)
            todo_count_stmt = todo_count_stmt.where(*request_filters)

        return {
            "userCount": db.scalar(user_count_stmt) or 0,
            "issuerCount": db.scalar(issuer_count_stmt) or 0,
            "requestCount": db.scalar(request_count_stmt) or 0,
            "todoCount": db.scalar(todo_count_stmt) or 0,
        }


dashboard_repository = DashboardRepository()
