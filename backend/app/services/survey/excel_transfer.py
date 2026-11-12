# -*- coding: utf-8 -*-
"""承包方调查表 Excel 导入 / 导出（.xls 模板）。

模板列布局（与样例 ``青阳镇宏伟居一组农村土地承包经营权承包方调查表.xls`` 一致，0 基）：

====  ================  ======  =================================================
列号  标题              字段    说明
====  ================  ======  =================================================
0     承包方编号        cbfbm   18 位编码，必须以调查批次区域码开头（导入匹配键）
1     承包方姓名        cbfmc
2     承包方类型        cbflx   1 农户 / 2 其他（导入导出互转中文）
3     家庭成员数（个）  cbfcysl 导出取库值；导入按成员行实数回算（不符仅告警）
4-10  成员：姓名/性别/证件类型/证件号码/家庭关系/是否共有人/备注
11    共有人信息修改意见  ——    模板占位，不读写
12    承包方地址        cbfdz
13    邮政编码          yzbm
14    联系电话          lxdh
15    调查员            cbfdcy  surveyorName
16    调查日期          cbfdcrq surveyDate
17    调查记事          cbfdcjs surveyNote
18    审核人            gsshr   publicNoticeReviewer
19    审核日期          gsshrq  publicNoticeReviewDate
20    审核意见          gsjs    publicNoticeNote
====  ================  ======  =================================================

一个承包方占多行：第一行带承包方信息 + 首名成员，其后每名成员一行。
导入规则（用户 2026-11-03 拍板）：

1. 按页面 /surveys 的调查批次导入：每户「承包方编号」必须以批次区域码开头；
2. 一户一户验证、导入：户按编号匹配——批次内存在则更新，不存在（且前缀合法）则新增；
3. 成员按**证件号码**匹配：存在则对比修改，不存在则新增；库内成员不在 Excel 里
   原样保留（不删，预览时告警）；
4. 变化记录与页面保存同源：复用 ``update_result``，生成 ``SurveyChangeRecord`` /
   ``SurveyChangeDiff``，更新任务计数；已确认（confirmed）或已终结的户自动跳过。
5. 删除标记（底色填充或删除线，2026-11-03 拍板）：成员行「姓名」列标记 ⇒ 删该成员；
   户行「承包方姓名」列标记 ⇒ 整户注销（复用页面同源 ``deregister_contractor``，
   底档保留可撤回，变化原因「承包方调查表（Excel）标记注销」）。

⛔ 导出时承包方编号按**文本**写入：18 位数字若被 Excel 存成数值会丢精度
（float64 只有 15~16 位有效数字），导入就再也匹配不回去。同样地，
导入读到数值型编号只能尽力取整——模板必须用系统导出的文件改。
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date, datetime, timezone

import xlrd
import xlwt
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyCbfBase,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyFbfBase,
    SurveyFbfResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service
from app.services.relation_codes import (
    HEAD_RELATION_PRIORITY,
    relation_labels,
)

logger = logging.getLogger(__name__)

# ── 模板常量 ────────────────────────────────────────────────────────────────
TITLE_TEXT = "第二轮土地承包到期后再延长三十年承包"
CONTRACTOR_TYPE_LABELS = {"1": "农户", "2": "其他"}
CONTRACTOR_TYPE_CODES = {v: k for k, v in CONTRACTOR_TYPE_LABELS.items()}
ID_TYPE_LABELS = {"1": "居民身份证"}
ID_TYPE_CODES = {v: k for k, v in ID_TYPE_LABELS.items()}
GENDER_LABELS = {"1": "男", "2": "女"}
GENDER_CODES = {v: k for k, v in GENDER_LABELS.items()}
YES = "是"
NO = "否"

# 导入写变化原因的默认值：与合户/分户同口径——写「发生了什么」的事实陈述。
IMPORT_CHANGE_REASON = "承包方调查表（Excel）导入更新"
IMPORT_MEMBER_CHANGE_REASON = "家庭成员信息随承包方调查表（Excel）导入更新"

_DEFAULT_ID_TYPE = "1"
_DEFAULT_RELATION = "80"  # 字典 80 = 其他（关系无从考证时的语义诚实兜底）


def _text(value) -> str:
    """xls 单元格 → 去空白文本；整数浮点去掉尾 .0（编号/邮编/电话常见）。"""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, float):
        return repr(value)
    return str(value).strip()


def _cell(sh, r: int, c: int) -> str:
    """xls 单元格 → 去空白文本；行内短行（ragged row）与越界都安全返回空串。

    ⛔ 不能直接 sh.cell_value(r, c)：用户手改的文件可能某行只写到中间某列，
    xlrd 按行存 list，越界直接 IndexError（2026-11-03 删除标记 e2e 踩过）。
    """
    if r >= sh.nrows or c >= sh.ncols:
        return ""
    try:
        return _text(sh.cell_value(r, c))
    except IndexError:
        return ""


def _raw_cell(sh, r: int, c: int):
    """取原始单元格值（不做文本化，供日期序列值解析）；越界/短行安全返回 None。"""
    if r >= sh.nrows or c >= sh.ncols:
        return None
    try:
        return sh.cell_value(r, c)
    except IndexError:
        return None


_DATE_PATTERNS = (
    re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日?$"),
    re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$"),
)


def _parse_date_cell(value, datemode: int) -> str:
    """xls 日期单元格 → ``YYYY-MM-DD``；无法解析返回空串。"""
    if value in (None, ""):
        return ""
    if isinstance(value, float):
        try:
            dt = xlrd.xldate_as_datetime(value, datemode)
            if dt.year >= 1900:
                return dt.date().isoformat()
        except Exception:  # noqa: BLE001
            return ""
        return ""
    text = _text(value)
    for pattern in _DATE_PATTERNS:
        m = pattern.match(text)
        if m:
            y, mo, d = (int(g) for g in m.groups())
            try:
                return date(y, mo, d).isoformat()
            except ValueError:
                return ""
    return ""


def _gender_from_id_no(id_no: str) -> str:
    """18 位身份证号倒数第二位判性别：奇数男 / 偶数女；判不出返回空串。"""
    if len(id_no) == 18 and id_no[:17].isdigit():
        return "1" if int(id_no[16]) % 2 else "2"
    return ""


# 删除标记（2026-11-03 拍板）：成员行「姓名」单元格
# ① 填充底色（非白/非默认）或 ② 字体加删除线 ⇒ 该成员在库内删除。
# 实测（xlwt 写 → xlrd formatting_info 读）：solid 填充 fill_pattern=1 且
# pattern_colour_index=色值（9=白、64/65=默认背景）；删除线在 font.struck_out。
_MARK_FILL_DEFAULT_INDICES = {0, 9, 64, 65}


def _member_delete_marked(sh, r: int, c: int) -> bool:
    """成员「姓名」单元格是否带删除标记（底色填充或删除线）。"""
    try:
        xf = sh.book.xf_list[sh.cell_xf_index(r, c)]
    except Exception:  # noqa: BLE001
        return False
    try:
        if sh.book.font_list[xf.font_index].struck_out:
            return True
    except Exception:  # noqa: BLE001
        pass
    bg = getattr(xf, "background", None)
    if bg is None:
        return False
    if getattr(bg, "fill_pattern", 0):
        for index in (getattr(bg, "pattern_colour_index", 64), getattr(bg, "background_colour_index", 65)):
            if index not in _MARK_FILL_DEFAULT_INDICES:
                return True
    return False


class SurveyServiceExcelTransferMixin:
    # ── 导出 ────────────────────────────────────────────────────────────────

    def export_contractors_xls(
        self,
        db: Session,
        batch_id: int,
        current_user: User,
        progress_cb=None,
        contractor_uids: list[str] | None = None,
    ) -> tuple[str, bytes]:
        """progress_cb(done, total, phase, current="")：后台任务上报进度用，可空。"""
        batch = self._ensure_batch(db, batch_id)
        data_access_service.ensure_region_filter_in_scope(
            current_user, batch.region_code, detail="当前批次区域不在可导出范围内"
        )

        def report(done: int, total: int, phase: str, current: str = "") -> None:
            if progress_cb is not None:
                try:
                    progress_cb(done, total, phase, current)
                except Exception:  # noqa: BLE001
                    pass

        task_filters = self._tenant_filters(SurveyCbfBase, current_user)
        task_filters.append(SurveyCbfBase.batch_id == batch_id)
        if contractor_uids:
            task_filters.append(SurveyCbfBase.contractor_uid.in_(contractor_uids))
        tasks = db.scalars(
            select(SurveyCbfBase)
            .where(*task_filters)
            .order_by(SurveyCbfBase.cbfbm.asc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        report(0, len(tasks), "读取承包方任务")
        uids = [task.contractor_uid for task in tasks]
        contractors: dict[str, SurveyCbfResult] = {}
        members_by_uid: dict[str, list[SurveyCbfJtcyResult]] = {}
        if uids:
            rows = db.scalars(
                select(SurveyCbfResult)
                .where(
                    SurveyCbfResult.contractor_uid.in_(uids),
                    *self._tenant_filters(SurveyCbfResult, current_user),
                )
                .order_by(SurveyCbfResult.id.asc())
                .execution_options(skip_tenant_scope=True)
            ).all()
            for item in rows:  # 同 uid 多行时取最新
                contractors[item.contractor_uid] = item
            report(0, len(tasks), "读取家庭成员")
            member_rows = db.scalars(
                select(SurveyCbfJtcyResult)
                .where(
                    SurveyCbfJtcyResult.contractor_uid.in_(uids),
                    *self._tenant_filters(SurveyCbfJtcyResult, current_user),
                )
                .execution_options(skip_tenant_scope=True)
            ).all()
            for member in member_rows:
                members_by_uid.setdefault(member.contractor_uid, []).append(member)

        labels = relation_labels(db)
        households = []
        for idx, task in enumerate(tasks):
            households.append(
                self._household_export_row(
                    task, contractors.get(task.contractor_uid), members_by_uid.get(task.contractor_uid) or [], labels
                )
            )
            report(idx + 1, len(tasks), "组装调查表数据", task.cbfmc or task.cbfbm)
        report(len(tasks), len(tasks), "生成 Excel 文件")
        wb = self._build_template_workbook(
            batch.region_name or batch.batch_name or "",
            households,
            issuer_name=self._single_issuer_name(db, batch, tasks),
        )
        safe_name = (batch.region_name or batch.batch_no or f"batch_{batch_id}").replace("/", "_").replace("\\", "_")
        filename = f"承包方调查表_{safe_name}.xls"
        buffer = io.BytesIO()
        wb.save(buffer)
        logger.info(
            "承包方调查表导出 batch_id=%s 户数=%s 操作人=%s", batch_id, len(households), getattr(current_user, "username", None)
        )
        return filename, buffer.getvalue()

    def _household_export_row(
        self, task: SurveyCbfBase, result: SurveyCbfResult | None, members: list, labels: dict
    ) -> dict:
        members = sorted(
            members,
            key=lambda m: (not bool(m.is_household_head), m.cyxm or "", m.cyzjhm or ""),
        )
        return {
            "cbfbm": (result.cbfbm if result else task.cbfbm) or "",
            "cbfmc": (result.cbfmc if result else task.cbfmc) or "",
            "groupRegionName": (getattr(result, "group_region_name", None) if result else None) or "",
            "cbflx": CONTRACTOR_TYPE_LABELS.get(result.cbflx if result else task.cbflx, ""),
            "members": [
                {
                    "name": m.cyxm or "",
                    "gender": GENDER_LABELS.get(m.cyxb, ""),
                    "id_type": ID_TYPE_LABELS.get(m.cyzjlx, ""),
                    "id_no": m.cyzjhm or "",
                    "relation": labels.get((m.yhzgx or "").strip(), m.yhzgx or ""),
                    "is_co_owner": YES if (m.sfgyr or "") == "1" else (NO if (m.sfgyr or "") == "0" else ""),
                    "note": m.cybzsm or "",
                }
                for m in members
            ],
            "address": (result.cbfdz if result else task.cbfdz) or "",
            "postcode": (result.yzbm if result else task.yzbm) or "",
            "mobile": (result.lxdh if result else task.lxdh) or "",
            "surveyor": (result.cbfdcy if result else "") or "",
            "survey_date": (result.cbfdcrq.date().isoformat() if result and result.cbfdcrq else "") or "",
            "survey_note": (result.cbfdcjs if result else "") or "",
            "reviewer": (result.gsshr if result else "") or "",
            "review_date": (result.gsshrq.date().isoformat() if result and result.gsshrq else "") or "",
            "review_note": (result.gsjs if result else "") or "",
        }

    def _single_issuer_name(self, db: Session, batch, tasks: list[SurveyCbfBase]) -> str | None:
        """本工作簿仅包含一个发包方时返回其名称，供表头/A2 使用；多发包方返回 None。"""
        issuer_codes = sorted({
            str(task.cbfbm)[:14]
            for task in tasks
            if task.cbfbm and len(str(task.cbfbm)) >= 14
        })
        if len(issuer_codes) != 1:
            return None
        code = issuer_codes[0]
        row = db.scalars(
            select(SurveyFbfBase)
            .where(
                SurveyFbfBase.batch_id == batch.id,
                SurveyFbfBase.fbfbm == code,
            )
            .execution_options(skip_tenant_scope=True)
        ).first()
        if row is None:
            row = db.scalars(
                select(SurveyFbfResult)
                .where(
                    SurveyFbfResult.tenant_code == batch.tenant_code,
                    SurveyFbfResult.fbfbm == code,
                )
                .order_by(SurveyFbfResult.id.desc())
                .execution_options(skip_tenant_scope=True)
            ).first()
        if row is not None and (row.fbfmc or "").strip():
            return row.fbfmc.strip()
        for task in tasks:
            name = (getattr(task, "group_region_name", "") or "").split("/")[-1].strip()
            if name:
                return name
        return None

    @staticmethod
    def _build_template_workbook(
        region_name: str, households: list[dict], issuer_name: str | None = None
    ):
        style_cache: dict[tuple, xlwt.XFStyle] = {}

        def style(font_height: int = 200, bold: bool = False, wrap: bool = False) -> xlwt.XFStyle:
            key = (font_height, bold, wrap)
            if key in style_cache:
                return style_cache[key]
            font = xlwt.Font()
            font.name = "宋体"
            font.height = font_height
            font.bold = bold
            borders = xlwt.Borders()
            borders.left = borders.right = borders.top = borders.bottom = 1
            alignment = xlwt.Alignment()
            alignment.horz = xlwt.Alignment.HORZ_CENTER
            alignment.vert = xlwt.Alignment.VERT_CENTER
            alignment.wrap = 1 if wrap else 0
            st = xlwt.XFStyle()
            st.font = font
            st.borders = borders
            st.alignment = alignment
            style_cache[key] = st
            return st

        wb = xlwt.Workbook(encoding="utf-8")
        ws = wb.add_sheet("承包方调查表")
        ncols = 21
        widths = [16, 10, 8, 8, 10, 6, 12, 22, 10, 10, 14, 14, 30, 8, 14, 10, 12, 24, 10, 12, 14]
        for c, w in enumerate(widths):
            ws.col(c).width = 256 * w
        ws.row(0).height_mismatch = True
        ws.row(0).height = 20 * 28

        if issuer_name:
            title_text = f"{issuer_name}-承包方信息表"
            header_left = f"发包方：{issuer_name}"
        else:
            title_text = TITLE_TEXT
            header_left = f"单位:  {region_name}"
        ws.write_merge(0, 0, 0, ncols - 1, title_text, style(font_height=16 * 20, bold=True))
        ws.write_merge(1, 1, 0, 2, header_left, style(font_height=200, bold=True))
        ws.write_merge(1, 1, 3, 6, f"日期: {datetime.now():%Y 年 %m 月 %d}", style(font_height=200, bold=True))
        # 表头两行：0-2 列纵向合并；3-11「家庭成员情况（含户主）」；12-20「承包方调查信息」
        for c, header in enumerate(["承包方编号", "承包方姓名", "承包方类型"]):
            ws.write_merge(2, 3, c, c, header, style(bold=True, wrap=True))
        ws.write_merge(2, 2, 3, 11, "家庭成员情况（含户主）", style(bold=True))
        ws.write_merge(2, 2, 12, ncols - 1, "承包方调查信息", style(bold=True))
        sub_headers = [
            "家庭成员数（个）", "姓名", "性别", "证件类型", "证件号码", "家庭关系",
            "是否共有人", "备注", "共有人信息修改意见", "承包方地址", "邮政编码", "联系电话",
            "调查员", "调查日期", "调查记事", "审核人", "审核日期", "审核意见",
        ]
        for i, header in enumerate(sub_headers):
            ws.write(3, 3 + i, header, style(bold=True, wrap=True))

        member_keys = ["name", "gender", "id_type", "id_no", "relation", "is_co_owner", "note"]
        # 户级列：一个承包方占多行时纵向合并（与样例模板一致）；11 列「共有人信息修改意见」
        # 无数据字段，仅写空单元格保住边框（不写会整列无框线）。
        household_cells = [
            (0, "cbfbm", False), (1, "cbfmc", False), (2, "cbflx", False), (3, "_member_count", False),
            (11, None, False),
            (12, "address", False), (13, "postcode", False), (14, "mobile", False),
            (15, "surveyor", False), (16, "survey_date", False), (17, "survey_note", True),
            (18, "reviewer", False), (19, "review_date", False), (20, "review_note", False),
        ]
        base_style = style()
        wrap_style = style(wrap=True)
        r = 4
        for household in households:
            n_members = len(household["members"])
            span = max(1, n_members)
            r_end = r + span - 1
            for col, key, wrap in household_cells:
                value = n_members if key == "_member_count" else (household.get(key) if key else "")
                cell_style = wrap_style if wrap else base_style
                if span > 1:
                    ws.write_merge(r, r_end, col, col, value, cell_style)
                else:
                    ws.write(r, col, value, cell_style)
            first_member = household["members"][0] if n_members else None
            for offset, key in enumerate(member_keys):
                ws.write(r, 4 + offset, (first_member or {}).get(key, ""), base_style)
            for member in household["members"][1:]:
                r += 1
                for offset, key in enumerate(member_keys):
                    ws.write(r, 4 + offset, member.get(key, ""), base_style)
            r = r_end + 1
        return wb

    # ── 解析 ────────────────────────────────────────────────────────────────

    @staticmethod
    def parse_contractors_xls(content: bytes) -> tuple[list[dict], list[str]]:
        """解析上传的 xls → (户块列表, 全局告警)。

        户块字段已做基础归一化（日期转 ISO、编号文本化），码值转换在
        ``_normalize_household`` 里做（需要字典）。
        """
        warnings: list[str] = []
        try:
            book = xlrd.open_workbook(file_contents=content, formatting_info=True)
        except Exception:  # noqa: BLE001
            # 个别异常文件读格式信息失败：退化为纯值解析（此时删除标记不可用）
            try:
                book = xlrd.open_workbook(file_contents=content)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=400, detail=f"无法读取 Excel 文件：{exc}") from exc
        sh = book.sheet_by_index(0)

        header_row = None
        for r in range(min(sh.nrows, 20)):
            for c in range(min(sh.ncols, 6)):
                if "承包方编号" in _cell(sh, r, c):
                    header_row = r
                    break
            if header_row is not None:
                break
        if header_row is None:
            raise HTTPException(status_code=400, detail="未找到表头（应包含「承包方编号」列），请使用系统导出的模板")

        # 双行表头：第二行是成员子表头（col0 空、col3 起「家庭成员数（个）/姓名/…」）。
        # ⛔ 不跳过它会把子表头的「姓名」当成首条成员行（2026-11-03 自测发现）。
        while header_row + 1 < min(sh.nrows, 25):
            nxt = header_row + 1
            row_texts = [_cell(sh, nxt, c) for c in range(8)]
            sub_header_hit = any(
                ("家庭成员数" in t) or (t in {"姓名", "性别", "证件类型", "证件号码", "家庭关系", "是否共有人"})
                for t in row_texts[3:8]
            )
            if not row_texts[0] and sub_header_hit:
                header_row = nxt
            else:
                break

        blocks: list[dict] = []
        current: dict | None = None
        for r in range(header_row + 1, sh.nrows):
            code = _cell(sh, r, 0)
            member_name = _cell(sh, r, 4)
            if not code and not member_name:
                continue
            # 成员列（4-10）：承包方行同时携带首名成员（户主），独立成员行仅此 7 列；
            # delete_marked = 「姓名」单元格带底色填充或删除线 ⇒ 导入时删除该成员
            member_cells = {
                "name": member_name,
                "gender_raw": _cell(sh, r, 5),
                "id_type_raw": _cell(sh, r, 6),
                "id_no": _cell(sh, r, 7),
                "relation_raw": _cell(sh, r, 8),
                "is_co_owner_raw": _cell(sh, r, 9),
                "note": _cell(sh, r, 10),
                "delete_marked": _member_delete_marked(sh, r, 4),
            }
            if code:
                current = {
                    "rowIndex": r + 1,
                    "cbfbm": code,
                    "cbfmc": _cell(sh, r, 1),
                    "cbflx_raw": _cell(sh, r, 2),
                    "member_count_raw": _cell(sh, r, 3),
                    "members": [],
                    "address": _cell(sh, r, 12),
                    "postcode": _cell(sh, r, 13),
                    "mobile": _cell(sh, r, 14),
                    "surveyor": _cell(sh, r, 15),
                    "survey_date": _parse_date_cell(_raw_cell(sh, r, 16), book.datemode),
                    "survey_note": _cell(sh, r, 17),
                    "reviewer": _cell(sh, r, 18),
                    "review_date": _parse_date_cell(_raw_cell(sh, r, 19), book.datemode),
                    "review_note": _cell(sh, r, 20),
                }
                # 首行成员（户主行）：模板中户主与承包方信息同 row
                if member_name:
                    current["members"].append(member_cells)
                blocks.append(current)
            elif current is not None:
                current["members"].append(member_cells)
            else:
                warnings.append(f"第 {r + 1} 行：缺少承包方编号，已忽略该行")
            # 整户注销标记：该户「承包方姓名」（col 1）单元格带底色/删除线。
            # ⛔ 必须在 current 可能被重新赋值之后判——读的是本行 col1 的格式，
            # 与成员标记（col 4）互不干扰；merged 单元格只有锚点带格式，
            # 而户行就是锚点行，读法天然正确。
            if current is not None and current["rowIndex"] == r + 1:
                current["household_delete_marked"] = _member_delete_marked(sh, r, 1)
        return blocks, warnings

    # ── 归一化 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _relation_name_to_code(labels: dict[str, str]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for code, name in labels.items():
            mapping.setdefault(str(name).strip(), code)
        # 常见别名
        mapping.setdefault("户主本人", "02")
        mapping.setdefault("本人", "01")
        return mapping

    def _normalize_household(self, block: dict, db: Session) -> tuple[dict | None, list[str]]:
        """原始块 → 码值归一化的户数据；返回 (data, errors)。data 为 None 表示该户结构性错误。"""
        errors: list[str] = []
        code = (block.get("cbfbm") or "").strip()
        if not code:
            errors.append("承包方编号为空")
        elif not code.isdigit() or len(code) != 18:
            errors.append(f"承包方编号「{code}」不是 18 位数字")

        labels = relation_labels(db)
        name_to_code = self._relation_name_to_code(labels)
        label_codes = set(labels)
        members: list[dict] = []
        for member in block.get("members") or []:
            name = (member.get("name") or "").strip()
            if not name:
                errors.append("存在未填姓名的成员行")
                continue
            id_no = (member.get("id_no") or "").strip()
            gender = GENDER_CODES.get((member.get("gender_raw") or "").strip()) or _gender_from_id_no(id_no)
            relation_raw = (member.get("relation_raw") or "").strip()
            relation = name_to_code.get(relation_raw) or (relation_raw if relation_raw in label_codes else "")
            co_owner_raw = (member.get("is_co_owner_raw") or "").strip()
            is_co_owner = (
                "1" if co_owner_raw in {YES, "1"} else ("0" if co_owner_raw in {NO, "0"} else "")
            )
            members.append({
                "name": name,
                "gender": gender,
                "id_type": ID_TYPE_CODES.get((member.get("id_type_raw") or "").strip()) or _DEFAULT_ID_TYPE,
                "id_no": id_no,
                "relation": relation,
                "is_co_owner": is_co_owner,
                "note": (member.get("note") or "").strip(),
                "is_head_label": relation_raw in {"户主", "本人", "户主本人"},
                "marked_delete": bool(member.get("delete_marked")),
            })

        data = {
            "rowIndex": block.get("rowIndex"),
            "cbfbm": code,
            "cbfmc": (block.get("cbfmc") or "").strip(),
            "cbflx": CONTRACTOR_TYPE_CODES.get((block.get("cbflx_raw") or "").strip()) or "",
            "member_count_raw": (block.get("member_count_raw") or "").strip(),
            "members": members,
            "address": (block.get("address") or "").strip(),
            "postcode": (block.get("postcode") or "").strip(),
            "mobile": (block.get("mobile") or "").strip(),
            "surveyor": (block.get("surveyor") or "").strip(),
            "survey_date": (block.get("survey_date") or "").strip(),
            "survey_note": (block.get("survey_note") or "").strip(),
            "reviewer": (block.get("reviewer") or "").strip(),
            "review_date": (block.get("review_date") or "").strip(),
            "review_note": (block.get("review_note") or "").strip(),
            "household_delete_marked": bool(block.get("household_delete_marked")),
        }
        return (data if not errors else None), errors

    # ── 公共差异比对（建库中心批次导入 / 数据中心导入同源）─────────────────

    def _diff_members_for_import(
        self,
        existing_members: list[dict],
        excel_members: list[dict],
        *,
        member_change_reason: str,
    ) -> dict:
        """家庭成员差异比对（按证件号码匹配）。

        供两条导入链路共用：
        - 建库中心批次导入（``_plan_household`` update 分支）
        - 数据中心清单导入（``_plan_household_db``，按承包方编号匹配主表）

        ``existing_members`` 为库内成员字典列表（须含 ``idNo``；``memberUid``/
        ``isHouseholdHead``/``changeReason`` 可缺省——两条链路的详情序列化口径
        不同，缺失的键按空值处理，payload 由调用方全量重写成员表）。

        返回 dict：``members_payload`` / ``added`` / ``updated`` / ``deleted_names`` /
        ``deleted_payloads``（批次链路的 deletedMembers，数据中心忽略）/
        ``warnings`` / ``errors`` / ``excel_row_count``（未标记删除的成员行数）。
        """
        members_payload: list[dict] = []
        added_names: list[str] = []
        updated_summaries: list[str] = []
        deleted_names: list[str] = []
        deleted_payloads: list[dict] = []
        deleted_keys: set[str] = set()
        matched_keys: set[str] = set()
        warnings: list[str] = []
        errors: list[str] = []

        existing_by_id: dict[str, dict] = {}
        for member in existing_members:
            id_no = (member.get("idNo") or "").strip()
            if id_no:
                existing_by_id.setdefault(id_no, member)

        def _member_key(target: dict) -> str:
            """成员身份键：memberUid 优先，缺省（数据中心详情口径）退回证件号。"""
            return str(target.get("memberUid") or "") or f"id:{target.get('idNo') or ''}"

        for member in excel_members:
            if member.get("marked_delete"):
                # 删除标记：按证件号码匹配库内成员 → 从 payload 剔除并记 deletedMembers
                # （两条链路的成员表都是整体重写，省略即删除；deleted_payloads 只承载变化原因）
                target = existing_by_id.get(member["id_no"]) if member["id_no"] else None
                if target is None:
                    warnings.append(
                        f"标记删除的成员「{member['name']}」在库内不存在或证件号为空无法匹配，忽略删除"
                    )
                    continue
                # 户主判定：批次详情带 isHouseholdHead；数据中心详情按关系码兜底
                is_head = bool(target.get("isHouseholdHead")) or (
                    target.get("relationToHead") or ""
                ) in HEAD_RELATION_PRIORITY
                if is_head:
                    errors.append(f"成员「{member['name']}」是户主，不能标记删除；如需调整请直接修改户主信息")
                    continue
                key = _member_key(target)
                matched_keys.add(key)
                deleted_keys.add(key)
                deleted_names.append(member["name"])
                deleted_payloads.append({
                    "memberUid": target.get("memberUid"),
                    "changeReason": member_change_reason,
                })
                continue
            if not member["id_no"]:
                errors.append(f"成员「{member['name']}」证件号码为空，无法匹配（导入要求证件号码必填）")
                continue
            target = existing_by_id.get(member["id_no"])
            if target is None:
                if not member["gender"]:
                    errors.append(f"新增成员「{member['name']}」性别为空且无法从证件号码判定")
                    continue
                members_payload.append({
                    "name": member["name"],
                    "gender": member["gender"],
                    "idType": member["id_type"] or _DEFAULT_ID_TYPE,
                    "idNo": member["id_no"],
                    "relationToHead": member["relation"] or _DEFAULT_RELATION,
                    "isCoOwner": member["is_co_owner"] or "0",
                    "note": member["note"] or None,
                    "isHouseholdHead": member["is_head_label"],
                    "changeReason": member_change_reason,
                })
                added_names.append(member["name"])
                continue
            matched_keys.add(_member_key(target))
            entry = dict(target)
            changed_fields = []
            for excel_key, payload_key, label in [
                ("name", "name", "姓名"),
                ("gender", "gender", "性别"),
                ("id_type", "idType", "证件类型"),
                ("relation", "relationToHead", "与户主关系"),
                ("is_co_owner", "isCoOwner", "是否共有人"),
            ]:
                new_value = member.get(excel_key)
                if new_value and str(new_value) != str(target.get(payload_key) or ""):
                    entry[payload_key] = new_value
                    changed_fields.append(label)
            new_note = member.get("note") or ""
            if new_note and new_note != str(target.get("note") or ""):
                entry["note"] = new_note
                changed_fields.append("备注")
            if changed_fields:
                if not (entry.get("changeReason") or "").strip():
                    entry["changeReason"] = member_change_reason
                updated_summaries.append(f"{member['name']}（{'、'.join(changed_fields)}）")
            members_payload.append(entry)

        for member in existing_members:
            key = _member_key(member)
            if key and key not in matched_keys and key not in deleted_keys:
                members_payload.append(member)
                warnings.append(
                    f"库内成员「{member.get('name') or member.get('idNo')}」不在 Excel 中，按原样保留"
                )

        excel_row_count = sum(1 for m in excel_members if not m.get("marked_delete"))
        return {
            "members_payload": members_payload,
            "added": added_names,
            "updated": updated_summaries,
            "deleted_names": deleted_names,
            "deleted_payloads": deleted_payloads,
            "warnings": warnings,
            "errors": errors,
            "excel_row_count": excel_row_count,
        }

    def _assign_head_flags(self, members_payload: list[dict], excel_members: list[dict]) -> None:
        """户主唯一化（⛔ 一个户里绝不能出现两个户主类标记）。

        Excel 标「户主/本人」的成员优先 → payload 既有 isHouseholdHead →
        关系码兜底（统一口径）；户主关系统一收敛为「02」。
        ``excel_members`` 与 ``members_payload`` 前 N 项同序（Excel 成员在前）。
        """
        head_idx: int | None = None
        for i, member in enumerate(excel_members):
            if member.get("is_head_label") and i < len(members_payload) and members_payload[i].get("idNo") == member["id_no"]:
                head_idx = i
                break
        if head_idx is None:
            for i, entry in enumerate(members_payload):
                if entry.get("isHouseholdHead"):
                    head_idx = i
                    break
        if head_idx is None:
            for i, entry in enumerate(members_payload):
                if (entry.get("relationToHead") or "") in HEAD_RELATION_PRIORITY:
                    head_idx = i
                    break
        if head_idx is None and members_payload:
            head_idx = 0
        for i, entry in enumerate(members_payload):
            entry["isHouseholdHead"] = head_idx is not None and i == head_idx
            head_entry = members_payload[head_idx]
            if head_entry.get("relationToHead") not in HEAD_RELATION_PRIORITY:
                head_entry["relationToHead"] = "02"

    # ── 匹配与差异 ──────────────────────────────────────────────────────────

    # (payload key, 规范化数据 key, 标签)
    # ⛔ 表格里有的字段必须全部参与差异对比：只更新“已比对”的字段，否则当某户
    # 只有调查日期/审核日期变化时会被判定为 no_change 而整户跳过，库值永远不更新。
    _CONTRACTOR_FIELD_MAP = [
        ("name", "cbfmc", "承包方名称"),
        ("address", "address", "承包方地址"),
        ("postcode", "postcode", "邮政编码"),
        ("mobile", "mobile", "联系电话"),
        ("surveyorName", "surveyor", "调查员"),
        ("surveyDate", "survey_date", "调查日期"),
        ("surveyNote", "survey_note", "调查记事"),
        ("publicNoticeReviewer", "reviewer", "审核人"),
        ("publicNoticeReviewDate", "review_date", "审核日期"),
        ("publicNoticeNote", "review_note", "审核意见"),
    ]

    def _find_batch_task(self, db: Session, batch, cbfbm: str) -> SurveyCbfBase | None:
        return db.scalars(
            select(SurveyCbfBase)
            .where(
                SurveyCbfBase.tenant_code == batch.tenant_code,
                SurveyCbfBase.batch_id == batch.id,
                SurveyCbfBase.cbfbm == cbfbm,
            )
            .execution_options(skip_tenant_scope=True)
        ).first()

    def _plan_household(self, db: Session, batch, household: dict, current_user: User) -> dict:
        """单户计划：匹配、差异对比。返回 plan dict（含 errors 则不可导入）。"""
        errors: list[str] = []
        warnings: list[str] = []
        code = household["cbfbm"]

        # 规则 1：编号必须以批次区域码开头
        region_code = (batch.region_code or "").strip()
        if not region_code or not code.startswith(region_code):
            errors.append(f"编号必须以调查批次区域码「{region_code or '(未配置)'}」开头")

        task = self._find_batch_task(db, batch, code) if code else None
        result: SurveyCbfResult | None = None
        if task is not None:
            result = db.scalars(
                select(SurveyCbfResult)
                .where(
                    SurveyCbfResult.tenant_code == batch.tenant_code,
                    SurveyCbfResult.contractor_uid == task.contractor_uid,
                )
                .order_by(SurveyCbfResult.id.desc())
                .execution_options(skip_tenant_scope=True)
            ).first()
            if result is not None and result.survey_status in self.locked_survey_statuses:
                return self._plan_skip(code, household, "调查成果已确认，自动跳过")
            if result is not None and self.is_terminal_result(result):
                return self._plan_skip(code, household, "该户已注销/合户/分户终结，自动跳过")

        action = "update" if task is not None else "create"

        # 整户注销标记（「承包方姓名」单元格底色/删除线）：
        # 复用页面「注销承包方」同源 deregister_contractor（底档保留可撤回）。
        # 已确认/已终结的户在上面已按 locked/terminal 跳过；批次内不存在的标记户忽略。
        if household.get("household_delete_marked"):
            return self._plan_deregister(code, household, task, errors, warnings)

        current = self.get_result(db, batch.id, task.contractor_uid, current_user) if task is not None else None

        contractor_changes: list[str] = []
        members_payload: list[dict] = []
        added_names: list[str] = []
        updated_summaries: list[str] = []
        deleted_names: list[str] = []
        deleted_member_payloads: list[dict] = []
        excel_row_count = 0

        if action == "update":
            # 公共成员差异比对（与数据中心清单导入同源）
            diff = self._diff_members_for_import(
                list(current.get("familyMembers") or []),
                household["members"],
                member_change_reason=IMPORT_MEMBER_CHANGE_REASON,
            )
            members_payload = diff["members_payload"]
            added_names = diff["added"]
            updated_summaries = diff["updated"]
            deleted_names = diff["deleted_names"]
            deleted_member_payloads = diff["deleted_payloads"]
            warnings.extend(diff["warnings"])
            errors.extend(diff["errors"])
            excel_row_count = diff["excel_row_count"]

            if household["member_count_raw"]:
                try:
                    if int(household["member_count_raw"]) != excel_row_count:
                        warnings.append(
                            f"家庭成员数（{household['member_count_raw']}）与成员行数（{excel_row_count}）不一致，按实际行数导入"
                        )
                except ValueError:
                    warnings.append(f"家庭成员数「{household['member_count_raw']}」无法识别，按实际行数导入")

            # 承包方字段对比（空单元格不覆盖库值，也不借导入清空字段）
            for payload_key, data_key, label in self._CONTRACTOR_FIELD_MAP:
                new_value = household.get(data_key) or ""
                if new_value and str(new_value) != str(current.get(payload_key) or ""):
                    contractor_changes.append(label)
            if household.get("cbflx") and household["cbflx"] != current.get("typeCode"):
                contractor_changes.append("承包方类型")
        else:  # create
            for member in household["members"]:
                if member.get("marked_delete"):
                    warnings.append(f"新增户不存在成员「{member['name']}」，删除标记已忽略")
                    continue
                if not member["id_no"]:
                    errors.append(f"成员「{member['name']}」证件号码为空")
                    continue
                if not member["gender"]:
                    errors.append(f"新增成员「{member['name']}」性别为空且无法从证件号码判定")
                    continue
                members_payload.append({
                    "name": member["name"],
                    "gender": member["gender"],
                    "idType": member["id_type"] or _DEFAULT_ID_TYPE,
                    "idNo": member["id_no"],
                    "relationToHead": member["relation"] or ("02" if member["is_head_label"] else _DEFAULT_RELATION),
                    "isCoOwner": member["is_co_owner"] or "0",
                    "note": member["note"] or None,
                    "isHouseholdHead": member["is_head_label"],
                    "changeReason": IMPORT_MEMBER_CHANGE_REASON,
                })
                added_names.append(member["name"])
            if not members_payload:
                errors.append("新增户至少需要一名带证件号码的家庭成员")

        # 户主唯一化（⛔ 一个户里绝不能出现两个户主类标记）：
        # Excel 标「户主/本人」的成员优先 → 既有 isHouseholdHead → 关系码兜底（统一口径）。
        self._assign_head_flags(members_payload, household["members"] if action == "update" else [])

        # 有没有实际变化
        if action == "update":
            has_change = bool(contractor_changes or added_names or updated_summaries or deleted_names)
            effective = "update" if has_change else "no_change"
        else:
            effective = "create"

        if not household["cbfmc"]:
            errors.append("承包方姓名为空")
        if action == "create" and not errors:
            exists = db.scalars(
                select(SurveyCbfBase)
                .where(SurveyCbfBase.tenant_code == batch.tenant_code, SurveyCbfBase.cbfbm == code)
                .execution_options(skip_tenant_scope=True)
            ).first()
            if exists is not None:
                errors.append("该编号已存在于其他调查批次，不能重复创建")

        return {
            "cbfbm": code,
            "cbfmc": household["cbfmc"],
            "rowIndex": household["rowIndex"],
            "action": effective,
            "errors": errors,
            "warnings": warnings,
            "contractorChanges": contractor_changes,
            "memberSummary": {"added": added_names, "updated": updated_summaries, "deleted": deleted_names},
            "_membersPayload": members_payload,
            "_deletedMembers": deleted_member_payloads,
            "_contractorUid": task.contractor_uid if task is not None else None,
        }

    def _plan_deregister(self, code: str, household: dict, task, errors: list[str], warnings: list[str]) -> dict:
        """整户注销计划：不复用 _plan_skip（action 不同），错误仍按 error 上报拦截。"""
        base = {
            "cbfbm": code, "cbfmc": household["cbfmc"], "rowIndex": household["rowIndex"],
            "errors": errors, "warnings": warnings,
            "contractorChanges": [], "memberSummary": {"added": [], "updated": [], "deleted": []},
        }
        if task is None:
            base.update({"action": "skipped", "message": "标记注销的承包户在批次内不存在，忽略"})
            return base
        if errors:
            base["action"] = "error"
            return base
        base.update({
            "action": "deregister",
            "_membersPayload": [], "_deletedMembers": [],
            "_contractorUid": task.contractor_uid,
        })
        return base

    @staticmethod
    def _plan_skip(code: str, household: dict, message: str) -> dict:
        return {
            "cbfbm": code, "cbfmc": household["cbfmc"], "rowIndex": household["rowIndex"],
            "action": "skipped", "message": message,
            "errors": [], "warnings": [], "contractorChanges": [],
            "memberSummary": {"added": [], "updated": [], "deleted": []},
        }

    # ── 预览 ────────────────────────────────────────────────────────────────

    def preview_contractor_xls_import(self, db: Session, batch_id: int, current_user: User, content: bytes) -> dict:
        batch = self._ensure_batch(db, batch_id)
        blocks, warnings = self.parse_contractors_xls(content)
        if batch.status == "finished":
            warnings.insert(0, "该调查批次已结束，导入将被拒绝")
        households: list[dict] = []
        summary = {"create": 0, "update": 0, "no_change": 0, "skipped": 0, "error": 0, "deregister": 0}
        for block in blocks:
            normalized, errors = self._normalize_household(block, db)
            if normalized is None:
                plan = {
                    "cbfbm": block.get("cbfbm") or "", "cbfmc": block.get("cbfmc") or "",
                    "rowIndex": block.get("rowIndex"), "action": "error",
                    "errors": errors, "warnings": [], "contractorChanges": [],
                    "memberSummary": {"added": [], "updated": []},
                }
            else:
                try:
                    plan = self._plan_household(db, batch, normalized, current_user)
                except HTTPException as exc:
                    plan = {
                        "cbfbm": normalized["cbfbm"], "cbfmc": normalized["cbfmc"],
                        "rowIndex": normalized["rowIndex"], "action": "error",
                        "errors": [str(exc.detail)], "warnings": [], "contractorChanges": [],
                        "memberSummary": {"added": [], "updated": []},
                    }
            plan.pop("_membersPayload", None)
            plan.pop("_contractorUid", None)
            summary[plan["action"]] = summary.get(plan["action"], 0) + 1
            households.append(plan)
        return {
            "batchId": batch_id,
            "batchRegionCode": batch.region_code,
            "totalHouseholds": len(households),
            "summary": summary,
            "warnings": warnings,
            "households": households,
        }

    # ── 导入 ────────────────────────────────────────────────────────────────

    def import_contractors_xls(
        self, db: Session, batch_id: int, current_user: User, content: bytes, progress_cb=None
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=400, detail="调查批次已结束，不能导入")
        blocks, warnings = self.parse_contractors_xls(content)
        results: list[dict] = []
        summary = {"created": 0, "updated": 0, "no_change": 0, "skipped": 0, "failed": 0, "deregistered": 0}

        def report(done: int, current: str = "") -> None:
            if progress_cb is not None:
                try:
                    progress_cb(done, len(blocks), f"导入第 {done}/{len(blocks)} 户", current)
                except Exception:  # noqa: BLE001
                    pass

        report(0, "解析 Excel")
        for idx, block in enumerate(blocks):
            report(idx, f"{block.get('cbfmc') or block.get('cbfbm') or ''}（第 {block.get('rowIndex') or '?'} 行）")
            normalized, errors = self._normalize_household(block, db)
            if normalized is None:
                summary["failed"] += 1
                results.append({
                    "cbfbm": block.get("cbfbm") or "", "cbfmc": block.get("cbfmc") or "",
                    "rowIndex": block.get("rowIndex"), "status": "failed", "message": "；".join(errors),
                })
                continue
            try:
                plan = self._plan_household(db, batch, normalized, current_user)
                if plan["errors"]:
                    raise HTTPException(status_code=400, detail="；".join(plan["errors"]))
                result_row = self._apply_household_plan(db, batch, plan, normalized, current_user)
                summary[result_row["status"]] = summary.get(result_row["status"], 0) + 1
                results.append(result_row)
            except HTTPException as exc:
                db.rollback()
                summary["failed"] += 1
                results.append({
                    "cbfbm": normalized["cbfbm"], "cbfmc": normalized["cbfmc"],
                    "rowIndex": normalized["rowIndex"], "status": "failed", "message": str(exc.detail),
                })
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                logger.exception("Excel 导入单户失败 cbfbm=%s", normalized.get("cbfbm"))
                summary["failed"] += 1
                results.append({
                    "cbfbm": normalized["cbfbm"], "cbfmc": normalized["cbfmc"],
                    "rowIndex": normalized["rowIndex"], "status": "failed",
                    "message": f"导入异常：{exc}",
                })
        logger.info(
            "承包方调查表导入完成 batch_id=%s 结果=%s 操作人=%s",
            batch_id, summary, getattr(current_user, "username", None),
        )
        return {
            "batchId": batch_id,
            "totalHouseholds": len(results),
            "summary": summary,
            "warnings": warnings,
            "households": results,
        }

    def _mark_surveyed_from_import(self, db: Session, batch_id: int, contractor_uid: str | None) -> None:
        """Excel 导入视为"该户已调查"：无变化户也把成果态/任务态推进为已调查。

        ⛔ update_result 只在真正保存的户上推进状态；导出→原样导入的整批户全是
        no_change 短路，批次"已调查"计数永远不动（2026-11-04 用户反馈 0/141）。
        这里只推状态，不建变化记录（无字段差异可记），已定案态一律不动。
        """
        if not contractor_uid:
            return
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status in self.terminal_survey_statuses:
            return  # confirmed / skipped：定案态不动
        if result.survey_status in self.confirmable_survey_statuses:
            return  # surveyed / changed / unchanged：已是"已调查"口径，不动
        result.survey_status = "surveyed"
        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.task_status = "surveyed"
            task.investigated_at = datetime.now(timezone.utc)
        db.commit()

    def _apply_household_plan(self, db: Session, batch, plan: dict, household: dict, current_user: User) -> dict:
        """把单户计划落库：与页面保存同源（update_result），逐户提交、逐户回滚。"""
        if plan["action"] == "skipped":
            return {
                "cbfbm": plan["cbfbm"], "cbfmc": plan["cbfmc"], "rowIndex": plan["rowIndex"],
                "status": "skipped", "message": plan.get("message") or "已跳过",
            }
        if plan["action"] == "no_change":
            self._mark_surveyed_from_import(db, batch.id, plan.get("_contractorUid"))
            return {
                "cbfbm": plan["cbfbm"], "cbfmc": plan["cbfmc"], "rowIndex": plan["rowIndex"],
                "status": "no_change", "message": "数据无变化，调查状态已置为已调查",
            }
        if plan["action"] == "deregister":
            # 与页面「注销承包方」同源：底档保留、变化原因可追溯、可在注销列表撤回
            self.deregister_contractor(
                db, batch.id, plan["_contractorUid"],
                "承包方调查表（Excel）标记注销", current_user,
            )
            return {
                "cbfbm": plan["cbfbm"], "cbfmc": plan["cbfmc"], "rowIndex": plan["rowIndex"],
                "status": "deregistered", "message": "整户注销（Excel 标记），底档保留、可在注销列表撤回",
            }

        contractor_uid = plan.get("_contractorUid")
        if contractor_uid:
            current = self.get_result(db, batch.id, contractor_uid, current_user)
        else:
            # 新增户：先 create_contractor 建基线+结果行（自带提交），再全量写调查信息
            first_member = next((m for m in plan["_membersPayload"]), None)
            created = self.create_contractor(db, batch.id, {
                "code": plan["cbfbm"],
                "name": plan["cbfmc"],
                "idType": (first_member or {}).get("idType") or _DEFAULT_ID_TYPE,
                "idNo": (first_member or {}).get("idNo") or "",
                "address": household.get("address") or "",
                "postcode": household.get("postcode") or None,
                "mobile": household.get("mobile") or None,
            }, current_user)
            contractor_uid = created["contractorUid"]
            current = self.get_result(db, batch.id, contractor_uid, current_user)

        payload = dict(current)
        for payload_key, data_key, _label in self._CONTRACTOR_FIELD_MAP:
            new_value = household.get(data_key) or ""
            if new_value:
                payload[payload_key] = new_value
        if household.get("cbflx"):
            payload["typeCode"] = household["cbflx"]
        if household.get("survey_date"):
            payload["surveyDate"] = household["survey_date"]
        if household.get("review_date"):
            payload["publicNoticeReviewDate"] = household["review_date"]
        if plan["action"] == "create":
            payload["changeReason"] = "承包方调查表（Excel）导入新增"
        elif not (current.get("changeReason") or "").strip():
            payload["changeReason"] = IMPORT_CHANGE_REASON

        payload["familyMembers"] = plan["_membersPayload"]
        payload["deletedMembers"] = plan.get("_deletedMembers") or []
        payload["pendingOperations"] = []
        payload["contractorUid"] = contractor_uid

        self.update_result(db, batch.id, contractor_uid, payload, current_user)

        status_label = "created" if plan["action"] == "create" else "updated"
        detail_parts = []
        if plan.get("contractorChanges"):
            detail_parts.append(f"承包方信息（{'、'.join(plan['contractorChanges'])}）")
        member_summary = plan.get("memberSummary") or {}
        if member_summary.get("added"):
            detail_parts.append(f"新增成员 {len(member_summary['added'])} 名")
        if member_summary.get("updated"):
            detail_parts.append(f"修改成员 {len(member_summary['updated'])} 名")
        if member_summary.get("deleted"):
            detail_parts.append(f"删除成员 {len(member_summary['deleted'])} 名（{('、'.join(member_summary['deleted']))}）")
        return {
            "cbfbm": plan["cbfbm"], "cbfmc": plan["cbfmc"], "rowIndex": plan["rowIndex"],
            "status": status_label,
            "message": "；".join(detail_parts) or "已更新",
        }
