import logging
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyBatch,
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

logger = logging.getLogger(__name__)

class SurveyServiceBatchMixin:
    def list_batches(
        self,
        db: Session,
        page: int,
        page_size: int,
        keyword: str | None,
        batch_status: str | None,
        region_code: str | None,
        current_user: User,
    ) -> dict:
        normalized_region_code = data_access_service.normalize_region_code(region_code)
        if normalized_region_code:
            data_access_service.ensure_region_in_scope(current_user, normalized_region_code)
        filters = [SurveyBatch.survey_type == "household_survey"]
        scope_filter = data_access_service.build_scoped_filter(SurveyBatch, current_user)
        if scope_filter is not None:
            filters.append(scope_filter)
        if normalized_region_code:
            filters.append(SurveyBatch.region_code.like(f"{normalized_region_code}%"))
        if batch_status:
            filters.append(SurveyBatch.status == batch_status)
        stmt = (
            select(SurveyBatch)
            .where(*filters)
            .order_by(SurveyBatch.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        total_stmt = select(func.count(SurveyBatch.id)).where(*filters)
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
        region_code = data_access_service.normalize_region_code(payload.get("regionCode"))
        if not region_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="region code is required")
        data_access_service.ensure_region_in_scope(current_user, region_code)
        tenant_code = data_access_service.get_tenant_code(current_user) or data_access_service.derive_tenant_code(region_code)
        # 妫€鏌ュ悓鍖哄煙鏄惁鏈夋湭缁撴潫鐨勮皟鏌ユ壒娆?
        active_batch = db.scalars(
            select(SurveyBatch).where(
                SurveyBatch.region_code.like(f"{region_code}%"),
                SurveyBatch.survey_type == "household_survey",
                SurveyBatch.status == "active",
            ).limit(1)
        ).first()
        if active_batch:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"an active survey batch already exists in this region: {active_batch.batch_no}",
            )
        batch_no = self._next_no(db, "SUR", SurveyBatch.id)
        batch = SurveyBatch(
            tenant_code=tenant_code,
            region_code=region_code,
            batch_no=batch_no,
            batch_name=payload.get("batchName") or self._short_region_name(payload.get("regionName"), region_code),
            region_name=payload.get("regionName"),
            survey_type="household_survey",
            status="active",
            started_at=now,
            created_by=current_user.id,
            remark=payload.get("remark"),
        )
        db.add(batch)
        db.flush()
        filters = self._tenant_filters(SurveyCbfResult, current_user)
        filters.extend(data_access_service.build_code_scope_filters(SurveyCbfResult.group_region_code, current_user))
        self._append_group_region_filter(filters, SurveyCbfResult.group_region_code, region_code)
        source_results = db.scalars(
            select(SurveyCbfResult)
            .where(*filters)
            .order_by(SurveyCbfResult.cbfbm.asc(), SurveyCbfResult.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        latest_by_code: dict[str, SurveyCbfResult] = {}
        for item in source_results:
            latest_by_code.setdefault(item.cbfbm, item)
        if not latest_by_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no contractor data available for initialization")

        for contractor in latest_by_code.values():
            contractor_uid = str(uuid5(NAMESPACE_URL, f"survey:{batch.id}:cbf:{contractor.cbfbm}"))
            base = SurveyCbfBase(
                tenant_code=contractor.tenant_code,
                region_code=contractor.group_region_code or contractor.region_code,
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
                result_id=contractor.id,
            )
            db.add(base)
            db.flush()
            db.add(
                SurveyCbfBase(
                    batch_id=batch.id,
                    contractor_uid=contractor_uid,
                    cbfbm=contractor.cbfbm,
                    cbfmc=contractor.cbfmc,
                    tenant_code=contractor.tenant_code,
                    region_code=contractor.group_region_code or contractor.region_code,
                    task_status="not_started",
                )
            )
            members = db.scalars(
                select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.tenant_code == contractor.tenant_code,
                    SurveyCbfJtcyResult.cbfbm == contractor.cbfbm,
                )
                .execution_options(skip_tenant_scope=True)
            ).all()
            for member in members:
                member_uid = str(uuid5(NAMESPACE_URL, f"survey:{batch.id}:member:{contractor.cbfbm}:{member.cyzjhm}"))
                member_base = SurveyCbfJtcyBase(
                    tenant_code=member.tenant_code,
                    region_code=contractor.group_region_code or member.region_code,
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

        self._initialize_related_survey_data(db, batch, list(latest_by_code.values()), now)
        db.commit()
        db.refresh(batch)
        return self._serialize_batch(db, batch)


    def finish_batch(self, db: Session, batch_id: int, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        unfinished = db.scalar(
            select(func.count(SurveyCbfBase.id)).where(
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.task_status.notin_(["confirmed", "skipped"]),
            )
        ) or 0
        if unfinished:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request failed")
        skipped_without_reason = db.scalar(
            select(func.count(SurveyCbfBase.id)).where(
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.task_status == "skipped",
                or_(SurveyCbfBase.skip_reason.is_(None), SurveyCbfBase.skip_reason == ""),
            )
        ) or 0
        if skipped_without_reason:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"鏉╂ɑ婀?{skipped_without_reason} 閹寸柉鐑︽潻鍥у斧閸ョ姳璐熺粚鐚寸礉娑撳秷鍏樼紒鎾存将閹佃顐?")
        changed_confirmed = db.scalars(
            select(SurveyCbfBase).where(
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.task_status == "confirmed",
                SurveyCbfBase.has_change.is_(True),
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"鏉╂ɑ婀?{missing_change_trace} 閹撮攱婀侀崣妯哄娴ｅ棛宸辩亸鎴濆綁閸栨牞顔囪ぐ鏇礉娑撳秷鍏樼紒鎾存将閹佃顐?")
        batch.status = "finished"
        batch.ended_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(batch)
        return self._serialize_batch(db, batch)


    def _serialize_batch(self, db: Session, item: SurveyBatch, scope_filters: list | None = None) -> dict:
        result_filters = [SurveyCbfBase.tenant_code == item.tenant_code, SurveyCbfBase.batch_id == item.id]
        if item.region_code:
            self._append_group_region_filter(result_filters, SurveyCbfBase.group_region_code, item.region_code)
        task_count = db.scalar(
            select(func.count(func.distinct(SurveyCbfBase.cbfbm))).where(*result_filters).execution_options(skip_tenant_scope=True)
        ) or 0
        task_filters = [SurveyCbfBase.tenant_code == item.tenant_code, SurveyCbfBase.batch_id == item.id]
        not_started_count = max(
            task_count - (db.scalar(select(func.count(SurveyCbfBase.id)).where(*task_filters).execution_options(skip_tenant_scope=True)) or 0),
            0,
        )
        surveyed_count = db.scalar(
            select(func.count(SurveyCbfBase.id)).where(
                *task_filters,
                SurveyCbfBase.task_status.in_(["surveyed", "changed", "unchanged", "confirmed"]),
            ).execution_options(skip_tenant_scope=True)
        ) or 0
        changed_count = db.scalar(
            select(func.count(SurveyChangeRecord.id)).where(SurveyChangeRecord.tenant_code == item.tenant_code, SurveyChangeRecord.batch_id == item.id)
            .execution_options(skip_tenant_scope=True)
        ) or 0
        confirmed_count = db.scalar(
            select(func.count(SurveyCbfBase.id)).where(*task_filters, SurveyCbfBase.task_status == "confirmed")
            .execution_options(skip_tenant_scope=True)
        ) or 0
        skipped_count = db.scalar(
            select(func.count(SurveyCbfBase.id)).where(*task_filters, SurveyCbfBase.task_status == "skipped")
            .execution_options(skip_tenant_scope=True)
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


    def _initialize_related_survey_data(self, db: Session, batch: SurveyBatch, contractors: list[SurveyCbfResult], now: datetime) -> None:
        cbfbms = {item.cbfbm for item in contractors if item.cbfbm}
        if not cbfbms:
            return
        cbdkxx_results = db.scalars(
            select(SurveyCbdkxxResult)
            .where(
                SurveyCbdkxxResult.tenant_code == batch.tenant_code,
                SurveyCbdkxxResult.cbfbm.in_(cbfbms),
                SurveyCbdkxxResult.result_status != "removed",
            )
            .order_by(SurveyCbdkxxResult.dkbm.asc(), SurveyCbdkxxResult.cbfbm.asc(), SurveyCbdkxxResult.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        latest_cbdkxx: dict[tuple[str, str], SurveyCbdkxxResult] = {}
        for item in cbdkxx_results:
            latest_cbdkxx.setdefault((item.dkbm, item.cbfbm), item)

        dkbms = {item.dkbm for item in latest_cbdkxx.values() if item.dkbm}
        fbfbms = {item.fbfbm for item in latest_cbdkxx.values() if item.fbfbm}
        dk_by_code = self._latest_dk_results(db, batch.tenant_code, dkbms)
        fbf_by_code = self._latest_fbf_results(db, batch.tenant_code, fbfbms)

        for fbf in fbf_by_code.values():
            base = self._fbf_base_from_result(batch.id, fbf, now)
            db.add(base)
            db.flush()

        for dk in dk_by_code.values():
            base = self._dk_base_from_result(batch.id, dk, now)
            db.add(base)
            db.flush()
            self._copy_dk_geometry(db, dk.id, "survey_dk_base", base.id)

        for parcel_info in latest_cbdkxx.values():
            base = self._cbdkxx_base_from_result(batch.id, parcel_info, now)
            db.add(base)
            db.flush()


    def _latest_dk_results(self, db: Session, tenant_code: str, dkbms: set[str]) -> dict[str, SurveyDkResult]:
        if not dkbms:
            return {}
        rows = db.scalars(
            select(SurveyDkResult)
            .where(SurveyDkResult.tenant_code == tenant_code, SurveyDkResult.dkbm.in_(dkbms))
            .order_by(SurveyDkResult.dkbm.asc(), SurveyDkResult.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        latest: dict[str, SurveyDkResult] = {}
        for item in rows:
            latest.setdefault(item.dkbm, item)
        return latest


    def _latest_fbf_results(self, db: Session, tenant_code: str, fbfbms: set[str]) -> dict[str, SurveyFbfResult]:
        if not fbfbms:
            return {}
        rows = db.scalars(
            select(SurveyFbfResult)
            .where(SurveyFbfResult.tenant_code == tenant_code, SurveyFbfResult.fbfbm.in_(fbfbms))
            .order_by(SurveyFbfResult.fbfbm.asc(), SurveyFbfResult.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        latest: dict[str, SurveyFbfResult] = {}
        for item in rows:
            latest.setdefault(item.fbfbm, item)
        return latest


    def _latest_results_by_code(self, db: Session, tenant_code: str, cbfbms: set[str]) -> dict[str, SurveyCbfResult]:
        if not cbfbms:
            return {}
        rows = db.scalars(
            select(SurveyCbfResult)
            .where(SurveyCbfResult.tenant_code == tenant_code, SurveyCbfResult.cbfbm.in_(cbfbms))
            .order_by(SurveyCbfResult.cbfbm.asc(), SurveyCbfResult.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        latest: dict[str, SurveyCbfResult] = {}
        for item in rows:
            latest.setdefault(item.cbfbm, item)
        return latest




    def _copy_dk_geometry(self, db: Session, source_result_id: int, target_table: str, target_id: int) -> None:
        db.execute(
            text(
                f"""
                UPDATE {target_table} AS target
                SET geom = source.geom
                FROM survey_dk_result AS source
                WHERE target.id = :target_id
                  AND source.id = :source_result_id
                """
            ),
            {"target_id": target_id, "source_result_id": source_result_id},
        )

