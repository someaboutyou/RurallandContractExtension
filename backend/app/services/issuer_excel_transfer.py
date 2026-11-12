# -*- coding: utf-8 -*-
"""发包方调查表 Excel 导入 / 导出（发包方管理页）。

与批次内的 ``services/survey/issuer_excel_transfer.py`` 使用同一套
Excel 版式与解析规则，区别在于本服务操作的是发包方主表 ``fbf``：
- 导出按当前查询关键字 + 数据权限范围取数；
- 导入按 14 位发包方编码匹配，库内存在则更新、不存在则新增；
- 「发包方名称」单元格填充底色或加删除线 ⇒ 删除该发包方
  （复用 ``issuer_service.delete_issuer`` 的删除闸门，名下有承包方时拦截）。
"""

from __future__ import annotations

import io
import logging
import re

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.fbf import Fbf
from app.models.user import User
from app.services.data_access_service import data_access_service
from app.services.issuer_service import issuer_service
from app.services.survey.issuer_excel_transfer import (
    DEFAULT_ID_TYPE,
    ISSUER_ID_TYPE_LABELS,
    IssuerXlsTemplate,
)

logger = logging.getLogger(__name__)

# 对比字段：(Fbf 列名, 导入数据 key, 展示标签)
_FIELD_MAP = [
    ("fbfmc", "name", "发包方名称"),
    ("fbffzrxm", "responsibleName", "负责人姓名"),
    ("lxdh", "phone", "联系电话"),
    ("fbfdz", "address", "发包方地址"),
    ("yzbm", "postcode", "邮政编码"),
    ("fzrzjlx", "responsibleIdType", "证件类型"),
    ("fzrzjhm", "responsibleIdNo", "证件号码"),
    ("fbfdcy", "surveyorName", "调查员"),
    ("fbfdcjs", "surveyNote", "调查记事"),
    ("tyshxydm", "creditCode", "统一社会信用代码"),
    ("shr", "auditor", "审核人"),
    ("shyj", "auditOpinion", "审核意见"),
    ("bzxx", "remark", "备注"),
]

_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|]')


class IssuerExcelTransferService:
    # ── 导出 ────────────────────────────────────────────────────────────────

    def export_xls(
        self,
        db: Session,
        current_user: User,
        *,
        keyword: str | None = None,
        batch_codes: list[str] | None = None,
        region_code: str | None = None,
        selected_codes: list[str] | None = None,
    ) -> tuple[str, bytes]:
        """导出当前数据权限 + 查询关键字下的发包方清单（可再按批次/区域过滤）。

        ``region_code`` 为数据中心口径：按发包方编码前缀（省县镇村组码）收敛范围，
        为空即整库（数据权限仍生效）。
        ``selected_codes`` 为数据中心「已选数据」口径：按勾选的发包方编码精确导出，
        优先于 batch_codes / region_code / keyword。
        """
        filters = data_access_service.build_code_scope_filters(Fbf.fbfbm, current_user)
        if selected_codes is not None:
            # 勾选清单为空时也给出带表头的空文件，而不是损坏的响应。
            filters.append(Fbf.fbfbm.in_(selected_codes or [""]))
        elif batch_codes is not None:
            # 批次内无发包方时也要给出带表头的空文件，而不是损坏的响应。
            filters.append(Fbf.fbfbm.in_(batch_codes or [""]))
        if region_code and region_code.strip():
            filters.append(Fbf.fbfbm.like(f"{region_code.strip()}%"))
        stmt = select(Fbf).where(*filters)
        if keyword and keyword.strip():
            pattern = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    Fbf.fbfbm.ilike(pattern),
                    Fbf.fbfmc.ilike(pattern),
                    Fbf.fbffzrxm.ilike(pattern),
                    Fbf.fzrzjhm.ilike(pattern),
                    Fbf.lxdh.ilike(pattern),
                )
            )
        issuers = list(db.scalars(stmt.order_by(Fbf.fbfbm.asc())).all())
        rows = [self._export_row(item) for item in issuers]
        workbook = IssuerXlsTemplate.build_workbook(rows)
        buffer = io.BytesIO()
        workbook.save(buffer)

        filename = "发包方调查表.xls"
        if selected_codes is not None:
            filename = f"发包方清单_已选{len(selected_codes)}户.xls"
        elif region_code and region_code.strip():
            filename = f"发包方清单_{_UNSAFE_FILENAME.sub('_', region_code.strip())}.xls"
        if keyword and keyword.strip():
            filename = f"发包方调查表_{_UNSAFE_FILENAME.sub('_', keyword.strip())}.xls"
        logger.info(
            "发包方管理导出 Excel 行数=%s 操作人=%s",
            len(rows),
            getattr(current_user, "username", None),
        )
        return filename, buffer.getvalue()

    @staticmethod
    def _export_row(item: Fbf) -> dict:
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
            "auditor": item.shr or "",
            "audit_date": item.shrq.date().isoformat() if item.shrq else "",
            "audit_opinion": item.shyj or "",
            "remark": item.bzxx or "",
            "credit_code": item.tyshxydm or "",
        }

    # ── 预览 ────────────────────────────────────────────────────────────────

    def preview_xls(
        self,
        db: Session,
        current_user: User,
        content: bytes,
    ) -> dict:
        rows, warnings = IssuerXlsTemplate.parse(content)
        plans: list[dict] = []
        summary = {"create": 0, "update": 0, "no_change": 0, "delete": 0, "error": 0}

        for row in rows:
            data, errors = IssuerXlsTemplate.normalize_row(row)
            if data is None:
                plan = self._error_plan(row, errors)
            else:
                try:
                    data_access_service.ensure_code_in_scope(
                        current_user,
                        data["code"],
                        detail="发包方不在当前数据权限范围内",
                    )
                    plan = self._plan_issuer(db, data)
                except HTTPException as exc:
                    plan = self._error_plan(data, [str(exc.detail)])
            plan.pop("_payload", None)
            summary[plan["action"]] = summary.get(plan["action"], 0) + 1
            plans.append(plan)

        return {
            "totalRows": len(plans),
            "summary": summary,
            "warnings": warnings,
            "issuers": plans,
        }

    @staticmethod
    def _error_plan(row: dict, errors: list[str]) -> dict:
        return {
            "code": row.get("code") or "",
            "name": row.get("name") or "",
            "rowIndex": row.get("rowIndex"),
            "action": "error",
            "errors": errors,
            "warnings": [],
            "changes": [],
        }

    def _plan_issuer(self, db: Session, data: dict) -> dict:
        code = data["code"]
        existing = db.get(Fbf, code)
        base = {
            "code": code,
            "name": data.get("name") or "",
            "rowIndex": data.get("rowIndex"),
            "errors": [],
            "warnings": [],
        }

        if data.get("delete_marked"):
            if existing is None:
                return {**base, "action": "error", "errors": ["发包方不存在，无法删除"], "changes": []}
            contractor_count = issuer_service.count_related_contractors(db, code)
            if contractor_count:
                return {
                    **base,
                    "action": "error",
                    "errors": [f"该发包方下存在 {contractor_count} 个承包方，不能删除"],
                    "changes": [],
                }
            return {**base, "action": "delete", "changes": ["删除该发包方"]}

        if existing is None:
            missing = data.get("_missingRequired") or []
            if missing:
                return {
                    **base,
                    "action": "error",
                    "errors": ["新增发包方缺少：" + "、".join(missing)],
                    "changes": [],
                }
            return {
                **base,
                "action": "create",
                "changes": ["新增发包方"],
                "_payload": self._create_payload(data),
            }

        changes = self._diff(existing, data)
        if not changes:
            return {**base, "action": "no_change", "changes": []}
        return {
            **base,
            "action": "update",
            "changes": changes,
            "_payload": self._update_payload(existing, data),
        }

    @staticmethod
    def _diff(existing: Fbf, data: dict) -> list[str]:
        changes: list[str] = []
        for attr, key, label in _FIELD_MAP:
            imported = (data.get(key) or "").strip()
            if not imported:
                continue
            current = getattr(existing, attr, "") or ""
            if key == "responsibleIdType":
                if imported != str(current):
                    changes.append(
                        f"{label}：{ISSUER_ID_TYPE_LABELS.get(current, current)} → "
                        f"{ISSUER_ID_TYPE_LABELS.get(imported, imported)}"
                    )
                continue
            if str(imported) != str(current):
                changes.append(f"{label}：{current or '空'} → {imported}")

        imported_date = (data.get("surveyDate") or "").strip()
        if imported_date:
            current_date = existing.fbfdcrq.date().isoformat() if existing.fbfdcrq else ""
            if imported_date != current_date:
                changes.append(f"调查日期：{current_date or '空'} → {imported_date}")

        imported_audit_date = (data.get("auditDate") or "").strip()
        if imported_audit_date:
            current_audit_date = existing.shrq.date().isoformat() if existing.shrq else ""
            if imported_audit_date != current_audit_date:
                changes.append(f"审核日期：{current_audit_date or '空'} → {imported_audit_date}")
        return changes

    @staticmethod
    def _create_payload(data: dict) -> dict:
        return {
            "code": data["code"],
            "name": data["name"],
            "ownerName": data["responsibleName"],
            "ownerIdType": data["responsibleIdType"] or DEFAULT_ID_TYPE,
            "ownerIdNo": data["responsibleIdNo"],
            "mobile": data.get("phone") or None,
            "address": data["address"],
            "postcode": data.get("postcode") or "000000",
            "surveyorName": data.get("surveyorName") or "",
            "surveyDate": data.get("surveyDate") or None,
            "notes": data.get("surveyNote") or None,
            "creditCode": data.get("creditCode") or None,
            "auditor": data.get("auditor") or None,
            "auditDate": data.get("auditDate") or None,
            "auditOpinion": data.get("auditOpinion") or None,
            "remark": data.get("remark") or None,
        }

    @staticmethod
    def _update_payload(existing: Fbf, data: dict) -> dict:
        return {
            "code": existing.fbfbm,
            "name": data.get("name") or existing.fbfmc,
            "ownerName": data.get("responsibleName") or existing.fbffzrxm,
            "ownerIdType": data.get("responsibleIdType") or existing.fzrzjlx,
            "ownerIdNo": data.get("responsibleIdNo") or existing.fzrzjhm,
            "mobile": data.get("phone") or existing.lxdh,
            "address": data.get("address") or existing.fbfdz,
            "postcode": data.get("postcode") or existing.yzbm,
            "surveyorName": data.get("surveyorName") or existing.fbfdcy,
            "surveyDate": data.get("surveyDate")
            or (existing.fbfdcrq.date().isoformat() if existing.fbfdcrq else None),
            "notes": data.get("surveyNote") or existing.fbfdcjs,
            "creditCode": data.get("creditCode") or existing.tyshxydm,
            "auditor": data.get("auditor") or existing.shr,
            "auditDate": data.get("auditDate")
            or (existing.shrq.date().isoformat() if existing.shrq else None),
            "auditOpinion": data.get("auditOpinion") or existing.shyj,
            "remark": data.get("remark") or existing.bzxx,
        }

    # ── 导入 ────────────────────────────────────────────────────────────────

    def import_xls(
        self,
        db: Session,
        current_user: User,
        content: bytes,
    ) -> dict:
        rows, warnings = IssuerXlsTemplate.parse(content)
        results: list[dict] = []
        summary = {
            "created": 0,
            "updated": 0,
            "no_change": 0,
            "deleted": 0,
            "failed": 0,
        }

        for row in rows:
            base = {
                "code": row.get("code") or "",
                "name": row.get("name") or "",
                "rowIndex": row.get("rowIndex"),
            }
            try:
                data, errors = IssuerXlsTemplate.normalize_row(row)
                if data is None:
                    raise HTTPException(status_code=400, detail="；".join(errors))
                data_access_service.ensure_code_in_scope(
                    current_user,
                    data["code"],
                    detail="发包方不在当前数据权限范围内",
                )
                plan = self._plan_issuer(db, data)
                if plan["errors"]:
                    raise HTTPException(status_code=400, detail="；".join(plan["errors"]))
                status, message = self._apply_plan(db, plan, current_user)
                summary[status] = summary.get(status, 0) + 1
                results.append({**base, "status": status, "message": message})
            except HTTPException as exc:
                db.rollback()
                summary["failed"] += 1
                results.append({**base, "status": "failed", "message": str(exc.detail)})
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                logger.exception("发包方管理导入单行失败 code=%s", row.get("code"))
                summary["failed"] += 1
                results.append({**base, "status": "failed", "message": f"导入异常：{exc}"})

        logger.info(
            "发包方管理导入完成 结果=%s 操作人=%s",
            summary,
            getattr(current_user, "username", None),
        )
        return {
            "totalRows": len(results),
            "summary": summary,
            "warnings": warnings,
            "issuers": results,
        }

    def _apply_plan(self, db: Session, plan: dict, current_user: User) -> tuple[str, str]:
        action = plan["action"]
        code = plan["code"]
        if action == "no_change":
            return "no_change", "数据无变化"
        if action == "delete":
            issuer_service.delete_issuer(db, code, current_user)
            return "deleted", "已删除（Excel 标记）"
        payload = plan.get("_payload") or {}
        if action == "create":
            issuer_service.create_issuer(db, payload, current_user)
            return "created", "新增发包方"
        issuer_service.update_issuer(db, code, payload, current_user)
        return "updated", f"更新：{'、'.join(plan.get('changes') or [])}"


issuer_excel_transfer_service = IssuerExcelTransferService()
