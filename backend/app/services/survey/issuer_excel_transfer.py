# -*- coding: utf-8 -*-
"""发包方调查表 Excel 模板（版式定义 / 导出构建 / 解析 / 行归一化）。

本模块只负责 Excel 版式本身，不含落库逻辑；导入/导出的业务实现见
``app/services/issuer_excel_transfer.py``（发包方管理页，操作 ``fbf`` 主表）。

模板与样例 ``datas/发包方/32132410002201-发包方调查表.xls`` 一致（0 基行号）：

====  ====================  ======  =================================================
行号  说明
====  ====================  ======  =================================================
0     标题「农村土地承包经营权发包方调查表」（横向合并 16 列）
1     单行表头（16 列）
2+    数据行：一行一个发包方
末行  「合计」行（导入时跳过）
====  ====================  ======  =================================================

模板列布局（0 基）：

====  =====================  ==========  =====================================
列号  标题                  字段        说明
====  =====================  ==========  =====================================
0     发包方编码            fbfbm       14 位编码，导入匹配键
1     发包方名称            fbfmc       删除标记列（底色填充 / 删除线 ⇒ 删除）
2     发包方负责人姓名      fbffzrxm
3     发包方负责人联系电话  lxdh
4     发包方负责人地址      fbfdz
5     邮政编码              yzbm
6     负责人证件类型        fzrzjlx     居民身份证 ↔ 1（导入导出互转）
7     负责人证件号码        fzrzjhm
8     调查员                fbfdcy
9     调查日期              fbfdcrq     ISO YYYY-MM-DD（兼容样例的中文日期）
10    调查记事              fbfdcjs
11    审核人                shr
12    审核日期              shrq        ISO YYYY-MM-DD
13    审核意见              shyj
14    备注                  bzxx
15    统一社会信用代码      tyshxydm
====  =====================  ==========  =====================================

⛔ 导出时发包方编码按**文本**写入（与承包方编号同一口径），导入读到数值型
编码只能尽力取整——模板必须用系统导出的文件改。
"""
from __future__ import annotations

import xlrd
import xlwt
from fastapi import HTTPException

from app.services.survey.excel_transfer import (
    _cell,
    _member_delete_marked,
    _parse_date_cell,
    _raw_cell,
)

ISSUER_XLS_TITLE = "农村土地承包经营权发包方调查表"
ISSUER_ID_TYPE_LABELS = {"1": "居民身份证"}
ISSUER_ID_TYPE_CODES = {v: k for k, v in ISSUER_ID_TYPE_LABELS.items()}
DEFAULT_ID_TYPE = "1"


class IssuerXlsTemplate:
    """发包方调查表 xls 的构建 / 解析 / 行归一化（无状态，纯版式逻辑）。"""

    @staticmethod
    def build_workbook(rows: list[dict]):
        headers = [
            "发包方编码", "发包方名称", "发包方负责人姓名", "发包方负责人联系电话",
            "发包方负责人地址", "邮政编码", "发包方负责人证件类型", "发包方负责人证件号码",
            "调查员", "调查日期", "调查记事", "审核人", "审核日期", "审核意见", "备注", "统一社会信用代码",
        ]
        widths = [16, 26, 12, 14, 32, 8, 14, 20, 14, 12, 32, 10, 12, 18, 18, 22]
        field_keys = [
            "code", "name", "responsible_name", "mobile", "address", "postcode",
            "id_type", "id_no", "surveyor", "survey_date", "survey_note",
            "auditor", "audit_date", "audit_opinion", "remark", "credit_code",
        ]

        style_cache: dict[tuple, xlwt.XFStyle] = {}

        def style(bold: bool = False, wrap: bool = False) -> xlwt.XFStyle:
            key = (bold, wrap)
            if key in style_cache:
                return style_cache[key]
            font = xlwt.Font()
            font.name = "宋体"
            font.height = 200
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
        ws = wb.add_sheet("发包方调查表")
        ncols = len(headers)
        for c, w in enumerate(widths):
            ws.col(c).width = 256 * w
        ws.row(0).height_mismatch = True
        ws.row(0).height = 20 * 28
        ws.write_merge(0, 0, 0, ncols - 1, ISSUER_XLS_TITLE, style(bold=True))
        for c, header in enumerate(headers):
            ws.write(1, c, header, style(bold=True, wrap=True))
        r = 2
        for row in rows:
            for c, key in enumerate(field_keys):
                # 兼容调用方未提供的新列：None 直接写进 xlwt 会在 save 时抛异常。
                value = (row.get(key) if key else "") or ""
                # ⛔ 编码必须是文本：数值型在 Excel 里显示成科学计数法，
                #    且用户另存/复制后可能丢精度导致导入匹配不上
                ws.write(r, c, value, style(wrap=key == "survey_note"))
            r += 1
        # 合计行（与样例模板一致；导入时按此跳过）
        ws.write(r, 0, "合计", style())
        for c in range(1, ncols):
            ws.write(r, c, "\\", style())
        return wb

    @staticmethod
    def parse(content: bytes) -> tuple[list[dict], list[str]]:
        """解析上传的 xls → (发包方行列表, 全局告警)。"""
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
                if "发包方编码" in _cell(sh, r, c):
                    header_row = r
                    break
            if header_row is not None:
                break
        if header_row is None:
            raise HTTPException(status_code=400, detail="未找到表头（应包含「发包方编码」列），请使用系统导出的模板")

        rows: list[dict] = []
        for r in range(header_row + 1, sh.nrows):
            code = _cell(sh, r, 0)
            name = _cell(sh, r, 1)
            if code == "合计":
                continue
            if not code and not name:
                continue
            if not code:
                warnings.append(f"第 {r + 1} 行：发包方编码为空，已忽略该行")
                continue
            rows.append({
                "rowIndex": r + 1,
                "code": code,
                "name": name,
                "responsible_name": _cell(sh, r, 2),
                "mobile": _cell(sh, r, 3),
                "address": _cell(sh, r, 4),
                "postcode": _cell(sh, r, 5),
                "id_type_raw": _cell(sh, r, 6),
                "id_no": _cell(sh, r, 7),
                "surveyor": _cell(sh, r, 8),
                "survey_date": _parse_date_cell(_raw_cell(sh, r, 9), book.datemode),
                "survey_note": _cell(sh, r, 10),
                "auditor": _cell(sh, r, 11),
                "audit_date": _parse_date_cell(_raw_cell(sh, r, 12), book.datemode),
                "audit_opinion": _cell(sh, r, 13),
                "remark": _cell(sh, r, 14),
                "credit_code": _cell(sh, r, 15),
                # 删除标记：「发包方名称」单元格底色填充或删除线 ⇒ 删除该发包方
                "delete_marked": _member_delete_marked(sh, r, 1),
            })
        return rows, warnings

    @staticmethod
    def normalize_row(row: dict) -> tuple[dict | None, list[str]]:
        """原始行 → 规范化数据；返回 (data, errors)。data 为 None 表示结构性错误。"""
        errors: list[str] = []
        code = (row.get("code") or "").strip()
        if not code:
            errors.append("发包方编码为空")
        elif not code.isdigit() or len(code) != 14:
            errors.append(f"发包方编码「{code}」不是 14 位数字")

        name = (row.get("name") or "").strip()
        if not name:
            errors.append("发包方名称为空")
        # 删除标记行（「发包方名称」底色/删除线）：只要求编码定位得到行。
        # 必填口径（与承包户导入同源）：「空单元格不覆盖库值」——
        # 更新场景下负责人/证件号/地址为空不报错、保留库值；只有**新增**行才要求填全
        # （由业务层的 create 分支拦截），缺哪些列在 `_missingRequired` 里带回。
        missing_required = []
        responsible_name = (row.get("responsible_name") or "").strip()
        id_no = (row.get("id_no") or "").strip()
        address = (row.get("address") or "").strip()
        if not row.get("delete_marked"):
            if not responsible_name:
                missing_required.append("发包方负责人姓名")
            if not id_no:
                missing_required.append("负责人证件号码")
            if not address:
                missing_required.append("发包方负责人地址")

        id_type_raw = (row.get("id_type_raw") or "").strip()
        id_type = ISSUER_ID_TYPE_CODES.get(id_type_raw) or (id_type_raw if id_type_raw in ISSUER_ID_TYPE_LABELS else "")
        # ⛔ 空证件类型保持为空：缺省值「1」只允许在**新增落库**时兜底。
        # 若在这里默认成「1」，更新行会把库内的组织机构代码等类型误判为变更
        # 并悄悄覆盖（导出→原样回传也会整批误判，2026-11-06 审计发现）。

        data = {
            "rowIndex": row.get("rowIndex"),
            "code": code,
            "name": name,
            "responsibleName": responsible_name,
            "phone": (row.get("mobile") or "").strip(),
            "address": address,
            # 空邮编不覆盖库值；create_issuer 落库时自己兜底 "000000"
            "postcode": (row.get("postcode") or "").strip(),
            "responsibleIdType": id_type,
            "responsibleIdNo": id_no,
            "surveyorName": (row.get("surveyor") or "").strip(),
            "surveyDate": (row.get("survey_date") or "").strip(),
            "surveyNote": (row.get("survey_note") or "").strip(),
            "auditor": (row.get("auditor") or "").strip(),
            "auditDate": (row.get("audit_date") or "").strip(),
            "auditOpinion": (row.get("audit_opinion") or "").strip(),
            "remark": (row.get("remark") or "").strip(),
            "creditCode": (row.get("credit_code") or "").strip(),
            "delete_marked": bool(row.get("delete_marked")),
            "_missingRequired": missing_required,
        }
        return (data if not errors else None), errors
