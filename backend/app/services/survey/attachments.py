import logging
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.survey_attachment import SURVEY_ATTACHMENT_TEMPLATE_SCOPE
from app.models.request_attachment_template import RequestAttachmentTemplate
from app.models.survey import (
    SurveyAttachment,
    SurveyCbfResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service

logger = logging.getLogger(__name__)

class SurveyServiceAttachmentsMixin:
    def list_attachments(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> list[dict]:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        rows = db.scalars(
            select(SurveyAttachment)
            .where(SurveyAttachment.batch_id == batch_id, SurveyAttachment.contractor_uid == contractor_uid)
            .order_by(SurveyAttachment.id.desc())
        ).all()
        return [self._serialize_attachment(item) for item in rows]


    # 上传时的类别下拉项来自「附件组管理」页（request_type=调查附件 / stage_code=survey_entry）。
    # 两点与 request_attachment_template_service 的既有口径不同，都是有意的：
    #   1. 不复用它（也不复用其权限）：调查录入人员只有 contractors.*，拿个下拉框不该被迫开 requests.manage；
    #   2. 租户覆盖按「同名逐项覆盖」而不是「整节点替换」—— 类别是枚举，租户补一个不该顶掉其余；
    #      分组行（有子节点的）不算类别，读取时排除。
    def list_attachment_categories(self, db: Session, current_user: User) -> list[dict]:
        request_type, stage_code = SURVEY_ATTACHMENT_TEMPLATE_SCOPE
        tenant_code = data_access_service.get_tenant_code(current_user)
        scope_conditions = [RequestAttachmentTemplate.tenant_code.is_(None)]
        if tenant_code:
            scope_conditions.append(RequestAttachmentTemplate.tenant_code == tenant_code)
        rows = db.scalars(
            select(RequestAttachmentTemplate)
            .where(
                RequestAttachmentTemplate.request_type == request_type,
                RequestAttachmentTemplate.stage_code == stage_code,
                RequestAttachmentTemplate.enabled.is_(True),
                or_(*scope_conditions),
            )
            .order_by(RequestAttachmentTemplate.sort_order.asc(), RequestAttachmentTemplate.id.asc())
        ).all()

        parent_ids = {row.parent_id for row in rows if row.parent_id}
        picked: dict[str, RequestAttachmentTemplate] = {}
        for row in rows:
            if row.id in parent_ids:
                continue
            name = (row.name or "").strip()
            if not name:
                continue
            existing = picked.get(name)
            if existing is None or (row.tenant_code and not existing.tenant_code):
                picked[name] = row
        return [
            {"value": name, "label": name, "sortOrder": row.sort_order or 0}
            for name, row in picked.items()
        ]


    async def upload_attachment(self, db: Session, batch_id: int, contractor_uid: str, category: str, description: str | None, upload_file: UploadFile, current_user: User) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        self._ensure_editable_batch_and_result(db, result, current_user)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        storage_path, file_size = await self._store_upload(self.attachment_root / str(batch_id) / contractor_uid, upload_file)
        item = SurveyAttachment(
            batch_id=batch_id,
            contractor_uid=contractor_uid,
            cbfbm=result.cbfbm,
            category=category,
            original_name=upload_file.filename or "attachment",
            storage_path=str(storage_path),
            content_type=upload_file.content_type,
            file_size=file_size,
            uploaded_by_id=current_user.id,
            uploaded_by_name=current_user.real_name,
            description=description,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return self._serialize_attachment(item)


    def get_attachment(self, db: Session, attachment_id: int, current_user: User) -> SurveyAttachment:
        item = db.get(SurveyAttachment, attachment_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request failed")
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        return item


    def delete_attachment(self, db: Session, attachment_id: int, current_user: User) -> None:
        item = self.get_attachment(db, attachment_id, current_user)
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        self._ensure_editable_batch_and_result(db, result, current_user)
        try:
            Path(item.storage_path).unlink(missing_ok=True)
        except OSError:
            pass
        db.delete(item)
        db.commit()


    def _serialize_attachment(self, item: SurveyAttachment) -> dict:
        return {
            "id": item.id,
            "batchId": item.batch_id,
            "contractorUid": item.contractor_uid,
            "cbfbm": item.cbfbm,
            "category": item.category,
            "originalName": item.original_name,
            "contentType": item.content_type,
            "fileSize": item.file_size,
            "uploadedByName": item.uploaded_by_name,
            "description": item.description,
            "createdAt": item.created_at,
        }

