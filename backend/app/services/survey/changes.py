import json
import logging
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.fbf import Fbf
from app.models.survey import (
    SurveyCbfBase,
    SurveyCbfJtcyBase,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyCbdkxxBase,
    SurveyCbdkxxResult,
    SurveyChangeDiff,
    SurveyChangeRecord,
    SurveyDkBase,
    SurveyDkResult,
    SurveyFbfBase,
    SurveyFbfResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service
from app.services.request_case_service import request_case_service

logger = logging.getLogger(__name__)

class SurveyServiceChangesMixin:
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
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
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
        region_code: str | None,
        page: int,
        page_size: int,
        current_user: User,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        normalized_region_code = data_access_service.normalize_region_code(region_code)
        if normalized_region_code:
            data_access_service.ensure_region_in_scope(current_user, normalized_region_code)
        stmt = (
            select(SurveyChangeRecord)
            .where(SurveyChangeRecord.tenant_code == batch.tenant_code, SurveyChangeRecord.batch_id == batch_id)
            .order_by(SurveyChangeRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .execution_options(skip_tenant_scope=True)
        )
        total_stmt = (
            select(func.count(SurveyChangeRecord.id))
            .where(SurveyChangeRecord.tenant_code == batch.tenant_code, SurveyChangeRecord.batch_id == batch_id)
            .execution_options(skip_tenant_scope=True)
        )
        filters = self._tenant_filters(SurveyChangeRecord, current_user)
        filters.extend(data_access_service.build_code_scope_filters(SurveyChangeRecord.region_code, current_user))
        if normalized_region_code:
            filters.append(SurveyChangeRecord.region_code.like(f"{normalized_region_code}%"))
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


    def generate_request_from_result(self, db: Session, batch_id: int, contractor_uid: str, payload: dict, current_user: User) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        if result.generated_request_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="鐠囥儴鐨熼弻銉﹀灇閺嬫粌鍑￠悽鐔稿灇娑撴艾濮熼悽瀹狀嚞")
        request_type = payload.get("requestType") or self._infer_request_type(result)
        issuer_code = self._resolve_issuer_code(db, result.cbfbm)
        request_payload = {
            "requestType": request_type,
            "requestTitle": payload.get("requestTitle") or f"{request_type}-{result.cbfmc}-survey",
            "issuerCode": issuer_code,
            "contractorCode": result.cbfbm,
            "contractorName": result.cbfmc,
            "contractorIdType": result.cbfzjlx,
            "contractorIdNo": result.cbfzjhm,
            "mobile": result.lxdh,
            "address": result.cbfdz,
            "reason": payload.get("reason") or result.change_reason or result.evidence_summary,
            "note": payload.get("note") or f"generated from survey batch {batch_id}, contractor {result.cbfbm}",
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


    def _infer_request_type(self, result: SurveyCbfResult) -> str:
        if result.change_type in {"extinct"} or result.result_status in {"extinct", "cancelled"}:
            return "濞夈劑鏀㈤惂鏄忣唶"
        return "閸欐ɑ娲块惂鏄忣唶"


    def _resolve_issuer_code(self, db: Session, cbfbm: str) -> str:
        candidates = [cbfbm[:14], cbfbm[:12], cbfbm[:9], cbfbm[:6]]
        for code in candidates:
            issuer = db.get(Fbf, code)
            if issuer is not None:
                return issuer.fbfbm
        issuer = db.scalars(select(Fbf).where(Fbf.fbfbm.like(f"{cbfbm[:12]}%")).limit(1)).first()
        if issuer is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="request failed")
        return issuer.fbfbm


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
            "beforeSummary": item.before_summary,
            "afterSummary": item.after_summary,
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


    def _collect_diff_rebuild_uids(self, batch_id: int, contractor_uid: str, pending_operations: list[dict] | None) -> list[str]:
        affected = [contractor_uid]
        seen = {contractor_uid}
        for operation in pending_operations or []:
            if not isinstance(operation, dict):
                continue
            op_type = operation.get("type")
            payload = operation.get("payload") or {}
            if op_type == "swap_parcels":
                target_uid = payload.get("targetContractorUid")
                if target_uid and target_uid not in seen:
                    seen.add(target_uid)
                    affected.append(target_uid)
            elif op_type == "split_household":
                new_cbfbm = payload.get("newCbfbm")
                if new_cbfbm:
                    new_uid = str(uuid5(NAMESPACE_URL, f"survey:{batch_id}:cbf:{new_cbfbm}"))
                    if new_uid not in seen:
                        seen.add(new_uid)
                        affected.append(new_uid)
        return affected


    def _load_diff_rebuild_context(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
    ) -> tuple[SurveyCbfResult, SurveyCbfBase | None, SurveyFbfResult | None, SurveyFbfBase | None]:
        result = self._get_result(db, batch_id, contractor_uid)
        base = db.scalar(
            select(SurveyCbfBase)
            .where(
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.contractor_uid == contractor_uid,
                SurveyCbfBase.initialized_from_table.in_(["survey_cbf_result", "manual_add"]),
            )
            .order_by(SurveyCbfBase.id.asc())
        )
        issuer, base_issuer = self._get_result_issuer(db, result)
        return result, base, issuer, base_issuer


    def _rebuild_contractor_diffs(
        self,
        db: Session,
        batch_id: int,
        contractor_uids: list[str],
        *,
        change_ids: dict[str, int | None] | None = None,
        deleted_member_reasons: dict[str, dict[str, str | None]] | None = None,
    ) -> None:
        change_ids = change_ids or {}
        deleted_member_reasons = deleted_member_reasons or {}
        for uid in contractor_uids:
            result, base, issuer, base_issuer = self._load_diff_rebuild_context(db, batch_id, uid)
            self._rebuild_diffs(
                db,
                batch_id,
                uid,
                result,
                base,
                change_ids.get(uid),
                issuer,
                base_issuer,
                deleted_member_reasons.get(uid),
            )


    def _rebuild_diffs(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        result: SurveyCbfResult,
        base: SurveyCbfBase | None,
        change_id: int | None,
        issuer: SurveyFbfResult | None = None,
        base_issuer: SurveyFbfBase | None = None,
        deleted_member_reasons: dict[str, str | None] | None = None,
    ) -> None:
        db.execute(
            delete(SurveyChangeDiff).where(
                SurveyChangeDiff.batch_id == batch_id,
                SurveyChangeDiff.contractor_uid == contractor_uid,
                SurveyChangeDiff.entity_type.in_(self.form_diff_entity_types),
            )
        )
        db.execute(
            delete(SurveyChangeDiff).where(
                SurveyChangeDiff.batch_id == batch_id,
                SurveyChangeDiff.contractor_uid == contractor_uid,
                SurveyChangeDiff.entity_type.in_(self.parcel_diff_entity_types),
            )
        )
        data_batch_id = batch_id
        if base is not None:
            contractor_fields = [
                ("cbfbm", "cbfbm"),
                ("cbflx", "cbflx"),
                ("cbfmc", "cbfmc"),
                ("cbfzjlx", "鐠囦椒娆㈢猾璇茬€?",),
                ("cbfzjhm", "鐠囦椒娆㈤崣椋庣垳"),
                ("cbfdz", "閹靛灝瀵橀弬鐟版勾閸р偓"),
                ("yzbm", "闁喗鏂傜紓鏍垳"),
                ("lxdh", "閼辨梻閮撮悽浣冪樈"),
                ("cbfcysl", "cbfcysl"),
                ("cbfdcrq", "鎵垮寘鏂硅皟鏌ユ棩鏈?",),
                ("cbfdcy", "鎵垮寘鏂硅皟鏌ュ憳"),
                ("cbfdcjs", "鎵垮寘鏂硅皟鏌ヨ浜?",),
                ("gsjs", "鍏ず璁颁簨"),
                ("gsjsr", "鍏ず璁颁簨浜?",),
                ("gsshrq", "鍏ず瀹℃牳鏃ユ湡"),
                ("gsshr", "鍏ず瀹℃牳浜?",),
                ("group_region_code", "閹碘偓鐏炵偟绮嶆禒锝囩垳"),
                ("group_region_name", "閹碘偓鐏炵偟绮嶉崥宥囆?",),
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

        if issuer is not None and base_issuer is not None:
            issuer_fields = [
                ("fbfbm", "fbfbm"),
                ("fbfmc", "fbfmc"),
                ("fbffzrxm", "閸欐垵瀵橀弬纭呯鐠愶絼姹?",),
                ("fzrzjlx", "fzrzjlx"),
                ("fzrzjhm", "fzrzjhm"),
                ("lxdh", "閼辨梻閮撮悽浣冪樈"),
                ("fbfdz", "閸欐垵瀵橀弬鐟版勾閸р偓"),
                ("yzbm", "闁喗鏂傜紓鏍垳"),
                ("fbfdcy", "fbfdcy"),
                ("fbfdcrq", "鐠嬪啯鐓￠弮銉︽埂"),
                ("fbfdcjs", "鐠嬪啯鐓＄拋棰佺皑"),
            ]
            for field_name, field_label in issuer_fields:
                before = getattr(base_issuer, field_name)
                after = getattr(issuer, field_name)
                if self._diff_value(before) != self._diff_value(after):
                    db.add(
                        SurveyChangeDiff(
                            batch_id=batch_id,
                            contractor_uid=contractor_uid,
                            change_id=change_id,
                            entity_type="issuer",
                            entity_uid=issuer.issuer_uid,
                            entity_name=issuer.fbfmc,
                            field_name=field_name,
                            field_label=field_label,
                            before_value=self._diff_value(before),
                            after_value=self._diff_value(after),
                            change_reason=issuer.change_reason,
                        )
                    )

        base_members = {
            item.member_uid: item
            for item in db.scalars(
                select(SurveyCbfJtcyBase).where(
                    SurveyCbfJtcyBase.batch_id == data_batch_id,
                    SurveyCbfJtcyBase.contractor_uid == contractor_uid,
                )
            ).all()
        }
        result_members = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
        ).all()
        member_fields = [
            ("cyxm", "婵挸鎮?",),
            ("cyzjlx", "鐠囦椒娆㈢猾璇茬€?",),
            ("cyzjhm", "鐠囦椒娆㈤崣椋庣垳"),
            ("cyxb", "閹冨焼"),
            ("yhzgx", "yhzgx"),
            ("cybz", "閹存劕鎲虫径鍥ㄦ暈娴狅絿鐖?",),
            ("sfgyr", "sfgyr"),
            ("cybzsm", "閹存劕鎲虫径鍥ㄦ暈鐠囧瓨妲?",),
            ("member_result_status", "member_result_status"),
            ("is_urban_settled", "閺勵垰鎯佹潻娑樼厔閽€鑺ュ煕"),
            ("is_married_out_woman", "is_married_out_woman"),
            ("is_deceased", "閺勵垰鎯佸璁抽"),
            ("is_five_guarantees", "閺勵垰鎯佹禍鏂剧箽"),
            ("rights_disposition", "閺夊啰娉径鍕枂"),
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
                        field_label="閺傛澘顤冮幋鎰喅",
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
                delete_reason = (deleted_member_reasons or {}).get(member_uid) or result.change_reason
                db.add(
                    SurveyChangeDiff(
                        batch_id=batch_id,
                        contractor_uid=contractor_uid,
                        change_id=change_id,
                        entity_type="member",
                        entity_uid=member_uid,
                        entity_name=member_base.cyxm,
                        field_name="member",
                        field_label="閸掔娀娅庨幋鎰喅",
                        before_value=f"{member_base.cyxm} / {member_base.cyzjhm}",
                        after_value=None,
                        change_reason=delete_reason,
                    )
                )
        self._rebuild_parcel_diffs(
            db,
            batch_id,
            contractor_uid,
            result,
            base,
            change_id,
        )


    def _rebuild_parcel_diffs(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        result: SurveyCbfResult,
        base: SurveyCbfBase | None,
        change_id: int | None,
    ) -> None:
        base_cbfbm = base.cbfbm if base is not None else result.cbfbm
        base_relations = db.scalars(
            select(SurveyCbdkxxBase).where(
                SurveyCbdkxxBase.batch_id == batch_id,
                SurveyCbdkxxBase.cbfbm == base_cbfbm,
            )
        ).all()
        active_result_relations = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status != "removed",
            )
        ).all()
        base_relations_by_uid = {item.parcel_info_uid: item for item in base_relations}
        active_relations_by_uid = {item.parcel_info_uid: item for item in active_result_relations}

        relation_fields = [
            ("dkbm", "鍦板潡缂栫爜"),
            ("fbfbm", "鍙戝寘鏂逛唬鐮?",),
            ("cbfbm", "鎵垮寘鏂逛唬鐮?",),
            ("cbjyqqdfs", "鎵垮寘缁忚惀鏉冨彇寰楁柟寮?",),
            ("htmj", "鍚堝悓闈㈢Н"),
            ("cbhtbm", "鎵垮寘鍚堝悓缂栫爜"),
            ("lzhtbm", "娴佽浆鍚堝悓缂栫爜"),
            ("cbjyqzbm", "鎵垮寘缁忚惀鏉冭瘉缂栫爜"),
            ("yhtmj", "鍘熷悎鍚岄潰绉?",),
            ("htmjm", "鍚堝悓闈㈢Н(浜?"),
            ("yhtmjm", "鍘熷悎鍚岄潰绉?浜?"),
            ("sfqqqg", "鏄惁纭潈纭偂"),
        ]
        relation_uids = set(base_relations_by_uid) | set(active_relations_by_uid)
        for relation_uid in relation_uids:
            base_relation = base_relations_by_uid.get(relation_uid)
            result_relation = active_relations_by_uid.get(relation_uid)
            if base_relation is None and result_relation is not None:
                self._add_change_diff(
                    db,
                    batch_id=batch_id,
                    contractor_uid=contractor_uid,
                    change_id=change_id,
                    entity_type="parcel_relation",
                    entity_uid=relation_uid,
                    entity_name=result_relation.dkbm,
                    field_name="parcel_relation",
                    field_label="鏂板鍦板潡鍏宠仈",
                    before_value=None,
                    after_value=f"{result_relation.dkbm} -> {result_relation.cbfbm}",
                    change_reason=result_relation.change_reason or result.change_reason,
                )
                continue
            if base_relation is not None and result_relation is None:
                self._add_change_diff(
                    db,
                    batch_id=batch_id,
                    contractor_uid=contractor_uid,
                    change_id=change_id,
                    entity_type="parcel_relation",
                    entity_uid=relation_uid,
                    entity_name=base_relation.dkbm,
                    field_name="parcel_relation",
                    field_label="绉婚櫎鍦板潡鍏宠仈",
                    before_value=f"{base_relation.dkbm} -> {base_relation.cbfbm}",
                    after_value=None,
                    change_reason=result.change_reason,
                )
                continue
            for field_name, field_label in relation_fields:
                before = getattr(base_relation, field_name, None)
                after = getattr(result_relation, field_name, None)
                if self._diff_value(before) != self._diff_value(after):
                    self._add_change_diff(
                        db,
                        batch_id=batch_id,
                        contractor_uid=contractor_uid,
                        change_id=change_id,
                        entity_type="parcel_relation",
                        entity_uid=relation_uid,
                        entity_name=result_relation.dkbm,
                        field_name=field_name,
                        field_label=field_label,
                        before_value=before,
                        after_value=after,
                        change_reason=result_relation.change_reason or result.change_reason,
                    )

        relation_dkbms = {item.dkbm for item in base_relations}
        relation_dkbms.update(item.dkbm for item in active_result_relations)
        if not relation_dkbms:
            return

        base_parcels = db.scalars(
            select(SurveyDkBase).where(
                SurveyDkBase.batch_id == batch_id,
                SurveyDkBase.dkbm.in_(relation_dkbms),
            )
        ).all()
        result_parcels = db.scalars(
            select(SurveyDkResult).where(
                SurveyDkResult.dkbm.in_(relation_dkbms),
            ).order_by(SurveyDkResult.id.desc())
        ).all()
        base_parcels_by_dkbm = {item.dkbm: item for item in base_parcels}
        result_parcels_by_dkbm = {}
        for item in result_parcels:
            result_parcels_by_dkbm.setdefault(item.dkbm, item)

        parcel_fields = [
            ("dkmc", "鍦板潡鍚嶇О"),
            ("scmj", "瀹炴祴闈㈢Н"),
            ("syqxz", "鎵€鏈夋潈鎬ц川"),
            ("dklb", "鍦板潡绫诲埆"),
            ("tdlylx", "鍦熷湴鍒╃敤绫诲瀷"),
            ("dldj", "鍦扮被绛夌骇"),
            ("tdyt", "鍦熷湴鐢ㄩ€?",),
            ("sfjbnt", "鏄惁鍩烘湰鍐滅敯"),
            ("dkdz", "鍦板潡涓滆嚦"),
            ("dkxz", "鍦板潡瑗胯嚦"),
            ("dknz", "鍦板潡鍗楄嚦"),
            ("dkbz", "鍦板潡鍖楄嚦"),
            ("dkbzxx", "鍦板潡澶囨敞淇℃伅"),
        ]
        candidate_result_dkbms = {
            item.dkbm
            for item in result_parcels_by_dkbm.values()
            if item.is_changed or item.result_status != "normal"
        }
        parcel_dkbms = set(base_parcels_by_dkbm) | candidate_result_dkbms
        for dkbm in parcel_dkbms:
            base_parcel = base_parcels_by_dkbm.get(dkbm)
            result_parcel = result_parcels_by_dkbm.get(dkbm)
            if base_parcel is None and result_parcel is not None:
                self._add_change_diff(
                    db,
                    batch_id=batch_id,
                    contractor_uid=contractor_uid,
                    change_id=change_id,
                    entity_type="parcel",
                    entity_uid=result_parcel.parcel_uid,
                    entity_name=result_parcel.dkmc,
                    field_name="parcel",
                    field_label="鏂板鍦板潡",
                    before_value=None,
                    after_value=f"{result_parcel.dkbm} / {result_parcel.dkmc}",
                    change_reason=result_parcel.change_reason or result.change_reason,
                )
                continue
            if base_parcel is not None and result_parcel is None:
                self._add_change_diff(
                    db,
                    batch_id=batch_id,
                    contractor_uid=contractor_uid,
                    change_id=change_id,
                    entity_type="parcel",
                    entity_uid=base_parcel.parcel_uid,
                    entity_name=base_parcel.dkmc,
                    field_name="parcel",
                    field_label="绉婚櫎鍦板潡",
                    before_value=f"{base_parcel.dkbm} / {base_parcel.dkmc}",
                    after_value=None,
                    change_reason=result.change_reason,
                )
                continue
            for field_name, field_label in parcel_fields:
                before = getattr(base_parcel, field_name, None)
                after = getattr(result_parcel, field_name, None)
                if self._diff_value(before) != self._diff_value(after):
                    self._add_change_diff(
                        db,
                        batch_id=batch_id,
                        contractor_uid=contractor_uid,
                        change_id=change_id,
                        entity_type="parcel",
                        entity_uid=result_parcel.parcel_uid,
                        entity_name=result_parcel.dkmc,
                        field_name=field_name,
                        field_label=field_label,
                        before_value=before,
                        after_value=after,
                        change_reason=result_parcel.change_reason or result.change_reason,
                    )


    def _diff_value(self, value) -> str | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, default=str)
        return str(value)


    def _add_change_diff(
        self,
        db: Session,
        *,
        batch_id: int,
        contractor_uid: str,
        change_id: int | None,
        entity_type: str,
        entity_uid: str,
        entity_name: str | None,
        field_name: str,
        field_label: str,
        before_value=None,
        after_value=None,
        change_reason: str | None = None,
    ) -> None:
        db.add(
            SurveyChangeDiff(
                batch_id=batch_id,
                contractor_uid=contractor_uid,
                change_id=change_id,
                entity_type=entity_type,
                entity_uid=entity_uid,
                entity_name=entity_name,
                field_name=field_name,
                field_label=field_label,
                before_value=self._diff_value(before_value),
                after_value=self._diff_value(after_value),
                change_reason=change_reason,
            )
        )


    def _apply_pending_operations(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        pending_operations: list[dict],
        current_user: User,
    ) -> None:
        for operation in pending_operations or []:
            op_type = operation.get("type")
            payload = operation.get("payload") or {}
            if op_type == "change_head":
                self.change_household_head(
                    db, batch_id, contractor_uid,
                    payload.get("newHeadMemberUid"), payload.get("reason"),
                    current_user, commit=False,
                )
            elif op_type == "maintain_members":
                self.maintain_members(
                    db, batch_id, contractor_uid,
                    payload.get("membersToAdd") or [],
                    payload.get("membersToUpdate") or [],
                    payload.get("membersToDelete") or [],
                    payload.get("reason"),
                    current_user,
                    commit=False,
                )
            elif op_type == "deregister":
                self.deregister_contractor(
                    db, batch_id, contractor_uid,
                    payload.get("reason") or "",
                    current_user,
                    commit=False,
                )
            elif op_type == "add_parcel":
                self.add_parcel(db, batch_id, contractor_uid, payload, current_user, commit=False)
            elif op_type == "split_parcel":
                self.split_parcel(db, batch_id, contractor_uid, payload, current_user, commit=False)
            elif op_type == "rollback_split_parcel":
                self.rollback_split_parcel(
                    db,
                    batch_id,
                    contractor_uid,
                    int(payload.get("changeId") or 0),
                    payload,
                    current_user,
                    commit=False,
                )
            elif op_type == "swap_parcels":
                self.swap_parcels(db, batch_id, contractor_uid, payload, current_user, commit=False)
            elif op_type == "rollback_swap_parcels":
                self.rollback_swap_parcels(
                    db,
                    batch_id,
                    contractor_uid,
                    int(payload.get("changeId") or 0),
                    payload,
                    current_user,
                    commit=False,
                )
            elif op_type == "remove_parcel":
                self.remove_parcel(db, batch_id, contractor_uid, payload, current_user, commit=False)
            elif op_type == "rollback_remove_parcel":
                self.rollback_remove_parcel(
                    db,
                    batch_id,
                    contractor_uid,
                    int(payload.get("changeId") or 0),
                    payload,
                    current_user,
                    commit=False,
                )
            elif op_type == "split_household":
                self.split_household(db, batch_id, contractor_uid, payload, current_user, commit=False)
            elif op_type == "merge_household":
                self.merge_household(db, batch_id, contractor_uid, payload, current_user, commit=False)
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"unsupported pending operation: {op_type}")


    def _create_change_record(
        self, db: Session, batch_id: int, contractor_uid: str, cbfbm: str,
        change_type: str, before_summary: dict, after_summary: dict,
        reason: str | None, current_user: User, now: datetime,
    ) -> SurveyChangeRecord:
        batch = self._ensure_batch(db, batch_id)
        result = db.scalars(
            select(SurveyCbfResult)
            .where(SurveyCbfResult.tenant_code == batch.tenant_code, SurveyCbfResult.contractor_uid == contractor_uid)
            .order_by(SurveyCbfResult.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).first()
        record = SurveyChangeRecord(
            tenant_code=batch.tenant_code,
            region_code=(result.group_region_code or result.region_code) if result else batch.region_code,
            batch_id=batch_id,
            change_no=self._next_no(db, "CHG", SurveyChangeRecord.id),
            contractor_uid=contractor_uid,
            cbfbm=cbfbm,
            change_type=change_type,
            change_level="household",
            change_status="surveyed",
            before_summary=before_summary,
            after_summary=after_summary,
            change_reason=reason,
            investigated_at=now,
            investigator_id=current_user.id,
            investigator_name=current_user.real_name,
        )
        db.add(record)
        return record

