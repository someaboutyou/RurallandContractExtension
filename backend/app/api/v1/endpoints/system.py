"""部署级系统配置下发（只读）。

/map-config：地图默认中心点等部署初始化固化的配置，前端 GIS 页面用它做
初始定位（替代历史上写死在 GisView.vue 里的泗洪坐标）。数据来自
system_config 表（init_db.ensure_map_center 首次启动固化）。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.schemas.response import ApiResponse
from app.services.dictionary_service import dictionary_service

router = APIRouter()


class MapConfigRead(BaseModel):
    homeRegionCode: str | None = None
    mapCenter: list[float] | None = None


class AppDownloadRead(BaseModel):
    url: str | None = None
    configured: bool = False


@router.get("/map-config", response_model=ApiResponse[MapConfigRead])
def get_map_config(
    db: Session = Depends(get_db),
    current_user: object = Depends(get_current_user),
):
    rows = db.execute(
        text("SELECT key, value FROM system_config WHERE key IN ('map_center', 'home_region_code')")
    ).fetchall()
    values = {key: value for key, value in rows}
    center: list[float] | None = None
    raw_center = values.get("map_center")
    if raw_center:
        try:
            lng, lat = (float(part.strip()) for part in str(raw_center).split(","))
            center = [lng, lat]
        except (ValueError, TypeError):
            center = None
    return {
        "data": MapConfigRead(
            homeRegionCode=values.get("home_region_code"),
            mapCenter=center,
        )
    }


@router.get("/app-download-url", response_model=ApiResponse[AppDownloadRead])
def get_app_download_url(
    db: Session = Depends(get_db),
    current_user: object = Depends(get_current_user),
):
    """手机 App 下载地址（外网），PC 端右上角二维码用。

    地址 = http://{ip}:{port}{path}，三项均来自字典 ``app_download``
    （「字典管理」页维护）。ip 未配置时 url 为 null，前端隐藏二维码入口。
    只要求登录（不要求 dictionaries.view）——所有用户都要能扫码下载。
    """
    url = dictionary_service.compose_app_download_url(db)
    return {"data": AppDownloadRead(url=url, configured=bool(url))}
