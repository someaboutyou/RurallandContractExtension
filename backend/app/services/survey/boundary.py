"""地块界址点 / 界址线属性维护。

设计要点（与《地籍调查表》承包地块调查表口径一致）：

1. **界址点、界址线都是独立实体，不隶属于某个地块。**
   相邻地块共用界址点/界址线时只存一条——这正是"共点共线不重复生成"。
2. **判重键来自图形**：地块图形 ``survey_dk_result.geom`` 才是界址点位置的
   唯一来源。界址点按 ``(tenant_code, x, y)``（毫米对齐，实测相邻地块的共用
   顶点在毫米精度下精确相等）判重；界址线按两端界址点号的**规范化有序对**
   判重，因此 A→B 与 B→A 落到同一行。
3. **两套编号**：``jzdh`` 是全库唯一编号（``JZD`` + 12 位序号），只在库内与
   数据交换中使用；调查表上打印的 ``J1``、``J2``… 是**每户按外环顶点顺序**
   临时编的显示序号，不落库。因此同一个界址点在相邻两户的打印件里可以是
   ``J3`` 和 ``J7``。
4. **地块的界址点/界址线列表由图形推导**，不做增删（要改结构就改图形），
   本模块只负责维护它们的属性。这样永远不会出现"线还在，但图形上已经没有
   这条边"的孤儿数据。
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select, text, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyCbdkxxResult,
    SurveyDkResult,
    SurveyJzdResult,
    SurveyJzxResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service
from app.services.dictionary_service import dictionary_service

logger = logging.getLogger(__name__)

# ── 选项口径：国家标准《NY/T 2539》字典表（「字典管理」页可维护） ────────────
# 界标类型、界址线类别、界址线位置的候选项一律取自字典，不再在代码里写死，
# 避免"代码口径"和"字典口径"各说各话（曾经写死的码值 1/2/3 与国标 01/02/03
# 对不上，导致入库存的值后续无法与字典互认）。
BOUNDARY_MARK_TYPE_DICT_TYPE = "nyt2539_c12_boundary_marker_type"  # C.12 界标类型
BOUNDARY_LINE_CATEGORY_DICT_TYPE = "nyt2539_c13_boundary_line_category"  # C.13 界址线类别
BOUNDARY_LINE_POSITION_DICT_TYPE = "nyt2539_c14_boundary_line_position"  # C.14 界址线位置

# 字典整类被清空、或全部停用时的兜底，与预置数据同源，
# 保证维护界面与保存校验都不会开天窗。
FALLBACK_MARK_TYPES: tuple[tuple[str, str], ...] = (
    ("1", "钢钉"),
    ("2", "水泥桩"),
    ("3", "石灰桩"),
    ("4", "喷涂标志"),
    ("5", "木桩"),
    ("6", "塑料桩"),
    ("7", "带钢帽水泥桩"),
    ("8", "瓷标志"),
    ("9", "其他"),
)
FALLBACK_LINE_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("01", "田垄（埂）"),
    ("02", "沟渠"),
    ("03", "道路"),
    ("04", "围墙"),
    ("05", "栅栏"),
    ("06", "屋墙"),
    ("07", "滴水线"),
    ("08", "山脊线"),
    ("09", "其他"),
)
FALLBACK_LINE_POSITIONS: tuple[tuple[str, str], ...] = (
    ("01", "内"),
    ("02", "中"),
    ("03", "外"),
)

# ── 打印口径：甲方《地籍调查表》承包地块调查表里的**固定勾选格** ─────────────
# 结构、顺序、列跨度照抄甲方 docx 表头；每格后面跟一组"能点亮它"的字典码值。
# 甲方的表格口径与 NY/T 2539 并不一致（甲方三组格子共 19 个，国标 C.12/13/14
# 共 21 个码值，两边对不齐），因此会出现两类情况：
#   · **空码值集合** = 甲方表上有格子，但国标字典里没有对应项
#     （界标类型的「埋石」「无」，界址线类别的「行树」「两点连线」）；
#   · 字典里有、甲方表上没格子的项（界标类型的「钢钉」，界址线类别的
#     「滴水线」「山脊线」），打印时无处可勾 —— 需要时在「字典管理」里停用，
#     或按下面的映射关系调整。
# 元组 = (打印标签, 占几列, 能点亮该格的字典码值)。
#
# ⚠️ 2026-09-20 业务口径**分两组，别一刀切**：
#   ① **界标类型（木桩/埋石/无）恒定三选一** —— 走 CADASTRAL_MARK_TYPE_FALLBACK，
#      每个界址点**有且只有一格**被勾，绝不留空；
#   ② **界址线类别 / 界址线位置维持甲方版式**：能勾就勾、勾不到留空，不为对齐
#      国标而增删格子（「行树」「两点连线」码值集合为空是**有意为之**，别当 bug 修；
#      国标 07 滴水线 / 08 山脊线 无处可勾）。
CADASTRAL_MARK_TYPE_COLUMNS: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ("木桩", 1, ("5",)),  # C.12 05 木桩
    ("埋石", 1, ()),  # 国标 C.12 无此类型，靠 fallback 兜底
    ("无", 1, ()),  # 国标 C.12 无此类型，靠 fallback 兜底
)
#: 「界标类型」三格怎么被点亮：(有值但都没命中时补勾的格, 值为空时补勾的格)。
#:
#: 甲方表上界标类型只有「木桩 / 埋石 / 无」三格，国标 C.12 却有 9 个码值
#: （1 钢钉 / 2 水泥桩 / 3 石灰桩 / 4 喷涂标志 / 5 木桩 / 6 塑料桩 /
#: 7 带钢帽水泥桩 / 8 瓷标志 / 9 其他），其中**只有 5 木桩在甲方表上有对应格**。
#: 业务口径（2026-09-20 用户明确）：
#:   · 码值 = 5（木桩）      → 勾「木桩」；
#:   · 其余**任何非空码值**  → 勾「埋石」（实地立了标志物，甲方三格里一律归埋石）；
#:   · 码值为空（没录属性）  → 勾「无」。
#: 于是每行恒有且只有一格被勾。上一版口径是"勾不到就留空"，实际后果：
#: 042 户界址点全录的是 jblx='4'（喷涂标志），打印出来界标类型三格全空 ——
#: 用户看到这个后果后改成本口径。
CADASTRAL_MARK_TYPE_FALLBACK: tuple[str, str] = ("埋石", "无")
CADASTRAL_LINE_CATEGORY_COLUMNS: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ("田埂", 1, ("01",)),  # C.13 01 田垄（埂）
    ("沟渠", 1, ("02",)),
    ("道路", 1, ("03",)),
    ("行树", 1, ()),  # 国标 C.13 无此类别
    ("围墙", 1, ("04",)),
    ("墙壁", 2, ("06",)),  # C.13 06 屋墙；表头跨 2 列
    ("栅栏", 1, ("05",)),
    ("其他界线", 2, ("09",)),  # C.13 09 其他；表头跨 2 列
    ("两点连线", 1, ()),  # 国标 C.13 无此类别
    ("", 1, ()),  # 表头留白列
)
CADASTRAL_LINE_POSITION_COLUMNS: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ("内", 1, ("01",)),
    ("中", 1, ("02",)),
    ("外", 1, ("03",)),
    ("", 1, ()),  # 表头留白列
)


def boundary_column_flags(
    columns: tuple[tuple[str, int, tuple[str, ...]], ...],
    selected: str | None,
    *,
    fallback: tuple[str, str] | None = None,
) -> list[dict]:
    """把打印列排布展开成逐列的勾选标记。

    ``selected``（库内保存的字典码值）命中该格声明的任一码值即勾选。

    ``fallback`` 给甲方**必须三选一**的勾选组用（目前只有界标类型），形如
    ``(有值但都没命中时补勾的标签, 值为空时补勾的标签)``：一个格都没命中时，
    按"码值是否为空"补勾一格，保证该组**恒有且只有一格**被勾。
    其余勾选组不传它 —— 那些"码值集合为空"的格子是甲方版式的固有缺失，
    留空是刻意的（见模块头注释）。
    """
    selected = (selected or "").strip()
    flags = [
        {
            "label": label,
            "checked": bool(selected) and selected in codes,
            "colspan": span,
        }
        for label, span, codes in columns
    ]
    if fallback and not any(item["checked"] for item in flags):
        target = fallback[0] if selected else fallback[1]
        for item in flags:
            if item["label"] == target:
                item["checked"] = True
                break
    return flags

# 全库唯一界址点号：JZD + 12 位序号（固定宽度，字典序 == 数值序）
POINT_CODE_PREFIX = "JZD"
POINT_CODE_WIDTH = 12

#: 一次性按 (x, y) 精确匹配界址点的分块大小——避免撞 PostgreSQL 参数上限
_POINT_LOOKUP_CHUNK = 500

_MM = Decimal("0.001")


def _to_mm(value) -> Decimal:
    """把图形坐标对齐到毫米，作为"共点"判重键。"""
    if value is None:
        return Decimal("0.000")
    return Decimal(str(value)).quantize(_MM, rounding=ROUND_HALF_UP)


def _fmt_mm(value: Decimal | None) -> str:
    return f"{value:.3f}" if value is not None else ""


def _display_code(index: int) -> str:
    """每户内部显示序号：界址点号 J1、J2…（不落库）。"""
    return f"J{index}"


def _order_pair(code_a: str, code_b: str) -> tuple[str, str]:
    """界址线两端规范化排序，保证 A→B 与 B→A 是同一条线。"""
    return (code_a, code_b) if code_a <= code_b else (code_b, code_a)


# ─────────────────────────────────────────────────────────────────────────────
# 图形解析：把地块外环拆成「环 → 顶点序列」
# ─────────────────────────────────────────────────────────────────────────────

def load_parcel_rings(db: Session, dkbms: list[str]) -> dict[str, list[list[tuple[Decimal, Decimal]]]]:
    """按外环解析地块顶点，返回 ``{dkbm: [环1顶点, 环2顶点, ...]}``。

    每个环内已去掉与首点重复的闭合点；坐标已对齐到毫米。
    ``geom`` 原生 SRID 就是 4527（米制），无需投影。
    """
    codes = [code for code in dict.fromkeys(dkbms) if code]
    if not codes:
        return {}
    placeholders = ", ".join(f":dkbm_{i}" for i in range(len(codes)))
    params = {f"dkbm_{i}": code for i, code in enumerate(codes)}
    stmt = text(
        f"""
        WITH src AS (
            SELECT dkbm, ST_DumpPoints(ST_Force2D(geom)) AS dp
            FROM public.survey_dk_result
            WHERE dkbm IN ({placeholders})
              AND result_status <> 'removed'
              AND geom IS NOT NULL
        )
        SELECT dkbm,
               (dp).path AS path,
               array_to_string(
                   (dp).path[1:array_upper((dp).path, 1) - 1], '-'
               ) AS ring_key,
               ST_X((dp).geom) AS easting,
               ST_Y((dp).geom) AS northing
        FROM src
        WHERE (dp).path[array_upper((dp).path, 1) - 1] = 1
        ORDER BY dkbm, path
        """
    )
    rows = db.execute(stmt, params).all()

    grouped: dict[str, dict[str, list[tuple[Decimal, Decimal]]]] = {}
    for dkbm, _path, ring_key, easting, northing in rows:
        rings = grouped.setdefault(dkbm, {})
        # X = 北坐标（northing），Y = 东坐标（easting，含 39 带前缀）
        rings.setdefault(str(ring_key), []).append((_to_mm(northing), _to_mm(easting)))

    result: dict[str, list[list[tuple[Decimal, Decimal]]]] = {}
    for dkbm, rings in grouped.items():
        cleaned: list[list[tuple[Decimal, Decimal]]] = []
        for ring in rings.values():
            if len(ring) > 1 and ring[0] == ring[-1]:
                ring = ring[:-1]  # 闭合点与首点重复，去掉
            if len(ring) >= 2:
                cleaned.append(ring)
        if cleaned:
            result[dkbm] = cleaned
    return result


def _ring_edges(ring: list[tuple[Decimal, Decimal]]) -> list[Decimal]:
    """环上每个顶点的"由此点出发的那条边"长度（闭合环，最后一点回连首点）。"""
    edges: list[Decimal] = []
    total = len(ring)
    for index, (north, east) in enumerate(ring):
        next_north, next_east = ring[(index + 1) % total]
        leg = ((next_east - east) ** 2 + (next_north - north) ** 2) ** Decimal("0.5")
        edges.append(leg.quantize(_MM, rounding=ROUND_HALF_UP))
    return edges


# ─────────────────────────────────────────────────────────────────────────────
# 已存属性读取
# ─────────────────────────────────────────────────────────────────────────────

def _load_points_by_coords(
    db: Session, tenant_code: str | None, coords: list[tuple[Decimal, Decimal]]
) -> dict[tuple[Decimal, Decimal], SurveyJzdResult]:
    """按坐标批量取界址点："共点只存一条"的查询侧实现。

    先走带租户/区域过滤的常规查询；漏掉的坐标再用**显式 tenant_code +
    skip_tenant_scope** 兜一次——因为界址点允许跨村共用，某个共用点的
    ``region_code`` 可能是邻村，若严格按区域过滤就查不到，随后插入会撞
    ``uq_survey_jzd_result_tenant_xy``。兜底查询仍然钉死 tenant_code，
    不会跨租户取数。
    """
    unique = list(dict.fromkeys(coords))
    if not unique:
        return {}
    found: dict[tuple[Decimal, Decimal], SurveyJzdResult] = {}
    for start in range(0, len(unique), _POINT_LOOKUP_CHUNK):
        chunk = unique[start : start + _POINT_LOOKUP_CHUNK]
        rows = db.scalars(
            select(SurveyJzdResult).where(
                tuple_(SurveyJzdResult.x, SurveyJzdResult.y).in_(chunk)
            )
        ).all()
        for row in rows:
            found[(_to_mm(row.x), _to_mm(row.y))] = row

    missing = [coord for coord in unique if coord not in found]
    if missing and tenant_code:
        for start in range(0, len(missing), _POINT_LOOKUP_CHUNK):
            chunk = missing[start : start + _POINT_LOOKUP_CHUNK]
            rows = db.scalars(
                select(SurveyJzdResult)
                .where(
                    SurveyJzdResult.tenant_code == tenant_code,
                    tuple_(SurveyJzdResult.x, SurveyJzdResult.y).in_(chunk),
                )
                .execution_options(skip_tenant_scope=True)
            ).all()
            for row in rows:
                found.setdefault((_to_mm(row.x), _to_mm(row.y)), row)
    return found


def _load_lines_by_points(
    db: Session, tenant_code: str | None, point_codes: list[str]
) -> dict[tuple[str, str], SurveyJzxResult]:
    """按界址点号批量取界址线（同样带跨村兜底）。"""
    unique = list(dict.fromkeys(point_codes))
    if not unique:
        return {}
    found: dict[tuple[str, str], SurveyJzxResult] = {}

    def collect(rows) -> None:
        for row in rows:
            found.setdefault((row.qdjzdh, row.zdjzdh), row)

    for start in range(0, len(unique), _POINT_LOOKUP_CHUNK):
        chunk = unique[start : start + _POINT_LOOKUP_CHUNK]
        rows = db.scalars(
            select(SurveyJzxResult).where(
                SurveyJzxResult.qdjzdh.in_(chunk) | SurveyJzxResult.zdjzdh.in_(chunk)
            )
        ).all()
        collect(rows)

    if tenant_code:
        # 兜底：只针对"还没命中任何线"的点再查一次，覆盖界址点跨村共用的情形
        touched = {code for pair in found for code in pair}
        missing = [code for code in unique if code not in touched]
        if missing:
            for start in range(0, len(missing), _POINT_LOOKUP_CHUNK):
                chunk = missing[start : start + _POINT_LOOKUP_CHUNK]
                rows = db.scalars(
                    select(SurveyJzxResult)
                    .where(
                        SurveyJzxResult.tenant_code == tenant_code,
                        SurveyJzxResult.qdjzdh.in_(chunk) | SurveyJzxResult.zdjzdh.in_(chunk),
                    )
                    .execution_options(skip_tenant_scope=True)
                ).all()
                collect(rows)
    return found


def _assemble_boundary(
    rings: list[list[tuple[Decimal, Decimal]]],
    points_map: dict[tuple[Decimal, Decimal], SurveyJzdResult],
    lines_map: dict[tuple[str, str], SurveyJzxResult],
) -> dict:
    """把"环 + 已登记点/线"组装成前端与打印模板共用的结构。

    地块在环上的每个界址点都参与**两条**界址线（前一条入、后一条出）；
    打印时"界址点号所在行"填的是**从该点出发**的那条线，因此这里按
    "序号 i 的点 → 序号 i+1 的点"组织 lines，与调查表逐行对应。
    """
    if not rings:
        return {"points": [], "lines": [], "ringCount": 0}

    # 展平所有环的顶点，显示序号 J1..Jn 跨环连续（与打印件口径一致）
    flat: list[tuple[Decimal, Decimal]] = [point for ring in rings for point in ring]

    points: list[dict] = []
    for index, (north, east) in enumerate(flat, start=1):
        row = points_map.get((north, east))
        points.append(
            {
                "seq": index,
                "code": _display_code(index),
                "jzdh": row.jzdh if row else None,
                "x": _fmt_mm(north),
                "y": _fmt_mm(east),
                "jblx": row.jblx if row else None,
                "bz": row.bz if row else None,
                "registered": row is not None,
            }
        )

    # 每条环单独成线：第 i 点与第 i+1 点（环内闭合）
    line_pairs: list[tuple[int, int]] = []  # (起点显示序号, 终点显示序号)
    offset = 0
    for ring in rings:
        total = len(ring)
        for index in range(total):
            line_pairs.append((offset + index + 1, offset + (index + 1) % total + 1))
        offset += total

    lines: list[dict] = []
    for seq, (from_seq, to_seq) in enumerate(line_pairs, start=1):
        from_point = points[from_seq - 1]
        to_point = points[to_seq - 1]
        row = None
        if from_point["jzdh"] and to_point["jzdh"]:
            row = lines_map.get(_order_pair(from_point["jzdh"], to_point["jzdh"]))
        lines.append(
            {
                "seq": seq,
                "fromCode": from_point["code"],
                "toCode": to_point["code"],
                "fromJzdh": from_point["jzdh"],
                "toJzdh": to_point["jzdh"],
                "jzxlb": row.jzxlb if row else None,
                "jzxwz": row.jzxwz if row else None,
                "jzxsm": row.jzxsm if row else None,
                "registered": row is not None,
            }
        )

    # 边长（成果表用）：按点列出"由此点出发的那条边"
    edges: list[Decimal] = []
    for ring in rings:
        edges.extend(_ring_edges(ring))
    for index, length in enumerate(edges):
        if index < len(points):
            points[index]["edge"] = _fmt_mm(length)

    return {"points": points, "lines": lines, "ringCount": len(rings)}


def build_boundary_map(
    db: Session, dkbms: list[str], *, tenant_code: str | None = None
) -> dict[str, dict]:
    """批量解析多个地块的界址点 / 界址线。

    打印场景（一批最多 300 户、每户多地块）逐地块查询会产生上百次往返，
    这里把全部坐标与点号汇总后**只查两次**，再按地块切开。
    """
    codes = [code for code in dict.fromkeys(dkbms) if code]
    if not codes:
        return {}

    rings_by_dkbm = load_parcel_rings(db, codes)

    all_coords: list[tuple[Decimal, Decimal]] = []
    for code in codes:
        for ring in rings_by_dkbm.get(code, []):
            all_coords.extend(ring)

    points_map = _load_points_by_coords(db, tenant_code, all_coords)
    lines_map = _load_lines_by_points(
        db, tenant_code, [row.jzdh for row in points_map.values() if row.jzdh]
    )

    return {
        code: _assemble_boundary(rings_by_dkbm.get(code, []), points_map, lines_map)
        for code in codes
    }


def build_parcel_boundary(
    db: Session,
    dkbm: str,
    rings: list[list[tuple[Decimal, Decimal]]] | None = None,
    *,
    tenant_code: str | None = None,
) -> dict:
    """解析单个地块的界址点 / 界址线（含已保存属性），只读、不创建记录。"""
    if rings is None:
        rings = load_parcel_rings(db, [dkbm]).get(dkbm, [])
    if not rings:
        return {"points": [], "lines": [], "ringCount": 0}

    flat: list[tuple[Decimal, Decimal]] = [point for ring in rings for point in ring]
    points_map = _load_points_by_coords(db, tenant_code, flat)
    lines_map = _load_lines_by_points(
        db, tenant_code, [row.jzdh for row in points_map.values() if row.jzdh]
    )
    return _assemble_boundary(rings, points_map, lines_map)


def _dict_backed_options(
    db: Session, dict_type: str, fallback: tuple[tuple[str, str], ...]
) -> list[dict]:
    """候选项取自字典；字典被清空或全部停用时退回内置兜底。"""
    options = dictionary_service.get_options(db, dict_type)
    if options:
        return options
    logger.warning("字典 %s 没有可用项，界址点/界址线维护退回内置兜底", dict_type)
    return [{"value": value, "label": label} for value, label in fallback]


def boundary_options(db: Session) -> dict:
    """选项表：前端维护界面与保存校验共用同一份口径，来源是字典。"""
    return {
        "markTypes": _dict_backed_options(
            db, BOUNDARY_MARK_TYPE_DICT_TYPE, FALLBACK_MARK_TYPES
        ),
        "lineCategories": _dict_backed_options(
            db, BOUNDARY_LINE_CATEGORY_DICT_TYPE, FALLBACK_LINE_CATEGORIES
        ),
        "linePositions": _dict_backed_options(
            db, BOUNDARY_LINE_POSITION_DICT_TYPE, FALLBACK_LINE_POSITIONS
        ),
    }


def boundary_code_sets(db: Session) -> dict[str, set[str]]:
    """把选项表转成校验用的码值集合（与展示口径同源，不会走偏）。"""
    options = boundary_options(db)
    return {
        "markTypes": {item["value"] for item in options["markTypes"]},
        "lineCategories": {item["value"] for item in options["lineCategories"]},
        "linePositions": {item["value"] for item in options["linePositions"]},
    }


# ─────────────────────────────────────────────────────────────────────────────
# 服务 mixin：读写接口
# ─────────────────────────────────────────────────────────────────────────────

class SurveyServiceBoundaryMixin:
    def _boundary_tenant_code(self, db: Session, current_user: User) -> str | None:
        return data_access_service.get_tenant_code(current_user)

    def _ensure_parcel_in_batch(
        self, db: Session, batch_id: int, contractor_uid: str, dkbm: str
    ) -> dict:
        """校验地块属于该批次的该承包方，并返回承包方编码。"""
        result = self._get_result(db, batch_id, contractor_uid)
        cbfbm = result.cbfbm
        relation = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.cbfbm == cbfbm,
                SurveyCbdkxxResult.dkbm == dkbm,
            )
        ).first()
        if relation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="该地块不属于当前承包方"
            )
        parcel = db.scalars(
            select(SurveyDkResult).where(
                SurveyDkResult.dkbm == dkbm,
                SurveyDkResult.result_status != "removed",
            )
        ).first()
        if parcel is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="地块不存在或已移除"
            )
        return {"result": result, "cbfbm": cbfbm, "parcel": parcel}

    def get_parcel_boundary(
        self, db: Session, batch_id: int, contractor_uid: str, dkbm: str, current_user: User
    ) -> dict:
        """界址点/界址线维护界面的读取入口（只读，不创建记录）。"""
        context = self._ensure_parcel_in_batch(db, batch_id, contractor_uid, dkbm)
        data_access_service.ensure_code_in_scope(
            current_user, dkbm, detail="地块不在当前数据权限范围内"
        )
        boundary = build_parcel_boundary(
            db, dkbm, tenant_code=self._boundary_tenant_code(db, current_user)
        )
        result = context["result"]
        return {
            "dkbm": dkbm,
            "dkmc": context["parcel"].dkmc,
            "contractorUid": contractor_uid,
            "cbfbm": context["cbfbm"],
            "mappingUnit": "米",
            "cordSystem": "CGCS2000 / 3° 高斯克吕格 39 带（EPSG:4527）",
            "editable": not (
                result.survey_status == "confirmed"
                or result.result_status in {"cancelled", "extinct"}
            ),
            "options": boundary_options(db),
            "points": boundary["points"],
            "lines": boundary["lines"],
        }

    def save_parcel_boundary(
        self, db: Session, batch_id: int, contractor_uid: str, dkbm: str, payload: dict, current_user: User
    ) -> dict:
        """保存界址点 / 界址线属性。

        结构由图形决定，所以请求体只带属性，并按**显示序号**对齐：
        ``points[].seq`` 对应外环第 seq 个界址点，``lines[].seq`` 对应
        从第 seq 个界址点出发的那条界址线。序号数量与图形不符时直接拒绝，
        避免图形改过之后把属性写到错误的点上。
        """
        context = self._ensure_parcel_in_batch(db, batch_id, contractor_uid, dkbm)
        result = context["result"]
        if result.survey_status == "confirmed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="调查成果已确认，不能继续编辑"
            )
        if result.result_status in {"cancelled", "extinct"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="该承包户已注销，不能继续编辑"
            )
        data_access_service.ensure_code_in_scope(
            current_user, dkbm, detail="地块不在当前数据权限范围内"
        )
        # 界址点线也是这一户的调查成果，归属口径与 update_result 一致：
        # 不是本户归属人就只能看，不能改。
        self.ensure_task_write_permission(db, self._ensure_batch(db, batch_id), result, current_user)

        tenant_code = self._boundary_tenant_code(db, current_user)
        rings = load_parcel_rings(db, [dkbm]).get(dkbm, [])
        if not rings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="该地块没有图形，无法维护界址点"
            )
        flat: list[tuple[Decimal, Decimal]] = [point for ring in rings for point in ring]

        point_payloads = list(payload.get("points") or [])
        line_payloads = list(payload.get("lines") or [])
        if len(point_payloads) != len(flat):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="地块图形已变化，界址点数量与提交的内容不一致，请重新打开后再保存",
            )

        self._validate_boundary_codes(
            boundary_code_sets(db), point_payloads, line_payloads
        )

        region_code = data_access_service.normalize_region_code(dkbm)
        points_map = self._ensure_boundary_points(
            db, flat, tenant_code=tenant_code, region_code=region_code, dkbm=dkbm
        )
        lines_map = self._ensure_boundary_lines(
            db, rings, points_map, tenant_code=tenant_code, region_code=region_code, dkbm=dkbm
        )

        # ── 写入属性 ──
        for index, item in enumerate(point_payloads):
            row = points_map[flat[index]]
            row.jblx = (item.get("jblx") or "").strip() or None
            row.bz = (item.get("bz") or "").strip() or None

        for index, item in enumerate(line_payloads):
            # lines[].seq 与点的显示序号一一对应：第 seq 个界址点"出发"的那条线
            seq = int(item.get("seq") or index + 1)
            if seq < 1 or seq > len(flat):
                continue
            target = self._line_of_ring_index(rings, points_map, flat, seq - 1)
            if target is None:
                continue
            row = lines_map.get(target)
            if row is None:
                continue
            row.jzxlb = (item.get("jzxlb") or "").strip() or None
            row.jzxwz = (item.get("jzxwz") or "").strip() or None
            row.jzxsm = (item.get("jzxsm") or "").strip() or None

        db.flush()
        db.commit()
        return self.get_parcel_boundary(db, batch_id, contractor_uid, dkbm, current_user)

    # ── 内部实现 ────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_boundary_codes(
        code_sets: dict[str, set[str]],
        point_payloads: list[dict],
        line_payloads: list[dict],
    ) -> None:
        """码值必须落在字典里（``code_sets`` 由 ``boundary_code_sets`` 从字典取）。"""
        for item in point_payloads:
            code = (item.get("jblx") or "").strip()
            if code and code not in code_sets["markTypes"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"无效的界标类型：{code}"
                )
        for item in line_payloads:
            category = (item.get("jzxlb") or "").strip()
            if category and category not in code_sets["lineCategories"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"无效的界址线类别：{category}"
                )
            position = (item.get("jzxwz") or "").strip()
            if position and position not in code_sets["linePositions"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"无效的界址线位置：{position}"
                )

    @staticmethod
    def _line_of_ring_index(
        rings: list[list[tuple[Decimal, Decimal]]],
        points_map: dict[tuple[Decimal, Decimal], SurveyJzdResult],
        flat: list[tuple[Decimal, Decimal]],
        index: int,
    ) -> tuple[str, str] | None:
        """第 index 个界址点"出发"的那条线，返回规范化后的两端界址点号。"""
        offset = 0
        for ring in rings:
            total = len(ring)
            if index < offset + total:
                local = index - offset
                first = points_map.get(flat[offset + local])
                second = points_map.get(flat[offset + (local + 1) % total])
                if first is None or second is None:
                    return None
                return _order_pair(first.jzdh, second.jzdh)
            offset += total
        return None

    def _allocate_point_codes(self, db: Session, count: int) -> list[str]:
        """分配全库唯一界址点号。

        取 ``max(id) + 1`` 作为序号起点（与本项目其他编号生成口径一致），
        并叠加 **session 级已分配集合**去重——Session 是 ``autoflush=False``，
        同一事务内批量创建时 ``max(id)`` 不会变化，不叠加集合会拿到同一个编号。
        """
        if count <= 0:
            return []
        next_id = (
            db.scalar(select(func.max(SurveyJzdResult.id)).execution_options(skip_tenant_scope=True))
            or 0
        ) + 1
        allocated: set[str] = db.info.setdefault("_allocated_boundary_point", set())
        codes: list[str] = []
        for _ in range(count):
            candidate = f"{POINT_CODE_PREFIX}{next_id:0{POINT_CODE_WIDTH}d}"
            while candidate in allocated:
                next_id += 1
                candidate = f"{POINT_CODE_PREFIX}{next_id:0{POINT_CODE_WIDTH}d}"
            allocated.add(candidate)
            codes.append(candidate)
            next_id += 1
        return codes

    def _ensure_boundary_points(
        self,
        db: Session,
        coords: list[tuple[Decimal, Decimal]],
        *,
        tenant_code: str | None,
        region_code: str | None,
        dkbm: str,
    ) -> dict[tuple[Decimal, Decimal], SurveyJzdResult]:
        """get-or-create：共用同一个坐标的界址点只建一条。"""
        existing = _load_points_by_coords(db, tenant_code, coords)
        missing = [coord for coord in dict.fromkeys(coords) if coord not in existing]
        if not missing:
            return existing

        for attempt in range(3):
            try:
                with db.begin_nested():
                    codes = self._allocate_point_codes(db, len(missing))
                    for coord, code in zip(missing, codes):
                        row = SurveyJzdResult(
                            jzdh=code,
                            x=coord[0],
                            y=coord[1],
                            source_dkbm=dkbm,
                            region_code=region_code,
                            tenant_code=tenant_code,
                        )
                        db.add(row)
                        existing[coord] = row
                    db.flush()
                break
            except IntegrityError:
                # 并发下可能撞 uq_survey_jzd_result_tenant_jzdh / _tenant_xy；
                # 回滚保存点后重查（另一个请求可能刚好把同一坐标的点建好了）。
                logger.warning(
                    "boundary point allocation conflict dkbm=%s attempt=%s", dkbm, attempt + 1
                )
                existing = _load_points_by_coords(db, tenant_code, coords)
                missing = [coord for coord in dict.fromkeys(coords) if coord not in existing]
                if not missing:
                    break
                if attempt == 2:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="界址点编号分配冲突，请重试",
                    )
        return existing

    def _ensure_boundary_lines(
        self,
        db: Session,
        rings: list[list[tuple[Decimal, Decimal]]],
        points_map: dict[tuple[Decimal, Decimal], SurveyJzdResult],
        *,
        tenant_code: str | None,
        region_code: str | None,
        dkbm: str,
    ) -> dict[tuple[str, str], SurveyJzxResult]:
        """get-or-create：共用同一条界址线（无序两端相同）只建一条。"""
        pairs: list[tuple[str, str]] = []
        for ring in rings:
            total = len(ring)
            for index in range(total):
                first = points_map.get(ring[index])
                second = points_map.get(ring[(index + 1) % total])
                if first is None or second is None:
                    continue
                pairs.append(_order_pair(first.jzdh, second.jzdh))
        pairs = list(dict.fromkeys(pairs))
        if not pairs:
            return {}

        all_codes = sorted({code for pair in pairs for code in pair})
        existing = _load_lines_by_points(db, tenant_code, all_codes)
        missing = [pair for pair in pairs if pair not in existing]
        if not missing:
            return existing

        for attempt in range(3):
            try:
                with db.begin_nested():
                    for first_code, second_code in missing:
                        row = SurveyJzxResult(
                            qdjzdh=first_code,
                            zdjzdh=second_code,
                            source_dkbm=dkbm,
                            region_code=region_code,
                            tenant_code=tenant_code,
                        )
                        db.add(row)
                        existing[(first_code, second_code)] = row
                    db.flush()
                break
            except IntegrityError:
                logger.warning(
                    "boundary line conflict dkbm=%s attempt=%s", dkbm, attempt + 1
                )
                existing = _load_lines_by_points(db, tenant_code, all_codes)
                missing = [pair for pair in pairs if pair not in existing]
                if not missing:
                    break
                if attempt == 2:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="界址线写入冲突，请重试",
                    )
        return existing
