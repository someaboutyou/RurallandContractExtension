import csv
import io
import json
import logging
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.orm import Session, object_session

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
    SurveyHouseholdRestructure,
    SurveyHouseholdRestructureMember,
    SurveyHouseholdTag,
    SurveyCbdkxxBase,
    SurveyCbdkxxResult,
    SurveyDkBase,
    SurveyDkResult,
    SurveyFbfBase,
    SurveyFbfResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service
from app.services.request_case_service import request_case_service


logger = logging.getLogger(__name__)


class SurveyService:
    attachment_root = Path(__file__).resolve().parents[2] / "storage" / "survey_attachments"
    authorization_root = Path(__file__).resolve().parents[2] / "storage" / "survey_authorizations"
    operation_change_types = {
        "change_head",
        "member_maintain",
        "deregister",
        "add_parcel",
        "split_parcel",
        "rollback_split_parcel",
        "swap_parcels",
        "rollback_swap_parcels",
        "remove_parcel",
        "split_household",
        "merge_household",
    }
    terminal_operation_types = {"deregister", "merge_household"}
    form_diff_entity_types = {"contractor", "issuer", "member"}
    parcel_diff_entity_types = {"parcel", "parcel_relation"}
    tag_names = {
        "whole_family_urbanized": "鍏ㄥ杩涘煄钀芥埛",
        "household_extinct": "鏁存埛娑堜骸",
        "five_guarantees": "浜斾繚鎴?",
        "little_or_no_land": "鏃犲湴灏戝湴",
    }
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

    def list_tasks(
        self,
        db: Session,
        batch_id: int,
        page: int,
        page_size: int,
        keyword: str | None,
        task_status: str | None,
        region_code: str | None,
        current_user: User,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        normalized_region_code = data_access_service.normalize_region_code(region_code)
        effective_region_code = normalized_region_code or data_access_service.normalize_region_code(batch.region_code)
        if normalized_region_code:
            data_access_service.ensure_region_in_scope(current_user, normalized_region_code)
        filters = self._tenant_filters(SurveyCbfBase, current_user)
        filters.append(SurveyCbfBase.batch_id == batch_id)
        filters.extend(data_access_service.build_code_scope_filters(SurveyCbfBase.cbfbm, current_user))
        if effective_region_code:
            filters.append(SurveyCbfBase.cbfbm.like(f"{effective_region_code}%"))
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(or_(SurveyCbfBase.cbfbm.ilike(pattern), SurveyCbfBase.cbfmc.ilike(pattern)))
        if task_status:
            filters.append(SurveyCbfBase.task_status == task_status)

        task_count_stmt = (
            select(func.count(SurveyCbfBase.id))
            .where(*filters)
            .execution_options(skip_tenant_scope=True)
        )
        task_list_stmt = (
            select(SurveyCbfBase)
            .where(*filters)
            .order_by(SurveyCbfBase.cbfbm.asc(), SurveyCbfBase.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .execution_options(skip_tenant_scope=True)
        )
        logger.info(
            "Survey task query params: batch_id=%s requested_region=%s effective_region=%s page=%s page_size=%s keyword=%s task_status=%s",
            batch.id,
            normalized_region_code,
            effective_region_code,
            page,
            page_size,
            keyword,
            task_status,
        )
        self._log_sql(db, "survey_tasks.count", task_count_stmt)
        self._log_sql(db, "survey_tasks.list", task_list_stmt)
        total = db.scalar(task_count_stmt) or 0
        tasks = db.scalars(task_list_stmt).all()
        if total == 0:
            fallback = self._list_tasks_from_results(
                db,
                batch,
                page,
                page_size,
                keyword,
                task_status,
                effective_region_code,
                current_user,
            )
            if fallback["total"]:
                logger.info(
                    "Survey task query used result fallback: batch_id=%s requested_region=%s effective_region=%s fallback_total=%s",
                    batch.id,
                    normalized_region_code,
                    effective_region_code,
                    fallback["total"],
                )
                return fallback
            self._log_empty_task_query(db, batch, normalized_region_code, effective_region_code, current_user)
        rows = [self._serialize_task(item) for item in tasks]
        return {
            "items": rows,
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def _list_tasks_from_results(
        self,
        db: Session,
        batch: SurveyBatch,
        page: int,
        page_size: int,
        keyword: str | None,
        task_status: str | None,
        effective_region_code: str | None,
        current_user: User,
    ) -> dict:
        base_filters = self._tenant_filters(SurveyCbfBase, current_user)
        base_filters.append(SurveyCbfBase.batch_id == batch.id)
        base_filters.extend(data_access_service.build_code_scope_filters(SurveyCbfBase.cbfbm, current_user))
        if effective_region_code:
            base_filters.append(SurveyCbfBase.cbfbm.like(f"{effective_region_code}%"))
        if keyword:
            pattern = f"%{keyword.strip()}%"
            base_filters.append(or_(SurveyCbfBase.cbfbm.ilike(pattern), SurveyCbfBase.cbfmc.ilike(pattern)))

        base_list_stmt = (
            select(SurveyCbfBase)
            .where(*base_filters)
            .order_by(SurveyCbfBase.cbfbm.asc(), SurveyCbfBase.id.desc())
            .execution_options(skip_tenant_scope=True)
        )
        self._log_sql(db, "survey_tasks.base_fallback.list", base_list_stmt)
        source_bases = db.scalars(base_list_stmt).all()
        latest_base_by_code: dict[str, SurveyCbfBase] = {}
        for item in source_bases:
            latest_base_by_code.setdefault(item.cbfbm, item)

        cbfbms = set(latest_base_by_code)
        task_overlays = {}
        if cbfbms:
            task_overlays = {
                item.cbfbm: item
                for item in db.scalars(
                    select(SurveyCbfBase)
                    .where(
                        SurveyCbfBase.tenant_code == batch.tenant_code,
                        SurveyCbfBase.batch_id == batch.id,
                        SurveyCbfBase.cbfbm.in_(cbfbms),
                    )
                    .execution_options(skip_tenant_scope=True)
                ).all()
            }
        result_overlays = self._latest_results_by_code(db, batch.tenant_code, cbfbms) if cbfbms else {}

        rows = [
            self._serialize_base_task(item, batch.id, task_overlays.get(item.cbfbm), result_overlays.get(item.cbfbm))
            for item in latest_base_by_code.values()
        ]
        if task_status:
            rows = [item for item in rows if item["taskStatus"] == task_status]
        total = len(rows)
        rows = rows[(page - 1) * page_size : page * page_size]
        return {"items": rows, "total": total, "page": page, "pageSize": page_size}

    def list_issuers(
        self,
        db: Session,
        batch_id: int,
        page: int,
        page_size: int,
        keyword: str | None,
        region_code: str | None,
        current_user: User,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        normalized_region_code = data_access_service.normalize_region_code(region_code) or data_access_service.normalize_region_code(batch.region_code)
        if normalized_region_code:
            data_access_service.ensure_region_in_scope(current_user, normalized_region_code)

        filters = self._tenant_filters(SurveyFbfResult, current_user)
        if normalized_region_code:
            if len(normalized_region_code) >= 14:
                filters.append(SurveyFbfResult.fbfbm == normalized_region_code[:14])
            else:
                filters.append(SurveyFbfResult.fbfbm.like(f"{normalized_region_code}%"))
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(or_(SurveyFbfResult.fbfbm.ilike(pattern), SurveyFbfResult.fbfmc.ilike(pattern), SurveyFbfResult.fbffzrxm.ilike(pattern)))

        total = db.scalar(
            select(func.count(SurveyFbfResult.id))
            .where(*filters)
            .execution_options(skip_tenant_scope=True)
        ) or 0
        rows = db.scalars(
            select(SurveyFbfResult)
            .where(*filters)
            .order_by(SurveyFbfResult.fbfbm.asc(), SurveyFbfResult.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .execution_options(skip_tenant_scope=True)
        ).all()

        issuer_codes = {item.fbfbm for item in rows}
        relation_counts = {code: 0 for code in issuer_codes}
        first_contractors: dict[str, str] = {}
        if issuer_codes:
            relation_rows = db.execute(
                select(
                    SurveyCbdkxxResult.fbfbm,
                    func.count(func.distinct(SurveyCbdkxxResult.cbfbm)),
                    func.min(SurveyCbdkxxResult.cbfbm),
                )
                .where(
                    SurveyCbdkxxResult.tenant_code == batch.tenant_code,
                    SurveyCbdkxxResult.fbfbm.in_(issuer_codes),
                )
                .group_by(SurveyCbdkxxResult.fbfbm)
                .execution_options(skip_tenant_scope=True)
            ).all()
            relation_counts.update({code: count for code, count, _cbfbm in relation_rows})
            first_contractors.update({code: cbfbm for code, _count, cbfbm in relation_rows if cbfbm})

        source_tasks = {}
        if first_contractors:
            task_rows = db.scalars(
                select(SurveyCbfBase)
                .where(
                    SurveyCbfBase.tenant_code == batch.tenant_code,
                    SurveyCbfBase.batch_id == batch_id,
                    SurveyCbfBase.cbfbm.in_(set(first_contractors.values())),
                )
                .execution_options(skip_tenant_scope=True)
            ).all()
            tasks_by_cbfbm = {task.cbfbm: task for task in task_rows}
            source_tasks = {
                issuer_code: tasks_by_cbfbm.get(cbfbm)
                for issuer_code, cbfbm in first_contractors.items()
            }

        items = [
            self._serialize_issuer_row(item, batch_id, relation_counts.get(item.fbfbm, 0), source_tasks.get(item.fbfbm))
            for item in rows
        ]
        return {"items": items, "total": total, "page": page, "pageSize": page_size}

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

    def create_issuer(self, db: Session, batch_id: int, payload: dict, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幍瑙勵偧瀹歌尙绮ㄩ弶鐕傜礉娑撳秷鍏橀弬鏉款杻")
        code = payload["code"].strip()
        data_access_service.ensure_code_in_scope(current_user, code, detail="issuer is out of scope")
        if batch.region_code:
            expected = batch.region_code[:14]
            if len(batch.region_code) >= 14 and code != expected:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="issuer code must equal the 14-digit batch region code")
            if len(batch.region_code) < 14 and not code.startswith(batch.region_code):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="issuer code is outside the batch region")
        exists = db.scalars(
            select(SurveyFbfResult).where(
                SurveyFbfResult.tenant_code == batch.tenant_code,
                SurveyFbfResult.fbfbm == code,
            ).execution_options(skip_tenant_scope=True)
        ).first()
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="issuer survey result already exists")

        now = datetime.now(timezone.utc)
        survey_date = self._parse_datetime(payload.get("surveyDate")) or datetime.combine(date.today(), datetime.min.time())
        issuer_uid = str(uuid5(NAMESPACE_URL, f"survey:{batch_id}:fbf:{code}"))
        base = SurveyFbfBase(
            tenant_code=batch.tenant_code,
            region_code=code,
            batch_id=batch_id,
            issuer_uid=issuer_uid,
            source_fbfbm=code,
            fbfbm=code,
            fbfmc=payload["name"],
            fbffzrxm=payload["responsibleName"],
            fzrzjlx=payload.get("responsibleIdType") or "1",
            fzrzjhm=payload["responsibleIdNo"],
            lxdh=payload.get("phone"),
            fbfdz=payload["address"],
            yzbm=payload.get("postcode") or "000000",
            fbfdcy=payload.get("surveyorName") or current_user.real_name,
            fbfdcrq=survey_date,
            fbfdcjs=payload.get("surveyNote"),
            initialized_from_table="manual_add",
            initialized_from_key=code,
            initialized_at=now,
            snapshot_at=now,
        )
        db.add(base)
        db.flush()
        result.result_status = "added"
        result.is_changed = True
        result.change_type = "add_issuer"
        result.remark = payload.get("remark")
        db.add(result)
        db.commit()
        return self._serialize_issuer_row(result, batch_id, 0)

    def get_issuer(self, db: Session, batch_id: int, issuer_uid: str, current_user: User) -> dict:
        issuer = self._get_issuer(db, batch_id, issuer_uid)
        data_access_service.ensure_code_in_scope(current_user, issuer.fbfbm, detail="閸欐垵瀵橀弬閫涚瑝閸︺劌缍嬮崜宥嗘殶閹诡喗娼堥梽鎰瘱閸ユ潙鍞?")
        base = db.scalars(
            select(SurveyFbfBase)
            .where(SurveyFbfBase.tenant_code == issuer.tenant_code, SurveyFbfBase.result_id == issuer.id)
            .execution_options(skip_tenant_scope=True)
        ).first()
        data = self._serialize_issuer(issuer)
        data["baseIssuer"] = self._serialize_base_issuer(base) if base else None
        return data

    def update_issuer(self, db: Session, batch_id: int, issuer_uid: str, payload: dict, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幍瑙勵偧瀹歌尙绮ㄩ弶鐕傜礉娑撳秷鍏樼紒褏鐢荤紓鏍帆")
        issuer = self._get_issuer(db, batch_id, issuer_uid)
        if issuer.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="issuer survey result already confirmed")
        data_access_service.ensure_code_in_scope(current_user, issuer.fbfbm, detail="issuer is out of scope")
        data_access_service.ensure_code_in_scope(current_user, payload["code"], detail="issuer is out of scope")
        if batch.region_code:
            if len(batch.region_code) >= 14 and payload["code"] != batch.region_code[:14]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="issuer code must equal the 14-digit batch region code")
            if len(batch.region_code) < 14 and not payload["code"].startswith(batch.region_code):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="issuer code is outside the batch region")

        base = db.scalars(
            select(SurveyFbfBase)
            .where(SurveyFbfBase.tenant_code == issuer.tenant_code, SurveyFbfBase.result_id == issuer.id)
            .execution_options(skip_tenant_scope=True)
        ).first()
        old_fbfbm = issuer.fbfbm
        issuer.fbfbm = payload["code"]
        issuer.fbfmc = payload["name"]
        issuer.fbffzrxm = payload["responsibleName"]
        issuer.fzrzjlx = payload["responsibleIdType"]
        issuer.fzrzjhm = payload["responsibleIdNo"]
        issuer.lxdh = payload.get("phone")
        issuer.fbfdz = payload["address"]
        issuer.yzbm = payload["postcode"]
        issuer.fbfdcy = payload.get("surveyorName") or current_user.real_name
        issuer.fbfdcrq = self._parse_datetime(payload.get("surveyDate")) or issuer.fbfdcrq
        issuer.fbfdcjs = payload.get("surveyNote")
        issuer.survey_status = payload.get("surveyStatus") or "surveyed"
        issuer.result_status = payload.get("resultStatus") or "normal"
        issuer.change_type = payload.get("changeType") or "none"
        issuer.change_reason = payload.get("changeReason")
        issuer.remark = payload.get("remark")
        issuer.is_changed = self._issuer_changed(issuer, base)
        if old_fbfbm != issuer.fbfbm:
            db.execute(
                update(SurveyCbdkxxResult)
                .where(
                    SurveyCbdkxxResult.tenant_code == issuer.tenant_code,
                    SurveyCbdkxxResult.fbfbm == old_fbfbm,
                )
                .values(fbfbm=issuer.fbfbm)
                .execution_options(skip_tenant_scope=True)
            )
        db.commit()
        return self.get_issuer(db, batch_id, issuer_uid, current_user)

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

    def get_phase2_context(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
        return {
            "tags": self.list_tags(db, batch_id, contractor_uid, current_user),
            "restructures": self.list_restructures(db, batch_id, contractor_uid, current_user),
            "authorizations": self.list_authorizations(db, batch_id, contractor_uid, current_user),
            "attachments": self.list_attachments(db, batch_id, contractor_uid, current_user),
        }

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
        self._ensure_editable_batch_and_result(db, result)
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
        self._ensure_editable_batch_and_result(db, result)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
        db.execute(delete(SurveyHouseholdRestructureMember).where(SurveyHouseholdRestructureMember.restructure_id == item.id))
        db.delete(item)
        db.commit()

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
        self._ensure_editable_batch_and_result(db, result)
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
        self._ensure_editable_batch_and_result(db, result)
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
        return f"{item.authorization_no}_閹哄牊娼堟慨鏃€澧稊?txt", content.encode("utf-8-sig")

    def revoke_authorization(self, db: Session, authorization_id: int, revoke_reason: str, current_user: User) -> dict:
        item = db.get(SurveyAuthorization, authorization_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request failed")
        result = self._get_result(db, item.batch_id, item.contractor_uid)
        self._ensure_editable_batch_and_result(db, result)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        item.status = "revoked"
        item.revoke_reason = revoke_reason
        db.commit()
        db.refresh(item)
        return self._serialize_authorization(item)

    def list_attachments(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> list[dict]:
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        rows = db.scalars(
            select(SurveyAttachment)
            .where(SurveyAttachment.batch_id == batch_id, SurveyAttachment.contractor_uid == contractor_uid)
            .order_by(SurveyAttachment.id.desc())
        ).all()
        return [self._serialize_attachment(item) for item in rows]

    async def upload_attachment(self, db: Session, batch_id: int, contractor_uid: str, category: str, description: str | None, upload_file: UploadFile, current_user: User) -> dict:
        result = self._get_result(db, batch_id, contractor_uid)
        self._ensure_editable_batch_and_result(db, result)
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
        self._ensure_editable_batch_and_result(db, result)
        try:
            Path(item.storage_path).unlink(missing_ok=True)
        except OSError:
            pass
        db.delete(item)
        db.commit()

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

    def update_result(self, db: Session, batch_id: int, contractor_uid: str, payload: dict, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幍瑙勵偧瀹歌尙绮ㄩ弶鐕傜礉娑撳秷鍏樼紒褏鐢荤紓鏍帆")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幋鎰亯瀹歌尙鈥樼拋銈忕礉娑撳秷鍏樼紒褏鐢荤紓鏍帆")
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
        result.result_status = payload.get("resultStatus") or "normal"
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
        if result.is_changed or result.change_reason:
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
        has_terminal_operation = any(
            (operation.get("type") if isinstance(operation, dict) else None) in self.terminal_operation_types
            for operation in pending_operations
        )
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

    def confirm_result(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幍瑙勵偧瀹歌尙绮ㄩ弶鐕傜礉娑撳秷鍏樼紒褏鐢荤涵顔款吇")
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        if result.survey_status not in {"surveyed", "changed", "unchanged"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠囧嘲鍘涙穱婵嗙摠鐠嬪啯鐓＄紒鎾寸亯閸氬骸鍟€绾喛顓?")
        self._validate_confirmable(db, result)
        now = datetime.now(timezone.utc)
        result.survey_status = "confirmed"
        result.confirmed_at = now
        result.reviewer_id = current_user.id
        result.reviewer_name = current_user.real_name
        result.reviewed_at = now
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
            task.task_status = "confirmed"
            task.confirmed_at = now
            task.reviewed_at = now
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def skip_task(self, db: Session, batch_id: int, contractor_uid: str, skip_reason: str, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幍瑙勵偧瀹歌尙绮ㄩ弶鐕傜礉娑撳秷鍏樼紒褏鐢婚幙宥勭稊")
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幋鎰亯瀹歌尙鈥樼拋銈忕礉娑撳秷鍏樼捄瀹犵箖")
        now = datetime.now(timezone.utc)
        result.survey_status = "skipped"
        result.result_status = "normal"
        result.remark = skip_reason
        result.investigator_id = current_user.id
        result.investigator_name = current_user.real_name
        result.investigated_at = now
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

    def _validate_confirmable(self, db: Session, result: SurveyCbfResult) -> None:
        members = db.scalars(
            select(SurveyCbfJtcyResult)
            .where(
                SurveyCbfJtcyResult.contractor_uid == result.contractor_uid,
            )
            .order_by(SurveyCbfJtcyResult.id.asc())
        ).all()
        errors: list[str] = []
        if result.cbflx == "1":
            if not members:
                errors.append("validation error")
            household_heads = [member for member in members if member.is_household_head or member.yhzgx == "01"]
            if len(household_heads) != 1:
                errors.append("validation error")

        seen_id_nos: set[str] = set()
        for member in members:
            id_no = (member.cyzjhm or "").strip()
            if id_no:
                if id_no in seen_id_nos:
                    errors.append(f"duplicate member id number: {id_no}")
                    break
                seen_id_nos.add(id_no)

        if result.is_changed or result.change_type != "none":
            if not self._has_text(result.change_reason):
                errors.append("閹靛灝瀵橀弬鐟扮摠閸︺劌褰夐崠鏍ㄦ韫囧懘銆忔繅顐㈠晸閸欐ê瀵查崢鐔锋礈")
            if not self._has_text(result.policy_basis):
                errors.append("閹靛灝瀵橀弬鐟扮摠閸︺劌褰夐崠鏍ㄦ韫囧懘銆忔繅顐㈠晸閺€璺ㄧ摜娓氭繃宓?")

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
                errors.append("validation error")

        if errors:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request failed")

    def _ensure_editable_batch_and_result(self, db: Session, result: SurveyCbfResult) -> None:
        base = db.scalar(select(SurveyCbfBase).where(SurveyCbfBase.contractor_uid == result.contractor_uid).order_by(SurveyCbfBase.id.desc())) if result else None
        batch = self._ensure_batch(db, base.batch_id) if base else None
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幍瑙勵偧瀹歌尙绮ㄩ弶鐕傜礉娑撳秷鍏樼紒褏鐢荤紓鏍帆")
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幋鎰亯瀹歌尙鈥樼拋銈忕礉娑撳秷鍏樼紒褏鐢荤紓鏍帆")

    async def _store_upload(self, directory: Path, upload_file: UploadFile) -> tuple[Path, int]:
        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="娑撳﹣绱堕弬鍥︽娑撹櫣鈹?")
        directory.mkdir(parents=True, exist_ok=True)
        suffix = Path(upload_file.filename or "").suffix
        storage_path = directory / f"{uuid4().hex}{suffix}"
        with storage_path.open("wb") as target:
            target.write(content)
        return storage_path, len(content)

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

    def _ensure_batch(self, db: Session, batch_id: int) -> SurveyBatch:
        batch = db.get(SurveyBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request failed")
        return batch

    @staticmethod
    def _short_region_name(region_name: str | None, region_code: str) -> str:
        if not region_name:
            return region_code
        parts = [part.strip() for part in region_name.replace("、", "/").split("/") if part.strip()]
        return parts[-1] if parts else region_name.strip()

    def _get_result(self, db: Session, batch_id: int, contractor_uid: str) -> SurveyCbfResult:
        batch = self._ensure_batch(db, batch_id)
        result = db.scalars(
            select(SurveyCbfResult)
            .where(SurveyCbfResult.tenant_code == batch.tenant_code, SurveyCbfResult.contractor_uid == contractor_uid)
            .order_by(SurveyCbfResult.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).first()
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request failed")
        result_scope_code = result.group_region_code or result.region_code
        if batch.survey_type == "household_survey" and batch.region_code and not (result_scope_code or "").startswith(batch.region_code):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request failed")
        return result



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
            db.add(result)
            db.flush()
            self._copy_dk_geometry(db, dk.id, "survey_dk_base", base.id)
            self._copy_dk_geometry(db, dk.id, "survey_dk_result", result.id)

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

    def _normalize_geojson_geometry(self, geometry: dict | None) -> dict | None:
        if geometry is None:
            return None
        candidate = geometry
        if isinstance(candidate, dict) and candidate.get("type") == "Feature":
            candidate = candidate.get("geometry")
        if not isinstance(candidate, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid parcel geometry")
        geometry_type = str(candidate.get("type") or "")
        if geometry_type not in {"Polygon", "MultiPolygon"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parcel geometry must be Polygon or MultiPolygon")
        if not candidate.get("coordinates"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parcel geometry is empty")
        return candidate

    def _geojson_4527_sql(self, geojson_param: str = "geojson", srid_param: str = "source_srid") -> str:
        return (
            "ST_Multi(ST_CollectionExtract(ST_MakeValid("
            f"ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:{geojson_param}), :{srid_param}), 4527)"
            "), 3))"
        )

    def _measure_geojson_area_mu(self, db: Session, geometry: dict, source_srid: int) -> float | None:
        stmt = text(
            f"""
            WITH input_geom AS (
                SELECT {self._geojson_4527_sql()} AS geom
            )
            SELECT
                CASE
                    WHEN geom IS NULL OR ST_IsEmpty(geom) THEN NULL
                    ELSE ROUND(CAST(ST_Area(geom) / 666.6666667 AS numeric), 4)
                END AS area_mu
            FROM input_geom
            """
        )
        try:
            area_mu = db.scalar(
                stmt,
                {
                    "geojson": json.dumps(geometry, ensure_ascii=False),
                    "source_srid": int(source_srid or 4326),
                },
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid parcel geometry") from exc
        return float(area_mu) if area_mu is not None else None

    def _find_local_geometry_conflicts(self, db: Session, geometry: dict, source_srid: int, local_parcels: list[dict] | None) -> list[dict]:
        candidate_parcels = [
            {
                "dkbm": item.get("dkbm"),
                "dkmc": item.get("dkmc"),
                "cbfbm": item.get("cbfbm"),
                "cbfmc": item.get("cbfmc"),
                "geometry": self._normalize_geojson_geometry(item.get("geometry")),
            }
            for item in (local_parcels or [])
            if isinstance(item, dict) and item.get("resultStatus") != "removed" and item.get("geometry")
        ]
        if not candidate_parcels:
            return []
        stmt = text(
            """
            WITH input_geom AS (
                SELECT """
            + self._geojson_4527_sql()
            + """ AS geom
            ),
            local_parcels AS (
                SELECT
                    item->>'dkbm' AS dkbm,
                    item->>'dkmc' AS dkmc,
                    item->>'cbfbm' AS cbfbm,
                    item->>'cbfmc' AS cbfmc,
                    ST_Multi(
                        ST_CollectionExtract(
                            ST_MakeValid(
                                ST_Transform(
                                    ST_SetSRID(ST_GeomFromGeoJSON((item->'geometry')::text), 4326),
                                    4527
                                )
                            ),
                            3
                        )
                    ) AS geom
                FROM jsonb_array_elements(CAST(:local_parcels_json AS jsonb)) AS item
            )
            SELECT
                'local' AS source,
                dkbm,
                dkmc,
                cbfbm,
                cbfmc,
                ROUND(CAST(ST_Area(ST_Intersection(local_parcels.geom, input_geom.geom)) / 666.6666667 AS numeric), 4) AS overlap_area_mu
            FROM local_parcels
            CROSS JOIN input_geom
            WHERE input_geom.geom IS NOT NULL
              AND local_parcels.geom IS NOT NULL
              AND NOT ST_IsEmpty(local_parcels.geom)
              AND ST_Intersects(local_parcels.geom, input_geom.geom)
              AND NOT ST_Touches(local_parcels.geom, input_geom.geom)
            ORDER BY overlap_area_mu DESC NULLS LAST, dkbm
            LIMIT 20
            """
        )
        rows = db.execute(
            stmt,
            {
                "geojson": json.dumps(geometry, ensure_ascii=False),
                "source_srid": int(source_srid or 4326),
                "local_parcels_json": json.dumps(candidate_parcels, ensure_ascii=False),
            },
        ).mappings().all()
        return [
            {
                "source": row["source"],
                "dkbm": row["dkbm"],
                "dkmc": row["dkmc"],
                "cbfbm": row["cbfbm"],
                "cbfmc": row["cbfmc"],
                "overlapAreaMu": float(row["overlap_area_mu"]) if row["overlap_area_mu"] is not None else None,
            }
            for row in rows
        ]

    def _find_database_geometry_conflicts(
        self,
        db: Session,
        tenant_code: str,
        geometry: dict,
        source_srid: int,
        exclude_dkbms: list[str] | None = None,
    ) -> list[dict]:
        params = {
            "tenant_code": tenant_code,
            "geojson": json.dumps(geometry, ensure_ascii=False),
            "source_srid": int(source_srid or 4326),
        }
        exclude_codes = [str(code).strip() for code in (exclude_dkbms or []) if str(code).strip()]
        exclude_sql = ""
        if exclude_codes:
            placeholders = []
            for index, code in enumerate(exclude_codes):
                key = f"exclude_dkbm_{index}"
                params[key] = code
                placeholders.append(f":{key}")
            exclude_sql = f" AND dk.dkbm NOT IN ({', '.join(placeholders)})"
        stmt = text(
            f"""
            WITH input_geom AS (
                SELECT {self._geojson_4527_sql()} AS geom
            ),
            current_dk AS (
                SELECT DISTINCT ON (dkbm)
                    dkbm,
                    dkmc,
                    geom
                FROM public.survey_dk_result
                WHERE tenant_code = :tenant_code
                  AND result_status NOT IN ('removed', 'split_source')
                  AND geom IS NOT NULL
                ORDER BY dkbm, id DESC
            ),
            current_relation AS (
                SELECT DISTINCT ON (dkbm)
                    dkbm,
                    cbfbm
                FROM public.survey_cbdkxx_result
                WHERE tenant_code = :tenant_code
                  AND result_status NOT IN ('removed', 'split_source')
                ORDER BY dkbm, id DESC
            ),
            current_contractor AS (
                SELECT DISTINCT ON (cbfbm)
                    cbfbm,
                    cbfmc
                FROM public.survey_cbf_result
                WHERE tenant_code = :tenant_code
                ORDER BY cbfbm, id DESC
            )
            SELECT
                'database' AS source,
                dk.dkbm,
                dk.dkmc,
                relation.cbfbm,
                contractor.cbfmc,
                ROUND(CAST(ST_Area(ST_Intersection(dk.geom, input_geom.geom)) / 666.6666667 AS numeric), 4) AS overlap_area_mu
            FROM current_dk AS dk
            CROSS JOIN input_geom
            LEFT JOIN current_relation AS relation ON relation.dkbm = dk.dkbm
            LEFT JOIN current_contractor AS contractor ON contractor.cbfbm = relation.cbfbm
            WHERE input_geom.geom IS NOT NULL
              AND dk.geom IS NOT NULL
              AND NOT ST_IsEmpty(dk.geom)
              AND ST_Intersects(dk.geom, input_geom.geom)
              AND NOT ST_Touches(dk.geom, input_geom.geom)
              {exclude_sql}
            ORDER BY overlap_area_mu DESC NULLS LAST, dk.dkbm
            LIMIT 20
            """
        )
        rows = db.execute(stmt, params).mappings().all()
        return [
            {
                "source": row["source"],
                "dkbm": row["dkbm"],
                "dkmc": row["dkmc"],
                "cbfbm": row["cbfbm"],
                "cbfmc": row["cbfmc"],
                "overlapAreaMu": float(row["overlap_area_mu"]) if row["overlap_area_mu"] is not None else None,
            }
            for row in rows
        ]

    def _write_survey_dk_geometry(self, db: Session, table_name: str, row_id: int, geometry: dict, source_srid: int) -> None:
        stmt = text(
            f"""
            UPDATE {table_name}
            SET geom = {self._geojson_4527_sql()}
            WHERE id = :row_id
            """
        )
        try:
            db.execute(
                stmt,
                {
                    "row_id": row_id,
                    "geojson": json.dumps(geometry, ensure_ascii=False),
                    "source_srid": int(source_srid or 4326),
                },
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="failed to save parcel geometry") from exc

    def _normalize_split_geometry(self, geometry: dict | None) -> dict | None:
        if geometry is None:
            return None
        candidate = geometry
        if isinstance(candidate, dict) and candidate.get("type") == "Feature":
            candidate = candidate.get("geometry")
        if not isinstance(candidate, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid split geometry")
        geometry_type = str(candidate.get("type") or "")
        if geometry_type not in {"LineString", "MultiLineString", "Polygon", "MultiPolygon"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="split geometry must be line or polygon",
            )
        if not candidate.get("coordinates"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split geometry is empty")
        return candidate

    @staticmethod
    def _parse_geojson_text(value: str | None) -> dict | None:
        if not value:
            return None
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid split geometry result") from exc

    def _load_result_geometry_extent(self, db: Session, row_id: int) -> dict:
        row = db.execute(
            text(
                """
                SELECT
                    ST_XMin(geom) AS min_x,
                    ST_YMin(geom) AS min_y,
                    ST_XMax(geom) AS max_x,
                    ST_YMax(geom) AS max_y,
                    ST_Area(geom) AS area_sqm
                FROM survey_dk_result
                WHERE id = :row_id
                  AND geom IS NOT NULL
                  AND NOT ST_IsEmpty(geom)
                """
            ),
            {"row_id": row_id},
        ).mappings().first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="selected parcel does not have geometry",
            )
        return {
            "minX": float(row["min_x"]),
            "minY": float(row["min_y"]),
            "maxX": float(row["max_x"]),
            "maxY": float(row["max_y"]),
            "areaSqm": float(row["area_sqm"]),
        }

    @staticmethod
    def _direction_clip_bounds(direction: str, threshold: float, extent: dict) -> dict:
        min_x = extent["minX"]
        min_y = extent["minY"]
        max_x = extent["maxX"]
        max_y = extent["maxY"]
        padding = 1.0
        if direction == "east":
            return {"left": threshold, "bottom": min_y - padding, "right": max_x + padding, "top": max_y + padding}
        if direction == "west":
            return {"left": min_x - padding, "bottom": min_y - padding, "right": threshold, "top": max_y + padding}
        if direction == "south":
            return {"left": min_x - padding, "bottom": min_y - padding, "right": max_x + padding, "top": threshold}
        if direction == "north":
            return {"left": min_x - padding, "bottom": threshold, "right": max_x + padding, "top": max_y + padding}
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid split direction")

    def _measure_directional_split_area_sqm(self, db: Session, row_id: int, bounds: dict) -> float:
        area_sqm = db.scalar(
            text(
                """
                WITH source AS (
                    SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)) AS geom
                    FROM survey_dk_result
                    WHERE id = :row_id
                ),
                clip AS (
                    SELECT ST_MakeEnvelope(:left, :bottom, :right, :top, 4527) AS geom
                )
                SELECT COALESCE(
                    ST_Area(
                        ST_Multi(
                            ST_CollectionExtract(
                                ST_MakeValid(ST_Intersection(source.geom, clip.geom)),
                                3
                            )
                        )
                    ),
                    0
                )
                FROM source
                CROSS JOIN clip
                """
            ),
            {"row_id": row_id, **bounds},
        )
        return float(area_sqm or 0)

    def _split_rows_to_parts(self, rows: list[dict] | None) -> list[dict]:
        parts: list[dict] = []
        for row in rows or []:
            geometry = self._parse_geojson_text(row.get("geojson"))
            area_mu = float(row["area_mu"]) if row.get("area_mu") is not None else 0
            if geometry and area_mu > 0:
                parts.append({
                    "geometry": geometry,
                    "areaMu": round(area_mu, 4),
                })
        return parts

    def _split_row_geometry_by_direction(
        self,
        db: Session,
        row_id: int,
        direction: str,
        target_area_mu: float,
    ) -> dict:
        normalized_direction = str(direction or "").strip().lower()
        if normalized_direction not in {"east", "west", "south", "north"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid split direction")
        extent = self._load_result_geometry_extent(db, row_id)
        target_area_sqm = float(target_area_mu) * 666.6666667
        source_area_sqm = float(extent["areaSqm"])
        if target_area_sqm <= 0 or target_area_sqm >= source_area_sqm:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split area must be smaller than source parcel area")

        low = extent["minX"] if normalized_direction in {"east", "west"} else extent["minY"]
        high = extent["maxX"] if normalized_direction in {"east", "west"} else extent["maxY"]
        increasing = normalized_direction in {"west", "south"}
        for _ in range(32):
            middle = (low + high) / 2
            bounds = self._direction_clip_bounds(normalized_direction, middle, extent)
            current_area_sqm = self._measure_directional_split_area_sqm(db, row_id, bounds)
            if increasing:
                if current_area_sqm < target_area_sqm:
                    low = middle
                else:
                    high = middle
            else:
                if current_area_sqm > target_area_sqm:
                    low = middle
                else:
                    high = middle
        threshold = (low + high) / 2
        bounds = self._direction_clip_bounds(normalized_direction, threshold, extent)
        rows = db.execute(
            text(
                """
                WITH source AS (
                    SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)) AS geom
                    FROM survey_dk_result
                    WHERE id = :row_id
                ),
                clip AS (
                    SELECT ST_MakeEnvelope(:left, :bottom, :right, :top, 4527) AS geom
                ),
                fragments AS (
                    SELECT
                        0 AS part_group,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid((dump).geom), 3)) AS geom
                    FROM source
                    CROSS JOIN clip
                    CROSS JOIN LATERAL ST_Dump(
                        ST_CollectionExtract(ST_MakeValid(ST_Intersection(source.geom, clip.geom)), 3)
                    ) AS dump
                    UNION ALL
                    SELECT
                        1 AS part_group,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid((dump).geom), 3)) AS geom
                    FROM source
                    CROSS JOIN clip
                    CROSS JOIN LATERAL ST_Dump(
                        ST_CollectionExtract(ST_MakeValid(ST_Difference(source.geom, clip.geom)), 3)
                    ) AS dump
                )
                SELECT
                    part_group,
                    ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geojson,
                    ROUND(CAST(ST_Area(geom) / 666.6666667 AS numeric), 4) AS area_mu
                FROM fragments
                WHERE geom IS NOT NULL
                  AND NOT ST_IsEmpty(geom)
                ORDER BY part_group, ST_Area(geom) DESC, ST_XMin(geom), ST_YMin(geom)
                """
            ),
            {"row_id": row_id, **bounds},
        ).mappings().all()
        parts = self._split_rows_to_parts(rows)
        if len(parts) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="failed to split parcel by direction")
        return {"parts": parts}

    def _split_row_geometry_by_shape(
        self,
        db: Session,
        row_id: int,
        split_geometry: dict,
        source_srid: int,
    ) -> dict:
        normalized_geometry = self._normalize_split_geometry(split_geometry)
        if normalized_geometry is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split geometry is required")
        geometry_type = str(normalized_geometry.get("type") or "")
        params = {
            "row_id": row_id,
            "geojson": json.dumps(normalized_geometry, ensure_ascii=False),
            "source_srid": int(source_srid or 4326),
        }
        if geometry_type in {"Polygon", "MultiPolygon"}:
            stmt = text(
                f"""
                WITH source AS (
                    SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)) AS geom
                    FROM survey_dk_result
                    WHERE id = :row_id
                ),
                splitter AS (
                    SELECT ST_MakeValid({self._geojson_4527_sql()}) AS geom
                ),
                fragments AS (
                    SELECT
                        0 AS part_group,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid((dump).geom), 3)) AS geom
                    FROM source
                    CROSS JOIN splitter
                    CROSS JOIN LATERAL ST_Dump(
                        ST_CollectionExtract(ST_MakeValid(ST_Intersection(source.geom, splitter.geom)), 3)
                    ) AS dump
                    UNION ALL
                    SELECT
                        1 AS part_group,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid((dump).geom), 3)) AS geom
                    FROM source
                    CROSS JOIN splitter
                    CROSS JOIN LATERAL ST_Dump(
                        ST_CollectionExtract(ST_MakeValid(ST_Difference(source.geom, splitter.geom)), 3)
                    ) AS dump
                )
                SELECT
                    part_group,
                    ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geojson,
                    ROUND(CAST(ST_Area(geom) / 666.6666667 AS numeric), 4) AS area_mu
                FROM fragments
                WHERE geom IS NOT NULL
                  AND NOT ST_IsEmpty(geom)
                ORDER BY part_group, ST_Area(geom) DESC, ST_XMin(geom), ST_YMin(geom)
                """
            )
        else:
            stmt = text(
                f"""
                WITH source AS (
                    SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)) AS geom
                    FROM survey_dk_result
                    WHERE id = :row_id
                ),
                splitter AS (
                    SELECT ST_MakeValid(
                        ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), :source_srid), 4527)
                    ) AS geom
                ),
                fragments AS (
                    SELECT
                        0 AS part_group,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid((dump).geom), 3)) AS geom
                    FROM source
                    CROSS JOIN splitter
                    CROSS JOIN LATERAL ST_Dump(ST_Split(source.geom, splitter.geom)) AS dump
                )
                SELECT
                    part_group,
                    ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geojson,
                    ROUND(CAST(ST_Area(geom) / 666.6666667 AS numeric), 4) AS area_mu
                FROM fragments
                WHERE geom IS NOT NULL
                  AND NOT ST_IsEmpty(geom)
                ORDER BY ST_Area(geom) DESC, ST_XMin(geom), ST_YMin(geom)
                """
            )
        rows = db.execute(stmt, params).mappings().all()
        parts = self._split_rows_to_parts(rows)
        if geometry_type in {"LineString", "MultiLineString"} and len(parts) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split line does not divide the parcel")
        if len(parts) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split geometry is invalid")
        return {"parts": parts}

    def validate_parcel_geometry(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        payload: dict,
        current_user: User,
    ) -> dict:
        logger.info(
            "survey.validate_parcel_geometry start batch_id=%s contractor_uid=%s payload_geometry_type=%s local_parcel_count=%s",
            batch_id,
            contractor_uid,
            payload.get("geometry", {}).get("type") if isinstance(payload.get("geometry"), dict) else None,
            len(payload.get("localParcels") or []),
        )
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")

        geometry = self._normalize_geojson_geometry(payload.get("geometry"))
        if geometry is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parcel geometry is required")
        source_srid = int(payload.get("geometrySourceSrid") or 4326)
        area_mu = self._measure_geojson_area_mu(db, geometry, source_srid)
        if area_mu is None or area_mu <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parcel geometry is invalid")

        local_conflicts = self._find_local_geometry_conflicts(db, geometry, source_srid, payload.get("localParcels") or [])
        known_dkbms = [
            item.get("dkbm")
            for item in (payload.get("localParcels") or [])
            if isinstance(item, dict) and item.get("dkbm")
        ]
        db_conflicts = self._find_database_geometry_conflicts(
            db,
            batch.tenant_code,
            geometry,
            source_srid,
            exclude_dkbms=known_dkbms,
        )
        overlaps = local_conflicts + db_conflicts
        logger.info(
            "survey.validate_parcel_geometry result batch_id=%s contractor_uid=%s area_mu=%s local_conflicts=%s db_conflicts=%s valid=%s",
            batch_id,
            contractor_uid,
            area_mu,
            len(local_conflicts),
            len(db_conflicts),
            len(overlaps) == 0,
        )
        return {
            "valid": len(overlaps) == 0,
            "areaMu": area_mu,
            "overlaps": overlaps,
        }

    def generate_next_parcel_code(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        current_user: User,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")

        prefix = (result.group_region_code or result.cbfbm[:14] or batch.region_code or "")[:14]
        if not prefix:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parcel code prefix is unavailable")

        existing_codes = db.scalars(
            select(SurveyDkResult.dkbm)
            .where(
                SurveyDkResult.tenant_code == batch.tenant_code,
                SurveyDkResult.dkbm.like(f"{prefix}%"),
            )
            .execution_options(skip_tenant_scope=True)
        ).all()

        max_sequence = 0
        for code in existing_codes:
            text = str(code or "").strip()
            if len(text) < len(prefix) + 5:
                continue
            suffix = text[len(prefix) : len(prefix) + 5]
            if suffix.isdigit():
                max_sequence = max(max_sequence, int(suffix))

        next_sequence = max_sequence + 1
        return {
            "prefix": prefix,
            "sequence": next_sequence,
            "dkbm": f"{prefix}{next_sequence:05d}",
        }

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

    def _build_task_scope_filters(self, current_user: User, region_code: str | None = None) -> list:
        filters = self._tenant_filters(SurveyCbfBase, current_user)
        filters.extend(data_access_service.build_code_scope_filters(SurveyCbfBase.region_code, current_user))
        if region_code:
            filters.append(SurveyCbfBase.region_code.like(f"{region_code}%"))
        return filters

    def _tenant_filters(self, model, current_user: User) -> list:
        tenant_code = data_access_service.get_tenant_code(current_user)
        if tenant_code and hasattr(model, "tenant_code"):
            return [model.tenant_code == tenant_code]
        tenant_filter = data_access_service.build_tenant_filter(model, current_user)
        return [] if tenant_filter is None else [tenant_filter]

    @staticmethod
    def _append_group_region_filter(filters: list, column, region_code: str | None) -> None:
        if not region_code:
            return
        if len(region_code) >= 14:
            filters.append(column == region_code)
        else:
            filters.append(column.like(f"{region_code}%"))

    @staticmethod
    def _log_sql(db: Session, label: str, stmt) -> None:
        try:
            compiled = stmt.compile(bind=db.get_bind(), compile_kwargs={"literal_binds": True})
            logger.info("SQL[%s]: %s", label, compiled)
        except Exception:
            logger.exception("Failed to compile SQL[%s]", label)
            logger.info("SQL[%s]: %s", label, stmt)

    def _log_empty_task_query(
        self,
        db: Session,
        batch: SurveyBatch,
        requested_region_code: str | None,
        effective_region_code: str | None,
        current_user: User,
    ) -> None:
        same_batch_count = db.scalar(
            select(func.count(SurveyCbfBase.id))
            .where(
                SurveyCbfBase.tenant_code == batch.tenant_code,
                SurveyCbfBase.batch_id == batch.id,
            )
            .execution_options(skip_tenant_scope=True)
        ) or 0
        code_prefix_count = 0
        region_prefix_count = 0
        if effective_region_code:
            code_prefix_count = db.scalar(
                select(func.count(SurveyCbfBase.id))
                .where(
                    SurveyCbfBase.tenant_code == batch.tenant_code,
                    SurveyCbfBase.batch_id == batch.id,
                    SurveyCbfBase.cbfbm.like(f"{effective_region_code}%"),
                )
                .execution_options(skip_tenant_scope=True)
            ) or 0
            region_prefix_count = db.scalar(
                select(func.count(SurveyCbfBase.id))
                .where(
                    SurveyCbfBase.tenant_code == batch.tenant_code,
                    SurveyCbfBase.batch_id == batch.id,
                    SurveyCbfBase.region_code.like(f"{effective_region_code}%"),
                )
                .execution_options(skip_tenant_scope=True)
            ) or 0
        logger.info(
            "Survey task query returned empty: batch_id=%s tenant=%s batch_region=%s requested_region=%s effective_region=%s user_id=%s data_scope=%s same_batch_count=%s code_prefix_count=%s region_prefix_count=%s",
            batch.id,
            batch.tenant_code,
            batch.region_code,
            requested_region_code,
            effective_region_code,
            current_user.id,
            current_user.role.data_scope,
            same_batch_count,
            code_prefix_count,
            region_prefix_count,
        )

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

    def _serialize_task(self, item: SurveyCbfBase) -> dict:
        result = None
        session = object_session(item)
        if session and item.contractor_uid:
            result = session.scalar(
                select(SurveyCbfResult).where(SurveyCbfResult.contractor_uid == item.contractor_uid).order_by(SurveyCbfResult.id.desc())
            )
        return {
            "id": item.id,
            "batchId": item.batch_id,
            "contractorUid": item.contractor_uid,
            "cbfbm": item.cbfbm,
            "cbfmc": item.cbfmc,
            "regionCode": item.region_code,
            "groupRegionCode": (result.group_region_code if result else None) or item.cbfbm[:14],
            "groupRegionName": result.group_region_name if result else None,
            "taskStatus": item.task_status,
            "hasChange": item.has_change,
            "changeCount": item.change_count,
            "investigatedAt": item.investigated_at,
            "remark": item.remark,
        }

    def _serialize_result_task(self, result: SurveyCbfResult, survey_batch_id: int, task: SurveyCbfBase | None = None) -> dict:
        result_task_status = "not_started" if result.survey_status == "not_surveyed" else (result.survey_status or "not_started")
        return {
            "id": task.id if task else result.id,
            "batchId": survey_batch_id,
            "contractorUid": result.contractor_uid,
            "cbfbm": result.cbfbm,
            "cbfmc": result.cbfmc,
            "regionCode": result.region_code,
            "groupRegionCode": result.group_region_code,
            "groupRegionName": result.group_region_name,
            "taskStatus": task.task_status if task else result_task_status,
            "hasChange": task.has_change if task else result.is_changed,
            "changeCount": task.change_count if task else 0,
            "investigatedAt": task.investigated_at if task else result.investigated_at,
            "remark": task.remark if task else result.remark,
        }

    def _serialize_base_task(
        self,
        base: SurveyCbfBase,
        survey_batch_id: int,
        task: SurveyCbfBase | None = None,
        result: SurveyCbfResult | None = None,
    ) -> dict:
        result_task_status = "not_started"
        if result is not None and result.survey_status:
            result_task_status = "not_started" if result.survey_status == "not_surveyed" else result.survey_status
        return {
            "id": task.id if task else base.id,
            "batchId": survey_batch_id,
            "contractorUid": task.contractor_uid if task else base.contractor_uid,
            "cbfbm": task.cbfbm if task else base.cbfbm,
            "cbfmc": task.cbfmc if task else base.cbfmc,
            "regionCode": task.region_code if task else base.region_code,
            "groupRegionCode": (result.group_region_code if result else None) or base.cbfbm[:14],
            "groupRegionName": result.group_region_name if result else None,
            "taskStatus": task.task_status if task else result_task_status,
            "hasChange": task.has_change if task else bool(result and result.is_changed),
            "changeCount": task.change_count if task else 0,
            "investigatedAt": task.investigated_at if task else (result.investigated_at if result else None),
            "remark": task.remark if task else (result.remark if result else None),
        }

    def _serialize_issuer_row(self, item: SurveyFbfResult, survey_batch_id: int, related_count: int = 0, source_task: SurveyCbfBase | None = None) -> dict:
        return {
            "id": item.id,
            "batchId": survey_batch_id,
            "issuerUid": item.issuer_uid,
            "code": item.fbfbm,
            "name": item.fbfmc,
            "responsibleName": item.fbffzrxm,
            "surveyStatus": item.survey_status,
            "relatedContractorCount": related_count,
            "surveyDate": item.fbfdcrq.date().isoformat() if item.fbfdcrq else None,
            "surveyorName": item.fbfdcy,
            "sourceTask": self._serialize_task(source_task) if source_task else None,
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
            elif op_type == "split_household":
                self.split_household(db, batch_id, contractor_uid, payload, current_user, commit=False)
            elif op_type == "merge_household":
                self.merge_household(db, batch_id, contractor_uid, payload, current_user, commit=False)
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"unsupported pending operation: {op_type}")

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

    def _get_issuer(self, db: Session, batch_id: int, issuer_uid: str) -> SurveyFbfResult:
        batch = self._ensure_batch(db, batch_id)
        issuer = db.scalars(
            select(SurveyFbfResult)
            .where(
                SurveyFbfResult.tenant_code == batch.tenant_code,
                SurveyFbfResult.issuer_uid == issuer_uid,
            )
            .execution_options(skip_tenant_scope=True)
        ).first()
        if issuer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="閸欐垵瀵橀弬纭呯殶閺屻儲鍨氶弸婊€绗夌€涙ê婀?")
        return issuer

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

    def _serialize_issuer(self, item: SurveyFbfResult) -> dict:
        return {
            "id": item.id,
            "issuerUid": item.issuer_uid,
            "baseId": None,  # TODO: lookup from base
            "code": item.fbfbm,
            "name": item.fbfmc,
            "responsibleName": item.fbffzrxm,
            "responsibleIdType": item.fzrzjlx,
            "responsibleIdNo": item.fzrzjhm,
            "phone": item.lxdh,
            "address": item.fbfdz,
            "postcode": item.yzbm,
            "surveyorName": item.fbfdcy,
            "surveyDate": item.fbfdcrq.date().isoformat() if item.fbfdcrq else None,
            "surveyNote": item.fbfdcjs,
            "surveyStatus": item.survey_status,
            "resultStatus": item.result_status,
            "isChanged": item.is_changed,
            "changeType": item.change_type,
            "changeReason": item.change_reason,
            "policyBasis": getattr(item, "policy_basis", None),
            "remark": item.remark,
        }

    def _serialize_base_issuer(self, item: SurveyFbfBase) -> dict:
        return {
            "code": item.fbfbm,
            "name": item.fbfmc,
            "responsibleName": item.fbffzrxm,
            "responsibleIdType": item.fzrzjlx,
            "responsibleIdNo": item.fzrzjhm,
            "phone": item.lxdh,
            "address": item.fbfdz,
            "postcode": item.yzbm,
            "surveyorName": item.fbfdcy,
            "surveyDate": item.fbfdcrq.date().isoformat() if item.fbfdcrq else None,
            "surveyNote": item.fbfdcjs,
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

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.combine(datetime.strptime(value, fmt).date(), datetime.min.time())
            except ValueError:
                pass
        return datetime.combine(date.fromisoformat(value), datetime.min.time())

    # 閳光偓閳光偓 鐠嬪啯鐓￠幙宥勭稊 閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓

    def change_household_head(
        self, db: Session, batch_id: int, contractor_uid: str,
        new_head_member_uid: str, reason: str | None, current_user: User,
        commit: bool = True,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        now = datetime.now(timezone.utc)

        old_head = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
                SurveyCbfJtcyResult.is_household_head.is_(True),
            )
        ).first()
        old_name = old_head.cyxm if old_head else None

        new_head = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
                SurveyCbfJtcyResult.member_uid == new_head_member_uid,
            )
        ).first()
        if new_head is None:
            raise HTTPException(404, "not found")
        if new_head.is_deceased:
            raise HTTPException(400, "invalid operation")

        if old_head:
            old_head.is_household_head = False
            old_head.is_changed = True
        new_head.is_household_head = True
        new_head.is_changed = True
        new_head.yhzgx = "01"

        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="change_head",
            before_summary={"old_head": old_name, "old_head_uid": old_head.member_uid if old_head else None},
            after_summary={"new_head": new_head.cyxm, "new_head_uid": new_head_member_uid},
            reason=reason,
            current_user=current_user, now=now,
        )
        db.flush()

        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now

        result.investigated_at = now
        if not commit:
            db.flush()
            return {"queued": True}
        self._rebuild_contractor_diffs(db, batch_id, [contractor_uid], change_ids={contractor_uid: record.id})
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def maintain_members(
        self, db: Session, batch_id: int, contractor_uid: str,
        members_to_add: list[dict], members_to_update: list[dict],
        members_to_delete: list[str | dict], reason: str | None, current_user: User,
        commit: bool = True,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        now = datetime.now(timezone.utc)

        change_details = {"added": [], "updated": [], "deleted": []}
        deleted_member_reasons = {}

        delete_requests = []
        for item in members_to_delete:
            if isinstance(item, str):
                delete_requests.append({"memberUid": item, "changeReason": reason})
            else:
                delete_requests.append({
                    "memberUid": item.get("memberUid"),
                    "changeReason": item.get("changeReason") or reason,
                })

        for item in delete_requests:
            member_uid = item.get("memberUid")
            if not member_uid:
                continue
            member = db.scalars(
                select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.contractor_uid == contractor_uid,
                    SurveyCbfJtcyResult.member_uid == member_uid,
                )
            ).first()
            if member is None:
                continue
            item_reason = item.get("changeReason") or reason
            deleted_member_reasons[member_uid] = item_reason
            change_details["deleted"].append({
                "member_uid": member_uid,
                "name": member.cyxm,
                "id_no": member.cyzjhm,
                "relation": member.yhzgx,
                "change_reason": item_reason,
            })
            db.delete(member)

        for item in members_to_update:
            member_uid = item.get("memberUid")
            if not member_uid:
                continue
            member = db.scalars(
                select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.contractor_uid == contractor_uid,
                    SurveyCbfJtcyResult.member_uid == member_uid,
                )
            ).first()
            if member is None:
                continue
            item_reason = item.get("changeReason") or reason
            field_map = [
                ("cyxm", "name"),
                ("cyxb", "gender"),
                ("cyzjlx", "idType"),
                ("cyzjhm", "idNo"),
                ("yhzgx", "relationToHead"),
                ("cybz", "noteCode"),
                ("sfgyr", "isCoOwner"),
                ("cybzsm", "note"),
                ("is_household_head", "isHouseholdHead"),
            ]
            changed_fields = []
            for attr, key in field_map:
                if key not in item:
                    continue
                before_value = getattr(member, attr)
                after_value = bool(item.get(key)) if attr == "is_household_head" else item.get(key)
                if self._diff_value(before_value) == self._diff_value(after_value):
                    continue
                setattr(member, attr, after_value)
                changed_fields.append(attr)
            if changed_fields:
                change_details["updated"].append({
                    "member_uid": member_uid,
                    "name": member.cyxm,
                    "fields": changed_fields,
                    "change_reason": item_reason,
                })
                member.is_changed = True
                member.change_reason = item_reason
                member.investigator_id = current_user.id
                member.investigator_name = current_user.real_name
                member.investigated_at = now

        for item in members_to_add:
            member_uid = item.get("memberUid") or str(uuid4())
            item_reason = item.get("changeReason") or reason
            member = SurveyCbfJtcyResult(
                contractor_uid=contractor_uid,
                member_uid=member_uid,
                cbfbm=result.cbfbm,
                cyxm=item["name"],
                cyxb=item.get("gender", "1"),
                cyzjlx=item.get("idType", "1"),
                cyzjhm=item.get("idNo", ""),
                yhzgx=item.get("relationToHead", "09"),
                cybz=item.get("noteCode"),
                sfgyr=item.get("isCoOwner"),
                cybzsm=item.get("note"),
                member_result_status="added",
                survey_status="surveyed",
                is_household_head=bool(item.get("isHouseholdHead")),
                is_changed=True,
                change_reason=item_reason,
                initialized_at=now,
                investigator_id=current_user.id,
                investigator_name=current_user.real_name,
                investigated_at=now,
            )
            db.add(member)
            change_details["added"].append({
                "member_uid": member_uid,
                "name": item["name"],
                "change_reason": item_reason,
            })

        member_count = db.scalar(
            select(func.count(SurveyCbfJtcyResult.id)).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
        ) or 0
        result.cbfcysl = member_count
        result.investigated_at = now

        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="member_maintain",
            before_summary={},
            after_summary=change_details,
            reason=reason,
            current_user=current_user, now=now,
        )
        db.flush()

        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + sum(len(change_details[key]) for key in ["added", "updated", "deleted"])
            task.investigated_at = now

        if not commit:
            db.flush()
            return {"queued": True}
        self._rebuild_contractor_diffs(
            db,
            batch_id,
            [contractor_uid],
            change_ids={contractor_uid: record.id},
            deleted_member_reasons={contractor_uid: deleted_member_reasons},
        )
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

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

    def deregister_contractor(
        self, db: Session, batch_id: int, contractor_uid: str,
        reason: str, current_user: User,
        commit: bool = True,
    ) -> dict:
        # repaired docstring
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(400, "鐠嬪啯鐓￠幋鎰亯瀹歌尙鈥樼拋銈忕礉娑撳秷鍏樺▔銊╂敘")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        now = datetime.now(timezone.utc)

        # 閺€鍫曟肠閸掔娀娅庨崜宥呯暚閺佹潙鎻╅悡?
        members = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
        ).all()
        parcel_relations = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status != "removed",
            )
        ).all()

        before_summary = {
            "contractor": {
                "code": result.cbfbm, "name": result.cbfmc,
                "typeCode": result.cbflx, "idType": result.cbfzjlx,
                "idNo": result.cbfzjhm, "address": result.cbfdz,
                "postcode": result.yzbm, "mobile": result.lxdh,
                "memberCount": result.cbfcysl, "groupRegionCode": result.group_region_code,
                "groupRegionName": result.group_region_name,
            },
            "members": [
                {
                    "memberUid": m.member_uid, "name": m.cyxm,
                    "idNo": m.cyzjhm, "gender": m.cyxb,
                    "relationToHead": m.yhzgx, "isCoOwner": m.sfgyr,
                    "noteCode": m.cybz, "note": m.cybzsm,
                    "isHouseholdHead": m.is_household_head,
                }
                for m in members
            ],
            "parcel_relations": [
                {
                    "parcelInfoUid": p.parcel_info_uid, "dkbm": p.dkbm,
                    "fbfbm": p.fbfbm, "cbjyqqdfs": p.cbjyqqdfs,
                    "htmj": float(p.htmj) if p.htmj else None,
                    "cbhtbm": p.cbhtbm, "cbjyqzbm": p.cbjyqzbm,
                }
                for p in parcel_relations
            ],
        }

        # 閸掓稑缂撻崣妯哄鐠佹澘缍嶉敍鍫濆帥閸掓稑缂撻敍灞芥礈娑撴椽娓剁憰?change_id 缂?diff閿?
        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="deregister",
            before_summary=before_summary,
            after_summary={"action": "deregistered", "reason": reason},
            reason=reason,
            current_user=current_user, now=now,
        )
        db.flush()

        # 閸掓稑缂?diffs閿涘牓鈧劒閲滅€圭偘缍嬬拋鏉跨秿閸掔娀娅庨敍?
        db.add(SurveyChangeDiff(
            batch_id=batch_id, contractor_uid=contractor_uid, change_id=record.id,
            entity_type="contractor", entity_uid=contractor_uid, entity_name=result.cbfmc,
            field_name="field", field_label="field",
            before_value=result.result_status, after_value="deregistered", change_reason=reason,
        ))
        for m in members:
            db.add(SurveyChangeDiff(
                batch_id=batch_id, contractor_uid=contractor_uid, change_id=record.id,
                entity_type="member", entity_uid=m.member_uid, entity_name=m.cyxm,
                field_name="member", field_label="閸掔娀娅庨幋鎰喅",
                before_value=f"{m.cyxm} / {m.cyzjhm}", after_value=None, change_reason=reason,
            ))
        for p in parcel_relations:
            db.add(SurveyChangeDiff(
                batch_id=batch_id, contractor_uid=contractor_uid, change_id=record.id,
                entity_type="parcel_relation", entity_uid=p.parcel_info_uid, entity_name=p.dkbm,
                field_name="parcel_relation", field_label="閸掔娀娅庨崷鏉挎健閸忓疇浠?",
                before_value=f"{p.dkbm} (閸忓疇浠?{result.cbfbm})", after_value=None, change_reason=reason,
            ))

        # 閻椻晝鎮婇崚鐘绘珟
        for m in members:
            db.delete(m)
        for p in parcel_relations:
            db.delete(p)
        db.delete(result)

        # 閺囧瓨鏌婃禒璇插閻樿埖鈧?
        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.task_status = "deregistered"
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now

        if not commit:
            db.flush()
            return {"queued": True}
        db.commit()
        return {"contractorUid": contractor_uid, "status": "deregistered", "changeNo": record.change_no}

    def add_parcel(
        self, db: Session, batch_id: int, contractor_uid: str,
        payload: dict, current_user: User,
        commit: bool = True,
    ) -> dict:
        # repaired docstring
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        now = datetime.now(timezone.utc)

        # 閺屻儲澹橀崣鎴濆瘶閺傜櫢绱欐禒搴″嚒閺堝婀撮崸妤€鍙х化璁宠厬閼惧嘲褰囬敍灞惧灗娴犲孩澹欓崠鍛煙娴狅絿鐖滈幒銊ヮ嚤閿?
        existing_parcel = db.scalars(
            select(SurveyCbdkxxResult.fbfbm).where(
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status != "removed",
            ).limit(1)
        ).first()
        fbfbm = existing_parcel or result.cbfbm[:14]
        geometry = self._normalize_geojson_geometry(payload.get("geometry"))
        geometry_source_srid = int(payload.get("geometrySourceSrid") or 4326)
        duplicate_dkbm = db.scalar(
            select(SurveyDkResult.id).where(
                SurveyDkResult.dkbm == payload["dkbm"],
                SurveyDkResult.result_status != "removed",
            ).limit(1)
        )
        if duplicate_dkbm:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"parcel code already exists: {payload['dkbm']}")
        if geometry is not None:
            area_mu = self._measure_geojson_area_mu(db, geometry, geometry_source_srid)
            if area_mu is None or area_mu <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parcel geometry is invalid")
            overlaps = self._find_database_geometry_conflicts(
                db,
                batch.tenant_code,
                geometry,
                geometry_source_srid,
            )
            if overlaps:
                overlap_text = "、".join(item.get("dkbm") or "-" for item in overlaps[:3])
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"parcel geometry overlaps existing parcels: {overlap_text}",
                )

        parcel_uid = str(uuid4())
        parcel_info_uid = str(uuid4())
        scmj = payload["scmj"]

        # 閸掓稑缂?SurveyDkResult
        dk_result = SurveyDkResult(
            parcel_uid=parcel_uid,
            ysdm=result.cbfbm[:6] or "000000",
            dkbm=payload["dkbm"],
            dkmc=payload["dkmc"],
            syqxz=payload.get("syqxz", "10"),
            dklb=payload["dklb"],
            tdlylx=payload.get("tdlylx", "001"),
            dldj=payload["dldj"],
            tdyt=payload["tdyt"],
            sfjbnt=payload.get("sfjbnt", "1"),
            scmj=scmj,
            dkdz=payload.get("dkdz"),
            dkxz=payload.get("dkxz"),
            dknz=payload.get("dknz"),
            dkbz=payload.get("dkbz"),
            dkbzxx=payload.get("dkbzxx"),
            survey_status="surveyed",
            result_status="added",
            is_changed=True,
            change_type="add_parcel",
            change_reason=payload.get("reason"),
            initialized_at=now,
        )
        db.add(dk_result)
        db.flush()
        if geometry is not None:
            self._write_survey_dk_geometry(db, "survey_dk_result", dk_result.id, geometry, geometry_source_srid)

        # 閸掓稑缂?SurveyCbdkxxResult
        cbdkxx = SurveyCbdkxxResult(
            parcel_info_uid=parcel_info_uid,
            dkbm=payload["dkbm"],
            fbfbm=fbfbm,
            cbfbm=result.cbfbm,
            cbjyqqdfs=payload.get("cbjyqqdfs", "001"),
            htmj=payload.get("htmj") or scmj,
            cbhtbm=payload.get("cbhtbm") or "",
            lzhtbm=payload.get("lzhtbm"),
            cbjyqzbm=payload.get("cbjyqzbm") or "",
            yhtmj=payload.get("yhtmj"),
            htmjm=payload.get("htmjm"),
            yhtmjm=payload.get("yhtmjm"),
            sfqqqg=payload.get("sfqqqg"),
            survey_status="surveyed",
            result_status="added",
            is_changed=True,
            change_type="add_parcel",
            change_reason=payload.get("reason"),
            initialized_at=now,
        )
        db.add(cbdkxx)

        # 閸欐ê瀵茬拋鏉跨秿
        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="add_parcel",
            before_summary={"parcels_count": db.scalar(
                select(func.count(SurveyCbdkxxResult.id)).where(
                    SurveyCbdkxxResult.cbfbm == result.cbfbm,
                )
            ) or 0},
            after_summary={"action": "add_parcel", "dkbm": payload["dkbm"], "scmj": scmj},
            reason=payload.get("reason"),
            current_user=current_user, now=now,
        )
        db.flush()

        # 閺囧瓨鏌婃禒璇插
        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now

        result.investigated_at = now
        if not commit:
            db.flush()
            return {"queued": True}
        self._rebuild_contractor_diffs(db, batch_id, [contractor_uid], change_ids={contractor_uid: None})
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def _prepare_split_generated_parcels(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        result: SurveyCbfResult,
        source_parcel: SurveyDkResult,
        split_mode: str,
        payload: dict,
        parts: list[dict],
        current_user: User,
    ) -> list[dict]:
        definitions = payload.get("generatedParcels") or []
        part_count = len(parts)
        if part_count < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split must generate at least two parcels")

        if definitions and len(definitions) > part_count:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="generated parcel count does not match split result")

        if not definitions:
            first_code = str(payload.get("newDkbm") or "").strip()
            first_name = str(payload.get("newDkmc") or "").strip()
            if not first_code or not first_name:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="generated parcel info is required")
            definitions = [{
                "dkbm": first_code,
                "dkmc": first_name,
            }]

        next_code_info = self.generate_next_parcel_code(db, batch_id, contractor_uid, current_user)
        prefix = str(next_code_info.get("prefix") or "").strip()
        sequence = int(next_code_info.get("sequence") or 1)
        existing_codes = set(
            db.scalars(
                select(SurveyDkResult.dkbm).where(
                    SurveyDkResult.tenant_code == result.tenant_code,
                ).execution_options(skip_tenant_scope=True)
            ).all()
        )
        used_codes: set[str] = set()

        def next_auto_code() -> str:
            nonlocal sequence
            while True:
                candidate = f"{prefix}{sequence:05d}" if prefix else str(sequence)
                sequence += 1
                if candidate not in existing_codes and candidate not in used_codes:
                    return candidate

        generated: list[dict] = []
        base_name = str(definitions[0].get("dkmc") or source_parcel.dkmc or "切割地块").strip() or "切割地块"
        for index, part in enumerate(parts):
            if index < len(definitions):
                item = definitions[index] or {}
                dkbm = str(item.get("dkbm") or "").strip()
                dkmc = str(item.get("dkmc") or "").strip()
                if not dkbm or not dkmc:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="generated parcel code and name are required")
            else:
                dkbm = next_auto_code()
                dkmc = f"{base_name}{index + 1}"
            if dkbm in used_codes or dkbm in existing_codes:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"parcel code already exists: {dkbm}")
            used_codes.add(dkbm)
            generated.append({
                "dkbm": dkbm,
                "dkmc": dkmc,
                "scmj": round(float(part["areaMu"]), 2),
                "htmj": round(float(part["areaMu"]), 2),
                "geometry": part["geometry"],
            })

        if split_mode == "area" and len(generated) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="direction split must generate two current parcels")
        return generated

    def preview_split_parcel(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        payload: dict,
        current_user: User,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")

        dkbm = payload["dkbm"]
        old_relation = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm == dkbm,
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ).first()
        if old_relation is None:
            raise HTTPException(404, "parcel relation not found")

        old_parcel = db.scalars(
            select(SurveyDkResult)
            .where(
                SurveyDkResult.dkbm == old_relation.dkbm,
                SurveyDkResult.result_status.notin_(("removed", "split_source")),
            )
            .order_by(SurveyDkResult.id.desc())
        ).first()
        if old_parcel is None:
            raise HTTPException(404, "parcel not found")

        split_mode = str(payload.get("splitMode") or "area").strip().lower()
        if split_mode == "geometry":
            split_result = self._split_row_geometry_by_shape(
                db,
                old_parcel.id,
                payload.get("splitGeometry"),
                int(payload.get("geometrySourceSrid") or 4326),
            )
        else:
            new_scmj = float(payload.get("newScmj") or 0)
            if new_scmj <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split area is required")
            split_result = self._split_row_geometry_by_direction(
                db,
                old_parcel.id,
                payload.get("splitDirection"),
                new_scmj,
            )

        generated_parcels = self._prepare_split_generated_parcels(
            db,
            batch_id,
            contractor_uid,
            result,
            old_parcel,
            split_mode,
            payload,
            split_result["parts"],
            current_user,
        )
        return {
            "sourceDkbm": old_parcel.dkbm,
            "splitMode": split_mode,
            "generatedParcels": generated_parcels,
        }

    def split_parcel(
        self, db: Session, batch_id: int, contractor_uid: str,
        payload: dict, current_user: User,
        commit: bool = True,
    ) -> dict:
        # repaired docstring
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        now = datetime.now(timezone.utc)

        # 閺屻儲澹橀崢鐔锋勾閸ф鍙ч懕?
        dkbm = payload["dkbm"]
        old_relation = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm == dkbm,
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ).first()
        if old_relation is None:
            raise HTTPException(404, "閸樼喎婀撮崸妤€鍙ч懕鏂剧瑝鐎涙ê婀?")

        # 閺屻儲澹橀崢鐔锋勾閸?
        old_parcel = db.scalars(
            select(SurveyDkResult)
            .where(
                SurveyDkResult.dkbm == old_relation.dkbm,
                SurveyDkResult.result_status.notin_(("removed", "split_source")),
            )
            .order_by(SurveyDkResult.id.desc())
        ).first()
        if old_parcel is None:
            raise HTTPException(404, "閸樼喎婀撮崸妞剧瑝鐎涙ê婀?")

        split_mode = str(payload.get("splitMode") or "area").strip().lower()
        old_area = float(old_parcel.scmj or 0)
        split_preview = None
        if split_mode == "geometry":
            split_preview = self._split_row_geometry_by_shape(
                db,
                old_parcel.id,
                payload.get("splitGeometry"),
                int(payload.get("geometrySourceSrid") or 4326),
            )
        else:
            new_scmj = float(payload.get("newScmj") or 0)
            if new_scmj <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split area is required")
            if payload.get("splitDirection"):
                split_preview = self._split_row_geometry_by_direction(
                    db,
                    old_parcel.id,
                    payload.get("splitDirection"),
                    new_scmj,
                )
            else:
                if new_scmj >= old_area:
                    raise HTTPException(400, f"閸掑洤澹婇棃銏⑿?{new_scmj})娑撳秷鍏樻径褌绨粵澶夌艾閸樼喎婀撮崸妤呮桨缁?{old_area})")
        split_parts = split_preview["parts"] if split_preview else []
        generated_parcels = self._prepare_split_generated_parcels(
            db,
            batch_id,
            contractor_uid,
            result,
            old_parcel,
            split_mode,
            payload,
            split_parts,
            current_user,
        )

        # 閸戝繐鐨崢鐔锋勾閸ф娼扮粔?
        old_parcel.is_changed = True
        old_parcel.result_status = "split_source"
        old_parcel.change_type = "split_parcel"
        old_parcel.change_reason = payload.get("reason")

        # 閺囧瓨鏌婇崢鐔锋勾閸ф鍙ч懕鏃傛畱闂堛垻袧
        old_relation.is_changed = True
        old_relation.result_status = "split_source"
        old_relation.change_type = "split_parcel"
        old_relation.change_reason = payload.get("reason")

        for item in generated_parcels:
            new_parcel = SurveyDkResult(
                parcel_uid=str(uuid4()),
                ysdm=old_parcel.ysdm,
                dkbm=item["dkbm"],
                dkmc=item["dkmc"],
                syqxz=old_parcel.syqxz,
                dklb=old_parcel.dklb,
                tdlylx=old_parcel.tdlylx,
                dldj=old_parcel.dldj,
                tdyt=old_parcel.tdyt,
                sfjbnt=old_parcel.sfjbnt,
                scmj=item["scmj"],
                dkdz=old_parcel.dkdz,
                dkxz=old_parcel.dkxz,
                dknz=old_parcel.dknz,
                dkbz=f"由 {old_parcel.dkbm} 切割生成",
                survey_status="surveyed",
                result_status="split_generated",
                is_changed=True,
                change_type="split_parcel",
                change_reason=payload.get("reason"),
                initialized_at=now,
            )
            db.add(new_parcel)
            db.flush()
            self._write_survey_dk_geometry(
                db,
                "survey_dk_result",
                new_parcel.id,
                item["geometry"],
                4326,
            )

            new_relation = SurveyCbdkxxResult(
                parcel_info_uid=str(uuid4()),
                dkbm=item["dkbm"],
                fbfbm=old_relation.fbfbm,
                cbfbm=result.cbfbm,
                cbjyqqdfs=old_relation.cbjyqqdfs,
                htmj=item["htmj"],
                cbhtbm=old_relation.cbhtbm,
                lzhtbm=old_relation.lzhtbm,
                cbjyqzbm=old_relation.cbjyqzbm,
                sfqqqg=old_relation.sfqqqg,
                survey_status="surveyed",
                result_status="split_generated",
                is_changed=True,
                change_type="split_parcel",
                change_reason=payload.get("reason"),
                initialized_at=now,
            )
            db.add(new_relation)

        # 閸欐ê瀵茬拋鏉跨秿
        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="split_parcel",
            before_summary={
                "dkbm": old_parcel.dkbm,
                "original_area": old_area,
                "source_result_status": old_parcel.result_status,
                "source_change_type": old_parcel.change_type,
                "source_change_reason": old_parcel.change_reason,
                "source_is_changed": old_parcel.is_changed,
            },
            after_summary={
                "action": "split_parcel",
                "split_mode": split_mode,
                "split_direction": payload.get("splitDirection"),
                "original_dkbm": old_parcel.dkbm,
                "generated_count": len(generated_parcels),
                "generated_parcels": [
                    {
                        "dkbm": item["dkbm"],
                        "dkmc": item["dkmc"],
                        "area": item["scmj"],
                    }
                    for item in generated_parcels
                ],
            },
            reason=payload.get("reason"),
            current_user=current_user, now=now,
        )
        db.flush()

        # 閺囧瓨鏌婃禒璇插
        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now

        result.investigated_at = now
        if not commit:
            db.flush()
            return {"queued": True}
        self._rebuild_contractor_diffs(db, batch_id, [contractor_uid], change_ids={contractor_uid: None})
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def swap_parcels(
        self, db: Session, batch_id: int, contractor_uid: str,
        payload: dict, current_user: User,
        commit: bool = True,
        change_type: str = "swap_parcels",
    ) -> dict:
        # repaired docstring
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        now = datetime.now(timezone.utc)

        target_uid = payload["targetContractorUid"]
        target_result = self._get_result(db, batch_id, target_uid)
        if target_result.survey_status == "confirmed":
            raise HTTPException(400, "閻╊喗鐖ｉ幍鍨瘶閺傜懓鍑＄涵顔款吇")
        if target_uid == contractor_uid:
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, target_result.cbfbm, detail="out of scope")
        source_group = result.group_region_code or (result.cbfbm[:14] if result.cbfbm else "")
        target_group = target_result.group_region_code or (target_result.cbfbm[:14] if target_result.cbfbm else "")
        if source_group and target_group and source_group != target_group:
            raise HTTPException(400, "鐩爣鎵垮寘鏂瑰彧鑳介€夋嫨鏈粍鎵垮寘鏂?")

        source_dkbms = payload["sourceDkbms"]
        target_dkbms = payload["targetDkbms"]
        reason = payload.get("reason")
        if len(source_dkbms) != len(set(source_dkbms)) or len(target_dkbms) != len(set(target_dkbms)):
            raise HTTPException(400, "浜掓崲鍦板潡涓嶈兘閲嶅閫夋嫨")

        def load_active_relations(dkbms: list[str], cbfbm: str, side: str) -> list[SurveyCbdkxxResult]:
            rows = db.scalars(
                select(SurveyCbdkxxResult).where(
                    SurveyCbdkxxResult.dkbm.in_(dkbms),
                    SurveyCbdkxxResult.cbfbm == cbfbm,
                    SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
                )
            ).all()
            by_code = {row.dkbm: row for row in rows}
            missing = [dkbm for dkbm in dkbms if dkbm not in by_code]
            if missing:
                raise HTTPException(404, f"{side}鍦板潡 {missing[0]} 涓嶅睘浜庡搴旀壙鍖呮柟")
            return [by_code[dkbm] for dkbm in dkbms]

        source_relations = load_active_relations(source_dkbms, result.cbfbm, "鏈柟")
        target_relations = load_active_relations(target_dkbms, target_result.cbfbm, "鐩爣鏂?")

        relation_fields = (
            ("cbfbm", "鎵垮寘鏂逛唬鐮?",),
            ("fbfbm", "鍙戝寘鏂逛唬鐮?",),
            ("cbjyqqdfs", "鎵垮寘缁忚惀鏉冨彇寰楁柟寮?",),
            ("cbhtbm", "鎵垮寘鍚堝悓缂栫爜"),
            ("lzhtbm", "娴佽浆鍚堝悓缂栫爜"),
            ("cbjyqzbm", "鎵垮寘缁忚惀鏉冭瘉缂栫爜"),
            ("sfqqqg", "鏄惁纭潈纭偂"),
        )
        source_contract = {
            field_name: getattr(source_relations[0], field_name)
            for field_name, _ in relation_fields
        }
        target_contract = {
            field_name: getattr(target_relations[0], field_name)
            for field_name, _ in relation_fields
        }

        def transfer_relation(
            rel: SurveyCbdkxxResult,
            recipient_cbfbm: str,
            recipient_contract: dict,
        ) -> list[dict]:
            changes = []
            for field_name, field_label in relation_fields:
                before_value = getattr(rel, field_name)
                after_value = (
                    recipient_cbfbm
                    if field_name == "cbfbm"
                    else recipient_contract[field_name]
                )
                if before_value != after_value:
                    changes.append({
                        "field_name": field_name,
                        "field_label": field_label,
                        "before_value": before_value,
                        "after_value": after_value,
                    })
                    setattr(rel, field_name, after_value)
            rel.is_changed = True
            rel.change_type = change_type
            rel.change_reason = reason
            return changes

        # 閹笛嗩攽娴滄帗宕?
        swapped_source = []
        swapped_target = []
        for rel in source_relations:
            swapped_source.append({
                "dkbm": rel.dkbm,
                "changes": transfer_relation(rel, target_result.cbfbm, target_contract),
            })

        for rel in target_relations:
            swapped_target.append({
                "dkbm": rel.dkbm,
                "changes": transfer_relation(rel, result.cbfbm, source_contract),
            })

        # 閸欐ê瀵茬拋鏉跨秿閿涘牊绨弬鐧哥礆
        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type=change_type,
            before_summary={"swapped_out": source_dkbms},
            after_summary={"swapped_in": target_dkbms, "counterparty": target_result.cbfbm},
            reason=reason,
            current_user=current_user, now=now,
        )
        db.flush()

        # 閸欐ê瀵茬拋鏉跨秿閿涘牏娲伴弽鍥ㄦ煙閿?
        target_record = self._create_change_record(
            db, batch_id, target_uid, target_result.cbfbm,
            change_type=change_type,
            before_summary={"swapped_out": target_dkbms},
            after_summary={"swapped_in": source_dkbms, "counterparty": result.cbfbm},
            reason=reason,
            current_user=current_user, now=now,
        )
        db.flush()

        # 閺囧瓨鏌婇崣灞炬煙娴犺濮?
        for uid in [contractor_uid, target_uid]:
            task = self._get_task(db, batch_id, uid)
            if task:
                task.has_change = True
                task.change_count = (task.change_count or 0) + 1
                task.investigated_at = now

        result.investigated_at = now
        target_result.investigated_at = now
        if not commit:
            db.flush()
            return {"queued": True}
        self._rebuild_contractor_diffs(
            db,
            batch_id,
            [contractor_uid, target_uid],
            change_ids={contractor_uid: None, target_uid: None},
        )
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def rollback_swap_parcels(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        change_id: int,
        payload: dict,
        current_user: User,
        commit: bool = True,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        result = self._get_result(db, batch_id, contractor_uid)
        self._ensure_editable_batch_and_result(db, result)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")

        change = db.scalars(
            select(SurveyChangeRecord)
            .where(
                SurveyChangeRecord.tenant_code == batch.tenant_code,
                SurveyChangeRecord.batch_id == batch_id,
                SurveyChangeRecord.contractor_uid == contractor_uid,
                SurveyChangeRecord.id == change_id,
            )
            .execution_options(skip_tenant_scope=True)
        ).first()
        if change is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="change record not found")
        if change.change_type != "swap_parcels":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="only saved parcel swaps can be rolled back")
        if change.change_status == "rolled_back":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="this parcel swap has already been rolled back")

        before_summary = change.before_summary or {}
        after_summary = change.after_summary or {}
        source_dkbms = [str(item).strip() for item in (after_summary.get("swapped_in") or []) if str(item).strip()]
        target_dkbms = [str(item).strip() for item in (before_summary.get("swapped_out") or []) if str(item).strip()]
        if not source_dkbms or not target_dkbms:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="saved parcel swap data is incomplete and cannot be rolled back")

        source_relations = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm.in_(source_dkbms),
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ).all()
        source_relation_by_code = {row.dkbm: row for row in source_relations}
        missing_source = [dkbm for dkbm in source_dkbms if dkbm not in source_relation_by_code]
        if missing_source:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="current parcel ownership has changed and this swap cannot be rolled back")

        target_relations = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm.in_(target_dkbms),
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ).all()
        target_relation_by_code = {row.dkbm: row for row in target_relations}
        missing_target = [dkbm for dkbm in target_dkbms if dkbm not in target_relation_by_code]
        if missing_target:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="current parcel ownership has changed and this swap cannot be rolled back")

        target_owner_codes = {target_relation_by_code[dkbm].cbfbm for dkbm in target_dkbms}
        if len(target_owner_codes) != 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="the swapped parcels are no longer held by the same contractor")
        target_cbfbm = next(iter(target_owner_codes))
        if target_cbfbm == result.cbfbm:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="the parcel swap has already been restored")

        target_task = db.scalars(
            select(SurveyCbfBase)
            .where(
                SurveyCbfBase.tenant_code == batch.tenant_code,
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.cbfbm == target_cbfbm,
            )
            .order_by(SurveyCbfBase.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).first()
        if target_task is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="the counterparty of this parcel swap could not be found")
        target_result = self._get_result(db, batch_id, target_task.contractor_uid)

        self._ensure_editable_batch_and_result(db, target_result)
        data_access_service.ensure_code_in_scope(current_user, target_result.cbfbm, detail="out of scope")

        rollback_reason = (payload.get("reason") or "").strip() or f"鎾ゅ洖浜掓崲 {change.change_no}"
        self.swap_parcels(
            db,
            batch_id,
            contractor_uid,
            {
                "targetContractorUid": target_result.contractor_uid,
                "sourceDkbms": source_dkbms,
                "targetDkbms": target_dkbms,
                "reason": rollback_reason,
            },
            current_user,
            commit=False,
            change_type="rollback_swap_parcels",
        )

        change.change_status = "rolled_back"
        counterpart_change = db.scalars(
            select(SurveyChangeRecord)
            .where(
                SurveyChangeRecord.tenant_code == batch.tenant_code,
                SurveyChangeRecord.batch_id == batch_id,
                SurveyChangeRecord.contractor_uid == target_result.contractor_uid,
                SurveyChangeRecord.change_type == "swap_parcels",
                SurveyChangeRecord.change_status != "rolled_back",
            )
            .order_by(SurveyChangeRecord.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        for item in counterpart_change:
            item_before = item.before_summary or {}
            item_after = item.after_summary or {}
            item_swapped_out = [str(code).strip() for code in (item_before.get("swapped_out") or []) if str(code).strip()]
            item_swapped_in = [str(code).strip() for code in (item_after.get("swapped_in") or []) if str(code).strip()]
            item_counterparty = str(item_after.get("counterparty") or "").strip()
            if (
                item_swapped_out == source_dkbms
                and item_swapped_in == target_dkbms
                and item_counterparty == result.cbfbm
            ):
                item.change_status = "rolled_back"
                break

        if not commit:
            db.flush()
            return {"queued": True}

        self._rebuild_contractor_diffs(
            db,
            batch_id,
            [contractor_uid, target_result.contractor_uid],
            change_ids={contractor_uid: None, target_result.contractor_uid: None},
        )
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def rollback_split_parcel(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        change_id: int,
        payload: dict,
        current_user: User,
        commit: bool = True,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        result = self._get_result(db, batch_id, contractor_uid)
        self._ensure_editable_batch_and_result(db, result)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")

        change = db.scalars(
            select(SurveyChangeRecord)
            .where(
                SurveyChangeRecord.tenant_code == batch.tenant_code,
                SurveyChangeRecord.batch_id == batch_id,
                SurveyChangeRecord.contractor_uid == contractor_uid,
                SurveyChangeRecord.id == change_id,
            )
            .execution_options(skip_tenant_scope=True)
        ).first()
        if change is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="change record not found")
        if change.change_type != "split_parcel":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="only saved parcel splits can be rolled back")
        if change.change_status == "rolled_back":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="this parcel split has already been rolled back")

        before_summary = change.before_summary or {}
        after_summary = change.after_summary or {}
        source_dkbm = str(before_summary.get("dkbm") or after_summary.get("original_dkbm") or "").strip()
        generated_items = after_summary.get("generated_parcels") or []
        generated_dkbms = [str(item.get("dkbm") or "").strip() for item in generated_items if str(item.get("dkbm") or "").strip()]
        if not generated_dkbms:
            legacy_dkbm = str(after_summary.get("new_dkbm") or "").strip()
            if legacy_dkbm:
                generated_dkbms = [legacy_dkbm]
        if not source_dkbm or not generated_dkbms:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="saved parcel split data is incomplete and cannot be rolled back")

        source_relation = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm == source_dkbm,
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status == "split_source",
            )
        ).first()
        source_parcel = db.scalars(
            select(SurveyDkResult).where(
                SurveyDkResult.dkbm == source_dkbm,
                SurveyDkResult.result_status == "split_source",
            ).order_by(SurveyDkResult.id.desc())
        ).first()
        if source_relation is None or source_parcel is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="the source parcel is no longer in a rollbackable split state")

        generated_relations = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm.in_(generated_dkbms),
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ).all()
        generated_relation_by_code = {item.dkbm: item for item in generated_relations}
        missing_relations = [dkbm for dkbm in generated_dkbms if dkbm not in generated_relation_by_code]
        if missing_relations:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="some generated parcels are no longer current and this split cannot be rolled back")

        generated_parcels = db.scalars(
            select(SurveyDkResult).where(
                SurveyDkResult.dkbm.in_(generated_dkbms),
                SurveyDkResult.result_status.notin_(("removed", "split_source")),
            )
        ).all()
        generated_parcel_by_code = {item.dkbm: item for item in generated_parcels}
        missing_parcels = [dkbm for dkbm in generated_dkbms if dkbm not in generated_parcel_by_code]
        if missing_parcels:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="some generated parcel geometries are no longer current and this split cannot be rolled back")

        rollback_reason = (payload.get("reason") or "").strip() or f"撤回切割 {change.change_no}"
        previous_result_status = str(before_summary.get("source_result_status") or "normal").strip() or "normal"
        previous_change_type = str(before_summary.get("source_change_type") or "none").strip() or "none"
        previous_change_reason = before_summary.get("source_change_reason")
        previous_is_changed = bool(before_summary.get("source_is_changed"))

        source_relation.result_status = previous_result_status
        source_relation.is_changed = previous_is_changed
        source_relation.change_type = previous_change_type
        source_relation.change_reason = previous_change_reason

        source_parcel.result_status = previous_result_status
        source_parcel.is_changed = previous_is_changed
        source_parcel.change_type = previous_change_type
        source_parcel.change_reason = previous_change_reason

        for dkbm in generated_dkbms:
            relation = generated_relation_by_code[dkbm]
            relation.result_status = "removed"
            relation.is_changed = True
            relation.change_type = "rollback_split_parcel"
            relation.change_reason = rollback_reason

            parcel = generated_parcel_by_code[dkbm]
            parcel.result_status = "removed"
            parcel.is_changed = True
            parcel.change_type = "rollback_split_parcel"
            parcel.change_reason = rollback_reason

        rollback_record = self._create_change_record(
            db,
            batch_id,
            contractor_uid,
            result.cbfbm,
            change_type="rollback_split_parcel",
            before_summary={
                "original_change_id": change.id,
                "source_dkbm": source_dkbm,
                "generated_dkbms": generated_dkbms,
            },
            after_summary={
                "action": "rollback_split_parcel",
                "source_dkbm": source_dkbm,
                "generated_dkbms": generated_dkbms,
            },
            reason=rollback_reason,
            current_user=current_user,
            now=datetime.now(timezone.utc),
        )
        db.add(rollback_record)

        change.change_status = "rolled_back"

        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = datetime.now(timezone.utc)
        result.investigated_at = datetime.now(timezone.utc)

        if not commit:
            db.flush()
            return {"queued": True}

        self._rebuild_contractor_diffs(db, batch_id, [contractor_uid], change_ids={contractor_uid: None})
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def remove_parcel(
        self, db: Session, batch_id: int, contractor_uid: str,
        payload: dict, current_user: User,
        commit: bool = True,
    ) -> dict:
        # repaired docstring
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        now = datetime.now(timezone.utc)

        dkbm = payload["dkbm"]

        # 閺屻儲澹橀崷鏉挎健閸忓疇浠?
        relation = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm == dkbm,
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ).first()
        if relation is None:
            raise HTTPException(404, "閸︽澘娼￠崗瀹犱粓娑撳秴鐡ㄩ崷銊﹀灗娑撳秴鐫樻禍搴＄秼閸撳秵澹欓崠鍛煙")

        # 閺屻儲澹橀崷鏉挎健鐠佹澘缍?
        parcel = db.scalars(
            select(SurveyDkResult).where(
                SurveyDkResult.dkbm == dkbm,
            )
        ).first()

        before_parcels_count = db.scalar(
            select(func.count(SurveyCbdkxxResult.id)).where(
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ) or 0

        # 鏉烆垰鍨归梽銈忕窗閺嶅洩顔囬崗瀹犱粓閸忓磭閮存稉鍝勫嚒缁夊娅?
        db.delete(relation)
        if parcel:
            remaining_relation = db.scalar(
                select(func.count(SurveyCbdkxxResult.id)).where(
                    SurveyCbdkxxResult.dkbm == dkbm,
                    SurveyCbdkxxResult.id != relation.id,
                    SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
                )
            ) or 0
            if remaining_relation == 0:
                db.delete(parcel)

        # 閸欐ê瀵茬拋鏉跨秿
        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="remove_parcel",
            before_summary={"parcels_count": before_parcels_count},
            after_summary={
                "action": "remove_parcel",
                "dkbm": dkbm,
                "parcels_count": before_parcels_count - 1,
            },
            reason=payload.get("reason"),
            current_user=current_user, now=now,
        )
        db.flush()

        # 閺囧瓨鏌婃禒璇插
        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now

        result.investigated_at = now
        if not commit:
            db.flush()
            return {"queued": True}
        self._rebuild_contractor_diffs(db, batch_id, [contractor_uid], change_ids={contractor_uid: None})
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def split_household(
        self, db: Session, batch_id: int, contractor_uid: str,
        payload: dict, current_user: User,
        commit: bool = True,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        now = datetime.now(timezone.utc)

        member_uids = payload["memberUids"]
        parcel_dkbms = payload.get("parcelDkbms") or []
        new_cbfbm = payload["newCbfbm"]
        new_cbfmc = payload["newCbfmc"]

        all_members = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
        ).all()
        if len(all_members) < 2:
            raise HTTPException(400, "invalid operation")
        stay_members = [m for m in all_members if m.member_uid not in member_uids]
        if not stay_members:
            raise HTTPException(400, "invalid operation")
        move_members = [m for m in all_members if m.member_uid in member_uids]
        if not move_members:
            raise HTTPException(400, "invalid operation")

        new_contractor_uid = str(uuid5(NAMESPACE_URL, f"survey:{batch_id}:cbf:{new_cbfbm}"))
        new_result = SurveyCbfResult(
            contractor_uid=new_contractor_uid,
            cbfbm=new_cbfbm,
            cbflx=result.cbflx,
            cbfmc=new_cbfmc,
            cbfzjlx=result.cbfzjlx,
            cbfzjhm="",
            cbfdz=result.cbfdz,
            yzbm=result.yzbm,
            lxdh=result.lxdh,
            cbfcysl=len(move_members),
            group_region_code=result.group_region_code,
            group_region_name=result.group_region_name,
            survey_status="surveyed",
            result_status="added",
            is_changed=True,
            change_type="split_household",
            change_reason=payload.get("reason"),
            investigator_id=current_user.id,
            investigator_name=current_user.real_name,
            investigated_at=now,
            initialized_at=now,
            remark=f"split from {result.cbfbm} {result.cbfmc}",
        )
        db.add(new_result)
        db.flush()

        db.add(SurveyCbfBase(
            batch_id=batch_id,
            contractor_uid=new_contractor_uid,
            cbfbm=new_cbfbm,
            cbfmc=new_cbfmc,
            task_status="surveyed",
            has_change=True,
            change_count=1,
            investigated_at=now,
            remark=f"split from {result.cbfbm}",
        ))

        moved_member_names = []
        for member in move_members:
            moved_member_names.append(member.cyxm)
            member.contractor_uid = new_contractor_uid
            member.cbfbm = new_cbfbm
            member.is_changed = True

        if move_members:
            if not any(m.is_household_head for m in stay_members):
                stay_members[0].is_household_head = True
            if not any(m.is_household_head for m in move_members):
                move_members[0].is_household_head = True

        moved_parcel_dkbms = []
        for dkbm in parcel_dkbms:
            rel = db.scalars(
                select(SurveyCbdkxxResult).where(
                    SurveyCbdkxxResult.dkbm == dkbm,
                    SurveyCbdkxxResult.cbfbm == result.cbfbm,
                    SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
                )
            ).first()
            if rel is None:
                continue
            moved_parcel_dkbms.append(dkbm)
            rel.cbfbm = new_cbfbm
            rel.is_changed = True
            rel.change_type = "split_household"
            rel.change_reason = payload.get("reason")

        result.cbfcysl = len(stay_members)
        result.is_changed = True
        result.change_type = "split_household"
        result.investigated_at = now

        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="split_household",
            before_summary={"member_count": len(all_members), "parcel_count": len(parcel_dkbms)},
            after_summary={
                "action": "split_out",
                "new_household": new_cbfbm,
                "moved_members": moved_member_names,
                "moved_parcels": moved_parcel_dkbms,
            },
            reason=payload.get("reason"),
            current_user=current_user, now=now,
        )
        db.flush()

        new_record = self._create_change_record(
            db, batch_id, new_contractor_uid, new_cbfbm,
            change_type="split_household",
            before_summary={},
            after_summary={
                "action": "created",
                "from_household": result.cbfbm,
                "members": moved_member_names,
                "parcels": moved_parcel_dkbms,
            },
            reason=payload.get("reason"),
            current_user=current_user, now=now,
        )
        db.flush()

        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now
            task.cbfmc = result.cbfmc

        if not commit:
            db.flush()
            return {"queued": True}
        self._rebuild_contractor_diffs(
            db,
            batch_id,
            [contractor_uid, new_contractor_uid],
            change_ids={contractor_uid: record.id, new_contractor_uid: new_record.id},
        )
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def merge_household(
        self, db: Session, batch_id: int, source_contractor_uid: str,
        payload: dict, current_user: User,
        commit: bool = True,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        source_result = self._get_result(db, batch_id, source_contractor_uid)
        if source_result.survey_status == "confirmed":
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, source_result.cbfbm, detail="out of scope")
        now = datetime.now(timezone.utc)

        target_contractor_uid = payload["targetContractorUid"]
        if target_contractor_uid == source_contractor_uid:
            raise HTTPException(400, "invalid operation")

        target_result = db.scalars(
            select(SurveyCbfResult).where(
                SurveyCbfResult.contractor_uid == target_contractor_uid,
            ).order_by(SurveyCbfResult.id.desc())
        ).first()
        if not target_result:
            raise HTTPException(400, "target household not found")
        if target_result.survey_status == "confirmed":
            raise HTTPException(400, "target household already confirmed")

        source_members = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == source_contractor_uid,
            )
        ).all()
        source_parcels = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.cbfbm == source_result.cbfbm,
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ).all()

        moved_member_names = [m.cyxm for m in source_members]
        moved_parcel_dkbms = [p.dkbm for p in source_parcels]

        source_record = self._create_change_record(
            db, batch_id, source_contractor_uid, source_result.cbfbm,
            change_type="merge_household",
            before_summary={
                "member_count": len(source_members),
                "parcel_count": len(source_parcels),
            },
            after_summary={
                "action": "merged_into",
                "target_household": target_result.cbfbm,
                "target_name": target_result.cbfmc,
                "moved_members": moved_member_names,
                "moved_parcels": moved_parcel_dkbms,
            },
            reason=payload.get("reason"),
            current_user=current_user, now=now,
        )
        db.flush()

        db.add(SurveyChangeDiff(
            batch_id=batch_id, contractor_uid=source_contractor_uid, change_id=source_record.id,
            entity_type="contractor", entity_uid=source_contractor_uid, entity_name=source_result.cbfmc,
            field_name="field", field_label="field",
            before_value=source_result.result_status, after_value="merged", change_reason=payload.get("reason"),
        ))
        for m in source_members:
            db.add(SurveyChangeDiff(
                batch_id=batch_id, contractor_uid=source_contractor_uid, change_id=source_record.id,
                entity_type="member", entity_uid=m.member_uid, entity_name=m.cyxm,
                field_name="contractor", field_label="merged_target",
                before_value=source_result.cbfbm, after_value=target_result.cbfbm, change_reason=payload.get("reason"),
            ))
        for p in source_parcels:
            db.add(SurveyChangeDiff(
                batch_id=batch_id, contractor_uid=source_contractor_uid, change_id=source_record.id,
                entity_type="parcel_relation", entity_uid=p.parcel_info_uid, entity_name=p.dkbm,
                field_name="field", field_label="field",
                before_value=source_result.cbfbm, after_value=target_result.cbfbm, change_reason=payload.get("reason"),
            ))

        target_record = self._create_change_record(
            db, batch_id, target_contractor_uid, target_result.cbfbm,
            change_type="merge_household",
            before_summary={
                "member_count": target_result.cbfcysl,
            },
            after_summary={
                "action": "received_merge",
                "from_household": source_result.cbfbm,
                "from_name": source_result.cbfmc,
                "received_members": moved_member_names,
                "received_parcels": moved_parcel_dkbms,
                "new_member_count": target_result.cbfcysl + len(source_members),
            },
            reason=payload.get("reason"),
            current_user=current_user, now=now,
        )
        db.flush()

        for member in source_members:
            member.contractor_uid = target_contractor_uid
            member.cbfbm = target_result.cbfbm
            member.is_household_head = False
            member.is_changed = True

        for parcel in source_parcels:
            parcel.cbfbm = target_result.cbfbm
            parcel.is_changed = True
            parcel.change_type = "merge_household"
            parcel.change_reason = payload.get("reason")

        target_result.cbfcysl = (target_result.cbfcysl or 0) + len(source_members)
        target_result.is_changed = True
        target_result.change_type = "merge_household"
        target_result.investigated_at = now

        db.delete(source_result)

        source_task = self._get_task(db, batch_id, source_contractor_uid)
        if source_task:
            source_task.task_status = "deregistered"
            source_task.has_change = True
            source_task.change_count = (source_task.change_count or 0) + 1
            source_task.investigated_at = now
            source_task.remark = f"merged into {target_result.cbfbm} {target_result.cbfmc}"

        target_task = self._get_task(db, batch_id, target_contractor_uid)
        if target_task:
            target_task.has_change = True
            target_task.change_count = (target_task.change_count or 0) + 1
            target_task.investigated_at = now

        self._rebuild_contractor_diffs(
            db,
            batch_id,
            [target_contractor_uid],
            change_ids={target_contractor_uid: target_record.id},
        )
        if not commit:
            db.flush()
            return {"queued": True}
        db.commit()
        return self.get_result(db, batch_id, target_contractor_uid, current_user)

    def _get_task(self, db: Session, batch_id: int, contractor_uid: str) -> SurveyCbfBase | None:
        return db.scalars(
            select(SurveyCbfBase).where(
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.contractor_uid == contractor_uid,
            )
        ).first()

    def _next_no(self, db: Session, prefix: str, id_column) -> str:
        next_id = (db.scalar(select(func.max(id_column))) or 0) + 1
        return f"{prefix}{datetime.now():%Y%m%d}{next_id:04d}"


survey_service = SurveyService()
