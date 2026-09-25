from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.schemas.dashboard import DashboardBigscreen, DashboardSummary
from app.schemas.response import ApiResponse
from app.services.dashboard_service import dashboard_service

router = APIRouter()


@router.get("/summary", response_model=ApiResponse[DashboardSummary])
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard.view")),
):
    return {"data": dashboard_service.get_summary(db, current_user)}


@router.get("/bigscreen", response_model=ApiResponse[DashboardBigscreen])
def get_bigscreen(
    batch_id: int | None = Query(default=None, alias="batchId", description="指定批次；不传取最新进行中的批次"),
    trend_days: int = Query(default=15, ge=7, le=90, alias="trendDays", description="趋势图天数"),
    top_n: int = Query(default=8, ge=3, le=20, alias="topN", description="排行榜取前 N 名"),
    region_level: str = Query(
        default="town",
        alias="regionLevel",
        pattern="^(town|village)$",
        description="区域排行粒度：town 镇级 / village 村级",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard.bigscreen")),
):
    """二轮延包工作进展大屏聚合数据。

    权限独立于 `/summary`：大屏目前只对平台管理员开放（`dashboard.bigscreen`），
    后续要放开给其他角色，在「人员权限 → 角色权限」里勾选该权限即可，无需改代码。
    """
    return {
        "data": dashboard_service.get_bigscreen(
            db,
            current_user,
            batch_id=batch_id,
            trend_days=trend_days,
            top_n=top_n,
            region_level=region_level,
        )
    }
