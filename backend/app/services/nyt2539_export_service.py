"""NY/T 2539-2016 标准格式数据导出。

把调查成果按《NY/T 2539-2016 农村土地承包经营权确权登记数据库规范》
附录 B 的属性表结构（CBF / FBF / CBF_JTCY / CBHT / CBDKXX）与空间要素层
（DK 地块面 / JZD 界址点 / JZX 界址线）导出为三种交付格式：

- ``nyt2539_gdb``    File Geodatabase（fiona OpenFileGDB，属性表以非空间表存储）
- ``nyt2539_db``     SQLite 数据库（空间几何以 WKT 文本列 GEOM 存储）
- ``nyt2539_mdb_shp`` Access MDB（属性表）+ Shapefile（空间层）

**有效数据口径**（只导有效数据，写进每份导出说明）：

- 承包方 / 发包方：``result_status`` 不属于终态 ``{cancelled, extinct}``
  （与 ``services/survey/base.py::SurveyServiceBase.terminal_result_statuses`` 同源）；
- 承包地块信息 / 地块：``result_status`` 不属于
  ``{cancelled, extinct, removed, split_source}``（历史/注销/被拆分源一律不导）；
- 家庭成员：所属承包方有效，且 ``member_result_status != 'removed'``；
- 承包合同：``contract_status == 'active'``（现行合同，历史版本不导）；
- 界址点 / 界址线：参与某条有效地块图形（点/线段落在有效地块边界上）；
- 区域、租户、用户编码权限三种过滤与现有 CSV 清册导出完全同源
  （``data_export_service._region_contractor_filters`` 同口径）。

实现注意：

- 列式查询 + ``yield_per`` 流式取行（县级十几万行不能全量进内存），
  与 ``data_export_service`` 同一纪律；子查询全部在库内关联，不用
  ``in_(十几万个参数)``。
- 界址点 x/y 的坐标序为**实测口径**（2026-10-04 以 source_dkbm 地块边界实测）：
  ``survey_jzd_result.x`` = 北坐标（northing），``y`` = 东坐标（easting，含带号）；
  地块 ``geom`` 为标准 (easting, northing) 序。PostGIS 取点用
  ``ST_MakePoint(jzd.y, jzd.x)``，GeoJSON/WKT 输出坐标均为 (东, 北)。
  （模型字段注释与之一致；``boundary.py`` 写入时把 dump 坐标 (x,y) 对调存入了
  x/y 字段，使用界址点坐标时务必先核对量级：北坐标 ≈ 3.7e6，东坐标 ≈ 3.96e7。）
- mdb 写入走 ADO（pywin32）：实测 ODBC（pyodbc + ACE Driver）路径在
  CREATE_DB 后的同进程 ``SQLDriverConnect`` 会随机段错误，ADO/OLEDB 路径
  稳定且中文无损。
"""

import json
import logging
import os
import shutil
import sqlite3
import zipfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import fiona
from fiona.crs import CRS
from sqlalchemy import exists, func, literal_column, select
from sqlalchemy.orm import Session, aliased

from app.models.cbht import CONTRACT_STATUS_ACTIVE, Cbht
from app.paths import STORAGE_DIR
from app.models.survey import (
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyCbdkxxResult,
    SurveyDkResult,
    SurveyFbfResult,
    SurveyJzdResult,
    SurveyJzxResult,
)
from app.services.data_access_service import data_access_service
from app.services.survey.base import SurveyServiceBase
from app.core.crs import get_target_srid, srid_display_name

logger = logging.getLogger(__name__)

# 几何原生坐标系：CGCS2000 3°高斯-克吕格投影（米制），geom 原生 SRID。
# 单一定义点在 app/core/crs.py（安装初始化时选定，见 get_target_srid）。
_EPSG = get_target_srid()

# 与 SurveyServiceBase.terminal_result_statuses 同源
_TERMINAL_RESULT_STATUSES = SurveyServiceBase.terminal_result_statuses  # {cancelled, extinct}

# 地块系（cbdkxx / dk）的历史/无效状态：注销、消亡、移除（拆分后被替代的源地块）
_INVALID_RESULT_STATUSES = {"cancelled", "extinct", "removed", "split_source"}

# 家庭成员的无效状态
_MEMBER_INVALID_STATUSES = {"removed"}

# 点是否落在地块边界上的判定容差（度→米制坐标系，2 毫米）
_BOUNDARY_SNAP_TOLERANCE = 0.002

SUPPORTED_EXPORT_TYPES = {"nyt2539_gdb", "nyt2539_db", "nyt2539_mdb_shp"}
EXPORT_TYPE_LABELS = {
    "nyt2539_gdb": "GDB 数据库",
    "nyt2539_db": "SQLite 数据库",
    "nyt2539_mdb_shp": "MDB + SHP",
}

# ---------------------------------------------------------------------------
# 字段定义（NY/T 2539-2016 附录 B / 空间要素层，字段名 = 规范代码大写）
# kind: s=文本(length)  i=整数  f=浮点  d=YYYYMMDD 日期字符串
# 属性表按规范长度；空间层统一把超长字段压到 254（DBF 单字段上限），
# GDB / SQLite / MDB 三种介质都沿用同一份定义，避免格式间结构漂移。
# ---------------------------------------------------------------------------

# (字段名, kind, length)
_ATTR_TABLES: dict[str, list[tuple[str, str, int]]] = {
    "CBF": [
        ("CBFBM", "s", 18), ("CBFLX", "s", 1), ("CBFMC", "s", 50),
        ("CBFZJLX", "s", 1), ("CBFZJHM", "s", 20), ("CBFDZ", "s", 100),
        ("YZBM", "s", 6), ("LXDH", "s", 20), ("CBFCYSL", "i", 0),
        ("CBFDCRQ", "d", 8), ("CBFDCY", "s", 50), ("CBFDCJS", "s", 254),
        ("GSJS", "s", 254), ("GSJSR", "s", 50), ("GSSHRQ", "d", 8),
        ("GSSHR", "s", 50),
    ],
    "FBF": [
        ("FBFBM", "s", 14), ("FBFMC", "s", 50), ("FBFFZRXM", "s", 50),
        ("FZRZJLX", "s", 1), ("FZRZJHM", "s", 30), ("LXDH", "s", 15),
        ("FBFDZ", "s", 100), ("YZBM", "s", 6), ("FBFDCY", "s", 254),
        ("FBFDCRQ", "d", 8), ("FBFDCJS", "s", 254),
    ],
    "CBF_JTCY": [
        ("CBFBM", "s", 18), ("CYXM", "s", 50), ("CYXB", "s", 1),
        ("CYZJLX", "s", 1), ("CYZJHM", "s", 20), ("YHZGX", "s", 2),
        ("CYBZ", "s", 1), ("SFGYR", "s", 1), ("CYBZSM", "s", 254),
    ],
    "CBHT": [
        ("CBHTBM", "s", 19), ("YCBHTBM", "s", 19), ("FBFBM", "s", 14),
        ("CBFBM", "s", 18), ("CBFS", "s", 3), ("CBQXQ", "d", 8),
        ("CBQXZ", "d", 8), ("HTZMJ", "f", 0), ("CBDKZS", "i", 0),
        ("QDSJ", "d", 8), ("HTZMJM", "f", 0), ("YHTZMJ", "f", 0),
        ("YHTZMJM", "f", 0),
    ],
    "CBDKXX": [
        ("DKBM", "s", 19), ("FBFBM", "s", 14), ("CBFBM", "s", 18),
        ("CBJYQQDFS", "s", 3), ("HTMJ", "f", 0), ("CBHTBM", "s", 19),
        ("LZHTBM", "s", 20), ("CBJYQZBM", "s", 19), ("YHTMJ", "f", 0),
        ("HTMJM", "f", 0), ("YHTMJM", "f", 0), ("SFQQQG", "s", 1),
    ],
}

# 空间要素层：geom_kind = Point / MultiPolygon / LineString
_SPATIAL_LAYERS: dict[str, tuple[str, list[tuple[str, str, int]]]] = {
    "DK": (
        "MultiPolygon",
        [
            ("BSM", "i", 0), ("YSDM", "s", 6), ("DKBM", "s", 19),
            ("DKMC", "s", 50), ("SYQXZ", "s", 2), ("DKLB", "s", 2),
            ("TDLYLX", "s", 3), ("DLDJ", "s", 2), ("TDYT", "s", 1),
            ("SFJBNT", "s", 1), ("SCMJ", "f", 0), ("DKDZ", "s", 50),
            ("DKXZ", "s", 50), ("DKNZ", "s", 50), ("DKBZ", "s", 50),
            ("DKBZXX", "s", 254), ("ZJRXM", "s", 100),
        ],
    ),
    "JZD": (
        "Point",
        [("JZDH", "s", 32), ("JBLX", "s", 2), ("BZ", "s", 200)],
    ),
    "JZX": (
        "LineString",
        [("QDJZDH", "s", 32), ("ZDJZDH", "s", 32), ("JZXLB", "s", 2),
         ("JZXWZ", "s", 2), ("JZXSM", "s", 200)],
    ),
}

# 层顺序：先属性表后空间层（导出说明与打包目录按此展示）
_ALL_LAYERS: list[tuple[str, str, list[tuple[str, str, int]]]] = []
for _name, _fields in _ATTR_TABLES.items():
    _ALL_LAYERS.append((_name, None, _fields))
for _name, (_geom, _fields) in _SPATIAL_LAYERS.items():
    _ALL_LAYERS.append((_name, _geom, _fields))

_GEOMETRY_KEY = "_geometry"  # 行 dict 中承载几何数据的保留键


def _date8(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    return str(value)[:8].replace("-", "")


def _f(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _s(value) -> str | None:
    """字符串字段：None 保持 NULL，其余按 str 收敛（trim 由库内数据保证）。"""
    if value is None:
        return None
    return str(value)


class _Scope:
    """一次导出的取数上下文：预构造有效数据子查询与各表过滤器。"""

    def __init__(self, db: Session, region_code: str, current_user):
        self.db = db
        self.user = current_user
        tenant = data_access_service.build_tenant_filter

        # 1) 有效承包方（区域前缀 + 租户 + 编码权限 + 非终态），与 CSV 清册同口径
        cbf_filters = [SurveyCbfResult.region_code.like(f"{region_code}%")]
        tf = tenant(SurveyCbfResult, current_user)
        if tf is not None:
            cbf_filters.append(tf)
        cbf_filters.extend(
            data_access_service.build_code_scope_filters(SurveyCbfResult.cbfbm, current_user)
        )
        cbf_filters.append(SurveyCbfResult.result_status.notin_(_TERMINAL_RESULT_STATUSES))
        self.cbf_filters = cbf_filters

        # 库内子查询：区域内有效承包方编码（成员/合同/地块信息都靠它关联，避免参数爆炸）
        valid_cbfbm_sq = select(SurveyCbfResult.cbfbm).where(*cbf_filters)

        # 2) 有效家庭成员：所属承包方有效 + 非移除
        jtcy_filters = []
        tf = tenant(SurveyCbfJtcyResult, current_user)
        if tf is not None:
            jtcy_filters.append(tf)
        jtcy_filters.append(SurveyCbfJtcyResult.cbfbm.in_(valid_cbfbm_sq))
        jtcy_filters.append(SurveyCbfJtcyResult.member_result_status.notin_(_MEMBER_INVALID_STATUSES))
        self.jtcy_filters = jtcy_filters

        # 3) 有效承包地块信息 → 反推有效地块编码 / 有效发包方编码
        cbdkxx_filters = []
        tf = tenant(SurveyCbdkxxResult, current_user)
        if tf is not None:
            cbdkxx_filters.append(tf)
        cbdkxx_filters.append(SurveyCbdkxxResult.cbfbm.in_(valid_cbfbm_sq))
        cbdkxx_filters.append(SurveyCbdkxxResult.result_status.notin_(_INVALID_RESULT_STATUSES))
        self.cbdkxx_filters = cbdkxx_filters
        valid_dkbm_sq = select(SurveyCbdkxxResult.dkbm).where(*cbdkxx_filters)
        valid_fbfbm_sq = select(SurveyCbdkxxResult.fbfbm).where(*cbdkxx_filters)

        # 4) 有效发包方
        fbf_filters = []
        tf = tenant(SurveyFbfResult, current_user)
        if tf is not None:
            fbf_filters.append(tf)
        fbf_filters.append(SurveyFbfResult.fbfbm.in_(valid_fbfbm_sq))
        fbf_filters.append(SurveyFbfResult.result_status.notin_(_TERMINAL_RESULT_STATUSES))
        self.fbf_filters = fbf_filters

        # 5) 现行有效合同
        cbht_filters = []
        tf = tenant(Cbht, current_user)
        if tf is not None:
            cbht_filters.append(tf)
        cbht_filters.append(Cbht.cbfbm.in_(valid_cbfbm_sq))
        cbht_filters.append(Cbht.contract_status == CONTRACT_STATUS_ACTIVE)
        self.cbht_filters = cbht_filters

        # 6) 有效地块：编码来自有效地块信息 + 自身非历史/注销
        dk_filters = []
        tf = tenant(SurveyDkResult, current_user)
        if tf is not None:
            dk_filters.append(tf)
        dk_filters.append(SurveyDkResult.dkbm.in_(valid_dkbm_sq))
        dk_filters.append(SurveyDkResult.result_status.notin_(_INVALID_RESULT_STATUSES))
        self.dk_filters = dk_filters
        self.valid_dkbm_sq = valid_dkbm_sq

        # 7) 界址点：落在有效地块边界上（无 result_status 字段，有效性随地块图形）
        jzd_filters = []
        tf = tenant(SurveyJzdResult, current_user)
        if tf is not None:
            jzd_filters.append(tf)
        jzd_filters.append(_jzd_on_valid_dk_exists(SurveyJzdResult, self))
        self.jzd_filters = jzd_filters

        # 8) 界址线：两端界址点都参与有效地块
        j1 = aliased(SurveyJzdResult)
        j2 = aliased(SurveyJzdResult)
        z = SurveyJzxResult
        jzx_filters = []
        tf = tenant(z, current_user)
        if tf is not None:
            jzx_filters.append(tf)
        jzx_filters.append(
            exists(
                select(1).select_from(j1).where(
                    j1.jzdh == z.qdjzdh,
                    j1.tenant_code == z.tenant_code,
                    _jzd_on_valid_dk_exists(j1, self),
                )
            )
        )
        jzx_filters.append(
            exists(
                select(1).select_from(j2).where(
                    j2.jzdh == z.zdjzdh,
                    j2.tenant_code == z.tenant_code,
                    _jzd_on_valid_dk_exists(j2, self),
                )
            )
        )
        self.jzx_filters = jzx_filters


def _jzd_on_valid_dk_exists(jzd, scope: _Scope):
    """界址点是否参与有效地块：点落在某条有效地块边界 2mm 容差内。

    坐标序为**实测口径**（2026-10-04 以 source_dkbm 地块边界实测：MakePoint(y,x)
    距边界 0.0000m，(x,y) 序偏离 5 万公里）：``survey_jzd_result.x`` 存北坐标
    （northing ≈ 3.7e6），``y`` 存东坐标（easting ≈ 3.96e7）；地块 geom 为标准
    (easting, northing) 序。故 PostGIS 取点用 ``ST_MakePoint(jzd.y, jzd.x)``，
    GeoJSON/WKT 输出坐标也按 ``[y, x]`` 即 (东, 北)。
    ``survey_dk_result.geom`` 是 PostGIS 原生列、ORM 模型未声明，须用 literal_column。
    """
    pt = func.ST_SetSRID(func.ST_MakePoint(jzd.y, jzd.x), _EPSG)
    geom_col = literal_column("survey_dk_result.geom")
    return exists(
        select(1).select_from(SurveyDkResult).where(
            SurveyDkResult.tenant_code == jzd.tenant_code,
            SurveyDkResult.result_status.notin_(_INVALID_RESULT_STATUSES),
            SurveyDkResult.dkbm.in_(scope.valid_dkbm_sq),
            geom_col.is_not(None),
            func.ST_DWithin(func.ST_Boundary(func.ST_Force2D(geom_col)), pt, _BOUNDARY_SNAP_TOLERANCE),
        )
    )


# ---------------------------------------------------------------------------
# 各表行迭代器：产出 dict（规范字段名 -> 规范化值；空间层带 _geometry）
# ---------------------------------------------------------------------------

_YIELD = {"yield_per": 2000}


def _iter_cbf(scope: _Scope):
    m = SurveyCbfResult
    stmt = (
        select(
            m.cbfbm, m.cbflx, m.cbfmc, m.cbfzjlx, m.cbfzjhm, m.cbfdz,
            m.yzbm, m.lxdh, m.cbfcysl, m.cbfdcrq, m.cbfdcy, m.cbfdcjs,
            m.gsjs, m.gsjsr, m.gsshrq, m.gsshr,
        )
        .where(*scope.cbf_filters)
        .execution_options(**_YIELD)
    )
    for r in scope.db.execute(stmt):
        yield {
            "CBFBM": _s(r[0]), "CBFLX": _s(r[1]), "CBFMC": _s(r[2]),
            "CBFZJLX": _s(r[3]), "CBFZJHM": _s(r[4]), "CBFDZ": _s(r[5]),
            "YZBM": _s(r[6]), "LXDH": _s(r[7]), "CBFCYSL": r[8],
            "CBFDCRQ": _date8(r[9]), "CBFDCY": _s(r[10]), "CBFDCJS": _s(r[11]),
            "GSJS": _s(r[12]), "GSJSR": _s(r[13]), "GSSHRQ": _date8(r[14]),
            "GSSHR": _s(r[15]),
        }


def _iter_fbf(scope: _Scope):
    m = SurveyFbfResult
    stmt = (
        select(
            m.fbfbm, m.fbfmc, m.fbffzrxm, m.fzrzjlx, m.fzrzjhm, m.lxdh,
            m.fbfdz, m.yzbm, m.fbfdcy, m.fbfdcrq, m.fbfdcjs,
        )
        .where(*scope.fbf_filters)
        .execution_options(**_YIELD)
    )
    for r in scope.db.execute(stmt):
        yield {
            "FBFBM": _s(r[0]), "FBFMC": _s(r[1]), "FBFFZRXM": _s(r[2]),
            "FZRZJLX": _s(r[3]), "FZRZJHM": _s(r[4]), "LXDH": _s(r[5]),
            "FBFDZ": _s(r[6]), "YZBM": _s(r[7]), "FBFDCY": _s(r[8]),
            "FBFDCRQ": _date8(r[9]), "FBFDCJS": _s(r[10]),
        }


def _iter_cbf_jtcy(scope: _Scope):
    m = SurveyCbfJtcyResult
    stmt = (
        select(
            m.cbfbm, m.cyxm, m.cyxb, m.cyzjlx, m.cyzjhm, m.yhzgx,
            m.cybz, m.sfgyr, m.cybzsm,
        )
        .where(*scope.jtcy_filters)
        .execution_options(**_YIELD)
    )
    for r in scope.db.execute(stmt):
        yield {
            "CBFBM": _s(r[0]), "CYXM": _s(r[1]), "CYXB": _s(r[2]),
            "CYZJLX": _s(r[3]), "CYZJHM": _s(r[4]), "YHZGX": _s(r[5]),
            "CYBZ": _s(r[6]), "SFGYR": _s(r[7]), "CYBZSM": _s(r[8]),
        }


def _iter_cbht(scope: _Scope):
    m = Cbht
    stmt = (
        select(
            m.cbhtbm, m.ycbhtbm, m.fbfbm, m.cbfbm, m.cbfs, m.cbqxq,
            m.cbqxz, m.htzmj, m.cbdkzs, m.qdsj, m.htzmjm, m.yhtzmj, m.yhtzmjm,
        )
        .where(*scope.cbht_filters)
        .execution_options(**_YIELD)
    )
    for r in scope.db.execute(stmt):
        yield {
            "CBHTBM": _s(r[0]), "YCBHTBM": _s(r[1]), "FBFBM": _s(r[2]),
            "CBFBM": _s(r[3]), "CBFS": _s(r[4]), "CBQXQ": _date8(r[5]),
            "CBQXZ": _date8(r[6]), "HTZMJ": _f(r[7]), "CBDKZS": r[8],
            "QDSJ": _date8(r[9]), "HTZMJM": _f(r[10]), "YHTZMJ": _f(r[11]),
            "YHTZMJM": _f(r[12]),
        }


def _iter_cbdkxx(scope: _Scope):
    m = SurveyCbdkxxResult
    stmt = (
        select(
            m.dkbm, m.fbfbm, m.cbfbm, m.cbjyqqdfs, m.htmj, m.cbhtbm,
            m.lzhtbm, m.cbjyqzbm, m.yhtmj, m.htmjm, m.yhtmjm, m.sfqqqg,
        )
        .where(*scope.cbdkxx_filters)
        .execution_options(**_YIELD)
    )
    for r in scope.db.execute(stmt):
        yield {
            "DKBM": _s(r[0]), "FBFBM": _s(r[1]), "CBFBM": _s(r[2]),
            "CBJYQQDFS": _s(r[3]), "HTMJ": _f(r[4]), "CBHTBM": _s(r[5]),
            "LZHTBM": _s(r[6]), "CBJYQZBM": _s(r[7]), "YHTMJ": _f(r[8]),
            "HTMJM": _f(r[9]), "YHTMJM": _f(r[10]), "SFQQQG": _s(r[11]),
        }


def _iter_dk(scope: _Scope, geometry_mode: str = "geojson"):
    """地块面。geometry_mode: geojson（gdb/shp 用）| wkt（sqlite 用）| none。"""
    m = SurveyDkResult
    geom_col = literal_column("survey_dk_result.geom")
    geom_cols = []
    if geometry_mode == "geojson":
        # ST_Multi 统一升为 MultiPolygon，避免 Polygon/MultiPolygon 混层
        geom_cols.append(func.ST_AsGeoJSON(func.ST_Multi(func.ST_Force2D(geom_col))).label("_geo"))
    elif geometry_mode == "wkt":
        geom_cols.append(func.ST_AsText(func.ST_Multi(func.ST_Force2D(geom_col))).label("_geo"))
    stmt = (
        select(
            m.bsm, m.ysdm, m.dkbm, m.dkmc, m.syqxz, m.dklb, m.tdlylx,
            m.dldj, m.tdyt, m.sfjbnt, m.scmj, m.dkdz, m.dkxz, m.dknz,
            m.dkbz, m.dkbzxx, m.zjrxm,
            *geom_cols,
        )
        .where(*scope.dk_filters)
        .execution_options(yield_per=500)  # 单行带几何，批次取小
    )
    for r in scope.db.execute(stmt):
        row = {
            "BSM": r[0], "YSDM": _s(r[1]), "DKBM": _s(r[2]), "DKMC": _s(r[3]),
            "SYQXZ": _s(r[4]), "DKLB": _s(r[5]), "TDLYLX": _s(r[6]),
            "DLDJ": _s(r[7]), "TDYT": _s(r[8]), "SFJBNT": _s(r[9]),
            "SCMJ": _f(r[10]), "DKDZ": _s(r[11]), "DKXZ": _s(r[12]),
            "DKNZ": _s(r[13]), "DKBZ": _s(r[14]), "DKBZXX": _s(r[15]),
            "ZJRXM": _s(r[16]),
        }
        if geometry_mode == "geojson":
            # PostGIS 3 的 ST_AsGeoJSON 会内嵌 "crs" 成员；GeoJSON 规范默认 WGS84，
            # fiona/GDAL 据此做坐标转换会报 "Point outside of projection domain"，
            # 剥掉后按 layer 自带 CRS（目标带）原样写入。
            geo = json.loads(r._mapping["_geo"]) if r._mapping["_geo"] else None
            if geo is not None:
                geo.pop("crs", None)
            row[_GEOMETRY_KEY] = geo
        elif geometry_mode == "wkt":
            row[_GEOMETRY_KEY] = r._mapping["_geo"]
        yield row


def _iter_jzd(scope: _Scope, geometry_mode: str = "geojson"):
    m = SurveyJzdResult
    stmt = (
        select(m.jzdh, m.jblx, m.bz, m.x, m.y)
        .where(*scope.jzd_filters)
        .execution_options(**_YIELD)
    )
    for r in scope.db.execute(stmt):
        x, y = r[3], r[4]  # x=北坐标(northing)、y=东坐标(easting)，见 _jzd_on_valid_dk_exists
        row = {"JZDH": _s(r[0]), "JBLX": _s(r[1]), "BZ": _s(r[2])}
        if x is not None and y is not None:
            fy, fx = float(y), float(x)
            if geometry_mode == "geojson":
                row[_GEOMETRY_KEY] = {"type": "Point", "coordinates": [fy, fx]}
            elif geometry_mode == "wkt":
                row[_GEOMETRY_KEY] = f"POINT({fy} {fx})"
        else:
            row[_GEOMETRY_KEY] = None
        yield row


def _iter_jzx(scope: _Scope, geometry_mode: str = "geojson"):
    """界址线：几何取两端界址点连线（两端坐标由界址点表 join 而来）。"""
    z = SurveyJzxResult
    j1 = aliased(SurveyJzdResult)
    j2 = aliased(SurveyJzdResult)
    stmt = (
        select(z.qdjzdh, z.zdjzdh, z.jzxlb, z.jzxwz, z.jzxsm, j1.x, j1.y, j2.x, j2.y)
        .join(j1, (j1.jzdh == z.qdjzdh) & (j1.tenant_code == z.tenant_code))
        .join(j2, (j2.jzdh == z.zdjzdh) & (j2.tenant_code == z.tenant_code))
        .where(*scope.jzx_filters)
        .execution_options(**_YIELD)
    )
    for r in scope.db.execute(stmt):
        x1, y1, x2, y2 = r[5], r[6], r[7], r[8]  # x=北、y=东（见 _jzd_on_valid_dk_exists）
        row = {
            "QDJZDH": _s(r[0]), "ZDJZDH": _s(r[1]), "JZXLB": _s(r[2]),
            "JZXWZ": _s(r[3]), "JZXSM": _s(r[4]),
        }
        if None not in (x1, y1, x2, y2):
            fy1, fx1, fy2, fx2 = float(y1), float(x1), float(y2), float(x2)
            if geometry_mode == "geojson":
                row[_GEOMETRY_KEY] = {
                    "type": "LineString",
                    "coordinates": [[fy1, fx1], [fy2, fx2]],
                }
            elif geometry_mode == "wkt":
                row[_GEOMETRY_KEY] = f"LINESTRING({fy1} {fx1}, {fy2} {fx2})"
        else:
            row[_GEOMETRY_KEY] = None
        yield row


def _layer_iterators(scope: _Scope, geometry_mode: str):
    """表名 -> 行迭代器（_ALL_LAYERS 顺序）。"""
    return {
        "CBF": _iter_cbf(scope),
        "FBF": _iter_fbf(scope),
        "CBF_JTCY": _iter_cbf_jtcy(scope),
        "CBHT": _iter_cbht(scope),
        "CBDKXX": _iter_cbdkxx(scope),
        "DK": _iter_dk(scope, geometry_mode),
        "JZD": _iter_jzd(scope, geometry_mode),
        "JZX": _iter_jzx(scope, geometry_mode),
    }


# ---------------------------------------------------------------------------
# 写盘实现
# ---------------------------------------------------------------------------

def _layer_progress(idx: int) -> int:
    """第 idx 个图层的进度基准：图层写入整体占 15%–90%。"""
    return 15 + int(75 * idx / max(len(_ALL_LAYERS), 1))


def _fiona_props(fields) -> dict:
    props = {}
    for name, kind, length in fields:
        if kind in ("s", "d"):
            props[name] = f"str:{max(length, 1)}"
        elif kind == "i":
            props[name] = "int"
        else:
            props[name] = "float"
    return props


def _ensure_proj_data() -> None:
    """把 PROJ_DATA 指向 pyproj 自带的完整 proj.db。

    fiona wheel 内置的 PROJ 资源初始化存在进程级两态问题：有时 OpenFileGDB
    在 SyncToDisk 阶段报 "Point outside of projection domain"（要素本身已写盘，
    仅元数据 extent 更新失败）。指向 pyproj 的完整资源后实测 10/10 稳定。
    必须在 PROJ 首次实际使用（首个 CRS 操作）之前设置。
    """
    try:
        import pyproj  # noqa: PLC0415

        data_dir = Path(pyproj.__file__).parent / "proj_dir" / "share" / "proj"
        if (data_dir / "proj.db").exists():
            os.environ.setdefault("PROJ_DATA", str(data_dir))
            os.environ.setdefault("PROJ_LIB", str(data_dir))
    except Exception:  # noqa: BLE001 — 环境探测失败不阻塞导出
        pass


def _close_quietly(coll) -> None:
    """关闭 fiona collection。

    OpenFileGDB 的 SyncToDisk 在个别进程环境下会报
    ``Point outside of projection domain``：此时要素与 CRS 均已写入磁盘
    （实测可正常读回坐标与 4527 坐标系定义），仅 GDB_Items 的元数据 extent
    可能缺省，GIS 软件打开后重算范围即可。仅吞这一条已知异常，其余照抛。
    """
    try:
        coll.close()
    except Exception as exc:  # noqa: BLE001
        if "projection domain" in str(exc):
            logger.warning("GDB 图层 close 时元数据 extent 更新失败（数据已写盘）：%s", exc)
            return
        raise


def _write_gdb(scope: _Scope, gdb_path: Path, reporter=None) -> dict[str, int]:
    """File Geodatabase：空间层 + 规范属性表（geometry='None' 非空间表）。"""
    import os  # noqa: PLC0415

    _ensure_proj_data()
    counts: dict[str, int] = {}
    iters = _layer_iterators(scope, "geojson")
    crs = CRS.from_epsg(_EPSG)
    for idx, (name, geom_kind, fields) in enumerate(_ALL_LAYERS):
        schema = {"properties": _fiona_props(fields)}
        schema["geometry"] = geom_kind if geom_kind else "None"
        kwargs = {"driver": "OpenFileGDB", "layer": name, "schema": schema}
        if geom_kind:
            kwargs["crs"] = crs
        if reporter:
            reporter.report(_layer_progress(idx), f"写入 {name}（{idx + 1}/{len(_ALL_LAYERS)}）")
        coll = fiona.open(gdb_path, "w", **kwargs)
        count = 0
        try:
            for row in iters[name]:
                geom = row.pop(_GEOMETRY_KEY, None)
                coll.write({"geometry": geom, "properties": row})
                count += 1
                if reporter and count % 5000 == 0:
                    reporter.report(_layer_progress(idx), f"写入 {name}…已 {count} 行")
        finally:
            _close_quietly(coll)
        counts[name] = count
    return counts


def _write_sqlite(scope: _Scope, db_path: Path, reporter=None) -> dict[str, int]:
    """SQLite：属性表 + 空间层（GEOM 列存 WKT 文本）。"""
    counts: dict[str, int] = {}
    iters = _layer_iterators(scope, "wkt")
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=OFF")
        for idx, (name, geom_kind, fields) in enumerate(_ALL_LAYERS):
            if reporter:
                reporter.report(_layer_progress(idx), f"写入 {name}（{idx + 1}/{len(_ALL_LAYERS)}）")
            col_defs = []
            for fname, kind, length in fields:
                if kind in ("s", "d"):
                    col_defs.append(f'"{fname}" TEXT({length})')
                elif kind == "i":
                    col_defs.append(f'"{fname}" INTEGER')
                else:
                    col_defs.append(f'"{fname}" REAL')
            if geom_kind:
                col_defs.append('"GEOM" TEXT')
            conn.execute(f'CREATE TABLE "{name}" ({", ".join(col_defs)})')
            col_names = [f[0] for f in fields] + (["GEOM"] if geom_kind else [])
            placeholders = ", ".join("?" for _ in col_names)
            insert_sql = f'INSERT INTO "{name}" ({", ".join(col_names)}) VALUES ({placeholders})'
            batch: list[tuple] = []
            count = 0
            for row in iters[name]:
                geom = row.pop(_GEOMETRY_KEY, None)
                values = tuple(row.get(f[0]) for f in fields)
                if geom_kind:
                    values = values + (geom,)
                batch.append(values)
                count += 1
                if reporter and count % 5000 == 0:
                    reporter.report(_layer_progress(idx), f"写入 {name}…已 {count} 行")
                if len(batch) >= 5000:
                    conn.executemany(insert_sql, batch)
                    batch.clear()
            if batch:
                conn.executemany(insert_sql, batch)
            conn.commit()
            counts[name] = count
    finally:
        conn.close()
    return counts


def _sql_literal(kind: str, value):
    """ADO Execute 拼 SQL 的字面量：字符串转义引号，NULL 直接写 NULL。"""
    if value is None:
        return "NULL"
    if kind in ("s", "d"):
        return "'" + str(value).replace("'", "''") + "'"
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _write_mdb_shp(scope: _Scope, out_dir: Path, reporter=None) -> dict[str, int]:
    """MDB（属性表，ADO 写入）+ shp 子目录（空间层）。"""
    counts: dict[str, int] = {}
    mdb_path = out_dir / "属性表.mdb"
    # 进度步序：shp 3 个空间层 + mdb 5 张属性表，合计正好 len(_ALL_LAYERS) 步
    step = {"idx": 0}

    def _beat(message: str) -> None:
        if reporter:
            idx = step["idx"]
            reporter.report(_layer_progress(idx), f"{message}（{idx + 1}/{len(_ALL_LAYERS)}）")

    # -- 空间层 → shp
    shp_dir = out_dir / "shp"
    shp_dir.mkdir(parents=True, exist_ok=True)
    _ensure_proj_data()
    iters = _layer_iterators(scope, "geojson")
    for name, (geom_kind, fields) in _SPATIAL_LAYERS.items():
        _beat(f"写入 shp/{name}")
        schema = {"geometry": geom_kind, "properties": _fiona_props(fields)}
        shp_path = shp_dir / f"{name}.shp"
        count = 0
        with fiona.open(
            shp_path, "w", driver="ESRI Shapefile", schema=schema,
            encoding="utf-8", crs=CRS.from_epsg(_EPSG),
        ) as dst:
            for row in iters[name]:
                geom = row.pop(_GEOMETRY_KEY, None)
                if geom is None:
                    continue  # shp 无法存空几何
                dst.write({"geometry": geom, "properties": row})
                count += 1
                if reporter and count % 5000 == 0:
                    reporter.report(_layer_progress(step["idx"]), f"写入 shp/{name}…已 {count} 行")
        step["idx"] += 1
        counts[name] = count

    # -- 属性表 → mdb（ADOX 建库 + ADODB 建表插入；ODBC 路径有段错误风险，弃用）
    from win32com.client import Dispatch  # noqa: PLC0415 — 仅 mdb 分支需要 pywin32

    conn_str = f"Provider=Microsoft.ACE.OLEDB.12.0;Data Source={mdb_path};"
    adox = Dispatch("ADOX.Catalog")
    adox.Create(conn_str)
    adox.ActiveConnection.Close()
    conn = Dispatch("ADODB.Connection")
    conn.Open(conn_str)
    try:
        for name, _geom, fields in _ALL_LAYERS:
            if name in _SPATIAL_LAYERS:
                continue  # 空间层在 shp，mdb 只放规范属性表
            _beat(f"写入 mdb {name}")
            col_defs = []
            for fname, kind, length in fields:
                if kind in ("s", "d"):
                    col_defs.append(f"[{fname}] TEXT({max(length, 1)})")
                elif kind == "i":
                    col_defs.append(f"[{fname}] LONG")
                else:
                    col_defs.append(f"[{fname}] DOUBLE")
            conn.Execute(f"CREATE TABLE [{name}] ({', '.join(col_defs)})")
            col_names = ", ".join(f"[{f[0]}]" for f in fields)
            insert_prefix = f"INSERT INTO [{name}] ({col_names}) VALUES ("
            batch = 0
            count = 0
            in_trans = False
            for row in iters[name]:
                row.pop(_GEOMETRY_KEY, None)
                literals = ", ".join(_sql_literal(f[1], row.get(f[0])) for f in fields)
                if not in_trans:
                    conn.BeginTrans()  # 空表不能开着事务关连接（ADO 会报"不能被明确地切断"）
                    in_trans = True
                conn.Execute(insert_prefix + literals + ")")
                count += 1
                if reporter and count % 5000 == 0:
                    reporter.report(_layer_progress(step["idx"]), f"写入 mdb {name}…已 {count} 行")
                batch += 1
                if batch >= 2000:
                    conn.CommitTrans()
                    in_trans = False
                    batch = 0
            if in_trans:
                conn.CommitTrans()
            step["idx"] += 1
            counts[name] = count
    finally:
        conn.Close()
    return counts


def _write_readme(path: Path, export, region_code: str, counts: dict[str, int], fmt_label: str) -> None:
    lines = [
        "NY/T 2539-2016 农村土地承包经营权确权登记数据库规范 — 标准格式数据导出",
        "=" * 68,
        f"导出编号：{export.export_no}",
        f"区域：{export.region_name or region_code}（{region_code}）",
        f"格式：{fmt_label}",
        f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        "",
        "【有效数据口径】",
        "- 承包方/发包方：排除已注销（cancelled）与已消亡（extinct）成果；",
        "- 承包地块信息/地块：排除注销、消亡、移除（removed）与被拆分源（split_source）；",
        "- 家庭成员：所属承包方有效，且排除已移除（removed）成员；",
        "- 承包合同：仅现行有效合同（contract_status=active），历史版本不导出；",
        "- 界址点/界址线：仅导出参与有效地块图形的点与线段；",
        "- 数据范围已按当前用户的区域权限与租户过滤。",
        "",
        "【表结构与行数】",
    ]
    for name, geom_kind, fields in _ALL_LAYERS:
        kind_desc = "空间要素层" if geom_kind else "属性表"
        fields_desc = "、".join(f[0] for f in fields)
        lines.append(f"- {name}（{kind_desc}，{len(fields)} 字段）：{counts.get(name, 0)} 行")
        lines.append(f"    字段：{fields_desc}")
    if fmt_label == EXPORT_TYPE_LABELS["nyt2539_db"]:
        lines.append("")
        lines.append(f"说明：SQLite 库中空间层（DK/JZD/JZX）的 GEOM 列为 WKT 文本，坐标系 {srid_display_name(_EPSG)}。")
    elif fmt_label == EXPORT_TYPE_LABELS["nyt2539_mdb_shp"]:
        lines.append("")
        lines.append(f"说明：shp/ 目录为空间要素层（{srid_display_name(_EPSG)}）；属性表在 属性表.mdb（Access）。")
    elif fmt_label == EXPORT_TYPE_LABELS["nyt2539_gdb"]:
        lines.append("")
        lines.append(f"说明：GDB 空间要素层坐标系为 {srid_display_name(_EPSG)}。")
    path.write_text("\n".join(lines), encoding="utf-8-sig")


def _zip_directory(zf: ZipFile, directory: Path, arc_prefix: str) -> None:
    for f in sorted(directory.rglob("*")):
        if f.is_file():
            zf.write(f, arcname=f"{arc_prefix}/{f.relative_to(directory).as_posix()}")


def build_standard_export(
    db: Session,
    export,
    region_code: str,
    current_user,
    export_type: str,
    reporter=None,
) -> tuple[str, str, int, int]:
    """生成 NY/T 2539 标准格式导出包，返回 (相对路径, 文件名, 记录数, 字节数)。

    由 ``data_export_service.create_export`` 分派调用；产物统一为 ZIP，
    与现有下载链路共用。``reporter`` 为可选的进度汇报器（ExportProgressReporter）。
    """
    if export_type not in SUPPORTED_EXPORT_TYPES:
        raise ValueError(f"不支持的导出格式：{export_type}")

    storage_root = STORAGE_DIR / "data_exports"
    work_dir = storage_root / str(export.id) / "work"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    safe_name = (export.region_name or region_code or "region").replace("/", "_").replace("\\", "_")
    base_name = f"NYT2539_{safe_name}_{export.export_no}"

    if reporter:
        reporter.report(2, "圈定有效数据范围…", force=True)
    scope = _Scope(db, region_code, current_user)
    if reporter:
        reporter.report(10, "准备写入图层…", force=True)
    if export_type == "nyt2539_gdb":
        product_dir = work_dir / f"{base_name}.gdb"
        counts = _write_gdb(scope, product_dir, reporter=reporter)
    elif export_type == "nyt2539_db":
        product_dir = work_dir / "db"
        product_dir.mkdir(parents=True, exist_ok=True)
        counts = _write_sqlite(scope, product_dir / f"{base_name}.db", reporter=reporter)
    else:
        product_dir = work_dir / "mdb_shp"
        product_dir.mkdir(parents=True, exist_ok=True)
        counts = _write_mdb_shp(scope, product_dir, reporter=reporter)

    if reporter:
        reporter.report(92, "打包压缩产物…", force=True)
    _write_readme(product_dir / "导出说明.txt", export, region_code, counts, EXPORT_TYPE_LABELS[export_type])

    file_name = f"{base_name}.zip"
    zip_path = work_dir.parent / file_name
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as zf:
        if product_dir.is_file():
            zf.write(product_dir, arcname=product_dir.name)
        else:
            _zip_directory(zf, product_dir, product_dir.name)

    file_size = zip_path.stat().st_size
    record_count = sum(counts.values())
    logger.info(
        "NY/T 2539 导出完成 export_no=%s type=%s region=%s counts=%s size=%d",
        export.export_no, export_type, region_code, counts, file_size,
    )
    # 生成成功后清理中间产物目录（zip 内已有完整产物）
    try:
        shutil.rmtree(work_dir)
    except OSError:
        logger.warning("清理导出中间目录失败 %s", work_dir)

    rel_path = f"data_exports/{export.id}/{file_name}"
    return rel_path, file_name, record_count, file_size
