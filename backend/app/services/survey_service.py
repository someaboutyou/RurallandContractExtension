import csv
import io
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.fbf import Fbf
from app.models.survey import (
    SurveyBatch,
    SurveyCbfBase,
    SurveyCbfJtcyBase,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyAttachment,
    SurveyAuthorization,
    SurveyChangeDiff,
    SurveyChangeRecord,
    SurveyContractorTask,
    SurveyHouseholdRestructure,
    SurveyHouseholdRestructureMember,
    SurveyHouseholdTag,
)
from app.models.user import User
from app.services.data_access_service import data_access_service
from app.services.request_case_service import request_case_service


class SurveyService:
    attachment_root = Path(__file__).resolve().parents[2] / "storage" / "survey_attachments"
    authorization_root = Path(__file__).resolve().parents[2] / "storage" / "survey_authorizations"
    tag_names = {
        "whole_family_urbanized": "全家进城落户户",
        "household_extinct": "整户消亡户",
        "five_guarantees": "五保户",
        "little_or_no_land": "无地少地户",
    }
    def list_batches(self, db: Session, page: int, page_size: int, keyword: str | None) -> dict:
        stmt = select(SurveyBatch).order_by(SurveyBatch.id.desc()).offset((page - 1) * page_size).limit(page_size)
        total_stmt = select(func.count(SurveyBatch.id))
        if keyword:
            pattern = f"%{keyword.strip()}%"
            condition = or_(SurveyBatch.batch_no.ilike(pattern), SurveyBatch.batch_name.ilike(pattern))
            stmt = stmt.where(condition)
            total_stmt = total_stmt.where(condition)
        batches = db.scalars(stmt).all()
        return {
            "items": [self._serialize_batch(db, item) for item in batches],
            "total": db.scalar(total_stmt) or 0,
            "page": page,
            "pageSize": page_size,
        }

    def create_batch(self, db: Session, payload: dict, current_user: User) -> dict:
        now = datetime.now(timezone.utc)
        batch = SurveyBatch(
            batch_no=self._next_no(db, "SUR", SurveyBatch.id),
            batch_name=payload["batchName"],
            region_code=payload.get("regionCode"),
            region_name=payload.get("regionName"),
            survey_type=payload.get("surveyType") or "household_survey",
            status="active",
            started_at=now,
            created_by=current_user.id,
            remark=payload.get("remark"),
        )
        db.add(batch)
        db.flush()

        filters = data_access_service.build_code_scope_filters(SurveyCbfResult.cbfbm, current_user)
        if payload.get("regionCode"):
            filters.append(SurveyCbfResult.region_code.like(f"{payload['regionCode']}%"))
        source_results = db.scalars(select(SurveyCbfResult).where(*filters).order_by(SurveyCbfResult.cbfbm.asc(), SurveyCbfResult.id.desc())).all()
        latest_by_code: dict[str, SurveyCbfResult] = {}
        for item in source_results:
            latest_by_code.setdefault(item.cbfbm, item)
        if not latest_by_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前范围内没有可初始化的承包方数据")

        for contractor in latest_by_code.values():
            contractor_uid = str(uuid5(NAMESPACE_URL, f"survey:{batch.id}:cbf:{contractor.cbfbm}"))
            base = SurveyCbfBase(
                tenant_code=contractor.tenant_code,
                region_code=contractor.region_code,
                batch_id=batch.id,
                contractor_uid=contractor_uid,
                source_cbfbm=contractor.cbfbm,
                cbfbm=contractor.cbfbm,
                cbflx=contractor.cbflx,
                cbfmc=contractor.cbfmc,
                cbfzjlx=contractor.cbfzjlx,
                cbfzjhm=contractor.cbfzjhm,
                cbfdz=contractor.cbfdz,
                yzbm=contractor.yzbm,
                lxdh=contractor.lxdh,
                cbfcysl=contractor.cbfcysl,
                cbfdcrq=contractor.cbfdcrq,
                cbfdcy=contractor.cbfdcy,
                cbfdcjs=contractor.cbfdcjs,
                gsjs=contractor.gsjs,
                gsjsr=contractor.gsjsr,
                gsshrq=contractor.gsshrq,
                gsshr=contractor.gsshr,
                group_region_code=contractor.group_region_code,
                group_region_name=contractor.group_region_name,
                source_import_batch_id=contractor.source_import_batch_id,
                source_import_row_id=contractor.source_import_row_id,
                last_import_batch_id=contractor.last_import_batch_id,
                last_import_row_id=contractor.last_import_row_id,
                initialized_from_table="survey_cbf_result",
                initialized_from_key=contractor.cbfbm,
                initialized_at=now,
                snapshot_at=now,
            )
            db.add(base)
            db.flush()
            result = self._result_from_base(base, now)
            db.add(result)
            db.add(
                SurveyContractorTask(
                    batch_id=batch.id,
                    contractor_uid=contractor_uid,
                    cbfbm=contractor.cbfbm,
                    cbfmc=contractor.cbfmc,
                    tenant_code=contractor.tenant_code,
                    region_code=contractor.region_code,
                    task_status="not_started",
                )
            )
            members = db.scalars(
                select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.batch_id == contractor.batch_id,
                    SurveyCbfJtcyResult.cbfbm == contractor.cbfbm,
                )
            ).all()
            for member in members:
                member_uid = str(uuid5(NAMESPACE_URL, f"survey:{batch.id}:member:{contractor.cbfbm}:{member.cyzjhm}"))
                member_base = SurveyCbfJtcyBase(
                    tenant_code=member.tenant_code,
                    region_code=member.region_code,
                    batch_id=batch.id,
                    contractor_uid=contractor_uid,
                    member_uid=member_uid,
                    base_contractor_code=member.cbfbm,
                    base_member_id_no=member.cyzjhm,
                    cbfbm=member.cbfbm,
                    cyxm=member.cyxm,
                    cyzjlx=member.cyzjlx,
                    cyzjhm=member.cyzjhm,
                    cyxb=member.cyxb,
                    yhzgx=member.yhzgx,
                    cybz=member.cybz,
                    sfgyr=member.sfgyr,
                    cybzsm=member.cybzsm,
                    source_import_batch_id=member.source_import_batch_id,
                    source_import_row_id=member.source_import_row_id,
                    last_import_batch_id=member.last_import_batch_id,
                    last_import_row_id=member.last_import_row_id,
                    initialized_from_table="survey_cbf_jtcy_result",
                    initialized_from_key=f"{member.cbfbm}:{member.cyzjhm}",
                    initialized_at=now,
                    snapshot_at=now,
                )
                db.add(member_base)
                db.flush()
                db.add(self._member_result_from_base(member_base, now))
        db.commit()
        db.refresh(batch)
        return self._serialize_batch(db, batch)

    def list_tasks(
        self,
        db: Session,
        batch_id: int,
        page: int,
        page_size: int,
        keyword: str | None,
        task_status: str | None,
        current_user: User,
    ) -> dict:
        self._ensure_batch(db, batch_id)
        stmt = (
            select(SurveyContractorTask)
            .where(SurveyContractorTask.batch_id == batch_id)
            .order_by(SurveyContractorTask.cbfbm.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        total_stmt = select(func.count(SurveyContractorTask.id)).where(SurveyContractorTask.batch_id == batch_id)
        filters = data_access_service.build_code_scope_filters(SurveyContractorTask.cbfbm, current_user)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(or_(SurveyContractorTask.cbfbm.ilike(pattern), SurveyContractorTask.cbfmc.ilike(pattern)))
        if task_status:
            filters.append(SurveyContractorTask.task_status == task_status)
        if filters:
            stmt = stmt.where(*filters)
            total_stmt = total_stmt.where(*filters)
        return {
            "items": [self._serialize_task(item) for item in db.scalars(stmt).all()],
            "total": db.scalar(total_stmt) or 0,
            "page": page,
            "pageSize": page_size,
        }

    def get_result(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        members = db.scalars(
            select(SurveyCbfJtcyResult)
            .where(SurveyCbfJtcyResult.batch_id == batch_id, SurveyCbfJtcyResult.contractor_uid == contractor_uid)
            .order_by(SurveyCbfJtcyResult.cyxm, SurveyCbfJtcyResult.cyzjhm)
        ).all()
        base = db.get(SurveyCbfBase, result.base_id)
        base_members = db.scalars(
            select(SurveyCbfJtcyBase)
            .where(SurveyCbfJtcyBase.batch_id == batch_id, SurveyCbfJtcyBase.contractor_uid == contractor_uid)
            .order_by(SurveyCbfJtcyBase.cyxm, SurveyCbfJtcyBase.cyzjhm)
        ).all()
        return self._serialize_result(result, members, base, base_members)

    def list_diffs(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        page: int,
        page_size: int,
        current_user: User,
    ) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        stmt = (
            select(SurveyChangeDiff)
            .where(SurveyChangeDiff.batch_id == batch_id, SurveyChangeDiff.contractor_uid == contractor_uid)
            .order_by(SurveyChangeDiff.entity_type.asc(), SurveyChangeDiff.entity_name.asc(), SurveyChangeDiff.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        total_stmt = select(func.count(SurveyChangeDiff.id)).where(
            SurveyChangeDiff.batch_id == batch_id,
            SurveyChangeDiff.contractor_uid == contractor_uid,
        )
        return {
            "items": [self._serialize_diff(item) for item in db.scalars(stmt).all()],
            "total": db.scalar(total_stmt) or 0,
            "page": page,
            "pageSize": page_size,
        }

    def list_changes(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str | None,
        page: int,
        page_size: int,
        current_user: User,
    ) -> dict:
        self._ensure_batch(db, batch_id)
        stmt = (
            select(SurveyChangeRecord)
            .where(SurveyChangeRecord.batch_id == batch_id)
            .order_by(SurveyChangeRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        total_stmt = select(func.count(SurveyChangeRecord.id)).where(SurveyChangeRecord.batch_id == batch_id)
        filters = data_access_service.build_code_scope_filters(SurveyChangeRecord.cbfbm, current_user)
        if contractor_uid:
            filters.append(SurveyChangeRecord.contractor_uid == contractor_uid)
        if filters:
            stmt = stmt.where(*filters)
            total_stmt = total_stmt.where(*filters)
        return {
            "items": [self._serialize_change(item) for item in db.scalars(stmt).all()],
            "total": db.scalar(total_stmt) or 0,
            "page": page,
            "pageSize": page_size,
        }

    def get_phase2_context(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        return {
            "tags": self.list_tags(db, batch_id, contractor_uid, current_user),
            "restructures": self.list_restructures(db, batch_id, contractor_uid, current_user),
            "authorizations": self.list_authorizations(db, batch_id, contractor_uid, current_user),
            "attachments": self.list_attachments(db, batch_id, contractor_uid, current_user),
        }

    def list_tags(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> list[dict]:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        rows = db.scalars(
            select(SurveyHouseholdTag)
            .where(SurveyHouseholdTag.batch_id == batch_id, SurveyHouseholdTag.contractor_uid == contractor_uid)
            .order_by(SurveyHouseholdTag.is_active.desc(), SurveyHouseholdTag.tag_source.asc(), SurveyHouseholdTag.id.asc())
        ).all()
        return [self._serialize_tag(item) for item in rows]

    def refresh_auto_tags(self, db: Session, batch_id: int, contractor_uid: str, current_user: User, commit: bool = True) -> list[dict]:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        members = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.batch_id == batch_id,
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
        ).all()
        now = datetime.now(timezone.utc)
        detected: dict[str, tuple[str, str]] = {}
        if members and all(member.is_urban_settled or member.member_result_status == "urbanized" for member in members):
            detected["whole_family_urbanized"] = ("rule_all_members_urbanized", "全部家庭成员调查标记为进城落户")
        if result.result_status in {"extinct", "cancelled"} or (members and all(member.is_deceased or member.member_result_status == "deceased" for member in members)):
            detected["household_extinct"] = ("rule_household_extinct_or_all_deceased", "结果状态为整户消亡/注销，或全部成员死亡")
        if any(member.is_five_guarantees for member in members):
            detected["five_guarantees"] = ("rule_any_member_five_guarantees", "存在五保成员调查标记")
        if result.change_type == "little_or_no_land" or result.result_status == "little_or_no_land":
            detected["little_or_no_land"] = ("rule_result_marked_little_or_no_land", "调查结果标记为无地少地")

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
                item.disabled_reason = "自动规则当前不再命中"
        if commit:
            db.commit()
        return self.list_tags(db, batch_id, contractor_uid, current_user)

    def create_manual_tag(self, db: Session, batch_id: int, contractor_uid: str, payload: dict, current_user: User) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        self._ensure_editable_batch_and_result(db, result)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="农户标签不存在")
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        self._ensure_editable_batch_and_result(db, result)
        data_access_service.ensure_code_in_scope(current_user, item.cbfbm, detail="调查成果不在当前数据权限范围内")
        item.is_active = False
        item.disabled_reason = disabled_reason
        db.commit()
        db.refresh(item)
        return self._serialize_tag(item)

    def list_restructures(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> list[dict]:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        rows = db.scalars(
            select(SurveyHouseholdRestructure)
            .where(SurveyHouseholdRestructure.batch_id == batch_id, SurveyHouseholdRestructure.contractor_uid == contractor_uid)
            .order_by(SurveyHouseholdRestructure.id.desc())
        ).all()
        return [self._serialize_restructure(db, item) for item in rows]

    def save_restructure(self, db: Session, batch_id: int, contractor_uid: str, payload: dict, current_user: User, item_id: int | None = None) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        self._ensure_editable_batch_and_result(db, result)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        item = db.get(SurveyHouseholdRestructure, item_id) if item_id else None
        if item_id and item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分合户专项不存在")
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分合户专项不存在")
        return self.save_restructure(db, item.batch_id, item.contractor_uid, payload, current_user, item_id=restructure_id)

    def delete_restructure(self, db: Session, restructure_id: int, current_user: User) -> None:
        item = db.get(SurveyHouseholdRestructure, restructure_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分合户专项不存在")
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        self._ensure_editable_batch_and_result(db, result)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        db.execute(delete(SurveyHouseholdRestructureMember).where(SurveyHouseholdRestructureMember.restructure_id == item.id))
        db.delete(item)
        db.commit()

    def list_authorizations(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> list[dict]:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        rows = db.scalars(
            select(SurveyAuthorization)
            .where(SurveyAuthorization.batch_id == batch_id, SurveyAuthorization.contractor_uid == contractor_uid)
            .order_by(SurveyAuthorization.id.desc())
        ).all()
        return [self._serialize_authorization(item) for item in rows]

    def save_authorization(self, db: Session, batch_id: int, contractor_uid: str, payload: dict, current_user: User, item_id: int | None = None) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        self._ensure_editable_batch_and_result(db, result)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        item = db.get(SurveyAuthorization, item_id) if item_id else None
        if item_id and item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="授权委托不存在")
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="授权委托不存在")
        return self.save_authorization(db, item.batch_id, item.contractor_uid, payload, current_user, item_id=authorization_id)

    async def upload_authorization_file(self, db: Session, authorization_id: int, upload_file: UploadFile, current_user: User) -> dict:
        item = db.get(SurveyAuthorization, authorization_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="授权委托不存在")
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        self._ensure_editable_batch_and_result(db, result)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="授权委托文件不存在")
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        return item

    def build_authorization_template(self, db: Session, authorization_id: int, current_user: User) -> tuple[str, bytes]:
        item = db.get(SurveyAuthorization, authorization_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="授权委托不存在")
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        content = item.generated_content or self._build_authorization_text(result, item)
        return f"{item.authorization_no}_授权委托书.txt", content.encode("utf-8-sig")

    def revoke_authorization(self, db: Session, authorization_id: int, revoke_reason: str, current_user: User) -> dict:
        item = db.get(SurveyAuthorization, authorization_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="授权委托不存在")
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        self._ensure_editable_batch_and_result(db, result)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        item.status = "revoked"
        item.revoke_reason = revoke_reason
        db.commit()
        db.refresh(item)
        return self._serialize_authorization(item)

    def list_attachments(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> list[dict]:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        rows = db.scalars(
            select(SurveyAttachment)
            .where(SurveyAttachment.batch_id == batch_id, SurveyAttachment.contractor_uid == contractor_uid)
            .order_by(SurveyAttachment.id.desc())
        ).all()
        return [self._serialize_attachment(item) for item in rows]

    async def upload_attachment(self, db: Session, batch_id: int, contractor_uid: str, category: str, description: str | None, upload_file: UploadFile, current_user: User) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        self._ensure_editable_batch_and_result(db, result)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调查附件不存在")
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        return item

    def delete_attachment(self, db: Session, attachment_id: int, current_user: User) -> None:
        item = self.get_attachment(db, attachment_id, current_user)
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        self._ensure_editable_batch_and_result(db, result)
        try:
            Path(item.storage_path).unlink(missing_ok=True)
        except OSError:
            pass
        db.delete(item)
        db.commit()

    def generate_request_from_result(self, db: Session, batch_id: int, contractor_uid: str, payload: dict, current_user: User) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        if result.generated_request_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该调查成果已生成业务申请")
        request_type = payload.get("requestType") or self._infer_request_type(result)
        issuer_code = self._resolve_issuer_code(db, result.cbfbm)
        request_payload = {
            "requestType": request_type,
            "requestTitle": payload.get("requestTitle") or f"{request_type}-{result.cbfmc}-调查转办",
            "issuerCode": issuer_code,
            "contractorCode": result.cbfbm,
            "contractorName": result.cbfmc,
            "contractorIdType": result.cbfzjlx,
            "contractorIdNo": result.cbfzjhm,
            "mobile": result.lxdh,
            "address": result.cbfdz,
            "reason": payload.get("reason") or result.change_reason or result.evidence_summary,
            "note": payload.get("note") or f"由调查批次 {batch_id}、承包方 {result.cbfbm} 调查成果生成。",
        }
        created = request_case_service.create_case(db, request_payload, current_user)
        case_id = created["id"]
        serial_no = created["serialNo"]
        now = datetime.now(timezone.utc)
        result.generated_request_id = case_id
        result.generated_request_no = serial_no
        result.generated_request_at = now
        change_records = db.scalars(
            select(SurveyChangeRecord).where(
                SurveyChangeRecord.batch_id == batch_id,
                SurveyChangeRecord.contractor_uid == contractor_uid,
            )
        ).all()
        for change in change_records:
            change.generated_request_id = case_id
            change.generated_request_no = serial_no
            change.generated_request_at = now
        db.commit()
        return created

    def build_results_zip(self, db: Session, batch_id: int, current_user: User) -> tuple[str, bytes]:
        batch = self._ensure_batch(db, batch_id)
        task_filters = data_access_service.build_code_scope_filters(SurveyContractorTask.cbfbm, current_user)
        contractor_filters = data_access_service.build_code_scope_filters(SurveyCbfResult.cbfbm, current_user)
        member_filters = data_access_service.build_code_scope_filters(SurveyCbfJtcyResult.cbfbm, current_user)

        tasks = db.scalars(
            select(SurveyContractorTask)
            .where(SurveyContractorTask.batch_id == batch_id, *task_filters)
            .order_by(SurveyContractorTask.cbfbm.asc())
        ).all()
        contractors = db.scalars(
            select(SurveyCbfResult)
            .where(SurveyCbfResult.batch_id == batch_id, *contractor_filters)
            .order_by(SurveyCbfResult.cbfbm.asc())
        ).all()
        members = db.scalars(
            select(SurveyCbfJtcyResult)
            .where(SurveyCbfJtcyResult.batch_id == batch_id, *member_filters)
            .order_by(SurveyCbfJtcyResult.cbfbm.asc(), SurveyCbfJtcyResult.cyxm.asc(), SurveyCbfJtcyResult.cyzjhm.asc())
        ).all()
        diffs = db.scalars(
            select(SurveyChangeDiff)
            .where(SurveyChangeDiff.batch_id == batch_id)
            .order_by(SurveyChangeDiff.contractor_uid.asc(), SurveyChangeDiff.id.asc())
        ).all()
        allowed_uids = {item.contractor_uid for item in tasks}
        diffs = [item for item in diffs if item.contractor_uid in allowed_uids]

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("survey_tasks.csv", self._build_tasks_csv(tasks))
            archive.writestr("survey_cbf_result.csv", self._build_contractor_results_csv(contractors))
            archive.writestr("survey_cbf_jtcy_result.csv", self._build_member_results_csv(members))
            archive.writestr("survey_change_diffs.csv", self._build_change_diffs_csv(diffs))
        return f"survey_{batch.batch_no}_results.zip", zip_buffer.getvalue()

    def update_result(self, db: Session, batch_id: int, contractor_uid: str, payload: dict, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调查批次已结束，不能继续编辑")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调查成果已确认，不能继续编辑")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        data_access_service.ensure_code_in_scope(current_user, payload["code"], detail="调查成果不在当前数据权限范围内")
        now = datetime.now(timezone.utc)
        base = db.get(SurveyCbfBase, result.base_id)
        before_summary = self._summary_from_base(base) if base else self._summary_from_result(result)

        result.cbfbm = payload["code"]
        result.cbflx = payload["typeCode"]
        result.cbfmc = payload["name"]
        result.cbfzjlx = payload["idType"]
        result.cbfzjhm = payload["idNo"]
        result.cbfdz = payload["address"]
        result.yzbm = payload["postcode"]
        result.lxdh = payload.get("mobile")
        result.cbfcysl = len(payload.get("familyMembers") or []) if payload["typeCode"] == "1" else 0
        result.cbfdcrq = self._parse_datetime(payload.get("surveyDate"))
        result.cbfdcy = payload.get("surveyorName") or current_user.real_name
        result.cbfdcjs = payload.get("surveyNote")
        result.gsjs = payload.get("publicNoticeNote")
        result.gsjsr = payload.get("publicNoticeRecorder")
        result.gsshrq = self._parse_datetime(payload.get("publicNoticeReviewDate"))
        result.gsshr = payload.get("publicNoticeReviewer")
        result.group_region_code = payload.get("groupRegionCode")
        result.group_region_name = payload.get("groupRegionName")
        result.survey_status = payload.get("surveyStatus") or "surveyed"
        result.result_status = payload.get("resultStatus") or "normal"
        result.change_type = payload.get("changeType") or "none"
        result.change_reason = payload.get("changeReason")
        result.policy_basis = payload.get("policyBasis")
        result.evidence_summary = payload.get("evidenceSummary")
        result.remark = payload.get("remark")
        result.investigator_id = current_user.id
        result.investigator_name = current_user.real_name
        result.investigated_at = now

        db.execute(
            delete(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.batch_id == batch_id,
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
        )
        for item in payload.get("familyMembers") or []:
            member_uid = item.get("memberUid") or str(uuid4())
            member_base = db.scalars(
                select(SurveyCbfJtcyBase).where(
                    SurveyCbfJtcyBase.batch_id == batch_id,
                    SurveyCbfJtcyBase.member_uid == member_uid,
                )
            ).first()
            member = SurveyCbfJtcyResult(
                batch_id=batch_id,
                contractor_uid=contractor_uid,
                member_uid=member_uid,
                base_id=member_base.id if member_base else None,
                cbfbm=result.cbfbm,
                cyxm=item["name"],
                cyzjlx=item["idType"],
                cyzjhm=item["idNo"],
                cyxb=item["gender"],
                yhzgx=item["relationToHead"],
                cybz=item.get("noteCode"),
                sfgyr=item.get("isCoOwner"),
                cybzsm=item.get("note"),
                member_result_status=item.get("memberResultStatus") or ("normal" if member_base else "added"),
                survey_status=item.get("surveyStatus") or "surveyed",
                is_household_head=bool(item.get("isHouseholdHead")),
                is_urban_settled=bool(item.get("isUrbanSettled")),
                urban_settled_date=self._parse_datetime(item.get("urbanSettledDate")),
                urban_settled_place=item.get("urbanSettledPlace"),
                is_married_out_woman=bool(item.get("isMarriedOutWoman")),
                married_out_date=self._parse_datetime(item.get("marriedOutDate")),
                married_out_place=item.get("marriedOutPlace"),
                is_deceased=bool(item.get("isDeceased")),
                deceased_date=self._parse_datetime(item.get("deceasedDate")),
                is_five_guarantees=bool(item.get("isFiveGuarantees")),
                current_residence_address=item.get("currentResidenceAddress"),
                household_register_address=item.get("householdRegisterAddress"),
                phone=item.get("phone"),
                change_reason=item.get("changeReason"),
                policy_basis=item.get("policyBasis"),
                rights_disposition=item.get("rightsDisposition"),
                source_import_batch_id=member_base.source_import_batch_id if member_base else None,
                source_import_row_id=member_base.source_import_row_id if member_base else None,
                last_import_batch_id=member_base.last_import_batch_id if member_base else None,
                last_import_row_id=member_base.last_import_row_id if member_base else None,
                initialized_from_base_id=member_base.id if member_base else None,
                initialized_at=now,
                investigator_id=current_user.id,
                investigator_name=current_user.real_name,
                investigated_at=now,
                remark=item.get("remark"),
            )
            member.is_changed = self._member_changed(member, member_base)
            db.add(member)

        changed_members = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.batch_id == batch_id,
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
                SurveyCbfJtcyResult.is_changed.is_(True),
            )
        ).all()
        base_member_uids = {
            item.member_uid
            for item in db.scalars(
                select(SurveyCbfJtcyBase).where(
                    SurveyCbfJtcyBase.batch_id == batch_id,
                    SurveyCbfJtcyBase.contractor_uid == contractor_uid,
                )
            ).all()
        }
        result_member_uids = {
            item.member_uid
            for item in db.scalars(
                select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.batch_id == batch_id,
                    SurveyCbfJtcyResult.contractor_uid == contractor_uid,
                )
            ).all()
        }
        deleted_member_count = len(base_member_uids - result_member_uids)
        result.is_changed = self._contractor_changed(result, base) or bool(changed_members) or deleted_member_count > 0
        task = db.scalars(
            select(SurveyContractorTask).where(
                SurveyContractorTask.batch_id == batch_id,
                SurveyContractorTask.contractor_uid == contractor_uid,
            )
        ).first()
        if task:
            task.cbfbm = result.cbfbm
            task.cbfmc = result.cbfmc
            task.task_status = result.survey_status
            task.has_change = result.is_changed
            task.change_count = (1 if self._contractor_changed(result, base) else 0) + len(changed_members) + deleted_member_count
            task.investigated_at = now
            task.remark = result.remark

        after_summary = self._summary_from_result(result)
        change_record = None
        if result.is_changed or result.change_reason:
            change_record = SurveyChangeRecord(
                    batch_id=batch_id,
                    change_no=self._next_no(db, "CHG", SurveyChangeRecord.id),
                    contractor_uid=contractor_uid,
                    cbfbm=result.cbfbm,
                    change_type=result.change_type if result.change_type != "none" else "info_change",
                    change_level="household",
                    change_status="surveyed",
                    before_summary=before_summary,
                    after_summary=after_summary,
                    change_reason=result.change_reason,
                    policy_basis=result.policy_basis,
                    investigated_at=now,
                    investigator_id=current_user.id,
                    investigator_name=current_user.real_name,
                    remark=result.remark,
                )
            db.add(change_record)
            db.flush()
        self._rebuild_diffs(db, batch_id, contractor_uid, result, base, change_record.id if change_record else None)
        self.refresh_auto_tags(db, batch_id, contractor_uid, current_user, commit=False)
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def confirm_result(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调查批次已结束，不能继续确认")
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
        if result.survey_status not in {"surveyed", "changed", "unchanged"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先保存调查结果后再确认")
        self._validate_confirmable(db, result)
        now = datetime.now(timezone.utc)
        result.survey_status = "confirmed"
        result.confirmed_at = now
        result.reviewer_id = current_user.id
        result.reviewer_name = current_user.real_name
        result.reviewed_at = now
        task = db.scalars(
            select(SurveyContractorTask).where(
                SurveyContractorTask.batch_id == batch_id,
                SurveyContractorTask.contractor_uid == contractor_uid,
            )
        ).first()
        if task:
            task.task_status = "confirmed"
            task.confirmed_at = now
            task.reviewed_at = now
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def skip_task(self, db: Session, batch_id: int, contractor_uid: str, skip_reason: str, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调查批次已结束，不能继续操作")
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查任务不在当前数据权限范围内")
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调查成果已确认，不能跳过")
        now = datetime.now(timezone.utc)
        result.survey_status = "skipped"
        result.result_status = "normal"
        result.remark = skip_reason
        result.investigator_id = current_user.id
        result.investigator_name = current_user.real_name
        result.investigated_at = now
        task = db.scalars(
            select(SurveyContractorTask).where(
                SurveyContractorTask.batch_id == batch_id,
                SurveyContractorTask.contractor_uid == contractor_uid,
            )
        ).first()
        if task:
            task.task_status = "skipped"
            task.has_change = False
            task.change_count = 0
            task.skip_reason = skip_reason
            task.investigated_at = now
            task.remark = skip_reason
        db.commit()
        return self._serialize_task(task) if task else {}

    def finish_batch(self, db: Session, batch_id: int, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        unfinished = db.scalar(
            select(func.count(SurveyContractorTask.id)).where(
                SurveyContractorTask.batch_id == batch_id,
                SurveyContractorTask.task_status.notin_(["confirmed", "skipped"]),
            )
        ) or 0
        if unfinished:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"还有 {unfinished} 户未确认，不能结束批次")
        skipped_without_reason = db.scalar(
            select(func.count(SurveyContractorTask.id)).where(
                SurveyContractorTask.batch_id == batch_id,
                SurveyContractorTask.task_status == "skipped",
                or_(SurveyContractorTask.skip_reason.is_(None), SurveyContractorTask.skip_reason == ""),
            )
        ) or 0
        if skipped_without_reason:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"还有 {skipped_without_reason} 户跳过原因为空，不能结束批次")
        changed_confirmed = db.scalars(
            select(SurveyContractorTask).where(
                SurveyContractorTask.batch_id == batch_id,
                SurveyContractorTask.task_status == "confirmed",
                SurveyContractorTask.has_change.is_(True),
            )
        ).all()
        missing_change_trace = 0
        for task in changed_confirmed:
            diff_count = db.scalar(
                select(func.count(SurveyChangeDiff.id)).where(
                    SurveyChangeDiff.batch_id == batch_id,
                    SurveyChangeDiff.contractor_uid == task.contractor_uid,
                )
            ) or 0
            change_count = db.scalar(
                select(func.count(SurveyChangeRecord.id)).where(
                    SurveyChangeRecord.batch_id == batch_id,
                    SurveyChangeRecord.contractor_uid == task.contractor_uid,
                )
            ) or 0
            if diff_count == 0 and change_count == 0:
                missing_change_trace += 1
        if missing_change_trace:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"还有 {missing_change_trace} 户有变化但缺少变化记录，不能结束批次")
        batch.status = "finished"
        batch.ended_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(batch)
        return self._serialize_batch(db, batch)

    def _validate_confirmable(self, db: Session, result: SurveyCbfResult) -> None:
        members = db.scalars(
            select(SurveyCbfJtcyResult)
            .where(
                SurveyCbfJtcyResult.batch_id == result.batch_id,
                SurveyCbfJtcyResult.contractor_uid == result.contractor_uid,
            )
            .order_by(SurveyCbfJtcyResult.id.asc())
        ).all()
        errors: list[str] = []
        if result.cbflx == "1":
            if not members:
                errors.append("农户类型承包方必须至少保留 1 名家庭成员")
            household_heads = [member for member in members if member.is_household_head or member.yhzgx == "01"]
            if len(household_heads) != 1:
                errors.append("农户类型承包方必须且只能有 1 名户主")

        seen_id_nos: set[str] = set()
        for member in members:
            id_no = (member.cyzjhm or "").strip()
            if id_no:
                if id_no in seen_id_nos:
                    errors.append(f"家庭成员证件号码重复：{id_no}")
                    break
                seen_id_nos.add(id_no)

        if result.is_changed or result.change_type != "none":
            if not self._has_text(result.change_reason):
                errors.append("承包方存在变化时必须填写变化原因")
            if not self._has_text(result.policy_basis):
                errors.append("承包方存在变化时必须填写政策依据")

        for member in members:
            has_member_survey_change = member.is_changed or member.member_result_status != "normal" or any(
                [
                    member.is_urban_settled,
                    member.is_married_out_woman,
                    member.is_deceased,
                    member.is_five_guarantees,
                    self._has_text(member.rights_disposition),
                ]
            )
            if has_member_survey_change and not self._has_text(member.change_reason):
                errors.append(f"成员 {member.cyxm} 存在变化时必须填写变化原因")

        if errors:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="；".join(errors))

    def _ensure_editable_batch_and_result(self, db: Session, result: SurveyCbfResult) -> None:
        batch = self._ensure_batch(db, result.batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调查批次已结束，不能继续编辑")
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调查成果已确认，不能继续编辑")

    async def _store_upload(self, directory: Path, upload_file: UploadFile) -> tuple[Path, int]:
        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传文件为空")
        directory.mkdir(parents=True, exist_ok=True)
        suffix = Path(upload_file.filename or "").suffix
        storage_path = directory / f"{uuid4().hex}{suffix}"
        with storage_path.open("wb") as target:
            target.write(content)
        return storage_path, len(content)

    def _build_authorization_text(self, result: SurveyCbfResult, authorization: SurveyAuthorization) -> str:
        valid_from = authorization.valid_from.date().isoformat() if authorization.valid_from else "____年__月__日"
        valid_to = authorization.valid_to.date().isoformat() if authorization.valid_to else "____年__月__日"
        return (
            "授权委托书\n\n"
            f"委托人：{authorization.principal_name}\n"
            f"委托人证件号码：{authorization.principal_id_no or ''}\n"
            f"受托人：{authorization.agent_name}\n"
            f"受托人证件号码：{authorization.agent_id_no or ''}\n"
            f"受托人联系电话：{authorization.agent_phone or ''}\n\n"
            f"委托事项：{authorization.authorized_matters}\n\n"
            f"关联承包方：{result.cbfmc}（{result.cbfbm}）\n"
            f"有效期：{valid_from} 至 {valid_to}\n\n"
            "委托人签字：____________    受托人签字：____________\n"
            "日期：____年__月__日\n"
        )

    def _infer_request_type(self, result: SurveyCbfResult) -> str:
        if result.change_type in {"extinct"} or result.result_status in {"extinct", "cancelled"}:
            return "注销登记"
        return "变更登记"

    def _resolve_issuer_code(self, db: Session, cbfbm: str) -> str:
        candidates = [cbfbm[:14], cbfbm[:12], cbfbm[:9], cbfbm[:6]]
        for code in candidates:
            issuer = db.get(Fbf, code)
            if issuer is not None:
                return issuer.fbfbm
        issuer = db.scalars(select(Fbf).where(Fbf.fbfbm.like(f"{cbfbm[:12]}%")).limit(1)).first()
        if issuer is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无法根据承包方代码匹配发包方，不能生成业务申请")
        return issuer.fbfbm

    def _ensure_batch(self, db: Session, batch_id: int) -> SurveyBatch:
        batch = db.get(SurveyBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调查批次不存在")
        return batch

    def _get_result(self, db: Session, batch_id: int, contractor_uid: str) -> SurveyCbfResult:
        result = db.scalars(
            select(SurveyCbfResult).where(
                SurveyCbfResult.batch_id == batch_id,
                SurveyCbfResult.contractor_uid == contractor_uid,
            )
        ).first()
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调查成果不存在")
        return result

    def _result_from_base(self, base: SurveyCbfBase, now: datetime) -> SurveyCbfResult:
        return SurveyCbfResult(
            batch_id=base.batch_id,
            contractor_uid=base.contractor_uid,
            base_id=base.id,
            cbfbm=base.cbfbm,
            cbflx=base.cbflx,
            cbfmc=base.cbfmc,
            cbfzjlx=base.cbfzjlx,
            cbfzjhm=base.cbfzjhm,
            cbfdz=base.cbfdz,
            yzbm=base.yzbm,
            lxdh=base.lxdh,
            cbfcysl=base.cbfcysl,
            cbfdcrq=base.cbfdcrq,
            cbfdcy=base.cbfdcy,
            cbfdcjs=base.cbfdcjs,
            gsjs=base.gsjs,
            gsjsr=base.gsjsr,
            gsshrq=base.gsshrq,
            gsshr=base.gsshr,
            group_region_code=base.group_region_code,
            group_region_name=base.group_region_name,
            source_import_batch_id=base.source_import_batch_id,
            source_import_row_id=base.source_import_row_id,
            last_import_batch_id=base.last_import_batch_id,
            last_import_row_id=base.last_import_row_id,
            initialized_from_base_id=base.id,
            initialized_at=now,
        )

    def _member_result_from_base(self, base: SurveyCbfJtcyBase, now: datetime) -> SurveyCbfJtcyResult:
        return SurveyCbfJtcyResult(
            batch_id=base.batch_id,
            contractor_uid=base.contractor_uid,
            member_uid=base.member_uid,
            base_id=base.id,
            cbfbm=base.cbfbm,
            cyxm=base.cyxm,
            cyzjlx=base.cyzjlx,
            cyzjhm=base.cyzjhm,
            cyxb=base.cyxb,
            yhzgx=base.yhzgx,
            cybz=base.cybz,
            sfgyr=base.sfgyr,
            cybzsm=base.cybzsm,
            is_household_head=base.yhzgx == "01",
            source_import_batch_id=base.source_import_batch_id,
            source_import_row_id=base.source_import_row_id,
            last_import_batch_id=base.last_import_batch_id,
            last_import_row_id=base.last_import_row_id,
            initialized_from_base_id=base.id,
            initialized_at=now,
        )

    def _contractor_changed(self, result: SurveyCbfResult, base: SurveyCbfBase | None) -> bool:
        if base is None:
            return True
        fields = ["cbfbm", "cbflx", "cbfmc", "cbfzjlx", "cbfzjhm", "cbfdz", "yzbm", "lxdh", "cbfcysl"]
        return any(getattr(result, field) != getattr(base, field) for field in fields) or result.change_type != "none"

    def _member_changed(self, result: SurveyCbfJtcyResult, base: SurveyCbfJtcyBase | None) -> bool:
        if base is None:
            return True
        fields = ["cbfbm", "cyxm", "cyzjlx", "cyzjhm", "cyxb", "yhzgx", "cybz", "sfgyr", "cybzsm"]
        survey_flags_changed = any(
            [
                result.is_urban_settled,
                result.is_married_out_woman,
                result.is_deceased,
                result.is_five_guarantees,
                bool(result.current_residence_address),
                bool(result.household_register_address),
                bool(result.phone),
                bool(result.change_reason),
                bool(result.policy_basis),
                bool(result.rights_disposition),
            ]
        )
        return any(getattr(result, field) != getattr(base, field) for field in fields) or result.member_result_status != "normal" or survey_flags_changed

    def _summary_from_base(self, base: SurveyCbfBase) -> dict:
        return {
            "code": base.cbfbm,
            "name": base.cbfmc,
            "idNo": base.cbfzjhm,
            "address": base.cbfdz,
            "memberCount": base.cbfcysl,
        }

    def _summary_from_result(self, result: SurveyCbfResult) -> dict:
        return {
            "code": result.cbfbm,
            "name": result.cbfmc,
            "idNo": result.cbfzjhm,
            "address": result.cbfdz,
            "memberCount": result.cbfcysl,
            "surveyStatus": result.survey_status,
            "resultStatus": result.result_status,
        }

    def _serialize_batch(self, db: Session, item: SurveyBatch) -> dict:
        task_count = db.scalar(select(func.count(SurveyContractorTask.id)).where(SurveyContractorTask.batch_id == item.id)) or 0
        not_started_count = db.scalar(
            select(func.count(SurveyContractorTask.id)).where(
                SurveyContractorTask.batch_id == item.id,
                SurveyContractorTask.task_status == "not_started",
            )
        ) or 0
        surveyed_count = db.scalar(
            select(func.count(SurveyContractorTask.id)).where(
                SurveyContractorTask.batch_id == item.id,
                SurveyContractorTask.task_status.in_(["surveyed", "changed", "unchanged", "confirmed"]),
            )
        ) or 0
        changed_count = db.scalar(
            select(func.count(SurveyContractorTask.id)).where(SurveyContractorTask.batch_id == item.id, SurveyContractorTask.has_change.is_(True))
        ) or 0
        confirmed_count = db.scalar(
            select(func.count(SurveyContractorTask.id)).where(
                SurveyContractorTask.batch_id == item.id,
                SurveyContractorTask.task_status == "confirmed",
            )
        ) or 0
        skipped_count = db.scalar(
            select(func.count(SurveyContractorTask.id)).where(
                SurveyContractorTask.batch_id == item.id,
                SurveyContractorTask.task_status == "skipped",
            )
        ) or 0
        return {
            "id": item.id,
            "batchNo": item.batch_no,
            "batchName": item.batch_name,
            "regionCode": item.region_code,
            "regionName": item.region_name,
            "surveyType": item.survey_type,
            "status": item.status,
            "taskCount": task_count,
            "notStartedCount": not_started_count,
            "surveyedCount": surveyed_count,
            "changedCount": changed_count,
            "confirmedCount": confirmed_count,
            "skippedCount": skipped_count,
            "createdAt": item.created_at,
            "remark": item.remark,
        }

    def _serialize_task(self, item: SurveyContractorTask) -> dict:
        return {
            "id": item.id,
            "batchId": item.batch_id,
            "contractorUid": item.contractor_uid,
            "cbfbm": item.cbfbm,
            "cbfmc": item.cbfmc,
            "regionCode": item.region_code,
            "taskStatus": item.task_status,
            "hasChange": item.has_change,
            "changeCount": item.change_count,
            "investigatedAt": item.investigated_at,
            "remark": item.remark,
        }

    def _serialize_change(self, item: SurveyChangeRecord) -> dict:
        return {
            "id": item.id,
            "changeNo": item.change_no,
            "batchId": item.batch_id,
            "contractorUid": item.contractor_uid,
            "cbfbm": item.cbfbm,
            "changeType": item.change_type,
            "changeLevel": item.change_level,
            "changeStatus": item.change_status,
            "changeReason": item.change_reason,
            "policyBasis": item.policy_basis,
            "generatedRequestId": item.generated_request_id,
            "generatedRequestNo": item.generated_request_no,
            "investigatorName": item.investigator_name,
            "investigatedAt": item.investigated_at,
            "createdAt": item.created_at,
        }

    def _serialize_diff(self, item: SurveyChangeDiff) -> dict:
        return {
            "id": item.id,
            "batchId": item.batch_id,
            "contractorUid": item.contractor_uid,
            "changeId": item.change_id,
            "entityType": item.entity_type,
            "entityUid": item.entity_uid,
            "entityName": item.entity_name,
            "fieldName": item.field_name,
            "fieldLabel": item.field_label,
            "beforeValue": item.before_value,
            "afterValue": item.after_value,
            "changeReason": item.change_reason,
            "createdAt": item.created_at,
        }

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

    def _rebuild_diffs(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        result: SurveyCbfResult,
        base: SurveyCbfBase | None,
        change_id: int | None,
    ) -> None:
        db.execute(
            delete(SurveyChangeDiff).where(
                SurveyChangeDiff.batch_id == batch_id,
                SurveyChangeDiff.contractor_uid == contractor_uid,
            )
        )
        if base is not None:
            contractor_fields = [
                ("cbfbm", "承包方代码"),
                ("cbflx", "承包方类型"),
                ("cbfmc", "承包方名称"),
                ("cbfzjlx", "证件类型"),
                ("cbfzjhm", "证件号码"),
                ("cbfdz", "承包方地址"),
                ("yzbm", "邮政编码"),
                ("lxdh", "联系电话"),
                ("cbfcysl", "家庭成员数"),
                ("group_region_code", "所属组代码"),
                ("group_region_name", "所属组名称"),
            ]
            for field_name, field_label in contractor_fields:
                before = getattr(base, field_name)
                after = getattr(result, field_name)
                if self._diff_value(before) != self._diff_value(after):
                    db.add(
                        SurveyChangeDiff(
                            batch_id=batch_id,
                            contractor_uid=contractor_uid,
                            change_id=change_id,
                            entity_type="contractor",
                            entity_uid=contractor_uid,
                            entity_name=result.cbfmc,
                            field_name=field_name,
                            field_label=field_label,
                            before_value=self._diff_value(before),
                            after_value=self._diff_value(after),
                            change_reason=result.change_reason,
                        )
                    )

        base_members = {
            item.member_uid: item
            for item in db.scalars(
                select(SurveyCbfJtcyBase).where(
                    SurveyCbfJtcyBase.batch_id == batch_id,
                    SurveyCbfJtcyBase.contractor_uid == contractor_uid,
                )
            ).all()
        }
        result_members = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.batch_id == batch_id,
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
        ).all()
        member_fields = [
            ("cyxm", "姓名"),
            ("cyzjlx", "证件类型"),
            ("cyzjhm", "证件号码"),
            ("cyxb", "性别"),
            ("yhzgx", "与户主关系"),
            ("cybz", "成员备注代码"),
            ("sfgyr", "是否共有人"),
            ("cybzsm", "成员备注说明"),
            ("member_result_status", "成员调查状态"),
            ("is_urban_settled", "是否进城落户"),
            ("is_married_out_woman", "是否外嫁女"),
            ("is_deceased", "是否死亡"),
            ("is_five_guarantees", "是否五保"),
            ("rights_disposition", "权益处置"),
        ]
        for member in result_members:
            member_base = base_members.get(member.member_uid)
            if member_base is None:
                db.add(
                    SurveyChangeDiff(
                        batch_id=batch_id,
                        contractor_uid=contractor_uid,
                        change_id=change_id,
                        entity_type="member",
                        entity_uid=member.member_uid,
                        entity_name=member.cyxm,
                        field_name="member",
                        field_label="新增成员",
                        before_value=None,
                        after_value=f"{member.cyxm} / {member.cyzjhm}",
                        change_reason=member.change_reason,
                    )
                )
                continue
            for field_name, field_label in member_fields:
                before = getattr(member_base, field_name, None)
                after = getattr(member, field_name, None)
                if self._diff_value(before) != self._diff_value(after):
                    db.add(
                        SurveyChangeDiff(
                            batch_id=batch_id,
                            contractor_uid=contractor_uid,
                            change_id=change_id,
                            entity_type="member",
                            entity_uid=member.member_uid,
                            entity_name=member.cyxm,
                            field_name=field_name,
                            field_label=field_label,
                            before_value=self._diff_value(before),
                            after_value=self._diff_value(after),
                            change_reason=member.change_reason,
                        )
                    )
        result_member_uids = {member.member_uid for member in result_members}
        for member_uid, member_base in base_members.items():
            if member_uid not in result_member_uids:
                db.add(
                    SurveyChangeDiff(
                        batch_id=batch_id,
                        contractor_uid=contractor_uid,
                        change_id=change_id,
                        entity_type="member",
                        entity_uid=member_uid,
                        entity_name=member_base.cyxm,
                        field_name="member",
                        field_label="删除成员",
                        before_value=f"{member_base.cyxm} / {member_base.cyzjhm}",
                        after_value=None,
                        change_reason=result.change_reason,
                    )
                )

    def _diff_value(self, value) -> str | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return "是" if value else "否"
        if isinstance(value, datetime):
            return value.date().isoformat()
        return str(value)

    def _has_text(self, value: str | None) -> bool:
        return bool(str(value or "").strip())

    def _csv_bytes(self, headers: list[str], rows: list[list[object]]) -> bytes:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return output.getvalue().encode("utf-8-sig")

    def _date_text(self, value: datetime | None) -> str:
        return value.date().isoformat() if value else ""

    def _bool_text(self, value: bool | None) -> str:
        return "是" if value else "否"

    def _build_tasks_csv(self, tasks: list[SurveyContractorTask]) -> bytes:
        return self._csv_bytes(
            ["批次内唯一标识", "承包方代码", "承包方名称", "任务状态", "是否变化", "变化数量", "调查时间", "确认时间", "跳过原因"],
            [
                [
                    item.contractor_uid,
                    item.cbfbm,
                    item.cbfmc,
                    item.task_status,
                    self._bool_text(item.has_change),
                    item.change_count,
                    self._date_text(item.investigated_at),
                    self._date_text(item.confirmed_at),
                    item.skip_reason or "",
                ]
                for item in tasks
            ],
        )

    def _build_contractor_results_csv(self, contractors: list[SurveyCbfResult]) -> bytes:
        return self._csv_bytes(
            [
                "批次内唯一标识",
                "承包方代码",
                "承包方类型",
                "承包方名称",
                "证件类型",
                "证件号码",
                "承包方地址",
                "邮政编码",
                "联系电话",
                "家庭成员数",
                "调查状态",
                "结果状态",
                "是否变化",
                "变化类型",
                "变化原因",
                "政策依据",
                "依据材料摘要",
                "调查人",
                "调查时间",
                "确认人",
                "确认时间",
                "来源导入批次ID",
                "来源导入行ID",
                "最近导入批次ID",
                "最近导入行ID",
            ],
            [
                [
                    item.contractor_uid,
                    item.cbfbm,
                    item.cbflx,
                    item.cbfmc,
                    item.cbfzjlx,
                    item.cbfzjhm,
                    item.cbfdz,
                    item.yzbm,
                    item.lxdh or "",
                    item.cbfcysl,
                    item.survey_status,
                    item.result_status,
                    self._bool_text(item.is_changed),
                    item.change_type,
                    item.change_reason or "",
                    item.policy_basis or "",
                    item.evidence_summary or "",
                    item.investigator_name or "",
                    self._date_text(item.investigated_at),
                    item.reviewer_name or "",
                    self._date_text(item.confirmed_at),
                    item.source_import_batch_id or "",
                    item.source_import_row_id or "",
                    item.last_import_batch_id or "",
                    item.last_import_row_id or "",
                ]
                for item in contractors
            ],
        )

    def _build_member_results_csv(self, members: list[SurveyCbfJtcyResult]) -> bytes:
        return self._csv_bytes(
            [
                "批次内户唯一标识",
                "成员唯一标识",
                "承包方代码",
                "成员姓名",
                "证件类型",
                "证件号码",
                "性别",
                "与户主关系",
                "成员状态",
                "是否变化",
                "是否户主",
                "是否进城落户",
                "是否外嫁女",
                "是否死亡",
                "是否五保",
                "变化原因",
                "政策依据",
                "权益处置",
                "来源导入批次ID",
                "来源导入行ID",
                "最近导入批次ID",
                "最近导入行ID",
            ],
            [
                [
                    item.contractor_uid,
                    item.member_uid,
                    item.cbfbm,
                    item.cyxm,
                    item.cyzjlx,
                    item.cyzjhm,
                    item.cyxb,
                    item.yhzgx,
                    item.member_result_status,
                    self._bool_text(item.is_changed),
                    self._bool_text(item.is_household_head),
                    self._bool_text(item.is_urban_settled),
                    self._bool_text(item.is_married_out_woman),
                    self._bool_text(item.is_deceased),
                    self._bool_text(item.is_five_guarantees),
                    item.change_reason or "",
                    item.policy_basis or "",
                    item.rights_disposition or "",
                    item.source_import_batch_id or "",
                    item.source_import_row_id or "",
                    item.last_import_batch_id or "",
                    item.last_import_row_id or "",
                ]
                for item in members
            ],
        )

    def _build_change_diffs_csv(self, diffs: list[SurveyChangeDiff]) -> bytes:
        return self._csv_bytes(
            ["批次内户唯一标识", "对象类型", "对象唯一标识", "对象名称", "字段名", "字段中文名", "调查前", "调查后", "变化原因"],
            [
                [
                    item.contractor_uid,
                    item.entity_type,
                    item.entity_uid,
                    item.entity_name or "",
                    item.field_name,
                    item.field_label,
                    item.before_value or "",
                    item.after_value or "",
                    item.change_reason or "",
                ]
                for item in diffs
            ],
        )

    def _serialize_result(
        self,
        item: SurveyCbfResult,
        members: list[SurveyCbfJtcyResult],
        base: SurveyCbfBase | None = None,
        base_members: list[SurveyCbfJtcyBase] | None = None,
    ) -> dict:
        return {
            "id": item.id,
            "batchId": item.batch_id,
            "contractorUid": item.contractor_uid,
            "baseId": item.base_id,
            "code": item.cbfbm,
            "typeCode": item.cbflx,
            "name": item.cbfmc,
            "idType": item.cbfzjlx,
            "idNo": item.cbfzjhm,
            "address": item.cbfdz,
            "postcode": item.yzbm,
            "mobile": item.lxdh,
            "memberCount": item.cbfcysl,
            "surveyDate": item.cbfdcrq.date().isoformat() if item.cbfdcrq else None,
            "surveyorName": item.cbfdcy,
            "surveyNote": item.cbfdcjs,
            "publicNoticeNote": item.gsjs,
            "publicNoticeRecorder": item.gsjsr,
            "publicNoticeReviewDate": item.gsshrq.date().isoformat() if item.gsshrq else None,
            "publicNoticeReviewer": item.gsshr,
            "groupRegionCode": item.group_region_code,
            "groupRegionName": item.group_region_name,
            "surveyStatus": item.survey_status,
            "resultStatus": item.result_status,
            "isChanged": item.is_changed,
            "changeType": item.change_type,
            "changeReason": item.change_reason,
            "policyBasis": item.policy_basis,
            "evidenceSummary": item.evidence_summary,
            "remark": item.remark,
            "generatedRequestId": item.generated_request_id,
            "generatedRequestNo": item.generated_request_no,
            "baseContractor": self._serialize_base(base, base_members or []) if base else None,
            "familyMembers": [self._serialize_member(member) for member in members],
        }

    def _serialize_base(self, item: SurveyCbfBase, members: list[SurveyCbfJtcyBase]) -> dict:
        return {
            "code": item.cbfbm,
            "typeCode": item.cbflx,
            "name": item.cbfmc,
            "idType": item.cbfzjlx,
            "idNo": item.cbfzjhm,
            "address": item.cbfdz,
            "postcode": item.yzbm,
            "mobile": item.lxdh,
            "memberCount": item.cbfcysl,
            "surveyDate": item.cbfdcrq.date().isoformat() if item.cbfdcrq else None,
            "surveyorName": item.cbfdcy,
            "surveyNote": item.cbfdcjs,
            "publicNoticeNote": item.gsjs,
            "publicNoticeRecorder": item.gsjsr,
            "publicNoticeReviewDate": item.gsshrq.date().isoformat() if item.gsshrq else None,
            "publicNoticeReviewer": item.gsshr,
            "groupRegionCode": item.group_region_code,
            "groupRegionName": item.group_region_name,
            "familyMembers": [self._serialize_base_member(member) for member in members],
        }

    def _serialize_base_member(self, item: SurveyCbfJtcyBase) -> dict:
        return {
            "memberUid": item.member_uid,
            "name": item.cyxm,
            "gender": item.cyxb,
            "idType": item.cyzjlx,
            "idNo": item.cyzjhm,
            "relationToHead": item.yhzgx,
            "noteCode": item.cybz,
            "isCoOwner": item.sfgyr,
            "note": item.cybzsm,
        }

    def _serialize_member(self, item: SurveyCbfJtcyResult) -> dict:
        return {
            "memberUid": item.member_uid,
            "baseId": item.base_id,
            "name": item.cyxm,
            "gender": item.cyxb,
            "idType": item.cyzjlx,
            "idNo": item.cyzjhm,
            "relationToHead": item.yhzgx,
            "noteCode": item.cybz,
            "isCoOwner": item.sfgyr,
            "note": item.cybzsm,
            "memberResultStatus": item.member_result_status,
            "surveyStatus": item.survey_status,
            "isChanged": item.is_changed,
            "isHouseholdHead": item.is_household_head,
            "isUrbanSettled": item.is_urban_settled,
            "urbanSettledDate": item.urban_settled_date.date().isoformat() if item.urban_settled_date else None,
            "urbanSettledPlace": item.urban_settled_place,
            "isMarriedOutWoman": item.is_married_out_woman,
            "marriedOutDate": item.married_out_date.date().isoformat() if item.married_out_date else None,
            "marriedOutPlace": item.married_out_place,
            "isDeceased": item.is_deceased,
            "deceasedDate": item.deceased_date.date().isoformat() if item.deceased_date else None,
            "isFiveGuarantees": item.is_five_guarantees,
            "currentResidenceAddress": item.current_residence_address,
            "householdRegisterAddress": item.household_register_address,
            "phone": item.phone,
            "changeReason": item.change_reason,
            "policyBasis": item.policy_basis,
            "rightsDisposition": item.rights_disposition,
            "remark": item.remark,
        }

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.combine(datetime.strptime(value, fmt).date(), datetime.min.time())
            except ValueError:
                pass
        return datetime.combine(date.fromisoformat(value), datetime.min.time())

    def _next_no(self, db: Session, prefix: str, id_column) -> str:
        next_id = (db.scalar(select(func.max(id_column))) or 0) + 1
        return f"{prefix}{datetime.now():%Y%m%d}{next_id:04d}"


survey_service = SurveyService()
