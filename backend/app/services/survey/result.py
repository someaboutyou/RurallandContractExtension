import logging
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyCbfBase,
    SurveyCbfJtcyBase,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyCbdkxxResult,
    SurveyChangeRecord,
    SurveyFbfBase,
    SurveyFbfResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service

logger = logging.getLogger(__name__)

class SurveyServiceResultMixin:
    def get_result(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
        data_batch_id = batch_id
        members = db.scalars(
            select(SurveyCbfJtcyResult)
            .where(
                SurveyCbfJtcyResult.tenant_code == result.tenant_code,
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
            .order_by(SurveyCbfJtcyResult.cyxm, SurveyCbfJtcyResult.cyzjhm)
            .execution_options(skip_tenant_scope=True)
        ).all()
        base = db.scalars(
            select(SurveyCbfBase)
            .where(
                SurveyCbfBase.tenant_code == result.tenant_code,
                SurveyCbfBase.batch_id == data_batch_id,
                SurveyCbfBase.contractor_uid == contractor_uid,
                SurveyCbfBase.initialized_from_table.in_(["survey_cbf_result", "manual_add"]),
            )
            .order_by(SurveyCbfBase.id.asc())
            .execution_options(skip_tenant_scope=True)
        ).first()
        base_members = db.scalars(
            select(SurveyCbfJtcyBase)
            .where(
                SurveyCbfJtcyBase.tenant_code == result.tenant_code,
                SurveyCbfJtcyBase.batch_id == data_batch_id,
                SurveyCbfJtcyBase.contractor_uid == contractor_uid,
            )
            .order_by(SurveyCbfJtcyBase.cyxm, SurveyCbfJtcyBase.cyzjhm)
            .execution_options(skip_tenant_scope=True)
        ).all()
        issuer, base_issuer = self._get_result_issuer(db, result)
        return self._serialize_result(result, members, batch_id, base, base_members, issuer, base_issuer)


    def update_result(self, db: Session, batch_id: int, contractor_uid: str, payload: dict, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幍瑙勵偧瀹歌尙绮ㄩ弶鐕傜礉娑撳秷鍏樼紒褏鐢荤紓鏍帆")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幋鎰亯瀹歌尙鈥樼拋銈忕礉娑撳秷鍏樼紒褏鐢荤紓鏍帆")
        if result.result_status in {"cancelled", "extinct"} or result.change_type in self.terminal_operation_types:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该承包户已注销，撤回注销、分户或合并操作后才能修改")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        data_access_service.ensure_code_in_scope(current_user, payload["code"], detail="out of scope")
        now = datetime.now(timezone.utc)
        data_batch_id = batch_id
        base = db.scalar(
            select(SurveyCbfBase)
            .where(
                SurveyCbfBase.batch_id == data_batch_id,
                SurveyCbfBase.contractor_uid == result.contractor_uid,
                SurveyCbfBase.initialized_from_table.in_(["survey_cbf_result", "manual_add"]),
            )
            .order_by(SurveyCbfBase.id.asc())
        )
        before_summary = self._summary_from_base(base) if base else self._summary_from_result(result)
        issuer_payload = None
        issuer = None
        base_issuer = None
        issuer_changed = False
        issuer_before_summary = None
        deleted_member_reasons = {
            item.get("memberUid"): item.get("changeReason")
            for item in payload.get("deletedMembers") or []
            if item.get("memberUid")
        }
        pending_operations = payload.get("pendingOperations") or []
        has_terminal_operation = any(
            (operation.get("type") if isinstance(operation, dict) else None) in self.terminal_operation_types
            for operation in pending_operations
        )
        if issuer_payload:
            issuer, base_issuer = self._get_result_issuer(db, result)
            if issuer is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="閸欐垵瀵橀弬纭呯殶閺屻儲鍨氶弸婊€绗夌€涙ê婀?")
            data_access_service.ensure_code_in_scope(current_user, issuer.fbfbm, detail="閸欐垵瀵橀弬閫涚瑝閸︺劌缍嬮崜宥嗘殶閹诡喗娼堥梽鎰瘱閸ユ潙鍞?")
            data_access_service.ensure_code_in_scope(current_user, issuer_payload["code"], detail="閸欐垵瀵橀弬閫涚瑝閸︺劌缍嬮崜宥嗘殶閹诡喗娼堥梽鎰瘱閸ユ潙鍞?")
            issuer_before_summary = self._issuer_summary_from_base(base_issuer) if base_issuer else self._issuer_summary_from_result(issuer)

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
        # Terminal operations own the lifecycle state.  Do not let the UI preview
        # overwrite the pre-operation state before its rollback snapshot is made.
        if not has_terminal_operation:
            result.result_status = payload.get("resultStatus") or "normal"
        if not has_terminal_operation:
            result.change_type = payload.get("changeType") or "none"
            result.change_reason = payload.get("changeReason")
        result.policy_basis = payload.get("policyBasis")
        result.evidence_summary = payload.get("evidenceSummary")
        result.remark = payload.get("remark")
        result.investigator_id = current_user.id
        result.investigator_name = current_user.real_name
        result.investigated_at = now

        if issuer_payload and issuer:
            old_fbfbm = issuer.fbfbm
            issuer.fbfbm = issuer_payload["code"]
            issuer.fbfmc = issuer_payload["name"]
            issuer.fbffzrxm = issuer_payload["responsibleName"]
            issuer.fzrzjlx = issuer_payload["responsibleIdType"]
            issuer.fzrzjhm = issuer_payload["responsibleIdNo"]
            issuer.lxdh = issuer_payload.get("phone")
            issuer.fbfdz = issuer_payload["address"]
            issuer.yzbm = issuer_payload["postcode"]
            issuer.fbfdcy = issuer_payload.get("surveyorName") or current_user.real_name
            issuer.fbfdcrq = self._parse_datetime(issuer_payload.get("surveyDate")) or issuer.fbfdcrq
            issuer.fbfdcjs = issuer_payload.get("surveyNote")
            issuer.survey_status = issuer_payload.get("surveyStatus") or "surveyed"
            issuer.result_status = issuer_payload.get("resultStatus") or "normal"
            issuer.change_type = issuer_payload.get("changeType") or "none"
            issuer.change_reason = issuer_payload.get("changeReason")
            issuer.policy_basis = issuer_payload.get("policyBasis")
            issuer.remark = issuer_payload.get("remark")
            issuer.investigator_id = current_user.id
            issuer.investigator_name = current_user.real_name
            issuer.investigated_at = now
            issuer_changed = self._issuer_changed(issuer, base_issuer)
            issuer.is_changed = issuer_changed
            if old_fbfbm != issuer.fbfbm:
                db.execute(
                    update(SurveyCbdkxxResult)
                    .where(
                        SurveyCbdkxxResult.fbfbm == old_fbfbm,
                    )
                    .values(fbfbm=issuer.fbfbm)
                )

        db.execute(
            delete(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
        )
        for item in payload.get("familyMembers") or []:
            member_uid = item.get("memberUid") or str(uuid4())
            member_base = db.scalars(
                select(SurveyCbfJtcyBase).where(
                    SurveyCbfJtcyBase.batch_id == data_batch_id,
                    SurveyCbfJtcyBase.member_uid == member_uid,
                )
            ).first()
            member = SurveyCbfJtcyResult(
                contractor_uid=contractor_uid,
                member_uid=member_uid,
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
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
                SurveyCbfJtcyResult.is_changed.is_(True),
            )
        ).all()
        base_member_uids = {
            item.member_uid
            for item in db.scalars(
                select(SurveyCbfJtcyBase).where(
                    SurveyCbfJtcyBase.batch_id == data_batch_id,
                    SurveyCbfJtcyBase.contractor_uid == contractor_uid,
                )
            ).all()
        }
        result_member_uids = {
            item.member_uid
            for item in db.scalars(
                select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.contractor_uid == contractor_uid,
                )
            ).all()
        }
        deleted_member_count = len(base_member_uids - result_member_uids)
        contractor_changed = self._contractor_changed(result, base)
        result.is_changed = contractor_changed or bool(changed_members) or deleted_member_count > 0 or issuer_changed
        form_change_count = (1 if contractor_changed else 0) + (1 if issuer_changed else 0) + len(changed_members) + deleted_member_count
        after_summary = self._summary_from_result(result)
        if issuer_payload and issuer:
            before_summary["issuer"] = issuer_before_summary
            after_summary["issuer"] = self._issuer_summary_from_result(issuer)
        change_record = None
        if not has_terminal_operation and (result.is_changed or result.change_reason):
            change_record = SurveyChangeRecord(
                    tenant_code=batch.tenant_code,
                    region_code=result.group_region_code or result.region_code,
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
        # Terminal household operations query the member rows that were rebuilt
        # above. Flush first so merge/split always sees the current form state.
        db.flush()
        self._apply_pending_operations(db, batch_id, contractor_uid, pending_operations, current_user)
        if not has_terminal_operation:
            preserved_operation_change_count = db.scalar(
                select(func.count(SurveyChangeRecord.id)).where(
                    SurveyChangeRecord.batch_id == batch_id,
                    SurveyChangeRecord.contractor_uid == contractor_uid,
                    SurveyChangeRecord.change_type.in_(self.operation_change_types),
                )
            ) or 0
            task = db.scalars(
                select(SurveyCbfBase).where(
                    SurveyCbfBase.batch_id == batch_id,
                    SurveyCbfBase.contractor_uid == contractor_uid,
                )
            ).first()
            if task is None:
                task = SurveyCbfBase(
                    tenant_code=result.tenant_code,
                    region_code=result.group_region_code or result.region_code,
                    batch_id=batch_id,
                    contractor_uid=contractor_uid,
                    cbfbm=result.cbfbm,
                    cbfmc=result.cbfmc,
                )
                db.add(task)
            if task:
                task.cbfbm = result.cbfbm
                task.cbfmc = result.cbfmc
                task.task_status = result.survey_status
                task.has_change = result.is_changed or preserved_operation_change_count > 0
                task.change_count = form_change_count + preserved_operation_change_count
                task.investigated_at = now
                task.remark = result.remark
            affected_uids = self._collect_diff_rebuild_uids(batch_id, contractor_uid, pending_operations)
            self._rebuild_contractor_diffs(
                db,
                batch_id,
                affected_uids,
                change_ids={contractor_uid: change_record.id if change_record else None},
                deleted_member_reasons={contractor_uid: deleted_member_reasons},
            )
            self.refresh_auto_tags(db, batch_id, contractor_uid, current_user, commit=False)
        db.commit()
        if has_terminal_operation:
            return {"contractorUid": contractor_uid, "status": "closed"}
        return self.get_result(db, batch_id, contractor_uid, current_user)


    def get_phase2_context(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
        return {
            "tags": self.list_tags(db, batch_id, contractor_uid, current_user),
            "restructures": self.list_restructures(db, batch_id, contractor_uid, current_user),
            "authorizations": self.list_authorizations(db, batch_id, contractor_uid, current_user),
            "attachments": self.list_attachments(db, batch_id, contractor_uid, current_user),
        }


    def create_contractor(self, db: Session, batch_id: int, payload: dict, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幍瑙勵偧瀹歌尙绮ㄩ弶鐕傜礉娑撳秷鍏橀弬鏉款杻")
        code = payload["code"].strip()
        data_access_service.ensure_code_in_scope(current_user, code, detail="contractor is out of scope")
        if batch.region_code and not code.startswith(batch.region_code):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="contractor code is outside the batch region")
        exists = db.scalars(
            select(SurveyCbfBase).where(
                SurveyCbfBase.tenant_code == batch.tenant_code,
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.cbfbm == code,
            ).execution_options(skip_tenant_scope=True)
        ).first()
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="contractor survey result already exists")

        now = datetime.now(timezone.utc)
        contractor_uid = str(uuid5(NAMESPACE_URL, f"survey:{batch_id}:cbf:{code}"))
        group_region_code = payload.get("groupRegionCode") or batch.region_code
        base = SurveyCbfBase(
            tenant_code=batch.tenant_code,
            region_code=group_region_code or batch.region_code,
            batch_id=batch_id,
            contractor_uid=contractor_uid,
            source_cbfbm=code,
            cbfbm=code,
            cbflx=payload.get("typeCode") or "1",
            cbfmc=payload["name"],
            cbfzjlx=payload.get("idType") or "1",
            cbfzjhm=payload["idNo"],
            cbfdz=payload["address"],
            yzbm=payload.get("postcode") or "000000",
            lxdh=payload.get("mobile"),
            cbfcysl=0,
            cbfdcrq=self._parse_datetime(payload.get("surveyDate")),
            cbfdcy=payload.get("surveyorName") or current_user.real_name,
            cbfdcjs=None,
            group_region_code=group_region_code,
            group_region_name=payload.get("groupRegionName") or batch.region_name,
            initialized_from_table="manual_add",
            initialized_from_key=code,
            initialized_at=now,
            snapshot_at=now,
        )
        db.add(base)
        db.flush()
        result = SurveyCbfResult(
            tenant_code=batch.tenant_code,
            region_code=group_region_code or batch.region_code,
            contractor_uid=contractor_uid,
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
            group_region_code=base.group_region_code,
            group_region_name=base.group_region_name,
            initialized_at=now,
        )
        result.tenant_code = batch.tenant_code
        result.region_code = group_region_code or batch.region_code
        result.result_status = "added"
        result.is_changed = True
        result.change_type = "add_contractor"
        result.remark = payload.get("remark")
        db.add(result)
        db.flush()
        base.result_id = result.id
        db.add(SurveyCbfBase(
            tenant_code=batch.tenant_code,
            region_code=group_region_code or batch.region_code,
            batch_id=batch_id,
            contractor_uid=contractor_uid,
            cbfbm=code,
            cbfmc=payload["name"],
            task_status="not_started",
            has_change=True,
            change_count=1,
            remark=payload.get("remark"),
        ))
        db.commit()
        return self._serialize_result_task(result, batch_id, self._get_task(db, batch_id, contractor_uid))


    def _contractor_changed(self, result: SurveyCbfResult, base: SurveyCbfBase | None) -> bool:
        if base is None:
            return True
        fields = [
            "cbfbm",
            "cbflx",
            "cbfmc",
            "cbfzjlx",
            "cbfzjhm",
            "cbfdz",
            "yzbm",
            "lxdh",
            "cbfcysl",
            "cbfdcrq",
            "cbfdcy",
            "cbfdcjs",
            "gsjs",
            "gsjsr",
            "gsshrq",
            "gsshr",
            "group_region_code",
            "group_region_name",
        ]
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


    def _issuer_changed(self, result: SurveyFbfResult, base: SurveyFbfBase | None) -> bool:
        if base is None:
            return True
        fields = ["fbfbm", "fbfmc", "fbffzrxm", "fzrzjlx", "fzrzjhm", "lxdh", "fbfdz", "yzbm", "fbfdcy", "fbfdcrq", "fbfdcjs"]
        return any(getattr(result, field) != getattr(base, field) for field in fields) or result.change_type != "none"


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


    def _issuer_summary_from_base(self, base: SurveyFbfBase) -> dict:
        return {
            "code": base.fbfbm,
            "name": base.fbfmc,
            "responsibleName": base.fbffzrxm,
            "responsibleIdNo": base.fzrzjhm,
            "address": base.fbfdz,
        }


    def _issuer_summary_from_result(self, result: SurveyFbfResult) -> dict:
        return {
            "code": result.fbfbm,
            "name": result.fbfmc,
            "responsibleName": result.fbffzrxm,
            "responsibleIdNo": result.fzrzjhm,
            "address": result.fbfdz,
            "surveyStatus": result.survey_status,
            "resultStatus": result.result_status,
        }


    def _serialize_result(
        self,
        item: SurveyCbfResult,
        members: list[SurveyCbfJtcyResult],
        batch_id: int = 0,
        base: SurveyCbfBase | None = None,
        base_members: list[SurveyCbfJtcyBase] | None = None,
        issuer: SurveyFbfResult | None = None,
        base_issuer: SurveyFbfBase | None = None,
    ) -> dict:
        return {
            "id": item.id,
            "batchId": batch_id,
            "contractorUid": item.contractor_uid,
            "baseId": None,  # TODO: lookup from base
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
            "issuer": self._serialize_issuer(issuer) if issuer else None,
            "baseIssuer": self._serialize_base_issuer(base_issuer) if base_issuer else None,
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
            "baseId": None,  # TODO: lookup from base
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


    def _get_result_issuer(self, db: Session, result: SurveyCbfResult) -> tuple[SurveyFbfResult | None, SurveyFbfBase | None]:
        relation = db.scalars(
            select(SurveyCbdkxxResult)
            .where(
                SurveyCbdkxxResult.tenant_code == result.tenant_code,
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status != "removed",
            )
            .order_by(SurveyCbdkxxResult.id.asc())
            .execution_options(skip_tenant_scope=True)
        ).first()
        if relation is None or not relation.fbfbm:
            return None, None
        issuer = db.scalars(
            select(SurveyFbfResult)
            .where(
                SurveyFbfResult.tenant_code == result.tenant_code,
                SurveyFbfResult.fbfbm == relation.fbfbm,
            )
            .order_by(SurveyFbfResult.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).first()
        if issuer is None:
            return None, None
        base = db.scalars(
            select(SurveyFbfBase)
            .where(SurveyFbfBase.tenant_code == result.tenant_code, SurveyFbfBase.result_id == issuer.id)
            .execution_options(skip_tenant_scope=True)
        ).first()
        return issuer, base

