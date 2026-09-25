import logging

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyAuthorization,
    SurveyCbfResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service

logger = logging.getLogger(__name__)

class SurveyServiceAuthorizationMixin:
    def list_authorizations(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> list[dict]:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
        rows = db.scalars(
            select(SurveyAuthorization)
            .where(SurveyAuthorization.batch_id == batch_id, SurveyAuthorization.contractor_uid == contractor_uid)
            .order_by(SurveyAuthorization.id.desc())
        ).all()
        return [self._serialize_authorization(item) for item in rows]


    def save_authorization(self, db: Session, batch_id: int, contractor_uid: str, payload: dict, current_user: User, item_id: int | None = None) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        self._ensure_editable_batch_and_result(db, result, current_user)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
        item = db.get(SurveyAuthorization, item_id) if item_id else None
        if item_id and item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="authorization not found")
        if item is None:
            item = SurveyAuthorization(
                batch_id=batch_id,
                contractor_uid=contractor_uid,
                authorization_no=self._next_no(db, "AUT", SurveyAuthorization.id),
                created_by_id=current_user.id,
                created_by_name=current_user.real_name,
            )
            db.add(item)
        item.principal_name = payload["principalName"]
        item.principal_id_no = payload.get("principalIdNo")
        item.agent_name = payload["agentName"]
        item.agent_id_no = payload.get("agentIdNo")
        item.agent_phone = payload.get("agentPhone")
        item.authorized_matters = payload["authorizedMatters"]
        item.valid_from = self._parse_datetime(payload.get("validFrom"))
        item.valid_to = self._parse_datetime(payload.get("validTo"))
        item.status = payload.get("status") or "active"
        item.remark = payload.get("remark")
        item.generated_content = self._build_authorization_text(result, item)
        db.commit()
        db.refresh(item)
        return self._serialize_authorization(item)


    def update_authorization(self, db: Session, authorization_id: int, payload: dict, current_user: User) -> dict:
        item = db.get(SurveyAuthorization, authorization_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="authorization not found")
        return self.save_authorization(db, item.batch_id, item.contractor_uid, payload, current_user, item_id=authorization_id)


    async def upload_authorization_file(self, db: Session, authorization_id: int, upload_file: UploadFile, current_user: User) -> dict:
        item = db.get(SurveyAuthorization, authorization_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="authorization not found")
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        self._ensure_editable_batch_and_result(db, result, current_user)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
        storage_path, file_size = await self._store_upload(self.authorization_root / str(item.batch_id), upload_file)
        item.original_name = upload_file.filename or "authorization"
        item.storage_path = str(storage_path)
        item.content_type = upload_file.content_type
        item.file_size = file_size
        db.commit()
        db.refresh(item)
        return self._serialize_authorization(item)


    def get_authorization_file(self, db: Session, authorization_id: int, current_user: User) -> SurveyAuthorization:
        item = db.get(SurveyAuthorization, authorization_id)
        if item is None or not item.storage_path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="authorization file not found")
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        return item


    def build_authorization_template(self, db: Session, authorization_id: int, current_user: User) -> tuple[str, bytes]:
        item = db.get(SurveyAuthorization, authorization_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request failed")
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        content = item.generated_content or self._build_authorization_text(result, item)
        return f"{item.authorization_no}_授权委托书.txt", content.encode("utf-8-sig")


    def revoke_authorization(self, db: Session, authorization_id: int, revoke_reason: str, current_user: User) -> dict:
        item = db.get(SurveyAuthorization, authorization_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request failed")
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        self._ensure_editable_batch_and_result(db, result, current_user)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        item.status = "revoked"
        item.revoke_reason = revoke_reason
        db.commit()
        db.refresh(item)
        return self._serialize_authorization(item)


    def _build_authorization_text(self, result: SurveyCbfResult, authorization: SurveyAuthorization) -> str:
        valid_from = authorization.valid_from.date().isoformat() if authorization.valid_from else "____-__-__"
        valid_to = authorization.valid_to.date().isoformat() if authorization.valid_to else "____-__-__"
        return (
            "授权委托书\n"
            f"委托人：{authorization.principal_name}\n"
            f"委托人证件号：{authorization.principal_id_no or ''}\n"
            f"受托人：{authorization.agent_name}\n"
            f"受托人证件号：{authorization.agent_id_no or ''}\n"
            f"受托人联系电话：{authorization.agent_phone or ''}\n\n"
            f"委托事项：{authorization.authorized_matters}\n\n"
            f"承包方：{result.cbfmc}（{result.cbfbm}）\n"
            f"有效期：{valid_from} 至 {valid_to}\n\n"
            "委托人签名：___________    受托人签名：___________\n"
            "日期：____年__月__日\n"
        )


    def _serialize_authorization(self, item: SurveyAuthorization) -> dict:
        return {
            "id": item.id,
            "batchId": item.batch_id,
            "contractorUid": item.contractor_uid,
            "authorizationNo": item.authorization_no,
            "principalName": item.principal_name,
            "principalIdNo": item.principal_id_no,
            "agentName": item.agent_name,
            "agentIdNo": item.agent_id_no,
            "agentPhone": item.agent_phone,
            "authorizedMatters": item.authorized_matters,
            "validFrom": item.valid_from.date().isoformat() if item.valid_from else None,
            "validTo": item.valid_to.date().isoformat() if item.valid_to else None,
            "status": item.status,
            "revokeReason": item.revoke_reason,
            "generatedContent": item.generated_content,
            "originalName": item.original_name,
            "contentType": item.content_type,
            "fileSize": item.file_size,
            "createdByName": item.created_by_name,
            "remark": item.remark,
            "createdAt": item.created_at,
        }

