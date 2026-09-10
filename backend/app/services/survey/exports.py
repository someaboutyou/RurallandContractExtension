import csv
import io
import logging
import zipfile
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyCbfBase,
    SurveyCbfJtcyBase,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyChangeDiff,
    SurveyChangeRecord,
    SurveyCbdkxxResult,
    SurveyDkResult,
    SurveyFbfResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service

logger = logging.getLogger(__name__)

class SurveyServiceExportsMixin:
    def build_results_zip(self, db: Session, batch_id: int, current_user: User, region_code: str | None = None) -> tuple[str, bytes]:
        batch = self._ensure_batch(db, batch_id)
        normalized_region_code = data_access_service.normalize_region_code(region_code)
        effective_region_code = normalized_region_code or data_access_service.normalize_region_code(batch.region_code)
        if normalized_region_code:
            data_access_service.ensure_region_in_scope(current_user, normalized_region_code)
        task_filters = self._tenant_filters(SurveyCbfBase, current_user)
        task_filters.append(SurveyCbfBase.batch_id == batch_id)
        contractor_filters = self._tenant_filters(SurveyCbfResult, current_user)
        contractor_filters.extend(data_access_service.build_code_scope_filters(SurveyCbfResult.group_region_code, current_user))
        member_filters = self._tenant_filters(SurveyCbfJtcyResult, current_user)
        self._append_group_region_filter(contractor_filters, SurveyCbfResult.group_region_code, effective_region_code)

        tasks = db.scalars(
            select(SurveyCbfBase)
            .where(*task_filters)
            .order_by(SurveyCbfBase.cbfbm.asc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        source_contractors = db.scalars(
            select(SurveyCbfResult)
            .where(*contractor_filters)
            .order_by(SurveyCbfResult.cbfbm.asc(), SurveyCbfResult.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        latest_by_code: dict[str, SurveyCbfResult] = {}
        for item in source_contractors:
            latest_by_code.setdefault(item.cbfbm, item)
        contractors = list(latest_by_code.values())
        data_batch_ids = {item.batch_id for item in contractors}
        contractor_uids = {item.contractor_uid for item in contractors}
        members = db.scalars(
            select(SurveyCbfJtcyResult)
            .where(
                SurveyCbfJtcyResult.contractor_uid.in_(contractor_uids),
                *member_filters,
            )
            .order_by(SurveyCbfJtcyResult.cbfbm.asc(), SurveyCbfJtcyResult.cyxm.asc(), SurveyCbfJtcyResult.cyzjhm.asc())
            .execution_options(skip_tenant_scope=True)
        ).all() if data_batch_ids and contractor_uids else []
        issuer_codes = {
            item.fbfbm
            for item in db.scalars(
                select(SurveyCbdkxxResult)
                .where(
                    SurveyCbdkxxResult.cbfbm.in_({item.cbfbm for item in contractors}),
                    SurveyCbdkxxResult.result_status != "removed",
                )
                .execution_options(skip_tenant_scope=True)
            ).all()
            if item.fbfbm
        } if data_batch_ids and contractors else set()
        issuers = db.scalars(
            select(SurveyFbfResult)
            .where(
                SurveyFbfResult.tenant_code == batch.tenant_code,
                SurveyFbfResult.fbfbm.in_(issuer_codes),
            )
            .order_by(SurveyFbfResult.fbfbm.asc())
            .execution_options(skip_tenant_scope=True)
        ).all() if issuer_codes else []
        diffs = db.scalars(
            select(SurveyChangeDiff)
            .where(SurveyChangeDiff.tenant_code == batch.tenant_code, SurveyChangeDiff.batch_id == batch_id)
            .order_by(SurveyChangeDiff.contractor_uid.asc(), SurveyChangeDiff.id.asc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        allowed_uids = {item.contractor_uid for item in tasks}
        diffs = [item for item in diffs if item.contractor_uid in allowed_uids]

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("survey_tasks.csv", self._build_tasks_csv(tasks))
            archive.writestr("survey_fbf_result.csv", self._build_issuer_results_csv(issuers))
            archive.writestr("survey_cbf_result.csv", self._build_contractor_results_csv(contractors))
            archive.writestr("survey_cbf_jtcy_result.csv", self._build_member_results_csv(members))
            archive.writestr("survey_change_diffs.csv", self._build_change_diffs_csv(diffs))
        return f"survey_{batch.batch_no}_results.zip", zip_buffer.getvalue()


    def _member_snapshot(self, member: SurveyCbfJtcyResult | SurveyCbfJtcyBase) -> dict:
        return {
            "memberUid": member.member_uid,
            "name": member.cyxm,
            "gender": member.cyxb,
            "idType": member.cyzjlx,
            "idNo": member.cyzjhm,
            "relationToHead": member.yhzgx,
            "noteCode": member.cybz,
            "isCoOwner": member.sfgyr,
            "note": member.cybzsm,
            "isHouseholdHead": getattr(member, "is_household_head", False),
        }


    def _csv_bytes(self, headers: list[str], rows: list[list[object]]) -> bytes:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return output.getvalue().encode("utf-8-sig")


    def _date_text(self, value: datetime | None) -> str:
        return value.date().isoformat() if value else ""


    def _bool_text(self, value: bool | None) -> str:
        return "yes" if value else "no"


    def _build_tasks_csv(self, tasks: list[SurveyCbfBase]) -> bytes:
        return self._csv_bytes(
            # repaired invalid string literal
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
                "閹佃顐奸崘鍛暜娑撯偓閺嶅洩鐦?",
                "field",
                "field",
                "field",
                "鐠囦椒娆㈢猾璇茬€?",
                "鐠囦椒娆㈤崣椋庣垳",
                "閹靛灝瀵橀弬鐟版勾閸р偓",
                "闁喗鏂傜紓鏍垳",
                "閼辨梻閮撮悽浣冪樈",
                "field",
                "field",
                "field",
                "閺勵垰鎯侀崣妯哄",
                "閸欐ê瀵茬猾璇茬€?",
                "閸欐ê瀵查崢鐔锋礈",
                "閺€璺ㄧ摜娓氭繃宓?",
                "娓氭繃宓侀弶鎰灐閹芥顩?",
                "field",
                "鐠嬪啯鐓￠弮鍫曟？",
                "field",
                "绾喛顓婚弮鍫曟？",
                "閺夈儲绨€电厧鍙嗛幍瑙勵偧ID",
                "閺夈儲绨€电厧鍙嗙悰瀛朌",
                "閺堚偓鏉╂垵顕遍崗銉﹀濞嗩搹D",
                "閺堚偓鏉╂垵顕遍崗銉攽ID",
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


    def _build_issuer_results_csv(self, issuers: list[SurveyFbfResult]) -> bytes:
        return self._csv_bytes(
            [
                "閸欐垵瀵橀弬鐟版暜娑撯偓閺嶅洩鐦?",
                "field",
                "field",
                "field",
                "field",
                "field",
                "閼辨梻閮撮悽浣冪樈",
                "閸欐垵瀵橀弬鐟版勾閸р偓",
                "闁喗鏂傜紓鏍垳",
                "field",
                "鐠嬪啯鐓￠弮銉︽埂",
                "鐠嬪啯鐓＄拋棰佺皑",
                "field",
                "閺勵垰鎯侀崣妯哄",
                "閸欐ê瀵茬猾璇茬€?",
                "閸欐ê瀵查崢鐔锋礈",
                "閺€璺ㄧ摜娓氭繃宓?",
            ],
            [
                [
                    item.issuer_uid,
                    item.fbfbm,
                    item.fbfmc,
                    item.fbffzrxm,
                    item.fzrzjlx,
                    item.fzrzjhm,
                    item.lxdh or "",
                    item.fbfdz,
                    item.yzbm,
                    item.fbfdcy,
                    item.fbfdcrq.date().isoformat() if item.fbfdcrq else "",
                    item.fbfdcjs or "",
                    item.survey_status,
                    "yes" if item.is_changed else "no",
                    item.change_type,
                    item.change_reason or "",
                    item.policy_basis or "",
                ]
                for item in issuers
            ],
        )


    def _build_member_results_csv(self, members: list[SurveyCbfJtcyResult]) -> bytes:
        return self._csv_bytes(
            [
                "閹佃顐奸崘鍛煕閸烆垯绔撮弽鍥槕",
                "閹存劕鎲抽崬顖欑閺嶅洩鐦?",
                "field",
                "閹存劕鎲虫慨鎾虫倳",
                "鐠囦椒娆㈢猾璇茬€?",
                "鐠囦椒娆㈤崣椋庣垳",
                "閹冨焼",
                "field",
                "field",
                "閺勵垰鎯侀崣妯哄",
                "閺勵垰鎯侀幋铚傚瘜",
                "閺勵垰鎯佹潻娑樼厔閽€鑺ュ煕",
                "field",
                "閺勵垰鎯佸璁抽",
                "閺勵垰鎯佹禍鏂剧箽",
                "閸欐ê瀵查崢鐔锋礈",
                "閺€璺ㄧ摜娓氭繃宓?",
                "閺夊啰娉径鍕枂",
                "閺夈儲绨€电厧鍙嗛幍瑙勵偧ID",
                "閺夈儲绨€电厧鍙嗙悰瀛朌",
                "閺堚偓鏉╂垵顕遍崗銉﹀濞嗩搹D",
                "閺堚偓鏉╂垵顕遍崗銉攽ID",
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
            ["batchUid", "entityType", "entityUid", "entityName", "fieldName", "fieldLabel", "beforeValue", "afterValue", "changeReason"],
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

