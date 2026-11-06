# -*- coding: utf-8 -*-
"""发包方调查表 Excel 导入 / 导出。

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
0     发包方编码            fbfbm       14 位编码，导入匹配键（必须属于批次区域）
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
11    审核人                ——          模板占位，不读写
12    审核日期              ——          模板占位，不读写
13    审核意见              ——          模板占位，不读写
14    备注                  remark
15    社会信用代码          ——          模板占位，不读写
====  =====================  ==========  =====================================

导入规则（与承包方调查表 Excel 导入同口径，2026-11-05）：

1. 按调查批次导入：每行「发包方编码」必须属于批次区域 —— 批次区域码满 14 位
   时必须与之相等（发包方编码即村级 14 位码），不足 14 位时须以其开头；
2. 按编码匹配：库内存在则对比更新，不存在（且前缀合法）则新增；
3. 已确认（confirmed）的发包方自动跳过；
4. 删除标记：「发包方名称」单元格填充底色或加删除线 ⇒ 删除该发包方
   （复用页面同源 ``delete_issuer``：名下仍有承包方 / 批次已结束时该行报错拦截）；
5. 落库同源：新增复用 ``create_issuer``、更新复用 ``update_issuer``、
   删除复用 ``delete_issuer``，与页面按钮走同一套闸门。

⛔ 导出时发包方编码按**文本**写入（与承包方编号同一口径），导入读到数值型
编码只能尽力取整——模板必须用系统导出的文件改。
"""
from __future__ import annotations

import io
import logging

import xlrd
import xlwt
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.survey import SurveyFbfResult
from app.models.user import User
from app.services.data_access_service import data_access_service
from app.services.survey.excel_transfer import (
    _cell,
    _member_delete_marked,
    _parse_date_cell,
    _raw_cell,
)

logger = logging.getLogger(__name__)

ISSUER_XLS_TITLE = "农村土地承包经营权发包方调查表"
ISSUER_ID_TYPE_LABELS = {"1": "居民身份证"}
ISSUER_ID_TYPE_CODES = {v: k for k, v in ISSUER_ID_TYPE_LABELS.items()}
_DEFAULT_ID_TYPE = "1"

# (SurveyFbfResult 列名, 规范化数据 key, 标签) —— 差异比对与预览展示共用
_ISSUER_FIELD_MAP = [
    ("fbfmc", "name", "发包方名称"),
    ("fbffzrxm", "responsibleName", "负责人姓名"),
    ("lxdh", "phone", "联系电话"),
    ("fbfdz", "address", "发包方地址"),
    ("yzbm", "postcode", "邮政编码"),
    ("fzrzjlx", "responsibleIdType", "证件类型"),
    ("fzrzjhm", "responsibleIdNo", "证件号码"),
    ("fbfdcy", "surveyorName", "调查员"),
    ("fbfdcjs", "surveyNote", "调查记事"),
    ("remark", "remark", "备注"),
]

ISSUER_IMPORT_CHANGE_REASON = "发包方调查表（Excel）导入更新"


class SurveyServiceIssuerExcelTransferMixin:
    # ── 导出 ────────────────────────────────────────────────────────────────

    def export_issuers_xls(self, db: Session, batch_id: int, current_user: User) -> tuple[str, bytes]:
        """导出本批次的发包方清单（口径与批次面板「本批次发包方清单」一致）。

        发包方数量少（一个村通常一两个），走同步导出即可，无需后台任务。
        """
        batch = self._ensure_batch(db, batch_id)
        normalized_region_code = data_access_service.normalize_region_code(batch.region_code)
        if normalized_region_code:
            data_access_service.ensure_region_filter_in_scope(
                current_user, normalized_region_code, detail="当前批次区域不在可导出范围内"
            )

        filters = self._tenant_filters(SurveyFbfResult, current_user)
        if normalized_region_code:
            if len(normalized_region_code) >= 14:
                filters.append(SurveyFbfResult.fbfbm == normalized_region_code[:14])
            else:
                filters.append(SurveyFbfResult.fbfbm.like(f"{normalized_region_code}%"))
        issuers = db.scalars(
            select(SurveyFbfResult)
            .where(*filters)
            .order_by(SurveyFbfResult.fbfbm.asc(), SurveyFbfResult.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).all()

        rows = [self._issuer_export_row(item) for item in issuers]
        wb = self._build_issuer_workbook(rows)
        safe_name = (batch.region_name or batch.batch_no or f"batch_{batch_id}").replace("/", "_").replace("\\", "_")
        filename = f"发包方调查表_{safe_name}.xls"
        buffer = io.BytesIO()
        wb.save(buffer)
        logger.info(
            "发包方调查表导出 batch_id=%s 行数=%s 操作人=%s",
            batch_id, len(rows), getattr(current_user, "username", None),
        )
        return filename, buffer.getvalue()

    @staticmethod
    def _issuer_export_row(item: SurveyFbfResult) -> dict:
        return {
            "code": item.fbfbm or "",
            "name": item.fbfmc or "",
            "responsible_name": item.fbffzrxm or "",
            "mobile": item.lxdh or "",
            "address": item.fbfdz or "",
            "postcode": item.yzbm or "",
            "id_type": ISSUER_ID_TYPE_LABELS.get(item.fzrzjlx, item.fzrzjlx or ""),
            "id_no": item.fzrzjhm or "",
            "surveyor": item.fbfdcy or "",
            "survey_date": item.fbfdcrq.date().isoformat() if item.fbfdcrq else "",
            "survey_note": item.fbfdcjs or "",
            "remark": item.remark or "",
        }

    @staticmethod
    def _build_issuer_workbook(rows: list[dict]):
        headers = [
            "发包方编码", "发包方名称", "发包方负责人姓名", "发包方负责人联系电话",
            "发包方负责人地址", "邮政编码", "发包方负责人证件类型", "发包方负责人证件号码",
            "调查员", "调查日期", "调查记事", "审核人", "审核日期", "审核意见", "备注", "社会信用代码",
        ]
        widths = [16, 26, 12, 14, 32, 8, 14, 20, 14, 12, 32, 10, 12, 12, 18, 20]
        field_keys = [
            "code", "name", "responsible_name", "mobile", "address", "postcode",
            "id_type", "id_no", "surveyor", "survey_date", "survey_note",
            None, None, None, "remark", None,
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
        ws = wb.add_sheet("鱼鳞图")
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
                value = row.get(key) if key else ""
                # ⛔ 编码必须是文本：数值型在 Excel 里显示成科学计数法，
                #    且用户另存/复制后可能丢精度导致导入匹配不上
                ws.write(r, c, value, style(wrap=key == "survey_note"))
            r += 1
        # 合计行（与样例模板一致；导入时按此跳过）
        ws.write(r, 0, "合计", style())
        for c in range(1, ncols):
            ws.write(r, c, "\\", style())
        return wb

    # ── 解析 ────────────────────────────────────────────────────────────────

    @staticmethod
    def parse_issuers_xls(content: bytes) -> tuple[list[dict], list[str]]:
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
                "remark": _cell(sh, r, 14),
                # 删除标记：「发包方名称」单元格底色填充或删除线 ⇒ 删除该发包方
                "delete_marked": _member_delete_marked(sh, r, 1),
            })
        return rows, warnings

    # ── 归一化 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_issuer_row(row: dict) -> tuple[dict | None, list[str]]:
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
        # 删除标记行（「发包方名称」底色/删除线）：只要求编码定位得到行，
        # 必填口径（与承包户导入同源）：「空单元格不覆盖库值」——
        # 更新场景下负责人/证件号/地址为空不报错、保留库值；只有**新增**行才要求填全
        # （在 _plan_issuer 的 create 分支拦截）。删除标记行更是只要求编码能定位到行。
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
        if not id_type:
            id_type = _DEFAULT_ID_TYPE

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
            "remark": (row.get("remark") or "").strip(),
            "delete_marked": bool(row.get("delete_marked")),
            "_missingRequired": missing_required,
        }
        return (data if not errors else None), errors

    # ── 匹配与计划 ──────────────────────────────────────────────────────────

    def _find_issuer_by_code(self, db: Session, tenant_code: str, code: str) -> SurveyFbfResult | None:
        return db.scalars(
            select(SurveyFbfResult)
            .where(
                SurveyFbfResult.tenant_code == tenant_code,
                SurveyFbfResult.fbfbm == code,
            )
            .order_by(SurveyFbfResult.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).first()

    def _ensure_issuer_code_in_import_region(self, batch, code: str, errors: list[str]) -> None:
        """发包方编码与批次区域的隶属校验 —— 与 create/update 的 HTTPException 口径一致。"""
        region_code = (batch.region_code or "").strip()
        if not region_code:
            return
        if len(region_code) >= 14 and code != region_code[:14]:
            errors.append(f"编码必须等于批次区域码「{region_code[:14]}」")
        elif len(region_code) < 14 and not code.startswith(region_code):
            errors.append(f"编码必须以批次区域码「{region_code}」开头")

    def _plan_issuer(self, db: Session, batch, data: dict) -> dict:
        """单行计划：匹配、差异对比。返回 plan dict（含 errors 则不可导入）。"""
        errors: list[str] = []
        warnings: list[str] = []
        code = data["code"]

        self._ensure_issuer_code_in_import_region(batch, code, errors)

        existing = self._find_issuer_by_code(db, batch.tenant_code, code) if code and not errors else None

        base = {
            "code": code,
            "name": data["name"],
            "rowIndex": data["rowIndex"],
            "errors": errors,
            "warnings": warnings,
        }

        # 删除标记（「发包方名称」单元格底色/删除线）：
        # 复用页面「删除发包方」同源 delete_issuer（名下有承包方会被闸门拦下）。
        if data.get("delete_marked"):
            if existing is None:
                base.update({"action": "skipped", "message": "标记删除的发包方在库内不存在，忽略"})
                return base
            if errors:
                base["action"] = "error"
                return base
            contractor_codes = self._issuer_contractor_codes(db, existing.tenant_code, existing.fbfbm)
            if contractor_codes:
                base["action"] = "error"
                errors.append(f"该发包方下存在 {len(contractor_codes)} 个承包方，不允许删除；请先在承包方管理中移走")
                return base
            base.update({"action": "delete", "issuerUid": existing.issuer_uid})
            return base

        if existing is None:
            if errors:
                base["action"] = "error"
                return base
            # 新增行才要求必填齐全（更新行走「空单元格不覆盖库值」口径）
            if data.get("_missingRequired"):
                base["action"] = "error"
                errors.append(f"新增发包方缺少必填项：{'、'.join(data['_missingRequired'])}")
                return base
            base.update({
                "action": "create",
                "issuerUid": None,
                "changes": ["新增发包方"],
                "_payload": self._issuer_import_payload(data, None),
            })
            return base

        if existing.survey_status in self.locked_survey_statuses:
            base.update({"action": "skipped", "message": "调查成果已确认，自动跳过"})
            return base

        changes: list[str] = []
        for column, data_key, label in _ISSUER_FIELD_MAP:
            new_value = data.get(data_key) or ""
            if new_value and str(new_value) != str(getattr(existing, column) or ""):
                changes.append(label)
        new_date = data.get("surveyDate") or ""
        old_date = existing.fbfdcrq.date().isoformat() if existing.fbfdcrq else ""
        if new_date and new_date != old_date:
            changes.append("调查日期")

        if errors:
            base["action"] = "error"
            return base
        if not changes:
            base.update({"action": "no_change", "issuerUid": existing.issuer_uid, "changes": []})
            return base
        payload = self._issuer_import_payload(data, existing)
        base.update({"action": "update", "issuerUid": existing.issuer_uid, "changes": changes, "_payload": payload})
        return base

    @staticmethod
    def _issuer_import_payload(data: dict, existing: SurveyFbfResult | None) -> dict:
        """Excel 行 → create_issuer / update_issuer 的 payload（与页面保存同源）。

        ⛔ 与承包户导入同口径：**空单元格不覆盖库值**——更新场景下空字段不进
        payload（update_issuer 是整字段赋值，payload 缺哪个就保留库值哪个）；
        新增行的必填已在 plan 里拦截，这里字段必然齐全。
        """
        payload = {"code": data["code"]}
        optional_fields = [
            ("name", "name"),
            ("responsibleName", "responsibleName"),
            ("responsibleIdType", "responsibleIdType"),
            ("responsibleIdNo", "responsibleIdNo"),
            ("phone", "phone"),
            ("address", "address"),
            ("postcode", "postcode"),
            ("surveyorName", "surveyorName"),
            ("surveyNote", "surveyNote"),
            ("remark", "remark"),
        ]
        for payload_key, data_key in optional_fields:
            value = (data.get(data_key) or "").strip() if isinstance(data.get(data_key), str) else data.get(data_key)
            if value:
                payload[payload_key] = value
        if data.get("surveyDate"):
            payload["surveyDate"] = data["surveyDate"]
        if existing is not None:
            # 更新时回填既有的簿记字段：页面编辑也是整体回传这些值，
            # 导入不该把 change_type / result_status 冲掉
            payload["resultStatus"] = existing.result_status
            payload["changeType"] = existing.change_type
            payload["changeReason"] = existing.change_reason or ISSUER_IMPORT_CHANGE_REASON
            payload["issuerUid"] = existing.issuer_uid
        return payload

    # ── 预览 ────────────────────────────────────────────────────────────────

    def preview_issuers_xls_import(self, db: Session, batch_id: int, current_user: User, content: bytes) -> dict:
        batch = self._ensure_batch(db, batch_id)
        rows, warnings = self.parse_issuers_xls(content)
        if batch.status == "finished":
            warnings.insert(0, "该调查批次已结束，导入将被拒绝")
        plans: list[dict] = []
        summary = {"create": 0, "update": 0, "no_change": 0, "skipped": 0, "error": 0, "delete": 0}
        for row in rows:
            data, errors = self._normalize_issuer_row(row)
            if data is None:
                plan = {
                    "code": row.get("code") or "", "name": row.get("name") or "",
                    "rowIndex": row.get("rowIndex"), "action": "error",
                    "errors": errors, "warnings": [], "changes": [],
                }
            else:
                try:
                    # 数据权限：与页面编辑同口径（ensure_code_in_scope），越权行报 error
                    data_access_service.ensure_code_in_scope(current_user, data["code"], detail="发包方不在当前数据权限范围内")
                    plan = self._plan_issuer(db, batch, data)
                except HTTPException as exc:
                    plan = {
                        "code": data["code"], "name": data["name"],
                        "rowIndex": data["rowIndex"], "action": "error",
                        "errors": [str(exc.detail)], "warnings": [], "changes": [],
                    }
            plan.pop("_payload", None)
            summary[plan["action"]] = summary.get(plan["action"], 0) + 1
            plans.append(plan)
        return {
            "batchId": batch_id,
            "batchRegionCode": batch.region_code,
            "totalRows": len(plans),
            "summary": summary,
            "warnings": warnings,
            "issuers": plans,
        }

    # ── 导入 ────────────────────────────────────────────────────────────────

    def import_issuers_xls(self, db: Session, batch_id: int, current_user: User, content: bytes) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=400, detail="调查批次已结束，不能导入")
        rows, warnings = self.parse_issuers_xls(content)
        results: list[dict] = []
        summary = {"created": 0, "updated": 0, "no_change": 0, "skipped": 0, "failed": 0, "deleted": 0}

        for row in rows:
            data, errors = self._normalize_issuer_row(row)
            if data is None:
                summary["failed"] += 1
                results.append({
                    "code": row.get("code") or "", "name": row.get("name") or "",
                    "rowIndex": row.get("rowIndex"), "status": "failed", "message": "；".join(errors),
                })
                continue
            try:
                data_access_service.ensure_code_in_scope(current_user, data["code"], detail="发包方不在当前数据权限范围内")
                plan = self._plan_issuer(db, batch, data)
                if plan["errors"]:
                    raise HTTPException(status_code=400, detail="；".join(plan["errors"]))
                result_row = self._apply_issuer_plan(db, batch_id, plan, current_user)
                summary[result_row["status"]] = summary.get(result_row["status"], 0) + 1
                results.append(result_row)
            except HTTPException as exc:
                db.rollback()
                summary["failed"] += 1
                results.append({
                    "code": data["code"], "name": data["name"],
                    "rowIndex": data["rowIndex"], "status": "failed", "message": str(exc.detail),
                })
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                logger.exception("发包方调查表导入单行失败 code=%s", data.get("code"))
                summary["failed"] += 1
                results.append({
                    "code": data["code"], "name": data["name"],
                    "rowIndex": data["rowIndex"], "status": "failed", "message": f"导入异常：{exc}",
                })
        logger.info(
            "发包方调查表导入完成 batch_id=%s 结果=%s 操作人=%s",
            batch_id, summary, getattr(current_user, "username", None),
        )
        return {
            "batchId": batch_id,
            "totalRows": len(results),
            "summary": summary,
            "warnings": warnings,
            "issuers": results,
        }

    def _apply_issuer_plan(self, db: Session, batch_id: int, plan: dict, current_user: User) -> dict:
        """把单行计划落库：与页面按钮同源（create/update/delete_issuer），逐行提交。"""
        base = {"code": plan["code"], "name": plan["name"], "rowIndex": plan["rowIndex"]}
        if plan["action"] == "skipped":
            return {**base, "status": "skipped", "message": plan.get("message") or "已跳过"}
        if plan["action"] == "no_change":
            return {**base, "status": "no_change", "message": "数据无变化"}
        if plan["action"] == "delete":
            self.delete_issuer(db, batch_id, plan["issuerUid"], current_user)
            return {**base, "status": "deleted", "message": "已删除（Excel 标记）"}
        payload = plan.get("_payload") or {}
        if plan["action"] == "create":
            created = self.create_issuer(db, batch_id, payload, current_user)
            return {**base, "status": "created", "message": "新增发包方", "issuerUid": created.get("issuerUid")}
        # update
        changes = plan.get("changes") or []
        self.update_issuer(db, batch_id, plan["issuerUid"], payload, current_user)
        return {**base, "status": "updated", "message": f"更新：{'、'.join(changes)}"}
