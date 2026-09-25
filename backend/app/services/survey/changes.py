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
            data_access_service.ensure_region_filter_in_scope(current_user, normalized_region_code)
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
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该调查成果已生成业务申请")
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
        # 差异行没有业务编码列，若不在构造时显式给定区域，before_flush 只能退化成
        # 取当前用户的 region.code（村码/县码），会出现两个问题：
        #   1) 组级权限用户（权限码 14 位）保存时 region_code 前缀匹配落空 → 403；
        #   2) 同一条差异行的区域与所属承包方不一致，按授权区域过滤时数据看不到。
        # 因此统一继承承包方结果的租户/村组码，与 survey_*_result 口径一致。
        scope_tenant = getattr(result, "tenant_code", None)
        scope_region = (
            getattr(result, "group_region_code", None)
            or getattr(result, "region_code", None)
            or getattr(result, "cbfbm", None)
        )
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
                ("cbfzjlx", "证件类型",),
                ("cbfzjhm", "证件号码"),
                ("cbfdz", "承包方地址"),
                ("yzbm", "邮政编码"),
                ("lxdh", "联系电话"),
                ("cbfcysl", "cbfcysl"),
                ("cbfdcrq", "承包方调查日期",),
                ("cbfdcy", "承包方调查员"),
                ("cbfdcjs", "承包方调查记事",),
                ("gsjs", "公示记事"),
                ("gsjsr", "公示记事人",),
                ("gsshrq", "公示审核日期"),
                ("gsshr", "公示审核人",),
                ("group_region_code", "村民小组编码"),
                ("group_region_name", "村民小组名称",),
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
                            tenant_code=scope_tenant,
                            region_code=scope_region,
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
                ("fbffzrxm", "发包方负责人姓名",),
                ("fzrzjlx", "fzrzjlx"),
                ("fzrzjhm", "fzrzjhm"),
                ("lxdh", "联系电话"),
                ("fbfdz", "发包方地址"),
                ("yzbm", "邮政编码"),
                ("fbfdcy", "fbfdcy"),
                ("fbfdcrq", "调查日期"),
                ("fbfdcjs", "调查记事"),
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
                            tenant_code=scope_tenant,
                            region_code=scope_region,
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
            ("cyxm", "姓名",),
            ("cyzjlx", "证件类型",),
            ("cyzjhm", "证件号码"),
            ("cyxb", "性别"),
            ("yhzgx", "yhzgx"),
            ("cybz", "成员备注",),
            ("sfgyr", "sfgyr"),
            ("cybzsm", "成员备注说明",),
            ("member_result_status", "member_result_status"),
            ("is_urban_settled", "是否进城落户"),
            ("is_married_out_woman", "is_married_out_woman"),
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
                        tenant_code=scope_tenant,
                        region_code=scope_region,
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
                        tenant_code=scope_tenant,
                        region_code=scope_region,
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
                        tenant_code=scope_tenant,
                        region_code=scope_region,
                        entity_type="member",
                        entity_uid=member_uid,
                        entity_name=member_base.cyxm,
                        field_name="member",
                        field_label="删除成员",
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
        scope_tenant = getattr(result, "tenant_code", None)
        scope_region = (
            getattr(result, "group_region_code", None)
            or getattr(result, "region_code", None)
            or getattr(result, "cbfbm", None)
        )
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
            ("dkbm", "地块编码"),
            ("fbfbm", "发包方代码",),
            ("cbfbm", "承包方代码",),
            ("cbjyqqdfs", "承包经营权取得方式",),
            ("htmj", "合同面积"),
            ("cbhtbm", "承包合同编码"),
            ("lzhtbm", "流转合同编码"),
            ("cbjyqzbm", "承包经营权证编码"),
            ("yhtmj", "原合同面积",),
            ("htmjm", "合同面积(亩)"),
            ("yhtmjm", "原合同面积(亩)"),
            ("sfqqqg", "是否确权确股"),
        ]
        relation_uids = set(base_relations_by_uid) | set(active_relations_by_uid)
        for relation_uid in relation_uids:
            base_relation = base_relations_by_uid.get(relation_uid)
            result_relation = active_relations_by_uid.get(relation_uid)
            if base_relation is None and result_relation is not None:
                self._add_change_diff(
                    db,
                    tenant_code=scope_tenant,
                    region_code=scope_region,
                    batch_id=batch_id,
                    contractor_uid=contractor_uid,
                    change_id=change_id,
                    entity_type="parcel_relation",
                    entity_uid=relation_uid,
                    entity_name=result_relation.dkbm,
                    field_name="parcel_relation",
                    field_label="新增地块关联",
                    before_value=None,
                    after_value=f"{result_relation.dkbm} -> {result_relation.cbfbm}",
                    change_reason=result_relation.change_reason or result.change_reason,
                )
                continue
            if base_relation is not None and result_relation is None:
                self._add_change_diff(
                    db,
                    tenant_code=scope_tenant,
                    region_code=scope_region,
                    batch_id=batch_id,
                    contractor_uid=contractor_uid,
                    change_id=change_id,
                    entity_type="parcel_relation",
                    entity_uid=relation_uid,
                    entity_name=base_relation.dkbm,
                    field_name="parcel_relation",
                    field_label="移除地块关联",
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
                        tenant_code=scope_tenant,
                        region_code=scope_region,
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
            ("dkmc", "地块名称"),
            ("scmj", "实测面积"),
            ("syqxz", "所有权性质"),
            ("dklb", "地块类别"),
            ("tdlylx", "土地利用类型"),
            ("dldj", "地类等级"),
            ("tdyt", "土地用途",),
            ("sfjbnt", "是否基本农田"),
            ("dkdz", "地块东至"),
            ("dkxz", "地块西至"),
            ("dknz", "地块南至"),
            ("dkbz", "地块北至"),
            ("dkbzxx", "地块备注信息"),
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
                    tenant_code=scope_tenant,
                    region_code=scope_region,
                    batch_id=batch_id,
                    contractor_uid=contractor_uid,
                    change_id=change_id,
                    entity_type="parcel",
                    entity_uid=result_parcel.parcel_uid,
                    entity_name=result_parcel.dkmc,
                    field_name="parcel",
                    field_label="新增地块",
                    before_value=None,
                    after_value=f"{result_parcel.dkbm} / {result_parcel.dkmc}",
                    change_reason=result_parcel.change_reason or result.change_reason,
                )
                continue
            if base_parcel is not None and result_parcel is None:
                self._add_change_diff(
                    db,
                    tenant_code=scope_tenant,
                    region_code=scope_region,
                    batch_id=batch_id,
                    contractor_uid=contractor_uid,
                    change_id=change_id,
                    entity_type="parcel",
                    entity_uid=base_parcel.parcel_uid,
                    entity_name=base_parcel.dkmc,
                    field_name="parcel",
                    field_label="移除地块",
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
                        tenant_code=scope_tenant,
                        region_code=scope_region,
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
        tenant_code: str | None = None,
        region_code: str | None = None,
    ) -> None:
        db.add(
            SurveyChangeDiff(
                batch_id=batch_id,
                contractor_uid=contractor_uid,
                change_id=change_id,
                tenant_code=tenant_code,
                region_code=region_code,
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

