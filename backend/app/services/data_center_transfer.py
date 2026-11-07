# -*- coding: utf-8 -*-
"""数据中心（无批次）清单导出 / 导入服务。

与建库中心的分工：
- 公共层（``survey/excel_transfer.py``）：模板解析、码值归一化、成员差异比对、
  户主唯一化、调查表工作簿构建——两条链路共用，不复制。
- 本模块只放数据中心的具体分支：
  - 导出：直接查主表成果（survey_cbf_result 等），按区域前缀收敛；承包方清单
    支持「整体一个 xls」与「按发包方分组、每村一个 xls 打包 zip」两种模式。
  - 导入：按承包方编号匹配主表，**仅更新已有数据**（不建新户——新增涉及批次
    快照与编号段分配，必须走建库中心批次流程）。
"""
from __future__ import annotations

import io
import logging
import zipfile
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.survey import SurveyCbfJtcyResult, SurveyCbfResult
from app.models.user import User
from app.services.data_access_service import data_access_service
from app.services.relation_codes import relation_labels

logger = logging.getLogger(__name__)

_UNSAFE_FILENAME = __import__("re").compile(r"[\\/:*?\"<>|]")
_DC_MEMBER_CHANGE_REASON = "数据中心清单导入"
_DC_IMPORT_CHANGE_REASON = "数据中心清单导入"


def _safe_name(value: str) -> str:
    return _UNSAFE_FILENAME.sub("_", value or "").strip() or "未命名"


class DataCenterTransferService:
    """数据中心清单导入导出（建库中心走 survey_service / issuer_excel_transfer）。"""

    # ── 承包方清单导出 ──────────────────────────────────────────────────────

    def export_contractor_xls(
        self,
        db: Session,
        current_user: User,
        *,
        region_code: str | None = None,
        mode: str = "single",  # single=整体一个 xls | group=按发包方分组打包 zip
        progress_cb=None,
    ) -> tuple[str, bytes]:
        """region_code 为空即整库（数据权限仍生效）。返回 (文件名, 字节)。"""
        from app.services.survey import survey_service

        prefix = (region_code or "").strip()
        if prefix:
            data_access_service.ensure_region_filter_in_scope(
                current_user, prefix, detail="所选区域不在当前数据权限范围内"
            )

        def report(done: int, total: int, phase: str, current: str = "") -> None:
            if progress_cb is not None:
                try:
                    progress_cb(done, total, phase, current)
                except Exception:  # noqa: BLE001
                    pass

        filters = survey_service._tenant_filters(SurveyCbfResult, current_user)
        filters.append(SurveyCbfResult.result_status != "cancelled")
        if prefix:
            # 承包方编码 18 位 = 组码(14) + 户号(4)，区域任一层级用前缀收敛
            filters.append(SurveyCbfResult.cbfbm.like(f"{prefix}%"))
        results = db.scalars(
            select(SurveyCbfResult)
            .where(*filters)
            .order_by(SurveyCbfResult.cbfbm.asc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        report(0, len(results), "读取家庭成员")

        members_by_uid: dict[str, list] = {}
        uids = [row.contractor_uid for row in results]
        if uids:
            member_rows = db.scalars(
                select(SurveyCbfJtcyResult)
                .where(
                    SurveyCbfJtcyResult.contractor_uid.in_(uids),
                    *survey_service._tenant_filters(SurveyCbfJtcyResult, current_user),
                )
                .execution_options(skip_tenant_scope=True)
            ).all()
            for member in member_rows:
                members_by_uid.setdefault(member.contractor_uid, []).append(member)

        labels = relation_labels(db)
        households = []
        for idx, result in enumerate(results):
            # base 传 result 自身：行构建器的 task 只作缺省兜底，result 恒存在
            households.append(
                survey_service._household_export_row(
                    result, result, members_by_uid.get(result.contractor_uid) or [], labels
                )
            )
            report(idx + 1, len(results), "组装清单数据", result.cbfmc or result.cbfbm)
        report(len(results), len(results), "生成文件")

        scope_label = _safe_name(prefix) if prefix else "整库"
        if mode == "group":
            return self._build_grouped_zip(households, scope_label)
        wb = survey_service._build_template_workbook(scope_label, households)
        buffer = io.BytesIO()
        wb.save(buffer)
        filename = f"承包方清单_{scope_label}.xls"
        logger.info(
            "数据中心承包方清单导出 region=%s 户数=%s 模式=%s 操作人=%s",
            prefix or "整库", len(households), mode, getattr(current_user, "username", None),
        )
        return filename, buffer.getvalue()

    def _build_grouped_zip(self, households: list[dict], scope_label: str) -> tuple[str, bytes]:
        """按发包方（组码 = 承包方编码前 14 位）分组，每组一个 xls，打包 zip。"""
        from app.services.survey import survey_service

        groups: dict[str, list[dict]] = {}
        for row in households:
            code = str(row.get("cbfbm") or "")
            groups.setdefault(code[:14] or "未知发包方", []).append(row)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for group_code, group_rows in sorted(groups.items()):
                # 组名取首户的 group_region_name（构建行时未带出，用编码兜底）
                group_label = _safe_name(group_rows[0].get("groupRegionName") or group_code)
                wb = survey_service._build_template_workbook(group_label, group_rows)
                inner = io.BytesIO()
                wb.save(inner)
                zf.writestr(f"承包方清单_{group_label}_{group_code}.xls", inner.getvalue())
        filename = f"承包方清单_{scope_label}_按发包方分组.zip"
        return filename, buffer.getvalue()

    # ── 承包方清单导入（仅更新已有数据）────────────────────────────────────

    def preview_contractor_xls_import(self, db: Session, current_user: User, content: bytes) -> dict:
        from app.services.survey import survey_service

        blocks, warnings = survey_service.parse_contractors_xls(content)
        households: list[dict] = []
        summary = {"update": 0, "no_change": 0, "skipped": 0, "error": 0, "deleted": 0}
        for block in blocks:
            normalized, errors = survey_service._normalize_household(block, db)
            if normalized is None:
                plan = {
                    "cbfbm": block.get("cbfbm") or "", "cbfmc": block.get("cbfmc") or "",
                    "rowIndex": block.get("rowIndex"), "action": "error",
                    "errors": errors, "warnings": [], "contractorChanges": [],
                    "memberSummary": {"added": [], "updated": [], "deleted": []},
                }
            else:
                try:
                    plan = self._plan_household_db(db, current_user, normalized)
                except HTTPException as exc:
                    plan = {
                        "cbfbm": normalized["cbfbm"], "cbfmc": normalized["cbfmc"],
                        "rowIndex": normalized["rowIndex"], "action": "error",
                        "errors": [str(exc.detail)], "warnings": [], "contractorChanges": [],
                        "memberSummary": {"added": [], "updated": [], "deleted": []},
                    }
            plan.pop("_payload", None)
            summary[plan["action"]] = summary.get(plan["action"], 0) + 1
            households.append(plan)
        return {
            "regionCode": "",
            "totalHouseholds": len(households),
            "summary": summary,
            "warnings": warnings,
            "households": households,
        }

    def _plan_household_db(self, db: Session, current_user: User, household: dict) -> dict:
        """数据中心单户计划：按承包方编号匹配主表，仅更新已有数据。"""
        from app.repositories.contractor_repository import contractor_repository
        from app.services.contractor_service import contractor_service
        from app.services.survey import survey_service

        errors: list[str] = []
        warnings: list[str] = []
        code = household["cbfbm"]

        result = contractor_repository.get_contractor(db, code)
        if result is None:
            return self._plan_base(code, household, action="error", errors=[
                "库内不存在该承包方编号（数据中心导入仅更新已有数据，新增请走建库中心批次流程）"
            ])
        if result.is_locked:
            return self._plan_base(code, household, action="skipped", message="承包方已锁定，自动跳过")
        if result.result_status == "cancelled":
            return self._plan_base(code, household, action="skipped", message="该户已注销，自动跳过")

        if household.get("household_delete_marked"):
            return self._plan_base(
                code, household, action="deleted",
                message="整户删除（Excel 标记，数据中心为物理删除且不可撤回）",
            )

        detail = contractor_service.get_contractor(db, code, current_user)

        # 公共成员差异比对（与建库中心批次导入同源）
        diff = survey_service._diff_members_for_import(
            list(detail.get("familyMembers") or []),
            household["members"],
            member_change_reason=_DC_MEMBER_CHANGE_REASON,
        )
        errors.extend(diff["errors"])
        warnings.extend(diff["warnings"])

        # 承包方字段对比（空单元格不覆盖库值，也不借导入清空字段）
        contractor_changes: list[str] = []
        for payload_key, data_key, label in survey_service._CONTRACTOR_FIELD_MAP:
            new_value = household.get(data_key) or ""
            if new_value and str(new_value) != str(detail.get(payload_key) or ""):
                contractor_changes.append(label)
        if household.get("cbflx") and household["cbflx"] != detail.get("typeCode"):
            contractor_changes.append("承包方类型")

        members_payload = diff["members_payload"]
        survey_service._assign_head_flags(members_payload, household["members"])

        has_change = bool(contractor_changes or diff["added"] or diff["updated"] or diff["deleted_names"])
        effective = "update" if has_change else "no_change"

        if not household["cbfmc"]:
            errors.append("承包方姓名为空")

        # payload 全量字段：空单元格用库值兜底（台账写入是整字段覆盖，见 _apply_contractor_payload）
        payload = {
            "code": code,
            "typeCode": household.get("cbflx") or detail.get("typeCode") or "1",
            "name": household.get("cbfmc") or detail.get("name") or "",
            "idType": detail.get("idType") or "1",
            "idNo": detail.get("idNo") or "",
            "address": household.get("address") or detail.get("address") or "",
            "postcode": household.get("postcode") or detail.get("postcode") or "",
            "mobile": household.get("mobile") or detail.get("mobile"),
            "surveyorName": household.get("surveyor") or detail.get("surveyorName") or "",
            "surveyDate": household.get("survey_date") or detail.get("surveyDate"),
            "surveyNote": household.get("survey_note") or detail.get("surveyNote"),
            "publicNoticeNote": household.get("review_note") or detail.get("publicNoticeNote"),
            "publicNoticeReviewDate": household.get("review_date") or detail.get("publicNoticeReviewDate"),
            "publicNoticeReviewer": household.get("reviewer") or detail.get("publicNoticeReviewer"),
            "groupRegionCode": detail.get("groupRegionCode"),
            "groupRegionName": detail.get("groupRegionName"),
            "familyMembers": members_payload,
        }
        return {
            "cbfbm": code,
            "cbfmc": household["cbfmc"],
            "rowIndex": household["rowIndex"],
            "action": effective,
            "errors": errors,
            "warnings": warnings,
            "contractorChanges": contractor_changes,
            "memberSummary": {"added": diff["added"], "updated": diff["updated"], "deleted": diff["deleted_names"]},
            "_payload": payload,
        }

    @staticmethod
    def _plan_base(code: str, household: dict, *, action: str, errors: list[str] | None = None,
                   message: str = "") -> dict:
        plan = {
            "cbfbm": code, "cbfmc": household["cbfmc"], "rowIndex": household["rowIndex"],
            "action": action, "errors": errors or [], "warnings": [],
            "contractorChanges": [], "memberSummary": {"added": [], "updated": [], "deleted": []},
        }
        if message:
            plan["message"] = message
        return plan

    def import_contractors_xls(self, db: Session, current_user: User, content: bytes, progress_cb=None) -> dict:
        """数据中心清单导入：逐户独立提交，单户失败不影响其他户。"""
        from app.services.contractor_service import contractor_service
        from app.services.survey import survey_service

        blocks, warnings = survey_service.parse_contractors_xls(content)
        results: list[dict] = []
        summary = {"updated": 0, "no_change": 0, "skipped": 0, "deleted": 0, "failed": 0}

        def report(done: int, current: str = "") -> None:
            if progress_cb is not None:
                try:
                    progress_cb(done, len(blocks), f"导入第 {done}/{len(blocks)} 户", current)
                except Exception:  # noqa: BLE001
                    pass

        report(0, "解析 Excel")
        for idx, block in enumerate(blocks):
            report(idx, f"{block.get('cbfmc') or block.get('cbfbm') or ''}（第 {block.get('rowIndex') or '?'} 行）")
            normalized, errors = survey_service._normalize_household(block, db)
            if normalized is None:
                summary["failed"] += 1
                results.append({
                    "cbfbm": block.get("cbfbm") or "", "cbfmc": block.get("cbfmc") or "",
                    "rowIndex": block.get("rowIndex"), "status": "failed", "message": "；".join(errors),
                })
                continue
            try:
                plan = self._plan_household_db(db, current_user, normalized)
                if plan["errors"]:
                    raise HTTPException(status_code=400, detail="；".join(plan["errors"]))
                result_row = self._apply_household_plan(db, plan, current_user)
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
                logger.exception("数据中心清单导入单户失败 cbfbm=%s", normalized.get("cbfbm"))
                summary["failed"] += 1
                results.append({
                    "cbfbm": normalized["cbfbm"], "cbfmc": normalized["cbfmc"],
                    "rowIndex": normalized["rowIndex"], "status": "failed",
                    "message": f"导入异常：{exc}",
                })
        logger.info("数据中心清单导入完成 结果=%s 操作人=%s", summary, getattr(current_user, "username", None))
        return {
            "totalHouseholds": len(results),
            "summary": summary,
            "warnings": warnings,
            "households": results,
        }

    def _apply_household_plan(self, db: Session, plan: dict, current_user: User) -> dict:
        """数据中心单户计划落库：走台账同源 CRUD（update/delete），逐户提交回滚。"""
        from app.services.contractor_service import contractor_service

        base = {
            "cbfbm": plan["cbfbm"], "cbfmc": plan["cbfmc"], "rowIndex": plan["rowIndex"],
        }
        if plan["action"] == "skipped":
            return {**base, "status": "skipped", "message": plan.get("message") or "已跳过"}
        if plan["action"] == "no_change":
            return {**base, "status": "no_change", "message": "数据无变化"}
        if plan["action"] == "deleted":
            contractor_service.delete_contractor(db, plan["cbfbm"], current_user)
            return {**base, "status": "deleted", "message": "整户删除（Excel 标记）"}

        contractor_service.update_contractor(db, plan["cbfbm"], plan["_payload"], current_user)
        detail_parts = []
        if plan.get("contractorChanges"):
            detail_parts.append(f"承包方信息（{'、'.join(plan['contractorChanges'])}）")
        member_summary = plan.get("memberSummary") or {}
        if member_summary.get("added"):
            detail_parts.append(f"新增成员 {len(member_summary['added'])} 名")
        if member_summary.get("updated"):
            detail_parts.append(f"修改成员 {len(member_summary['updated'])} 名")
        if member_summary.get("deleted"):
            detail_parts.append(f"删除成员 {len(member_summary['deleted'])} 名（{'、'.join(member_summary['deleted'])}）")
        return {**base, "status": "updated", "message": "；".join(detail_parts) or "已更新"}


data_center_transfer_service = DataCenterTransferService()
