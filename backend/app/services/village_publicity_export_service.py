"""村组公示签字表 Excel 导出（延长三十年调查信息公示签字表）。

口径与 CS 版《数据导入导出》导出的 xls 完全对齐：

- **一个发包方（村组）一个 sheet**，该组全部承包方（成员 × 地块交错块）在
  同一个 sheet 里，末尾合计行；
- 两级表头（46 列，四至分东/南/西/北四个子列）、户块首列纵向合并；
- 版式直写 xlwt（报表类不走 HTML 母版，列清单/样式是代码常量）；
- 码值文本一律经字典（与前端 useDictionary 同源），字典缺失退回原码。

文件名设计（与 CS 版公示表 .doc 的 ``名称(组码)`` 口径一致）：

- 单个发包方：``{发包方名称}({fbfbm})土地承包经营权村组公示签字表.xls``
- 多个发包方（一文件多 sheet）：``{首个名称}等{n}个村组土地承包经营权村组公示签字表.xls``
"""

from __future__ import annotations

import io
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Callable

import xlwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dictionary import DictionaryItem
from app.models.fbf import Fbf
from app.models.survey import (
    SurveyCbdkxxResult,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyDkResult,
)
from app.services.contract_template_service import TDLYLX_FULL_MAP

logger = logging.getLogger(__name__)

#: ㎡ → 亩（与 sheet.py 同口径）
_MU_DIVISOR = Decimal("666.67")

TITLE = "第二轮土地承包到期后再延长三十年调查信息公示签字表"
SUFFIX = "土地承包经营权村组公示签字表"
NCOLS = 46

_FILENAME_UNSAFE = str.maketrans({char: "_" for char in '\\/:*?"<>|[]'})

#: 两级表头：row2 为主表头（四至列跨 27-30 合并），row3 为四至子表头
HEADERS = [
    "承包方编号", "承包方名称", "承包方类型", "家庭成员数(个)",
    "姓名", "性别", "证件类型", "证件号码", "家庭关系", "是否共有人", "备注", "共有人修改意见",
    "承包方地址", "邮政编码", "电话号码", "调查员", "调查日期", "调查记事", "审核人", "审核日期", "审核意见",
    "地块名称", "地块编码", "图幅编号", "二轮合同面积", "实测面积", "实测总面积",
    "四至", None, None, None,  # 27-30：四至（子表头 东/南/西/北）
    "土地用途", "等级", "土地利用类型", "是否基本农田", "指界人", "地块类别", "备注", "地块修改意见",
    "调查员", "调查日期", "调查记事", "审核人", "审核日期", "审核意见", "签字人(按印)",
]
SUB_HEADERS_EWSN = ["东", "南", "西", "北"]

#: 列宽（Excel 字符单位，×256 落盘）
COL_WIDTHS = [
    8, 12, 8, 10, 10, 6, 14, 22, 10, 10, 10, 12,
    24, 8, 14, 10, 14, 30, 10, 14, 14,
    16, 22, 10, 10, 10, 10,
    10, 10, 10, 10,
    10, 8, 12, 10, 10, 10, 10, 12,
    10, 14, 20, 10, 14, 12, 12,
]

#: 码值 → 字典类型（与前端 useDictionary 同源；字典整类为空退回原码）
DICT_TYPES = {
    "cbflx": "nyt2539_c16_contractor_type",
    "zjlx": "nyt2539_c15_id_document_type",
    "xb": "nyt2539_c17_gender",
    "yhzgx": "nyt2539_c20_relation_to_head",
    "yes_no": "nyt2539_c19_yes_no",
    "member_remark": "nyt2539_c18_member_remark",
    "tdyt": "nyt2539_c09_land_use",
    "dldj": "nyt2539_c08_land_grade",
    "dklb": "nyt2539_c07_parcel_category",
}


def _dictionary_maps(db: Session) -> dict[str, dict[str, str]]:
    """一次取齐导出所需的全部字典（{dict_type: {code: label}}）。"""
    types = set(DICT_TYPES.values())
    rows = db.execute(
        select(DictionaryItem.dict_type, DictionaryItem.item_value, DictionaryItem.item_name)
        .where(DictionaryItem.dict_type.in_(types), DictionaryItem.enabled.is_(True))
        .order_by(DictionaryItem.sort_order.asc(), DictionaryItem.item_value.asc())
    ).all()
    maps: dict[str, dict[str, str]] = {}
    for dict_type, value, name in rows:
        if value:
            maps.setdefault(dict_type, {})[value] = name
    return maps


def _text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text in ("None", "\\") else text


def _dict_text(maps: dict[str, dict[str, str]], kind: str, code) -> str:
    code_text = _text(code)
    if not code_text:
        return ""
    return maps.get(DICT_TYPES[kind], {}).get(code_text, code_text)


def _mu(value) -> float | None:
    """㎡ → 亩（两位小数）；空值返回 None。"""
    if value in (None, ""):
        return None
    try:
        return round(float(Decimal(str(value)) / _MU_DIVISOR), 2)
    except Exception:  # noqa: BLE001
        return None


def _date_cn(value) -> str:
    """日期 → ``2015年3月5日``（与 CS 版公示表同格式，无前导零）。"""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return f"{value.year}年{value.month}月{value.day}日"
    return _text(value)


class VillagePublicityExportService:
    """按发包方（村组）生成《调查信息公示签字表》xls。"""

    # ── 数据装配 ────────────────────────────────────────────────────────

    def _load_contractors(self, db: Session, fbfbm: str) -> list[SurveyCbfResult]:
        """本组有效承包方（排除注销户），按编码序稳定排列。

        同一 cbfbm 若存在多条结果行（历史/重录），按 id 取最新一条——排序为
        ``cbfbm 升序 + id 降序``，首次出现即为该户最新行。
        """
        rows = db.execute(
            select(SurveyCbfResult)
            .where(
                SurveyCbfResult.cbfbm.like(f"{fbfbm}%"),
                SurveyCbfResult.result_status != "cancelled",
            )
            .order_by(SurveyCbfResult.cbfbm.asc(), SurveyCbfResult.id.desc())
        ).scalars()
        seen: set[str] = set()
        result: list[SurveyCbfResult] = []
        for row in rows:
            if row.cbfbm in seen:
                continue
            seen.add(row.cbfbm)
            result.append(row)
        return result

    def _load_members(self, db: Session, contractor_uids: list[str]) -> dict[str, list]:
        if not contractor_uids:
            return {}
        rows = db.execute(
            select(SurveyCbfJtcyResult)
            .where(SurveyCbfJtcyResult.contractor_uid.in_(contractor_uids))
            .order_by(SurveyCbfJtcyResult.contractor_uid.asc(), SurveyCbfJtcyResult.id.asc())
        ).scalars()
        grouped: dict[str, list] = {}
        for row in rows:
            grouped.setdefault(row.contractor_uid, []).append(row)
        return grouped

    def _load_parcels(self, db: Session, fbfbm: str) -> dict[str, list[dict]]:
        """本组有效承包地块（cbdkxx × dk），按承包方编码分组。"""
        links = list(
            db.execute(
                select(SurveyCbdkxxResult)
                .where(
                    SurveyCbdkxxResult.fbfbm == fbfbm,
                    SurveyCbdkxxResult.result_status != "cancelled",
                )
                .order_by(SurveyCbdkxxResult.cbfbm.asc(), SurveyCbdkxxResult.dkbm.asc())
            ).scalars()
        )
        if not links:
            return {}
        dk_map: dict[str, SurveyDkResult] = {}
        dkbms = [link.dkbm for link in links]
        for dk in db.execute(
            select(SurveyDkResult)
            .where(SurveyDkResult.dkbm.in_(dkbms))
            .order_by(SurveyDkResult.id.asc())
        ).scalars():
            dk_map[dk.dkbm] = dk  # 同码取最大 id（最新）
        grouped: dict[str, list[dict]] = {}
        for link in links:
            grouped.setdefault(link.cbfbm, []).append({"link": link, "dk": dk_map.get(link.dkbm)})
        return grouped

    # ── 样式 ────────────────────────────────────────────────────────────

    @staticmethod
    def _make_style(style_cache: dict, bold: bool = False, wrap: bool = False,
                    align_left: bool = False) -> xlwt.XFStyle:
        key = (bold, wrap, align_left)
        if key in style_cache:
            return style_cache[key]
        font = xlwt.Font()
        font.name = "宋体"
        font.height = 200
        font.bold = bold
        borders = xlwt.Borders()
        borders.left = borders.right = borders.top = borders.bottom = 1
        alignment = xlwt.Alignment()
        alignment.horz = xlwt.Alignment.HORZ_LEFT if align_left else xlwt.Alignment.HORZ_CENTER
        alignment.vert = xlwt.Alignment.VERT_CENTER
        alignment.wrap = 1 if wrap else 0
        st = xlwt.XFStyle()
        st.font = font
        st.borders = borders
        st.alignment = alignment
        style_cache[key] = st
        return st

    # ── sheet 构建 ──────────────────────────────────────────────────────

    def _build_sheet(self, db: Session, wb: xlwt.Workbook, sheet_name: str,
                     fbf: Fbf, maps: dict[str, dict[str, str]],
                     period: tuple[str, str]) -> None:
        fbfbm = fbf.fbfbm
        contractors = self._load_contractors(db, fbfbm)
        members_map = self._load_members(db, [c.contractor_uid for c in contractors])
        parcels_map = self._load_parcels(db, fbfbm)

        ws = wb.add_sheet(sheet_name)
        cache: dict[tuple, xlwt.XFStyle] = {}

        def st(bold: bool = False, wrap: bool = False, left: bool = False) -> xlwt.XFStyle:
            return self._make_style(cache, bold=bold, wrap=wrap, align_left=left)

        def cell(r: int, c: int, value, **kw) -> None:
            ws.write(r, c, "" if value is None else value, st(**kw))

        for c, width in enumerate(COL_WIDTHS):
            ws.col(c).width = 256 * width

        # 行 0：标题
        ws.row(0).height_mismatch = True
        ws.row(0).height = 20 * 32
        ws.write_merge(0, 0, 0, NCOLS - 1, TITLE, st(bold=True))
        # 行 1：单位 / 公示期（导出日 ~ 次年同日，与 CS 版口径一致）
        issuer_name = _text(fbf.fbfmc) or fbfbm
        ws.write_merge(1, 1, 0, 3, f"单位:  {issuer_name}", st(left=True))
        ws.write_merge(1, 1, 4, NCOLS - 1, f"日期：{period[0]}-{period[1]}", st())
        # 行 2/3：两级表头。除四至 4 列（27-30 主表头横跨、子表头分列）外，
        # 其余表头单元格纵向合并 2-3 两行。
        ws.row(2).height_mismatch = True
        ws.row(2).height = 20 * 24
        for c, label in enumerate(HEADERS):
            if c == 27:
                ws.write_merge(2, 2, 27, 30, "四至", st(bold=True, wrap=True))
            elif label is not None:
                ws.write_merge(2, 3, c, c, label, st(bold=True, wrap=True))
        for i, label in enumerate(SUB_HEADERS_EWSN):
            ws.write(3, 27 + i, label, st(bold=True))

        # 数据块
        r = 4
        total_members = 0
        total_parcels = 0
        sum_htmj = Decimal("0")
        sum_scmj = Decimal("0")

        for idx, cbf in enumerate(contractors, start=1):
            members = members_map.get(cbf.contractor_uid, [])
            my_parcels = parcels_map.get(cbf.cbfbm, [])
            rows_n = max(len(members), len(my_parcels), 1)
            r_end = r + rows_n - 1

            household_htmj = sum(
                (Decimal(str(item["link"].htmj)) for item in my_parcels), Decimal("0")
            )
            household_scmj = sum(
                (Decimal(str(item["dk"].scmj)) for item in my_parcels if item["dk"] is not None),
                Decimal("0"),
            )
            total_members += int(cbf.cbfcysl or 0)
            total_parcels += len(my_parcels)
            sum_htmj += household_htmj
            sum_scmj += household_scmj

            # 户级纵向合并列：编号 / 名称 / 类型 / 成员数 + 地址~审核意见 + 实测总面积
            ws.write_merge(r, r_end, 0, 0, idx, st())
            ws.write_merge(r, r_end, 1, 1, _text(cbf.cbfmc), st())
            ws.write_merge(r, r_end, 2, 2, _dict_text(maps, "cbflx", cbf.cbflx), st())
            ws.write_merge(r, r_end, 3, 3, int(cbf.cbfcysl or 0), st())
            household_cells = [
                (12, _text(cbf.cbfdz), dict(wrap=True, left=True)),
                (13, _text(cbf.yzbm), {}),
                (14, _text(cbf.lxdh), {}),
                (15, _text(cbf.cbfdcy), {}),
                (16, _date_cn(cbf.cbfdcrq), {}),
                (17, _text(cbf.cbfdcjs), dict(wrap=True, left=True)),
                (18, _text(cbf.gsshr), {}),
                (19, _date_cn(cbf.gsshrq), {}),
                (20, _text(cbf.gsjs), dict(wrap=True, left=True)),
            ]
            for c, value, kw in household_cells:
                if r == r_end:
                    cell(r, c, value, **kw)
                else:
                    ws.write_merge(r, r_end, c, c, value, st(**kw))
            total_mu = round(float(household_scmj / _MU_DIVISOR), 2) if household_scmj else None
            if r == r_end:
                cell(r, 26, total_mu)
            else:
                ws.write_merge(r, r_end, 26, 26, total_mu, st())

            for i in range(rows_n):
                row = r + i
                # 成员列 4-11
                if i < len(members):
                    m = members[i]
                    member_cells = [
                        (4, _text(m.cyxm), {}),
                        (5, _dict_text(maps, "xb", m.cyxb), {}),
                        (6, _dict_text(maps, "zjlx", m.cyzjlx), {}),
                        (7, _text(m.cyzjhm), {}),
                        (8, _dict_text(maps, "yhzgx", m.yhzgx), {}),
                        (9, _dict_text(maps, "yes_no", m.sfgyr), {}),
                        (10, _dict_text(maps, "member_remark", m.cybz), {}),
                        (11, "", {}),
                    ]
                else:
                    member_cells = [(c, "", {}) for c in range(4, 12)]
                for c, value, kw in member_cells:
                    cell(row, c, value, **kw)
                # 地块列 21-25 / 27-45（26 已户级合并）
                if i < len(my_parcels):
                    item = my_parcels[i]
                    link, dk = item["link"], item["dk"]
                    parcel_cells = [
                        (21, _text(dk.dkmc) if dk else "", dict(wrap=True, left=True)),
                        (22, _text(link.dkbm), {}),
                        (23, _text(getattr(dk, "image_number", None)) if dk else "", {}),
                        (24, _mu(link.htmj), {}),
                        (25, _mu(dk.scmj) if dk else None, {}),
                    ]
                    directions = [
                        (27, _text(dk.dkdz) if dk else ""),
                        (28, _text(dk.dkxz) if dk else ""),
                        (29, _text(dk.dknz) if dk else ""),
                        (30, _text(dk.dkbz) if dk else ""),
                    ]
                    parcel_cells.extend((c, v, {}) for c, v in directions)
                    parcel_cells.extend([
                        (31, _dict_text(maps, "tdyt", dk.tdyt) if dk else "", {}),
                        (32, _dict_text(maps, "dldj", dk.dldj) if dk else "", {}),
                        (33, (TDLYLX_FULL_MAP.get(dk.tdlylx, dk.tdlylx) if dk else "") or "", {}),
                        (34, (_text(dk.sfjbnt) == "1" and "是" or (_text(dk.sfjbnt) == "0" and "否" or "")) if dk else "", {}),
                        (35, _text(dk.zjrxm) if dk else "", {}),
                        (36, _dict_text(maps, "dklb", dk.dklb) if dk else "", {}),
                        (37, _text(dk.dkbzxx) if dk else "", {}),
                        (38, "", {}),  # 地块修改意见：公示时留白
                        (39, _text(dk.survey_person) if dk else "", {}),
                        (40, dk.survey_date.isoformat() if dk and dk.survey_date else "", {}),
                        (41, _text(dk.survey_note) if dk else "", {}),
                        (42, _text(dk.check_person) if dk else "", {}),
                        (43, dk.check_date.isoformat() if dk and dk.check_date else "", {}),
                        (44, _text(dk.check_opinion) if dk else "", {}),
                        (45, "", {}),  # 签字人(按印)：公示后手签
                    ])
                else:
                    parcel_cells = [(c, "", {}) for c in range(21, 26)] + [(c, "", {}) for c in range(27, 46)]
                for c, value, kw in parcel_cells:
                    cell(row, c, value, **kw)
            r = r_end + 1

        # 合计行（成员总数 / 地块数 / 面积合计；其余列按 CS 口径填 "\"）
        scmj_total_mu = round(float(sum_scmj / _MU_DIVISOR), 2)
        totals = {
            3: total_members,
            22: total_parcels,
            24: round(float(sum_htmj / _MU_DIVISOR), 2),
            25: scmj_total_mu,
            26: scmj_total_mu,
        }
        cell(r, 0, "合计")
        cell(r, 1, "")
        for c in range(2, NCOLS):
            cell(r, c, totals.get(c, "\\"))

    # ── 对外入口 ────────────────────────────────────────────────────────

    def export(
        self,
        db: Session,
        fbfbm_list: list[str],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> tuple[bytes, str]:
        """生成 xls（一个发包方一个 sheet）→ (字节, 文件名)。

        ``progress_callback(done, total)``：每完成一个发包方的 sheet 回报一次
        （后台批量导出任务用它汇报进度；同步调用传 None 即可）。
        """
        codes: list[str] = []
        seen: set[str] = set()
        for code in fbfbm_list:
            code = str(code or "").strip()
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
        if not codes:
            raise ValueError("未指定发包方")

        issuers = [db.get(Fbf, code) for code in codes]
        missing = [code for code, fbf in zip(codes, issuers) if fbf is None]
        if missing:
            raise ValueError(f"发包方不存在：{'、'.join(missing)}")

        maps = _dictionary_maps(db)
        today = date.today()
        try:
            period_end = today.replace(year=today.year + 1)
        except ValueError:  # 2月29日
            period_end = today + timedelta(days=365)
        period = (_date_cn(today), _date_cn(period_end))

        wb = xlwt.Workbook(encoding="utf-8")
        used_names: set[str] = set()
        for index, fbf in enumerate(issuers, start=1):
            sheet_name = self._unique_sheet_name(_text(fbf.fbfmc) or fbf.fbfbm, used_names)
            self._build_sheet(db, wb, sheet_name, fbf, maps, period)
            if progress_callback is not None:
                progress_callback(index, len(issuers))

        if len(issuers) == 1:
            stem = f"{_text(issuers[0].fbfmc)}({issuers[0].fbfbm})"
        else:
            stem = f"{_text(issuers[0].fbfmc)}等{len(issuers)}个村组"
        filename = f"{stem}{SUFFIX}.xls".translate(_FILENAME_UNSAFE)
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue(), filename

    @staticmethod
    def _unique_sheet_name(raw: str, used: set[str]) -> str:
        name = raw.translate(str.maketrans({c: "_" for c in '\\/:*?[]'}))[:31] or "公示签字表"
        candidate, index = name, 2
        while candidate in used:
            suffix = f"({index})"
            candidate = name[: 31 - len(suffix)] + suffix
            index += 1
        used.add(candidate)
        return candidate


village_publicity_export_service = VillagePublicityExportService()
