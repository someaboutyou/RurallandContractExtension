from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.dashboard_repository import dashboard_repository


class DashboardService:
    def get_summary(self, db: Session, current_user: User) -> dict:
        summary = dashboard_repository.get_summary(db, current_user)
        return {**summary, "workflowEnabled": False, "gisEnabled": False}

    def get_bigscreen(
        self,
        db: Session,
        current_user: User,
        *,
        batch_id: int | None = None,
        trend_days: int = 15,
        top_n: int = 8,
        region_level: str = "town",
    ) -> dict:
        """二轮延包工作进展大屏的数据。**

        空库 / 没有任何批次时**不报错**，返回一份全 0 的空结构（batch=None），
        前端据此显示"暂无调查批次"，避免大屏投屏时直接白屏或弹错误框。
        """
        batches = dashboard_repository.list_bigscreen_batches(db, current_user)
        batch = dashboard_repository.resolve_bigscreen_batch(db, current_user, batch_id)
        if batch is None:
            if batch_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="指定的调查批次不存在，或不在你的数据权限范围内",
                )
            return self._empty_bigscreen()

        payload = dashboard_repository.get_bigscreen(
            db,
            current_user,
            batch,
            trend_days=trend_days,
            top_n=top_n,
            region_level=region_level,
        )
        payload["generatedAt"] = datetime.now(timezone.utc)
        payload["batches"] = [dashboard_repository.serialize_batch_option(item) for item in batches]
        return payload

    @staticmethod
    def _empty_bigscreen() -> dict:
        return {
            "generatedAt": datetime.now(timezone.utc),
            "batch": None,
            "batches": [],
            "overview": {
                "contractorTotal": 0,
                "parcelTotal": 0,
                "issuerTotal": 0,
                "memberTotal": 0,
                "contractAreaMu": 0.0,
                "assignedCount": 0,
                "assignedRate": 0.0,
                "surveyedCount": 0,
                "surveyedRate": 0.0,
                "confirmedCount": 0,
                "confirmedRate": 0.0,
                "changedCount": 0,
                "changeRecordCount": 0,
                "requestGeneratedCount": 0,
                "attachmentCount": 0,
            },
            "funnel": [],
            "taskStatus": [],
            "assignees": [],
            "regionBoard": {"level": "town", "levelLabel": "镇级", "leading": [], "lagging": []},
            "changeTypes": [],
            "trend": [],
            "alerts": [],
        }


dashboard_service = DashboardService()
