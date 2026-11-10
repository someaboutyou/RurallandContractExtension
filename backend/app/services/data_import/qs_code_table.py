"""权属单位代码表（xls）与区域管理的同步。

国标数据包的「权属数据」目录通常带有 ``<县码><年份>权属单位代码表.xls``：
两列（权属单位代码 / 权属单位名称），14 位补零码覆盖县/镇/村/组四级
（如 ``32132410002201`` = 泗洪县青阳镇宏伟居一组）。

该表是权属单位**名称的权威源**。此前镇/村/组区域只能从 fbfmc 正则反推
（组名错拿合作社名、镇名靠猜），导入时用代码表补齐并覆盖校正区域名称；
导出时按所选区域从区域管理表反向生成代码表（多次部分导入在区域表里
累积，导出时合并为所选区域的完整代码表）。

码级判定（14 位补零码按尾零数）：
- 尾 8 个零 → 县（取前 6 位）
- 尾 5 个零 → 镇（取前 9 位）
- 尾 2 个零 → 村（取前 12 位）
- 其余     → 组（14 位全保留）
裸码（6/9/12/14 位不带补零）按长度直接定级。

只依赖 xlrd（读）/ xlwt（写），均已在后端依赖中；不 import 本包其他模块，
避免与导入/导出服务互相牵连。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.region import Region
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

QS_CODE_HEADER = "权属单位代码"
QS_NAME_HEADER = "权属单位名称"

_LEVEL_BY_BARE_LEN = {6: "county", 9: "town", 12: "village", 14: "group"}
_LEVEL_LABELS = {"county": "县域", "town": "镇级区域", "village": "村级区域", "group": "组级区域"}

_RENAME_DETAIL_CAP = 50


# ---------------------------------------------------------------------------
# 码级判定
# ---------------------------------------------------------------------------

def classify_qs_code(raw: str) -> tuple[str, str] | None:
    """权属单位代码 → (level, 区域码)；无法识别返回 None。"""
    code = str(raw or "").strip()
    if not code.isdigit():
        return None
    if len(code) == 14:
        if code.endswith("00000000"):
            return "county", code[:6]
        if code.endswith("00000"):
            return "town", code[:9]
        if code.endswith("00"):
            return "village", code[:12]
        return "group", code
    level = _LEVEL_BY_BARE_LEN.get(len(code))
    return (level, code) if level else None


def pad_region_code(code: str) -> str:
    """区域码 → 14 位补零码（县 6 位补 8 零、镇 9 位补 5 零、村 12 位补 2 零）。"""
    code = str(code or "").strip()
    if len(code) >= 14:
        return code
    return code + "0" * (14 - len(code))


# ---------------------------------------------------------------------------
# 读取（导入侧）
# ---------------------------------------------------------------------------

def _cell_text(value) -> str:
    """xlrd 单元格 → 文本：数字单元格（代码常被 Excel 存成数值）转整数字符串。"""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_qs_code_table(path: str | Path) -> list[dict]:
    """读取权属单位代码表，返回 [{code14, name}]；无法识别的行跳过。

    按 sheet 首行含「权属单位代码」识别；取第一个命中的 sheet。
    """
    import xlrd

    workbook = xlrd.open_workbook(str(path))
    for sheet in workbook.sheets():
        if sheet.nrows < 2 or sheet.ncols < 1:
            continue
        header = _cell_text(sheet.cell_value(0, 0))
        if QS_CODE_HEADER not in header:
            continue
        rows: list[dict] = []
        for r in range(1, sheet.nrows):
            code = _cell_text(sheet.cell_value(r, 0))
            name = _cell_text(sheet.cell_value(r, 1)) if sheet.ncols > 1 else ""
            # 数字单元格可能被 Excel 截成科学计数法文本，去掉小数尾巴
            code = re.sub(r"\.0+$", "", code)
            classified = classify_qs_code(code)
            if classified is None:
                logger.warning("权属单位代码表存在无法识别的代码行，已跳过：row=%s code=%r", r + 1, code)
                continue
            rows.append({"code": classified[1], "name": name.strip()})
        if rows:
            return rows
    return []


def find_qs_code_table(root_dir: str | Path) -> Path | None:
    """在解压目录里定位权属单位代码表（rglob *.xls，按内容识别）。"""
    for candidate in sorted(Path(root_dir).rglob("*.xls")):
        if not candidate.is_file():
            continue
        try:
            if read_qs_code_table(candidate):
                return candidate
        except Exception:  # noqa: BLE001 — 单个 xls 读不动就换下一个
            logger.warning("读取候选权属单位代码表失败：%s", candidate, exc_info=True)
    return None


# ---------------------------------------------------------------------------
# 写入区域表（导入侧）
# ---------------------------------------------------------------------------

def _ensure_tenant(db: Session, county_code: str, county_name: str | None) -> None:
    """县级租户缺则建（regions.tenant_code 有 FK，导入新县时租户必须先存在）。"""
    tenant = db.get(Tenant, county_code)
    if tenant is not None:
        return
    db.add(
        Tenant(
            code=county_code,
            name=(county_name or "").strip() or f"县级行政区 {county_code}",
            region_code=county_code,
            status="active",
            description="按县级行政区导入时自动创建",
        )
    )
    db.flush()


def _get_or_create_region(
    db: Session,
    code: str,
    level: str,
    name: str | None,
    stats: dict,
) -> Region:
    """按码取区域，缺则建（父级链递归补齐；建出的占位名后续导入会被代码表覆盖）。"""
    region = db.scalar(select(Region).where(Region.code == code))
    if region is not None:
        return region

    parent = _ensure_parent_region(db, code, level, stats)
    display_name = (name or "").strip() or f"{code} {_LEVEL_LABELS[level]}"
    if len(code) >= 6:
        # 租户只按县级建（与 ensure_tenants 同口径）；县级行用代码表名命名租户
        tenant_name = display_name if level == "county" else None
        _ensure_tenant(db, code[:6], tenant_name)
    region = Region(
        name=display_name,
        code=code,
        level=level,
        full_name=f"{parent.full_name} / {display_name}" if parent else display_name,
        parent_id=parent.id if parent else None,
        tenant_code=code[:6] if len(code) >= 6 else None,
    )
    db.add(region)
    db.flush()
    stats["created"] += 1
    if len(stats["details"]) < _RENAME_DETAIL_CAP:
        stats["details"].append(f"新建 {code} {display_name}")
    return region


def _ensure_parent_region(db: Session, code: str, level: str, stats: dict) -> Region | None:
    """补齐父级区域。县挂省/市种子链（缺则挂省级占位），镇/村/组递归向上。"""
    if level == "county":
        province_code = f"{code[:2]}0000"
        province = db.scalar(select(Region).where(Region.code == province_code))
        if province is not None:
            return province
        # 与 sync_regions_from_business_codes 同口径：挂导入数据省级占位
        province = db.scalar(select(Region).where(Region.code == "auto-province"))
        if province is None:
            province = Region(
                name="导入数据省级占位",
                code="auto-province",
                level="province",
                full_name="导入数据省级占位",
                parent_id=None,
                tenant_code=None,
            )
            db.add(province)
            db.flush()
        return province
    if level == "town":
        return _get_or_create_region(db, code[:6], "county", None, stats)
    if level == "village":
        return _get_or_create_region(db, code[:9], "town", None, stats)
    if level == "group":
        return _get_or_create_region(db, code[:12], "village", None, stats)
    return None


def sync_regions_from_qs_table(db: Session, rows: list[dict], region_code: str | None) -> dict:
    """把权属单位代码表灌进区域表：缺则补、名称以代码表为准覆盖。

    作用范围限定在批次县域前缀（region_code 前 6 位）内；不 commit，
    由调用方在同一事务里提交。返回统计 {total, applied, created, renamed,
    skipped, details}。
    """
    scope_prefix = (region_code or "")[:6] or None
    stats: dict = {"total": len(rows), "applied": 0, "created": 0, "renamed": 0, "skipped": 0, "details": []}

    # 表内去重（同名码取首个）+ 作用域过滤
    seen: dict[str, tuple[str, str]] = {}
    for row in rows:
        classified = classify_qs_code(row.get("code", ""))
        if classified is None:
            stats["skipped"] += 1
            continue
        level, code = classified
        if scope_prefix and not code.startswith(scope_prefix):
            stats["skipped"] += 1
            continue
        seen.setdefault(code, (level, str(row.get("name") or "").strip()))

    # 按码长升序处理：县 → 镇 → 村 → 组，保证父级先落库
    for code in sorted(seen, key=lambda c: (len(c), c)):
        level, name = seen[code]
        region = db.scalar(select(Region).where(Region.code == code))
        if region is None:
            _get_or_create_region(db, code, level, name, stats)
            stats["applied"] += 1
            continue

        if region.level != level:
            logger.warning(
                "权属单位代码表与区域表层级不一致：code=%s 表内=%s 库内=%s（名称仍以代码表为准）",
                code, level, region.level,
            )
        if name and region.name != name:
            old_name = region.name
            region.name = name
            if region.tenant_code is None and len(code) >= 6:
                _ensure_tenant(db, code[:6], None)
                region.tenant_code = code[:6]
            stats["renamed"] += 1
            if len(stats["details"]) < _RENAME_DETAIL_CAP:
                stats["details"].append(f"{code} {old_name} → {name}")
        stats["applied"] += 1

    # 名称可能变了：重算镇/村/组（县级以下）的 full_name，保持层级链一致
    if scope_prefix:
        subtree = db.scalars(
            select(Region).where(Region.code.startswith(scope_prefix))
        ).all()
        for region in sorted(subtree, key=lambda r: (len(r.code), r.code)):
            if region.level not in ("town", "village", "group"):
                continue
            parent = db.get(Region, region.parent_id) if region.parent_id else None
            region.full_name = f"{parent.full_name} / {region.name}" if parent else region.name

    return stats


# ---------------------------------------------------------------------------
# 导出（区域表 → 代码表）
# ---------------------------------------------------------------------------

def build_qs_rows_from_regions(db: Session, region_code: str | None) -> list[tuple[str, str]]:
    """按所选区域取区域子树（前缀匹配），生成 14 位补零码的 (代码, 名称) 行。

    多次部分导入的区域数据在此合并为所选范围的完整代码表；按补零码排序
    （县 → 镇 → 村 → 组）。
    """
    code = str(region_code or "").strip()
    if not code:
        return []
    regions = db.scalars(
        select(Region).where(Region.code.startswith(code)).order_by(Region.code)
    ).all()
    rows = [(pad_region_code(r.code), r.name) for r in regions]
    rows.sort(key=lambda item: item[0])
    return rows


def write_qs_code_table(path: str | Path, rows: list[tuple[str, str]]) -> int:
    """写出权属单位代码表 xls（两列：权属单位代码 / 权属单位名称）。返回行数。"""
    import xlwt

    workbook = xlwt.Workbook(encoding="utf-8")
    sheet = workbook.add_sheet(QS_CODE_HEADER[:6] or "Sheet1")
    header_style = xlwt.easyxf("font: bold on")
    sheet.write(0, 0, QS_CODE_HEADER, header_style)
    sheet.write(0, 1, QS_NAME_HEADER, header_style)
    sheet.col(0).width = 14 * 256
    sheet.col(1).width = 40 * 256
    for index, (code, name) in enumerate(rows, start=1):
        sheet.write(index, 0, code)
        sheet.write(index, 1, name)
    workbook.save(str(path))
    return len(rows)
