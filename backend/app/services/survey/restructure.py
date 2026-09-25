import logging

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyCbfResult,
    SurveyHouseholdRestructure,
    SurveyHouseholdRestructureMember,
)
from app.models.user import User
from app.services.data_access_service import data_access_service

logger = logging.getLogger(__name__)

class SurveyServiceRestructureMixin:
    def list_restructures(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> list[dict]:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
        rows = db.scalars(
            select(SurveyHouseholdRestructure)
            .where(SurveyHouseholdRestructure.batch_id == batch_id, SurveyHouseholdRestructure.contractor_uid == contractor_uid)
            .order_by(SurveyHouseholdRestructure.id.desc())
        ).all()
        return [self._serialize_restructure(db, item) for item in rows]


    def save_restructure(self, db: Session, batch_id: int, contractor_uid: str, payload: dict, current_user: User, item_id: int | None = None) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        self._ensure_editable_batch_and_result(db, result, current_user)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
        item = db.get(SurveyHouseholdRestructure, item_id) if item_id else None
        if item_id and item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="restructure record not found")
        if item is None:
            item = SurveyHouseholdRestructure(
                batch_id=batch_id,
                contractor_uid=contractor_uid,
                restructure_no=self._next_no(db, "RST", SurveyHouseholdRestructure.id),
                created_by_id=current_user.id,
                created_by_name=current_user.real_name,
            )
            db.add(item)
        item.restructure_type = payload["restructureType"]
        item.source_contractor_uid = payload.get("sourceContractorUid")
        item.source_cbfbm = payload.get("sourceCbfbm") or result.cbfbm
        item.source_cbfmc = payload.get("sourceCbfmc") or result.cbfmc
        item.target_contractor_uid = payload.get("targetContractorUid")
        item.target_cbfbm = payload.get("targetCbfbm")
        item.target_cbfmc = payload.get("targetCbfmc")
        item.new_cbfbm = payload.get("newCbfbm")
        item.new_cbfmc = payload.get("newCbfmc")
        item.status = payload.get("status") or "draft"
        item.reason = payload.get("reason")
        item.policy_basis = payload.get("policyBasis")
        item.rights_summary = payload.get("rightsSummary")
        item.contract_disposition = payload.get("contractDisposition")
        item.certificate_disposition = payload.get("certificateDisposition")
        item.remark = payload.get("remark")
        db.flush()
        db.execute(delete(SurveyHouseholdRestructureMember).where(SurveyHouseholdRestructureMember.restructure_id == item.id))
        for member in payload.get("members") or []:
            db.add(
                SurveyHouseholdRestructureMember(
                    restructure_id=item.id,
                    batch_id=batch_id,
                    contractor_uid=contractor_uid,
                    member_uid=member.get("memberUid"),
                    member_name=member["memberName"],
                    member_id_no=member.get("memberIdNo"),
                    from_cbfbm=member.get("fromCbfbm") or item.source_cbfbm,
                    to_cbfbm=member.get("toCbfbm") or item.target_cbfbm or item.new_cbfbm,
                    action_type=member.get("actionType") or "move",
                    rights_disposition=member.get("rightsDisposition"),
                    remark=member.get("remark"),
                )
            )
        db.commit()
        db.refresh(item)
        return self._serialize_restructure(db, item)


    def update_restructure(self, db: Session, restructure_id: int, payload: dict, current_user: User) -> dict:
        item = db.get(SurveyHouseholdRestructure, restructure_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="restructure record not found")
        return self.save_restructure(db, item.batch_id, item.contractor_uid, payload, current_user, item_id=restructure_id)


    def delete_restructure(self, db: Session, restructure_id: int, current_user: User) -> None:
        item = db.get(SurveyHouseholdRestructure, restructure_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="restructure record not found")
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        self._ensure_editable_batch_and_result(db, result, current_user)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
        db.execute(delete(SurveyHouseholdRestructureMember).where(SurveyHouseholdRestructureMember.restructure_id == item.id))
        db.delete(item)
        db.commit()


    def _serialize_restructure(self, db: Session, item: SurveyHouseholdRestructure) -> dict:
        members = db.scalars(
            select(SurveyHouseholdRestructureMember)
            .where(SurveyHouseholdRestructureMember.restructure_id == item.id)
            .order_by(SurveyHouseholdRestructureMember.id.asc())
        ).all()
        return {
            "id": item.id,
            "batchId": item.batch_id,
            "contractorUid": item.contractor_uid,
            "restructureNo": item.restructure_no,
            "restructureType": item.restructure_type,
            "sourceContractorUid": item.source_contractor_uid,
            "sourceCbfbm": item.source_cbfbm,
            "sourceCbfmc": item.source_cbfmc,
            "targetContractorUid": item.target_contractor_uid,
            "targetCbfbm": item.target_cbfbm,
            "targetCbfmc": item.target_cbfmc,
            "newCbfbm": item.new_cbfbm,
            "newCbfmc": item.new_cbfmc,
            "status": item.status,
            "reason": item.reason,
            "policyBasis": item.policy_basis,
            "rightsSummary": item.rights_summary,
            "contractDisposition": item.contract_disposition,
            "certificateDisposition": item.certificate_disposition,
            "generatedRequestId": item.generated_request_id,
            "createdByName": item.created_by_name,
            "remark": item.remark,
            "members": [
                {
                    "id": member.id,
                    "memberUid": member.member_uid,
                    "memberName": member.member_name,
                    "memberIdNo": member.member_id_no,
                    "fromCbfbm": member.from_cbfbm,
                    "toCbfbm": member.to_cbfbm,
                    "actionType": member.action_type,
                    "rightsDisposition": member.rights_disposition,
                    "remark": member.remark,
                }
                for member in members
            ],
            "createdAt": item.created_at,
        }

