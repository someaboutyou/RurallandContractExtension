"""目标坐标系（SRID）单一定义点。

系统采用"一部署一带号"策略：安装初始化时由部署人选定目标坐标系（EPSG 代码），
首次启动固化进 ``system_config`` 表，此后库内所有空间数据（geom 列、界址点 x/y）
都只使用这一个坐标系；导入/录入时源坐标系不是它就拒绝或显式转换。

改带号 = 换一个部署项目。**不允许**在已有数据后改 ``TARGET_SRID``，
真要换带走单独的全库投影迁移工具（ST_Transform 全部 geom 表 + 重算界址点）。

坐标系白名单：CGCS2000 / 3° 高斯-克吕格投影，带号 25–45（EPSG 4513–4533）。
换算关系：EPSG = 4488 + 带号（如 39 带 → 4527，中央子午线 117°E）。
6° 带、地方独立坐标系暂不支持；地方坐标系需要往 spatial_ref_sys 注册 proj4，
后续有需求再做成"白名单 + 注册脚本"。
"""

from __future__ import annotations

import re

from app.core.config import settings

#: 默认目标坐标系：CGCS2000 / 3° 带 39 带（中央子午线 117°E），现网兼容默认值
DEFAULT_TARGET_SRID = 4527

#: 3° 带带号范围（全国覆盖）
ZONE_MIN = 25
ZONE_MAX = 45

#: EPSG 下限：4513 = CGCS2000 / 3° GK zone 25；EPSG = 4488 + zone
_EPSG_BASE = 4488

#: 支持的目标坐标系集合 {epsg: "显示名"}
SUPPORTED_TARGET_SRIDS: dict[int, str] = {
    _EPSG_BASE + zone: f"CGCS2000 / 3° 高斯-克吕格 {zone} 带"
    for zone in range(ZONE_MIN, ZONE_MAX + 1)
}


def is_supported_srid(srid: int) -> bool:
    return srid in SUPPORTED_TARGET_SRIDS


def srid_display_name(srid: int) -> str:
    """坐标系的中文显示名，如 ``CGCS2000 / 3° 高斯-克吕格 39 带（EPSG:4527）``。"""
    base = SUPPORTED_TARGET_SRIDS.get(srid, f"EPSG:{srid}")
    return f"{base}（EPSG:{srid}）"


def srid_zone(srid: int) -> int | None:
    """3° 带带号（25–45）；不在白名单返回 None。"""
    if not is_supported_srid(srid):
        return None
    return srid - _EPSG_BASE


def srid_central_meridian(srid: int) -> float | None:
    """中央子午线经度（度）；不在白名单返回 None。"""
    zone = srid_zone(srid)
    return None if zone is None else zone * 3.0


def srid_y_zone_prefix(srid: int) -> str:
    """Y（东）坐标的带号前缀字符串，如 39 带坐标 ``39512345.67`` 的 ``39``。"""
    zone = srid_zone(srid)
    return "" if zone is None else str(zone)


def get_target_srid() -> int:
    """当前部署的目标坐标系 EPSG 代码（读取自 config，安装期写入 .env）。"""
    return settings.target_srid


def _epsg_from_proj_name(name: str) -> int | None:
    """从投影名兜底解析 3° 带号（ESRI 风格 WKT 无权威 EPSG 映射时的退路）。

    生产数据常见 ``CGCS2000 / 3-degree Gauss-Kruger zone 40``（pyproj 能解析
    投影参数、``to_epsg()`` 却返回 None）。带号直接写在名字里，且带号唯一
    决定中央子午线，按名字提号是确定性的，不属"盲收"。
    """
    match = re.search(r"3[\s-]*degree[\s-]*Gauss[-\s]*Kruger[\s-]*(?:CGCS2000[\s-]*)?zone\s*(\d{1,2})", name, re.IGNORECASE)
    if not match:
        return None
    epsg = _EPSG_BASE + int(match.group(1))
    return epsg if is_supported_srid(epsg) else None


def crs_to_epsg(crs: object) -> int | None:
    """把 fiona/GDAL 的 CRS 对象或 dict 尽力解析成 EPSG 代码，失败返回 None。

    依次尝试：fiona CRS 自带的 ``to_epsg()`` → ``{'wkt': ...}`` 字典 → pyproj
    通用 ``from_user_input`` → 投影名兜底（``_epsg_from_proj_name``）。解析不出
    （元数据缺失/不规范）返回 None，由调用方（导入闸门）按"无法识别"拒绝
    导入 —— 宁可拒收，不可盲收错带数据。

    注意：EPSG 4527 等"带号版"3°带的假东坐标是 ``带号*1e6 + 500000``（39 带 =
    39500000，即东坐标天然带 39 前缀）；proj4 串里 ``ellps=CGCS2000`` 这种写法
    PROJ 不认，会解析失败 → 拒收，需要源数据方改用 WKT 或 a/rf 参数。
    """
    if crs is None:
        return None
    # fiona.crs.CRS 自带 to_epsg
    to_epsg = getattr(crs, "to_epsg", None)
    if callable(to_epsg):
        try:
            epsg = to_epsg()
            if isinstance(epsg, int):
                return epsg
        except Exception:  # noqa: BLE001
            pass
    try:
        from pyproj import CRS

        if isinstance(crs, dict) and "wkt" in crs:
            parsed = CRS.from_wkt(crs["wkt"])
        else:
            parsed = CRS.from_user_input(crs)
        epsg = parsed.to_epsg()
        if isinstance(epsg, int):
            return epsg
        # ESRI 风格 WKT：投影参数能解析但没有权威 EPSG 编号 → 按投影名提带号
        for candidate_name in (parsed.name, getattr(parsed.datum, "name", "") or ""):
            matched = _epsg_from_proj_name(candidate_name)
            if matched is not None and "cgcs2000" in (parsed.name or "").lower():
                return matched
        return None
    except Exception:  # noqa: BLE001 —— 元数据残缺/自定义坐标系，统一按"解析不出"处理
        return None


def describe_mismatch(source_srid: int | None, target_srid: int) -> str:
    """导入拒绝时给部署人的错误文案，逐字说明两边坐标系。"""
    source_text = (
        srid_display_name(source_srid) if source_srid else "无法识别（缺少或不可解析的坐标系元数据）"
    )
    return (
        f"数据坐标系为 {source_text}，与本系统目标坐标系 "
        f"{srid_display_name(target_srid)} 不一致，已拒绝导入。"
        "请先在源数据软件（ArcGIS/QGIS 等）中投影变换到目标坐标系后再导入；"
        "如需更换本系统目标坐标系，须在无数据时重新初始化，或走全库投影迁移。"
    )
