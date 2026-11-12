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
from datetime import datetime
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

# 父级码：镇挂县（前 6 位）、村挂镇（前 9 位）、组挂村（前 12 位）；县无表内父级
_PARENT_CODE_OF = {"county": None, "town": lambda c: c[:6], "village": lambda c: c[:9], "group": lambda c: c[:12]}


# ---------------------------------------------------------------------------
# 相对名计算（下一级名称剥掉上一级名称前缀）
# ---------------------------------------------------------------------------

def _strip_county_admin_prefix(name: str) -> str:
    """县级行的相对名：剥掉前导省级（省/自治区）与市级（市/自治州/地区/盟）段。

    代码表里县名是「内蒙古省通辽市扎鲁特旗」这类全拼；表内没有省/市行可
    依前缀剥，只能按行政通名正则逐段剥。每段剥完剩余非空才生效（防止
    「恩施市」被整段剥空）。
    """
    result = name
    for pattern in (r"^.+?(?:省|自治区)", r"^.+?(?:自治州|地区|盟|市)"):
        match = re.match(pattern, result)
        if match and len(match.group(0)) < len(result):
            result = result[len(match.group(0)):]
    return result


# 兜底正则：表内/库内都拿不到父级全名时按行政通名剥前缀。
# 组名优先剥「村民委员会」整段，避免「…村民委员会第一村民小组」被第一个"村"截断。
_REGEX_STRIP_BY_LEVEL = {
    "town": r"^.*?(?:县|市|区|旗|盟|地区|自治州)",
    "village": r"^.*?(?:镇|乡|苏木|街道|开发区)",
    "group": r"^.*?(?:村民委员会|村委会|村委员会|村|居|社区|嘎查|生产队)",
}


def _regex_relative_name(level: str, full: str) -> str:
    pattern = _REGEX_STRIP_BY_LEVEL.get(level)
    if not pattern:
        return full
    stripped = re.sub(pattern, "", full, count=1)
    return stripped if stripped else full


def _parent_full_name(db: Session | None, code: str, level: str, entries: dict) -> str | None:
    """父级全名：优先取代码表内父行，取不到再查库（库内名可能是旧全名或相对名）。"""
    get_parent_code = _PARENT_CODE_OF.get(level)
    if get_parent_code is None:
        return None
    parent_code = get_parent_code(code)
    if parent_code in entries:
        return entries[parent_code]["full"]
    if db is not None:
        region = db.scalar(select(Region).where(Region.code == parent_code))
        if region is not None and (region.name or "").strip():
            return region.name.strip()
    return None


def compute_relative_names(
    rows: list[dict],
    db: Session | None = None,
    scope_prefix: str | None = None,
) -> dict[str, dict]:
    """代码表行 → {码: {level, full, relative}}；relative 供区域表 name 用。

    - full：代码表原始全名（导出侧要按它还原，存入 regions.qs_full_name）。
    - relative：下一级名称剥掉上一级全名前缀（镇「巨日合镇」、村「双山子村
      村民委员会」）；剥不动（父行缺失且正则不命中）时退回全名。
    - 同码多行取首现名称（与 sync_regions_from_qs_table 的去重口径一致）。
    """
    entries: dict[str, dict] = {}
    for row in rows:
        classified = classify_qs_code(str(row.get("code") or ""))
        if classified is None:
            continue
        level, code = classified
        if scope_prefix and not code.startswith(scope_prefix):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        entries.setdefault(code, {"level": level, "full": name})

    for code in sorted(entries, key=lambda c: (len(c), c)):
        info = entries[code]
        level, full = info["level"], info["full"]
        parent_full = _parent_full_name(db, code, level, entries)
        if parent_full and full.startswith(parent_full) and len(full) > len(parent_full):
            relative = full[len(parent_full):]
        elif level == "county":
            relative = _strip_county_admin_prefix(full)
        else:
            relative = _regex_relative_name(level, full)
        info["relative"] = relative or full
    return entries


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
    qs_full_name: str | None = None,
) -> Region:
    """按码取区域，缺则建（父级链递归补齐；建出的占位名后续导入会被代码表覆盖）。

    ``name`` 存相对名（如「巨日合镇」「双山子村村民委员会」）；
    ``qs_full_name`` 存代码表原始全名（导出权属单位代码表时还原用）。
    """
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
        qs_full_name=(qs_full_name or "").strip() or None,
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

    名称口径（2026-11-11）：regions.name 存**相对名**——下一级名称剥掉上一级
    全名前缀（镇「巨日合镇」、村「双山子村村民委员会」），避免区域树里层层
    重复「内蒙古省通辽市扎鲁特旗…」；代码表原始全名存 regions.qs_full_name，
    导出权属单位代码表时按它还原（保证导出/导入回环一致）。

    作用范围限定在批次县域前缀（region_code 前 6 位）内；不 commit，
    由调用方在同一事务里提交。返回统计 {total, applied, created, renamed,
    skipped, details}。
    """
    scope_prefix = (region_code or "")[:6] or None
    stats: dict = {"total": len(rows), "applied": 0, "created": 0, "renamed": 0, "skipped": 0, "details": []}

    # 相对名计算（表内父行优先、库内父级兜底）+ 同码取首现
    computed = compute_relative_names(rows, db=db, scope_prefix=scope_prefix)
    seen: dict[str, tuple[str, str, str]] = {}
    for code in sorted(computed, key=lambda c: (len(c), c)):
        info = computed[code]
        seen.setdefault(code, (info["level"], info["full"], info["relative"]))
    stats["skipped"] = stats["total"] - len(seen)

    # 按码长升序处理：县 → 镇 → 村 → 组，保证父级先落库
    for code in sorted(seen, key=lambda c: (len(c), c)):
        level, full_name, relative = seen[code]
        region = db.scalar(select(Region).where(Region.code == code))
        if region is None:
            _get_or_create_region(db, code, level, relative, stats, qs_full_name=full_name)
            stats["applied"] += 1
            continue

        if region.level != level:
            logger.warning(
                "权属单位代码表与区域表层级不一致：code=%s 表内=%s 库内=%s（名称仍以代码表为准）",
                code, level, region.level,
            )
        changed = False
        if relative and region.name != relative:
            old_name = region.name
            region.name = relative
            stats["renamed"] += 1
            if len(stats["details"]) < _RENAME_DETAIL_CAP:
                stats["details"].append(f"{code} {old_name} → {relative}")
            changed = True
        if full_name and getattr(region, "qs_full_name", None) != full_name:
            region.qs_full_name = full_name
            changed = True
        if changed and region.tenant_code is None and len(code) >= 6:
            _ensure_tenant(db, code[:6], None)
            region.tenant_code = code[:6]
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

def _qs_display_name(region: Region) -> str:
    """导出用名称：优先代码表原始全名（qs_full_name），回退区域名。"""
    return str(getattr(region, "qs_full_name", None) or region.name or "").strip()


def build_qs_rows_from_regions(db: Session, region_code: str | None) -> list[tuple[str, str]]:
    """按所选区域取区域子树（前缀匹配），生成 14 位补零码的 (代码, 名称) 行。

    多次部分导入的区域数据在此合并为所选范围的完整代码表；按补零码排序
    （县 → 镇 → 村 → 组）。

    口径（2026-11-11）：
    - 名称导出**全名**（qs_full_name 优先），与导入包回环一致；
    - 排除「村级发包方被误建为组」的伪组行（14 位码以 00 结尾，classify 会判为
      村级）——这类行与村节点补零后撞码，曾导致每个村民委员会导出两行且名称不同；
    - 按补零码去重兜底（同码只留第一行，排序保证村级行在前）；
    - 所选范围在县级以下时补上县级行，保持与原包结构一致（表首为县级行）。
    """
    code = str(region_code or "").strip()
    if not code:
        return []
    regions = db.scalars(
        select(Region).where(Region.code.startswith(code)).order_by(Region.code)
    ).all()

    rows: list[tuple[str, str]] = []
    seen_padded: set[str] = set()

    def _append(region: Region) -> None:
        padded = pad_region_code(region.code)
        if padded in seen_padded:
            return
        if region.level == "group" and (classify_qs_code(region.code) or "group") != "group":
            return  # 伪组：14 位码以 00 结尾，实为村级行，避免撞码重复
        seen_padded.add(padded)
        rows.append((padded, _qs_display_name(region)))

    if len(code) > 6:
        county = db.scalar(select(Region).where(Region.code == code[:6], Region.level == "county"))
        if county is not None:
            _append(county)
    for region in regions:
        _append(region)
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


def region_export_code(region_code: str | None) -> str:
    """导出文件命名用的行政区代码（2026-11-12 起不含权属年份）。

    直接取导出范围自身的代码：县级=6 位县码、镇级=9 位镇码、
    村/委员会=12 位村码；14 位组码截断到 12 位村码。文件名形如
    DK150526103201.shp / 150526103201.mdb / 150526103201权属单位代码表.xls。
    """
    code = str(region_code or "").strip()
    if not code:
        return "export"
    return code[:12] if len(code) > 12 else code


def qs_code_table_filename(region_code: str | None) -> str:
    """权属单位代码表导出文件名：<行政区代码>权属单位代码表.xls。"""
    return f"{region_export_code(region_code)}权属单位代码表.xls"


def region_display_path(db: Session, region_code: str | None) -> str:
    """行政区名称路径（县级起、下划线连接的相对名）。

    村级导出 = 县_镇_村（扎鲁特旗_巨日合镇_双山子村村民委员会）、
    镇级 = 县_镇、县级 = 县，与导出包顶层目录对齐源包习惯。名称取
    regions.name（相对名，2026-11-11 起口径）；某级缺行则跳过。
    """
    code = str(region_code or "").strip()
    parts: list[str] = []
    for n in (6, 9, 12):
        if len(code) < n:
            break
        name = db.scalar(select(Region.name).where(Region.code == code[:n]))
        if name and name.strip():
            parts.append(name.strip())
    if not parts:
        parts = [code or "export"]
    return "_".join(parts).replace("/", "_").replace("\\", "_") or "export"
