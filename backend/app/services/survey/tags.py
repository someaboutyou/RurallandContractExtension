import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyHouseholdTag,
)
from app.models.user import User
from app.services.data_access_service import data_access_service

logger = logging.getLogger(__name__)

class SurveyServiceTagsMixin:
    def list_tags(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> list[dict]:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
        rows = db.scalars(
            select(SurveyHouseholdTag)
            .where(SurveyHouseholdTag.batch_id == batch_id, SurveyHouseholdTag.contractor_uid == contractor_uid)
            .order_by(SurveyHouseholdTag.is_active.desc(), SurveyHouseholdTag.tag_source.asc(), SurveyHouseholdTag.id.asc())
        ).all()
        return [self._serialize_tag(item) for item in rows]


    def refresh_auto_tags(self, db: Session, batch_id: int, contractor_uid: str, current_user: User, commit: bool = True) -> list[dict]:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
        data_batch_id = batch_id
        members = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.tenant_code == result.tenant_code,
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
            .execution_options(skip_tenant_scope=True)
        ).all()
        now = datetime.now(timezone.utc)
        detected: dict[str, tuple[str, str]] = {}
        if members and all(member.is_urban_settled or member.member_result_status == "urbanized" for member in members):
            detected["whole_family_urbanized"] = ("rule_all_members_urbanized", "all household members are marked urban settled")
        if result.result_status in {"extinct", "cancelled"} or (members and all(member.is_deceased or member.member_result_status == "deceased" for member in members)):
            detected["household_extinct"] = ("rule_household_extinct_or_all_deceased", "household extinct or all members deceased")
        if any(member.is_five_guarantees for member in members):
            detected["five_guarantees"] = ("rule_any_member_five_guarantees", "member marked five guarantees")
        if result.change_type == "little_or_no_land" or result.result_status == "little_or_no_land":
            detected["little_or_no_land"] = ("rule_result_marked_little_or_no_land", "result marked little or no land")

        existing_auto = {
            item.tag_code: item
            for item in db.scalars(
                select(SurveyHouseholdTag).where(
                    SurveyHouseholdTag.batch_id == batch_id,
                    SurveyHouseholdTag.contractor_uid == contractor_uid,
                    SurveyHouseholdTag.tag_source == "auto",
                )
            ).all()
        }
        for tag_code, (rule_code, reason) in detected.items():
            item = existing_auto.get(tag_code)
            if item is None:
                item = SurveyHouseholdTag(
                    batch_id=batch_id,
                    contractor_uid=contractor_uid,
                    cbfbm=result.cbfbm,
                    tag_code=tag_code,
                    tag_name=self.tag_names[tag_code],
                    tag_source="auto",
                    rule_code=rule_code,
                    detected_at=now,
                )
                db.add(item)
            item.cbfbm = result.cbfbm
            item.is_active = True
            item.reason = reason
            item.rule_code = rule_code
            item.disabled_reason = None
        for tag_code, item in existing_auto.items():
            if tag_code not in detected:
                item.is_active = False
                item.disabled_reason = "automatically disabled because detection no longer matches"
        if commit:
            db.commit()
        return self.list_tags(db, batch_id, contractor_uid, current_user)


    def create_manual_tag(self, db: Session, batch_id: int, contractor_uid: str, payload: dict, current_user: User) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        self._ensure_editable_batch_and_result(db, result)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
        now = datetime.now(timezone.utc)
        item = SurveyHouseholdTag(
            batch_id=batch_id,
            contractor_uid=contractor_uid,
            cbfbm=result.cbfbm,
            tag_code=payload["tagCode"],
            tag_name=payload["tagName"],
            tag_source="manual",
            is_active=True,
            reason=payload.get("reason"),
            policy_basis=payload.get("policyBasis"),
            detected_at=now,
            confirmed_by_id=current_user.id,
            confirmed_by_name=current_user.real_name,
            confirmed_at=now,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return self._serialize_tag(item)


    def disable_tag(self, db: Session, tag_id: int, disabled_reason: str, current_user: User) -> dict:
        item = db.get(SurveyHouseholdTag, tag_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="household tag not found")
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        self._ensure_editable_batch_and_result(db, result)
        data_access_service.ensure_code_in_scope(current_user, item.cbfbm, detail="survey result out of scope")
        item.is_active = False
        item.disabled_reason = disabled_reason
        db.commit()
        db.refresh(item)
        return self._serialize_tag(item)


    def _serialize_tag(self, item: SurveyHouseholdTag) -> dict:
        return {
            "id": item.id,
            "batchId": item.batch_id,
            "contractorUid": item.contractor_uid,
            "cbfbm": item.cbfbm,
            "tagCode": item.tag_code,
            "tagName": item.tag_name,
            "tagSource": item.tag_source,
            "ruleCode": item.rule_code,
            "isActive": item.is_active,
            "reason": item.reason,
            "policyBasis": item.policy_basis,
            "disabledReason": item.disabled_reason,
            "detectedAt": item.detected_at,
            "confirmedByName": item.confirmed_by_name,
            "confirmedAt": item.confirmed_at,
            "createdAt": item.created_at,
        }

