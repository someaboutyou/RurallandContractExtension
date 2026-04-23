from __future__ import annotations

from datetime import datetime
import io
from pathlib import Path
import shutil
import zipfile
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.cbf import Cbf
from app.models.cbht import Cbht
from app.models.fbf import Fbf
from app.models.issuer import Issuer
from app.models.permission import Permission
from app.models.request_case import RequestCase
from app.models.request_case_attachment import RequestCaseAttachment
from app.models.request_case_participant import RequestCaseParticipant
from app.models.role import Role
from app.models.user import User
from app.repositories.request_case_repository import request_case_repository
from app.services.data_access_service import data_access_service
from app.services.request_attachment_template_service import request_attachment_template_service
from app.services.request_workflow_mapping_service import request_workflow_mapping_service
from app.services.workflow_definition_service import workflow_definition_service
from app.services.workflow_service import WorkflowTaskConfig, workflow_service


class RequestCaseService:
    attachment_root = Path(__file__).resolve().parents[2] / "storage" / "request_attachments"
    attachment_template_presets = {
        "首次登记": {
            "apply": [
                ("申请材料", "首次登记申请书", "村组统一申请表或农户书面申请。", "首次登记申请书.docx"),
                ("身份材料", "承包方身份证明", "承包方身份证、户口簿等身份证明扫描件。", "承包方身份证明.pdf"),
                ("权属材料", "承包合同或台账", "现有承包合同、台账、登记簿等权属依据。", "承包合同.pdf"),
                ("调查材料", "权属调查表", "调查指界、四至、面积等基础调查成果。", "权属调查表.xlsx"),
                ("图件材料", "宗地草图或地块示意图", "可用于核对地块范围的一张图资料。", "宗地图.jpg"),
            ],
            "village_review": [
                ("审核材料", "村级审核意见表", "村级审核意见、签字盖章页。", "村级审核意见表.pdf"),
                ("公示材料", "公示照片或公示表", "村级公示留痕材料。", "公示照片.jpg"),
            ],
            "town_review": [
                ("审核材料", "镇级审核意见表", "镇级审核意见、审签单。", "镇级审核意见表.pdf"),
                ("核实材料", "核实记录", "抽查、复核、核实记录。", "核实记录.docx"),
            ],
            "county_review": [
                ("审核材料", "县级审核审批表", "县级审批意见、签发页。", "县级审批表.pdf"),
                ("归档材料", "归档清单", "最终归档材料目录。", "归档清单.xlsx"),
            ],
        },
        "变更登记": {
            "apply": [
                ("申请材料", "变更登记申请书", "变更事项说明及申请。", "变更登记申请书.docx"),
                ("证明材料", "变更依据材料", "继承、分户、流转、纠错等证明材料。", "变更依据材料.pdf"),
                ("身份材料", "相关当事人身份证明", "涉及人员身份证明。", "身份证明.pdf"),
                ("调查材料", "变更调查表", "变更前后权属、面积、四至调查成果。", "变更调查表.xlsx"),
            ],
            "village_review": [
                ("审核材料", "村级变更审核意见", "村级审核意见及证明。", "村级变更审核意见.pdf"),
            ],
            "town_review": [
                ("审核材料", "镇级变更审核意见", "镇级审核意见及核实记录。", "镇级变更审核意见.pdf"),
            ],
            "county_review": [
                ("审核材料", "县级变更审批意见", "县级审批结论。", "县级变更审批意见.pdf"),
            ],
        },
        "注销登记": {
            "apply": [
                ("申请材料", "注销登记申请书", "注销原因及申请。", "注销登记申请书.docx"),
                ("证明材料", "注销依据材料", "收回、灭失、权利终止等依据。", "注销依据材料.pdf"),
            ],
            "county_review": [
                ("审核材料", "县级注销审批表", "注销审批及归档页。", "县级注销审批表.pdf"),
            ],
        },
        "证书补发": {
            "apply": [
                ("申请材料", "补发申请书", "遗失、损毁说明及补发申请。", "补发申请书.docx"),
                ("证明材料", "遗失声明或损毁说明", "遗失声明、公示材料或损毁照片。", "遗失声明.pdf"),
                ("身份材料", "申请人身份证明", "补发申请人身份证明。", "申请人身份证明.pdf"),
            ],
            "county_review": [
                ("审核材料", "补发审批表", "补发审批意见及登记页。", "补发审批表.pdf"),
            ],
        },
    }
    action_labels = {
        "create": "创建申请",
        "update": "修改申请",
        "submit": "提交申请",
        "approve": "审核通过",
        "reject": "审核退回",
    }

    def list_cases(
        self,
        db: Session,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        status_filter: str | None = None,
        current_user: User,
    ) -> dict:
        records, total = request_case_repository.list_cases(
            db,
            page=page,
            page_size=page_size,
            keyword=keyword,
            status=status_filter,
            extra_filters=data_access_service.build_request_case_filters(current_user),
        )
        return {
            "items": [self._serialize(db, item, current_user=current_user) for item in records],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def get_case(self, db: Session, case_id: int, current_user: User) -> dict:
        record = self._get_record(db, case_id, current_user)
        return self._serialize(db, record, current_user=current_user)

    def get_case_workflow_view(self, db: Session, case_id: int, current_user: User) -> dict:
        record = self._get_record(db, case_id, current_user)
        workflow_content = self._get_workflow_content(db, record)
        resolved_content = workflow_content or workflow_definition_service.get_definition(db, record.workflow_code)["content"]
        definition = workflow_service.get_definition(record.workflow_code, workflow_content=resolved_content)
        workflow_snapshot = self._current_workflow_snapshot(record, workflow_content=resolved_content)
        return {
            "workflowCode": record.workflow_code or workflow_service.default_workflow_code,
            "workflowName": definition.name,
            "workflowVersionId": record.workflow_version_id,
            "workflowVersionNo": record.workflow_version_no,
            "workflowVersionLabel": f"V{record.workflow_version_no}" if record.workflow_version_no else "跟随当前生效版本",
            "currentTaskCode": workflow_snapshot.current_task_code,
            "currentTaskName": workflow_snapshot.current_task_name,
            "content": resolved_content,
            "workflowSteps": self._build_workflow_steps(record, workflow_content=resolved_content),
        }

    def create_case(self, db: Session, payload: dict, current_user: User) -> dict:
        resolved = self._resolve_payload(db, payload, current_user)
        workflow_snapshot = workflow_service.create_workflow(
            resolved["workflowCode"],
            {"request_type": resolved["requestType"]},
            workflow_content=resolved["workflowContent"],
        )

        record = RequestCase(
            serial_no=self._generate_serial_no(),
            request_title=resolved["requestTitle"],
            request_type=resolved["requestType"],
            tenant_code=resolved["tenantCode"],
            region_code=resolved["regionCode"],
            issuer_id=resolved["issuerId"],
            issuer_code=resolved["issuerCode"],
            issuer_name=resolved["issuerName"],
            contractor_code=resolved["contractorCode"],
            contractor_name=resolved["contractorName"],
            contractor_id_type=resolved["contractorIdType"],
            contractor_id_no=resolved["contractorIdNo"],
            contract_code=resolved["contractCode"],
            workflow_state=workflow_snapshot.workflow_state,
            mobile=resolved["mobile"],
            address=resolved["address"],
            reason=resolved["reason"],
            note=resolved["note"],
            workflow_code=resolved["workflowCode"],
            workflow_version_id=resolved["workflowVersionId"],
            workflow_version_no=str(resolved["workflowVersionNo"]) if resolved["workflowVersionNo"] is not None else None,
            current_step=workflow_snapshot.current_step,
            status=workflow_snapshot.status,
            created_by_id=current_user.id,
        )
        record = request_case_repository.create_case(db, record)
        self._record_participant(db, record.id, current_user.id, action="create", step_name=record.current_step)
        return self._serialize(db, self._reload_case(db, record.id), current_user=current_user)

    def update_case(self, db: Session, case_id: int, payload: dict, current_user: User) -> dict:
        record = self._get_record(db, case_id, current_user)
        self._ensure_editable(record)
        resolved = self._resolve_payload(db, payload, current_user)
        binding_changed = (
            record.workflow_code != resolved["workflowCode"]
            or record.workflow_version_id != resolved["workflowVersionId"]
        )

        if binding_changed and record.submitted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该申请已经提交过流程，不允许再切换流程定义或版本",
            )

        record.request_title = resolved["requestTitle"]
        record.request_type = resolved["requestType"]
        record.tenant_code = resolved["tenantCode"]
        record.region_code = resolved["regionCode"]
        record.issuer_id = resolved["issuerId"]
        record.issuer_code = resolved["issuerCode"]
        record.issuer_name = resolved["issuerName"]
        record.contractor_code = resolved["contractorCode"]
        record.contractor_name = resolved["contractorName"]
        record.contractor_id_type = resolved["contractorIdType"]
        record.contractor_id_no = resolved["contractorIdNo"]
        record.contract_code = resolved["contractCode"]
        record.mobile = resolved["mobile"]
        record.address = resolved["address"]
        record.reason = resolved["reason"]
        record.note = resolved["note"]
        record.workflow_code = resolved["workflowCode"]
        record.workflow_version_id = resolved["workflowVersionId"]
        record.workflow_version_no = str(resolved["workflowVersionNo"]) if resolved["workflowVersionNo"] is not None else None
        record.workflow_version = None
        if binding_changed:
            workflow_snapshot = workflow_service.create_workflow(
                resolved["workflowCode"],
                {"request_type": resolved["requestType"]},
                workflow_content=resolved["workflowContent"],
            )
            record.workflow_state = workflow_snapshot.workflow_state
            record.current_step = workflow_snapshot.current_step
            record.status = workflow_snapshot.status
            record.completed_at = None
        request_case_repository.update_case(db, record)
        self._record_participant(db, record.id, current_user.id, action="update", step_name=record.current_step)
        return self._serialize(db, self._reload_case(db, record.id), current_user=current_user)

    def submit_case(self, db: Session, case_id: int, current_user: User) -> dict:
        record = self._get_record(db, case_id, current_user)
        self._ensure_editable(record)
        workflow_content = self._get_workflow_content(db, record)
        self._ensure_attachment_requirement(record, self._get_task_config(record, self._current_workflow_snapshot(record, workflow_content=workflow_content).current_task_code, workflow_content=workflow_content))
        applicant_codes = workflow_service.get_applicant_task_codes(record.workflow_code, workflow_content=workflow_content)
        self._sync_workflow_snapshot(
            record,
            workflow_service.complete_task(
                self._ensure_workflow_state(record),
                applicant_codes,
                {"approval_result": None},
                workflow_code=record.workflow_code,
                workflow_content=workflow_content,
            ),
        )
        record.submitted_at = datetime.now()
        record.note = self._append_note(record.note, "提交申请", current_user.real_name, None)
        request_case_repository.update_case(db, record)
        self._record_participant(db, record.id, current_user.id, action="submit", step_name=record.current_step)
        return self._serialize(db, self._reload_case(db, record.id), current_user=current_user)

    def approve_case(self, db: Session, case_id: int, current_user: User, comment: str | None = None) -> dict:
        record = self._get_record(db, case_id, current_user)
        workflow_content = self._get_workflow_content(db, record)
        workflow_snapshot = self._current_workflow_snapshot(record, workflow_content=workflow_content)
        task_config = self._get_task_config(record, workflow_snapshot.current_task_code, workflow_content=workflow_content)
        self._ensure_review_permission(record, workflow_snapshot.current_task_code, current_user, task_config)
        self._ensure_comment_requirement(task_config, comment)
        self._ensure_attachment_requirement(record, task_config)

        self._sync_workflow_snapshot(
            record,
            workflow_service.complete_task(
                self._ensure_workflow_state(record),
                {workflow_snapshot.current_task_code},
                {
                    "approval_result": "approved",
                    "audit_user": current_user.real_name,
                    "audit_comment": (comment or "").strip() or None,
                },
                workflow_code=record.workflow_code,
                workflow_content=workflow_content,
            ),
        )
        if record.status == "已办结":
            record.completed_at = datetime.now()
        record.note = self._append_note(record.note, "审核通过", current_user.real_name, comment)
        request_case_repository.update_case(db, record)
        self._record_participant(db, record.id, current_user.id, action="approve", step_name=record.current_step, comment=comment)
        return self._serialize(db, self._reload_case(db, record.id), current_user=current_user)

    def reject_case(self, db: Session, case_id: int, current_user: User, comment: str | None = None) -> dict:
        record = self._get_record(db, case_id, current_user)
        workflow_content = self._get_workflow_content(db, record)
        workflow_snapshot = self._current_workflow_snapshot(record, workflow_content=workflow_content)
        task_config = self._get_task_config(record, workflow_snapshot.current_task_code, workflow_content=workflow_content)
        self._ensure_review_permission(record, workflow_snapshot.current_task_code, current_user, task_config)
        if not comment or not comment.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="退回时请填写审核意见")

        self._sync_workflow_snapshot(
            record,
            workflow_service.complete_task(
                self._ensure_workflow_state(record),
                {workflow_snapshot.current_task_code},
                {
                    "approval_result": "rejected",
                    "audit_user": current_user.real_name,
                    "audit_comment": comment.strip(),
                },
                workflow_code=record.workflow_code,
                workflow_content=workflow_content,
            ),
        )
        record.completed_at = None
        record.note = self._append_note(record.note, "审核退回", current_user.real_name, comment)
        request_case_repository.update_case(db, record)
        self._record_participant(db, record.id, current_user.id, action="reject", step_name=record.current_step, comment=comment)
        return self._serialize(db, self._reload_case(db, record.id), current_user=current_user)

    def delete_case(self, db: Session, case_id: int, current_user: User) -> None:
        record = self._get_record(db, case_id, current_user)
        self._ensure_editable(record)
        request_case_repository.delete_case(db, record)

    def upload_attachment(self, db: Session, case_id: int, *, upload_file, category: str | None, current_user: User) -> dict:
        record = self._get_record(db, case_id, current_user)
        self._ensure_attachment_writeable(record, current_user)
        workflow_content = self._get_workflow_content(db, record)
        workflow_snapshot = self._current_workflow_snapshot(record, workflow_content=workflow_content)
        task_config = self._get_task_config(record, workflow_snapshot.current_task_code, workflow_content=workflow_content)
        normalized_category = self._normalize_attachment_category(category)
        self._validate_attachment_category(task_config, normalized_category)

        suffix = Path(upload_file.filename or "").suffix
        stored_name = f"{uuid4().hex}{suffix}"
        case_dir = self.attachment_root / str(record.id)
        case_dir.mkdir(parents=True, exist_ok=True)
        target_path = case_dir / stored_name

        with target_path.open("wb") as target:
            shutil.copyfileobj(upload_file.file, target)

        attachment = RequestCaseAttachment(
            case_id=record.id,
            tenant_code=record.tenant_code,
            category=normalized_category,
            stage_code=workflow_snapshot.current_task_code,
            original_name=upload_file.filename or stored_name,
            stored_name=stored_name,
            content_type=upload_file.content_type,
            file_size=target_path.stat().st_size,
            storage_path=str(target_path),
            uploaded_by_id=current_user.id,
        )
        db.add(attachment)
        db.commit()
        db.refresh(attachment)
        return self._serialize_attachment(attachment)

    def delete_attachment(self, db: Session, case_id: int, attachment_id: int, current_user: User) -> None:
        record = self._get_record(db, case_id, current_user)
        attachment = (
            db.query(RequestCaseAttachment)
            .filter(RequestCaseAttachment.case_id == record.id, RequestCaseAttachment.id == attachment_id)
            .first()
        )
        if attachment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在")
        self._ensure_attachment_deleteable(record, attachment, current_user)
        file_path = Path(attachment.storage_path)
        db.delete(attachment)
        db.commit()
        if file_path.exists():
            file_path.unlink(missing_ok=True)

    def get_attachment(self, db: Session, case_id: int, attachment_id: int, current_user: User) -> RequestCaseAttachment:
        record = self._get_record(db, case_id, current_user)
        attachment = (
            db.query(RequestCaseAttachment)
            .options(joinedload(RequestCaseAttachment.uploaded_by))
            .filter(RequestCaseAttachment.case_id == record.id, RequestCaseAttachment.id == attachment_id)
            .first()
        )
        if attachment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在")
        return attachment

    def build_attachment_archive(self, db: Session, case_id: int, current_user: User) -> tuple[str, bytes]:
        record = self._get_record(db, case_id, current_user)
        attachments = sorted(record.attachments, key=lambda item: ((item.category or ""), item.created_at, item.id))
        if not attachments:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="???????????")

        buffer = io.BytesIO()
        used_names: set[str] = set()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in attachments:
                source_path = Path(item.storage_path)
                if not source_path.exists():
                    continue
                category = self._normalize_attachment_category(item.category) or "???"
                safe_name = self._unique_archive_name(used_names, item.original_name or source_path.name)
                archive.write(source_path, f"{category}/{safe_name}")

        serial_no = record.serial_no or f"request-{record.id}"
        return f"{serial_no}-attachments.zip", buffer.getvalue()

    def _reload_case(self, db: Session, case_id: int) -> RequestCase:
        record = request_case_repository.get_case(db, case_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="业务申请不存在")
        return record

    def _get_record(self, db: Session, case_id: int, current_user: User) -> RequestCase:
        record = request_case_repository.get_case(
            db,
            case_id,
            extra_filters=data_access_service.build_request_case_filters(current_user),
        )
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="业务申请不存在")
        if not record.workflow_state:
            self._sync_workflow_snapshot(record, self._bootstrap_existing_workflow(record))
            request_case_repository.update_case(db, record)
            record = self._reload_case(db, case_id)
        if not data_access_service.can_access_request_case(current_user, record):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前用户无权访问该业务申请")
        return record

    def _resolve_payload(self, db: Session, payload: dict, current_user: User) -> dict:
        contract = self._get_contract(db, payload.get("contractCode"))
        issuer_code = payload.get("issuerCode") or (contract.fbfbm if contract else None)
        contractor_code = payload.get("contractorCode") or (contract.cbfbm if contract else None)

        issuer = self._get_issuer(db, issuer_code)
        contractor = self._get_contractor(db, contractor_code)

        data_access_service.ensure_code_in_scope(
            current_user,
            issuer_code,
            detail="当前业务不在所在租户或区域范围内",
        )
        if contractor_code:
            data_access_service.ensure_code_in_scope(
                current_user,
                contractor_code,
                detail="当前业务不在所在租户或区域范围内",
            )
        if payload.get("contractCode"):
            data_access_service.ensure_code_in_scope(
                current_user,
                payload.get("contractCode"),
                detail="当前业务不在所在租户或区域范围内",
            )

        if contract and issuer_code and contract.fbfbm and issuer_code != contract.fbfbm:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="合同代码与发包方代码不一致")
        if contract and contractor_code and contract.cbfbm and contractor_code != contract.cbfbm:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="合同代码与承包方代码不一致")

        issuer_name = payload.get("issuerName") or (issuer.fbfmc if issuer else None)
        contractor_name = payload.get("contractorName") or (contractor.cbfmc if contractor else None)
        contractor_id_type = payload.get("contractorIdType") or (contractor.cbfzjlx if contractor else None)
        contractor_id_no = payload.get("contractorIdNo") or (contractor.cbfzjhm if contractor else None)
        mobile = payload.get("mobile") or (contractor.lxdh if contractor else None)
        address = payload.get("address") or (contractor.cbfdz if contractor else None)

        if not issuer_name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="发包方信息不完整")
        if not contractor_name or not contractor_id_type or not contractor_id_no:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="承包方信息不完整")

        legacy_issuer = self._ensure_legacy_issuer(db, issuer) if issuer else None
        request_title = payload.get("requestTitle") or f"{payload['requestType']}-{contractor_name}"
        fallback_region_code = current_user.region.code if current_user.region else None
        tenant_code, region_code = data_access_service.derive_request_scope(
            issuer_code=issuer_code,
            contractor_code=contractor_code,
            contract_code=payload.get("contractCode"),
            fallback_region_code=fallback_region_code,
        )

        workflow_binding = request_workflow_mapping_service.resolve_workflow_binding(
            db,
            request_type=payload["requestType"],
            tenant_code=tenant_code,
            explicit_workflow_code=payload.get("workflowCode"),
            explicit_workflow_version_id=payload.get("workflowVersionId"),
        )
        workflow_service.get_definition(
            workflow_binding["workflowCode"],
            workflow_content=workflow_binding["workflowContent"],
        )

        return {
            "requestTitle": request_title,
            "requestType": payload["requestType"],
            "tenantCode": tenant_code,
            "regionCode": region_code,
            "issuerId": legacy_issuer.id if legacy_issuer else None,
            "issuerCode": issuer_code,
            "issuerName": issuer_name,
            "contractorCode": contractor_code,
            "contractorName": contractor_name,
            "contractorIdType": contractor_id_type,
            "contractorIdNo": contractor_id_no,
            "contractCode": payload.get("contractCode"),
            "mobile": mobile,
            "address": address,
            "reason": payload.get("reason"),
            "note": payload.get("note"),
            "workflowCode": workflow_binding["workflowCode"],
            "workflowVersionId": workflow_binding["workflowVersionId"],
            "workflowVersionNo": workflow_binding["workflowVersionNo"],
            "workflowContent": workflow_binding["workflowContent"],
        }

    def _get_issuer(self, db: Session, issuer_code: str | None) -> Fbf | None:
        if not issuer_code:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请选择发包方代码")
        issuer = db.get(Fbf, issuer_code)
        if issuer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发包方代码不存在")
        return issuer

    def _get_contractor(self, db: Session, contractor_code: str | None) -> Cbf | None:
        if not contractor_code:
            return None
        contractor = db.get(Cbf, contractor_code)
        if contractor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="承包方代码不存在")
        return contractor

    def _get_contract(self, db: Session, contract_code: str | None) -> Cbht | None:
        if not contract_code:
            return None
        contract = db.get(Cbht, contract_code)
        if contract is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="合同代码不存在")
        return contract

    def _ensure_legacy_issuer(self, db: Session, issuer: Fbf | None) -> Issuer | None:
        if issuer is None:
            return None

        legacy = db.query(Issuer).filter(Issuer.code == issuer.fbfbm).first()
        if legacy is not None:
            return legacy

        region_id = db.query(Issuer.region_id).order_by(Issuer.id.asc()).limit(1).scalar()
        legacy = Issuer(
            code=issuer.fbfbm,
            name=issuer.fbfmc,
            owner_name=issuer.fbffzrxm,
            owner_id_no=issuer.fzrzjhm,
            mobile=issuer.lxdh,
            address=issuer.fbfdz,
            postcode=issuer.yzbm,
            surveyor_name=issuer.fbfdcy,
            survey_date=issuer.fbfdcrq.date() if issuer.fbfdcrq else None,
            notes=issuer.fbfdcjs,
            status="待提交",
            region_id=region_id or 1,
        )
        db.add(legacy)
        db.commit()
        db.refresh(legacy)
        return legacy

    def _ensure_editable(self, record: RequestCase) -> None:
        snapshot = self._current_workflow_snapshot(record)
        workflow_content = self._get_workflow_content_from_record(record)
        if snapshot.current_task_code not in workflow_service.get_applicant_task_codes(
            record.workflow_code,
            workflow_content=workflow_content,
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前业务申请状态不可修改")

    def _ensure_review_permission(
        self,
        record: RequestCase,
        task_code: str | None,
        current_user: User,
        task_config: WorkflowTaskConfig | None,
    ) -> None:
        if not task_code or task_config is None or not task_config.permission_code:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前业务申请状态不可审核")

        user_permissions = {item.code for item in current_user.role.permissions}
        if task_config.permission_code not in user_permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前用户无权执行该审核动作")

        if not self._matches_task_scope(record, current_user, task_config):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前用户不在该节点允许的数据范围内")

    def _ensure_comment_requirement(self, task_config: WorkflowTaskConfig | None, comment: str | None) -> None:
        if task_config and task_config.require_comment and not (comment and comment.strip()):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="当前节点要求必须填写审核意见")

    def _ensure_attachment_requirement(self, record: RequestCase, task_config: WorkflowTaskConfig | None) -> None:
        if not task_config or not task_config.require_attachment:
            return
        if self._has_required_attachment(record, task_config):
            return
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="当前节点要求至少上传一个附件")

    def _has_required_attachment(self, record: RequestCase, task_config: WorkflowTaskConfig) -> bool:
        stage_code = task_config.code
        attachments = [item for item in record.attachments if item.stage_code == stage_code]
        if not attachments:
            return False
        expected_types = {item for item in (task_config.attachment_types or []) if item}
        if not expected_types:
            return True
        return any((item.category or "") in expected_types for item in attachments)

    def _normalize_attachment_category(self, category: str | None) -> str | None:
        normalized = (category or "").strip()
        return normalized or None

    def _unique_archive_name(self, used_names: set[str], filename: str) -> str:
        candidate = filename or "attachment"
        stem = Path(candidate).stem or "attachment"
        suffix = Path(candidate).suffix
        index = 1
        while candidate in used_names:
            candidate = f"{stem}-{index}{suffix}"
            index += 1
        used_names.add(candidate)
        return candidate

    def _validate_attachment_category(self, task_config: WorkflowTaskConfig | None, category: str | None) -> None:
        if task_config is None:
            return
        expected_types = {item for item in (task_config.attachment_types or []) if item}
        if not expected_types:
            return
        if not category:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="当前节点上传附件时必须选择附件分类")
        if category not in expected_types:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="当前节点不允许上传该附件分类")

    def _get_workflow_content(self, db: Session, record: RequestCase) -> str | None:
        if record.workflow_version is not None:
            return record.workflow_version.content
        if record.workflow_version_id:
            workflow_version = workflow_definition_service.get_version_record(db, record.workflow_code, record.workflow_version_id)
            if workflow_version is not None:
                record.workflow_version = workflow_version
                return workflow_version.content
        return None

    def _ensure_workflow_state(self, record: RequestCase) -> str:
        if record.workflow_state:
            return record.workflow_state
        snapshot = self._bootstrap_existing_workflow(record, workflow_content=self._get_workflow_content_from_record(record))
        record.workflow_state = snapshot.workflow_state
        record.current_step = snapshot.current_step
        record.status = snapshot.status
        return record.workflow_state

    def _get_workflow_content_from_record(self, record: RequestCase) -> str | None:
        return record.workflow_version.content if record.workflow_version is not None else None

    def _bootstrap_existing_workflow(self, record: RequestCase, workflow_content: str | None = None):
        return workflow_service.bootstrap_snapshot(
            workflow_code=record.workflow_code,
            status=record.status,
            current_step=record.current_step,
            request_context={"request_type": record.request_type},
            workflow_content=workflow_content,
        )

    def _current_workflow_snapshot(self, record: RequestCase, workflow_content: str | None = None):
        resolved_content = workflow_content if workflow_content is not None else self._get_workflow_content_from_record(record)
        workflow_state = self._ensure_workflow_state(record)
        workflow = workflow_service.restore_workflow(record.workflow_code, workflow_state, workflow_content=resolved_content)
        snapshot = workflow_service.snapshot(record.workflow_code, workflow, workflow_content=resolved_content)
        record.workflow_state = snapshot.workflow_state
        record.current_step = snapshot.current_step
        record.status = snapshot.status
        return snapshot

    def _sync_workflow_snapshot(self, record: RequestCase, snapshot) -> None:
        record.workflow_state = snapshot.workflow_state
        record.current_step = snapshot.current_step
        record.status = snapshot.status

    def _generate_serial_no(self) -> str:
        return f"RC{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    def _append_note(self, existing_note: str | None, action_name: str, actor_name: str, comment: str | None) -> str:
        action_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        parts = [f"[{action_time}] {action_name}", f"经办人：{actor_name}"]
        if comment and comment.strip():
            parts.append(f"意见：{comment.strip()}")
        line = "；".join(parts)
        if existing_note and existing_note.strip():
            return f"{existing_note.rstrip()}\n{line}"
        return line

    def _record_participant(
        self,
        db: Session,
        case_id: int,
        user_id: int,
        *,
        action: str,
        step_name: str | None,
        comment: str | None = None,
    ) -> None:
        case_record = request_case_repository.get_case(db, case_id)
        participant = RequestCaseParticipant(
            case_id=case_id,
            user_id=user_id,
            tenant_code=case_record.tenant_code if case_record else None,
            action=action,
            step_name=step_name,
            comment=(comment or "").strip() or None,
        )
        db.add(participant)
        db.commit()

    def _serialize_participant(self, item: RequestCaseParticipant) -> dict:
        user = item.user
        return {
            "id": item.id,
            "userId": item.user_id,
            "username": user.username if user else "",
            "userName": user.real_name if user else "未知用户",
            "roleName": user.role.name if user and user.role else None,
            "action": item.action,
            "actionLabel": self.action_labels.get(item.action, item.action),
            "stepName": item.step_name,
            "comment": item.comment,
            "createdAt": item.created_at.isoformat(),
        }

    def _serialize_attachment(self, item: RequestCaseAttachment) -> dict:
        return {
            "id": item.id,
            "category": item.category,
            "stageCode": item.stage_code,
            "originalName": item.original_name,
            "contentType": item.content_type,
            "fileSize": item.file_size,
            "uploadedByName": item.uploaded_by.real_name if item.uploaded_by else None,
            "createdAt": item.created_at.isoformat(),
        }

    def _build_attachment_templates(self, db: Session, item: RequestCase, task_config: WorkflowTaskConfig | None) -> list[dict]:
        stage_code = task_config.code if task_config else (item.current_step or "apply")
        configured_categories = list(task_config.attachment_types or []) if task_config else []
        template_rows = request_attachment_template_service.resolve_templates(
            db,
            request_type=item.request_type,
            stage_code=stage_code,
            tenant_code=item.tenant_code,
        )

        existing_categories = {row["category"] for row in template_rows}
        for category in configured_categories:
            if category not in existing_categories:
                template_rows.append(
                    {
                        "id": 0,
                        "tenantCode": item.tenant_code,
                        "requestType": item.request_type,
                        "stageCode": stage_code,
                        "stageName": task_config.name if task_config else item.current_step,
                        "category": category,
                        "name": f"{category}材料",
                        "required": True,
                        "description": "按当前节点要求上传该分类材料。",
                        "exampleFileName": f"{category}.pdf",
                        "sortOrder": 999,
                        "enabled": True,
                    }
                )

        if not template_rows:
            template_rows = [
                {
                    "id": 0,
                    "tenantCode": item.tenant_code,
                    "requestType": item.request_type,
                    "stageCode": stage_code,
                    "stageName": task_config.name if task_config else item.current_step,
                    "category": "业务材料",
                    "name": "业务附件",
                    "required": True,
                    "description": "当前业务暂未配置细化模板，可按实际需要上传。",
                    "exampleFileName": "业务附件.pdf",
                    "sortOrder": 999,
                    "enabled": True,
                }
            ]

        attachments = item.attachments or []
        templates: list[dict] = []
        for index, row in enumerate(sorted(template_rows, key=lambda item: (item.get("sortOrder", 0), item.get("id", 0), item["category"])), start=1):
            category = row["category"]
            matched = [
                attachment
                for attachment in attachments
                if (attachment.category or category) == category and (not stage_code or attachment.stage_code == stage_code)
            ]
            templates.append(
                {
                    "key": f"{stage_code}:{category}:{index}",
                    "category": category,
                    "name": row["name"],
                    "required": row.get("required", True),
                    "stageCode": stage_code,
                    "stageName": row.get("stageName") or (task_config.name if task_config else item.current_step),
                    "description": row.get("description"),
                    "exampleFileName": row.get("exampleFileName"),
                    "uploadedCount": len(matched),
                    "satisfied": len(matched) > 0,
                }
            )
        return templates

    def _serialize_candidate(self, user: User) -> dict:
        return {
            "userId": user.id,
            "username": user.username,
            "userName": user.real_name,
            "roleName": user.role.name if user.role else None,
            "tenantCode": user.tenant_code,
            "regionCode": user.region.code if user.region else None,
            "regionName": user.region.full_name if user.region else None,
        }

    def _serialize_task_config(self, task_config: WorkflowTaskConfig | None) -> dict | None:
        if task_config is None:
            return None
        return {
            "code": task_config.code,
            "name": task_config.name,
            "permissionCode": task_config.permission_code,
            "dataScope": task_config.data_scope,
            "requireComment": task_config.require_comment,
            "requireAttachment": task_config.require_attachment,
            "attachmentTypes": list(task_config.attachment_types or []),
            "candidateRoleCodes": list(task_config.candidate_role_codes or []),
            "candidateUserMode": task_config.candidate_user_mode,
            "isApplicantTask": task_config.is_applicant_task,
        }

    def _ensure_attachment_writeable(self, item: RequestCase, current_user: User) -> None:
        if self._can_edit_record(item, current_user) or self._can_review_record(item, current_user):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前用户无权上传附件")

    def _ensure_attachment_deleteable(
        self,
        item: RequestCase,
        attachment: RequestCaseAttachment,
        current_user: User,
    ) -> None:
        if attachment.uploaded_by_id == current_user.id:
            return
        if self._can_edit_record(item, current_user):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前用户无权删除该附件")

    def _can_edit_record(self, item: RequestCase, current_user: User | None) -> bool:
        if current_user is None:
            return False
        user_permissions = {permission.code for permission in current_user.role.permissions}
        if "requests.manage" not in user_permissions:
            return False
        try:
            self._ensure_editable(item)
        except HTTPException:
            return False
        return True

    def _can_review_record(self, item: RequestCase, current_user: User | None) -> bool:
        if current_user is None:
            return False
        snapshot = self._current_workflow_snapshot(item)
        task_config = self._get_task_config(item, snapshot.current_task_code)
        try:
            self._ensure_review_permission(item, snapshot.current_task_code, current_user, task_config)
        except HTTPException:
            return False
        return True

    def _build_available_actions(self, item: RequestCase, current_user: User | None) -> list[str]:
        actions = ["view"]
        if current_user is None:
            return actions

        user_permissions = {permission.code for permission in current_user.role.permissions}
        if self._can_edit_record(item, current_user):
            actions.extend(["edit", "delete"])
        if "requests.submit" in user_permissions and item.status == "待提交":
            actions.append("submit")
        if self._can_review_record(item, current_user):
            actions.extend(["approve", "reject"])
        return actions

    def _build_workflow_steps(self, item: RequestCase, workflow_content: str | None = None) -> list[dict]:
        resolved_content = workflow_content if workflow_content is not None else self._get_workflow_content_from_record(item)
        step_order = workflow_service.get_step_order(item.workflow_code, workflow_content=resolved_content)
        if not step_order:
            step_order = [("apply", "申请"), ("complete", "已办结")]

        last_reject_step = None
        for participant in sorted(item.participants, key=lambda p: p.created_at, reverse=True):
            if participant.action == "reject" and participant.step_name:
                last_reject_step = participant.step_name
                break

        current_name_to_code = {name: code for code, name in step_order}
        current_code = "complete" if item.status == "已办结" else current_name_to_code.get(item.current_step, "apply")
        current_index = next((index for index, (code, _name) in enumerate(step_order) if code == current_code), 0)

        steps = []
        for index, (code, name) in enumerate(step_order):
            step_status = "pending"
            if item.status == "已办结":
                step_status = "completed"
            elif item.status == "待提交":
                step_status = "current" if code == "apply" else "pending"
            elif item.status == "审核中":
                if index < current_index:
                    step_status = "completed"
                elif index == current_index:
                    step_status = "current"
            elif item.status == "已退回":
                if code == "apply":
                    step_status = "current"
                elif name == last_reject_step:
                    step_status = "rejected"
                elif index < current_index:
                    step_status = "completed"

            label = {
                "completed": "已完成",
                "current": "进行中",
                "pending": "待处理",
                "rejected": "已退回",
            }[step_status]
            steps.append({"code": code, "name": name, "status": step_status, "label": label})
        return steps

    def _get_task_config(
        self,
        item: RequestCase,
        current_task_code: str | None,
        workflow_content: str | None = None,
    ) -> WorkflowTaskConfig | None:
        resolved_content = workflow_content if workflow_content is not None else self._get_workflow_content_from_record(item)
        return workflow_service.get_task_config(item.workflow_code, current_task_code, workflow_content=resolved_content)

    def _matches_task_scope(self, item: RequestCase, user: User, task_config: WorkflowTaskConfig | None) -> bool:
        if user.role.data_scope == "all":
            return True

        if item.tenant_code and user.tenant_code and item.tenant_code != user.tenant_code:
            return False

        scope = task_config.data_scope if task_config and task_config.data_scope else user.role.data_scope
        if scope == "all":
            return True

        region_code = user.region.code if user.region else None
        item_region_code = item.region_code or item.issuer_code or item.contractor_code
        if not region_code or not item_region_code:
            return True

        if scope == "county":
            prefix = region_code[:6]
        elif scope == "town":
            prefix = region_code[:9] if len(region_code) >= 9 else region_code[:6]
        else:
            prefix = region_code
        return str(item_region_code).startswith(prefix)

    def _get_candidate_handlers(self, db: Session, item: RequestCase, task_config: WorkflowTaskConfig | None) -> list[dict]:
        if task_config is None:
            return []

        required_permission = task_config.permission_code
        candidate_role_codes = task_config.candidate_role_codes or []
        candidate_mode = task_config.candidate_user_mode or "permission_scope"

        stmt = (
            select(User)
            .join(User.role)
            .options(joinedload(User.role), joinedload(User.region), joinedload(User.tenant))
            .where(User.status == "active")
            .order_by(User.id.asc())
        )

        if item.tenant_code:
            stmt = stmt.where(or_(User.tenant_code == item.tenant_code, Role.data_scope == "all"))

        if candidate_role_codes:
            stmt = stmt.where(Role.code.in_(candidate_role_codes))

        if candidate_mode in {"permission_scope", "manual_assign"} and required_permission:
            stmt = stmt.join(Role.permissions).where(Permission.code == required_permission)

        users = list(db.scalars(stmt).unique().all())

        candidates = []
        for user in users:
            if not self._matches_task_scope(item, user, task_config):
                continue
            candidates.append(self._serialize_candidate(user))
        return candidates

    def _serialize(self, db: Session, item: RequestCase, current_user: User | None = None) -> dict:
        issuer_name = item.issuer_name or (item.issuer.name if item.issuer else None)
        issuer_code = item.issuer_code or (item.issuer.code if item.issuer else None)
        request_title = item.request_title or f"{item.request_type}-{item.contractor_name}"
        participants = sorted(item.participants, key=lambda participant: participant.created_at)
        workflow_content = self._get_workflow_content(db, item)
        workflow_snapshot = self._current_workflow_snapshot(item, workflow_content=workflow_content)
        task_config = self._get_task_config(item, workflow_snapshot.current_task_code, workflow_content=workflow_content)

        return {
            "id": item.id,
            "serialNo": item.serial_no,
            "requestTitle": request_title,
            "requestType": item.request_type,
            "tenantCode": item.tenant_code,
            "regionCode": item.region_code,
            "issuerCode": issuer_code,
            "issuerName": issuer_name,
            "contractorCode": item.contractor_code,
            "contractorName": item.contractor_name,
            "contractorIdType": item.contractor_id_type,
            "contractorIdNo": item.contractor_id_no,
            "contractCode": item.contract_code,
            "mobile": item.mobile,
            "address": item.address,
            "reason": item.reason,
            "note": item.note,
            "workflowCode": item.workflow_code,
            "workflowVersionId": item.workflow_version_id,
            "workflowVersionNo": item.workflow_version_no,
            "workflowVersionLabel": f"V{item.workflow_version_no}" if item.workflow_version_no else "跟随当前生效版本",
            "currentTaskCode": workflow_snapshot.current_task_code,
            "currentTaskName": workflow_snapshot.current_task_name,
            "currentStep": item.current_step,
            "status": item.status,
            "createdByName": item.created_by.real_name if item.created_by else None,
            "requiredPermission": workflow_snapshot.required_permission,
            "taskConfig": self._serialize_task_config(task_config),
            "availableActions": self._build_available_actions(item, current_user),
            "workflowSteps": self._build_workflow_steps(item, workflow_content=workflow_content),
            "candidateHandlers": self._get_candidate_handlers(db, item, task_config),
            "participants": [self._serialize_participant(participant) for participant in participants],
            "attachments": [self._serialize_attachment(attachment) for attachment in sorted(item.attachments, key=lambda a: a.created_at, reverse=True)],
            "attachmentTemplates": self._build_attachment_templates(db, item, task_config),
            "submittedAt": item.submitted_at.isoformat() if item.submitted_at else None,
            "completedAt": item.completed_at.isoformat() if item.completed_at else None,
            "createdAt": item.created_at.isoformat(),
            "updatedAt": item.updated_at.isoformat(),
        }


request_case_service = RequestCaseService()
