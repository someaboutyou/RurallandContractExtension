import csv
import io
import logging
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, or_, select, text, update
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
    tag_names = {
        "whole_family_urbanized": "全家进城落户",
        "household_extinct": "整户消亡",
        "five_guarantees": "五保户",
        "little_or_no_land": "无地少地",
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="璇烽€夋嫨璋冩煡鍖哄煙")
        data_access_service.ensure_region_in_scope(current_user, region_code)
        tenant_code = data_access_service.get_tenant_code(current_user) or data_access_service.derive_tenant_code(region_code)
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前范围内没有可初始化的承包方数据")

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
                db.add(self._member_result_from_base(member_base, now))

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
        filters = self._tenant_filters(SurveyContractorTask, current_user)
        filters.append(SurveyContractorTask.batch_id == batch_id)
        filters.extend(data_access_service.build_code_scope_filters(SurveyContractorTask.cbfbm, current_user))
        if effective_region_code:
            filters.append(SurveyContractorTask.cbfbm.like(f"{effective_region_code}%"))
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(or_(SurveyContractorTask.cbfbm.ilike(pattern), SurveyContractorTask.cbfmc.ilike(pattern)))
        if task_status:
            filters.append(SurveyContractorTask.task_status == task_status)

        task_count_stmt = (
            select(func.count(SurveyContractorTask.id))
            .where(*filters)
            .execution_options(skip_tenant_scope=True)
        )
        task_list_stmt = (
            select(SurveyContractorTask)
            .where(*filters)
            .order_by(SurveyContractorTask.cbfbm.asc(), SurveyContractorTask.id.desc())
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
                    select(SurveyContractorTask)
                    .where(
                        SurveyContractorTask.tenant_code == batch.tenant_code,
                        SurveyContractorTask.batch_id == batch.id,
                        SurveyContractorTask.cbfbm.in_(cbfbms),
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
                select(SurveyContractorTask)
                .where(
                    SurveyContractorTask.tenant_code == batch.tenant_code,
                    SurveyContractorTask.batch_id == batch_id,
                    SurveyContractorTask.cbfbm.in_(set(first_contractors.values())),
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="璋冩煡鎵规宸茬粨鏉燂紝涓嶈兘鏂板")
        code = payload["code"].strip()
        data_access_service.ensure_code_in_scope(current_user, code, detail="鎵垮寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴")
        if batch.region_code and not code.startswith(batch.region_code):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鎵垮寘鏂圭紪鐮佷笉鍦ㄥ綋鍓嶈皟鏌ユ壒娆″尯鍩熷唴")
        exists = db.scalars(
            select(SurveyCbfBase).where(
                SurveyCbfBase.tenant_code == batch.tenant_code,
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.cbfbm == code,
            ).execution_options(skip_tenant_scope=True)
        ).first()
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="鎵垮寘鏂硅皟鏌ユ暟鎹凡瀛樺湪")

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
        result = self._result_from_base(base, now)
        result.tenant_code = batch.tenant_code
        result.region_code = group_region_code or batch.region_code
        result.result_status = "added"
        result.is_changed = True
        result.change_type = "add_contractor"
        result.remark = payload.get("remark")
        db.add(result)
        db.add(SurveyContractorTask(
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="璋冩煡鎵规宸茬粨鏉燂紝涓嶈兘鏂板")
        code = payload["code"].strip()
        data_access_service.ensure_code_in_scope(current_user, code, detail="鍙戝寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴")
        if batch.region_code:
            expected = batch.region_code[:14]
            if len(batch.region_code) >= 14 and code != expected:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="灏忕粍鎵规鐨勫彂鍖呮柟缂栫爜蹇呴』绛変簬鎵规鍖哄煙缂栫爜")
            if len(batch.region_code) < 14 and not code.startswith(batch.region_code):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鍙戝寘鏂圭紪鐮佷笉鍦ㄥ綋鍓嶈皟鏌ユ壒娆″尯鍩熷唴")
        exists = db.scalars(
            select(SurveyFbfResult).where(
                SurveyFbfResult.tenant_code == batch.tenant_code,
                SurveyFbfResult.fbfbm == code,
            ).execution_options(skip_tenant_scope=True)
        ).first()
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="鍙戝寘鏂硅皟鏌ユ暟鎹凡瀛樺湪")

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
        result = self._fbf_result_from_base(base, now)
        result.result_status = "added"
        result.is_changed = True
        result.change_type = "add_issuer"
        result.remark = payload.get("remark")
        db.add(result)
        db.commit()
        return self._serialize_issuer_row(result, batch_id, 0)

    def get_issuer(self, db: Session, batch_id: int, issuer_uid: str, current_user: User) -> dict:
        issuer = self._get_issuer(db, batch_id, issuer_uid)
        data_access_service.ensure_code_in_scope(current_user, issuer.fbfbm, detail="鍙戝寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴")
        base = db.scalars(
            select(SurveyFbfBase)
            .where(SurveyFbfBase.tenant_code == issuer.tenant_code, SurveyFbfBase.id == issuer.base_id)
            .execution_options(skip_tenant_scope=True)
        ).first()
        data = self._serialize_issuer(issuer)
        data["baseIssuer"] = self._serialize_base_issuer(base) if base else None
        return data

    def update_issuer(self, db: Session, batch_id: int, issuer_uid: str, payload: dict, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="璋冩煡鎵规宸茬粨鏉燂紝涓嶈兘缁х画缂栬緫")
        issuer = self._get_issuer(db, batch_id, issuer_uid)
        if issuer.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="发包方调查成果已确认，不能继续编辑")
        data_access_service.ensure_code_in_scope(current_user, issuer.fbfbm, detail="鍙戝寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴")
        data_access_service.ensure_code_in_scope(current_user, payload["code"], detail="鍙戝寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴")
        if batch.region_code:
            if len(batch.region_code) >= 14 and payload["code"] != batch.region_code[:14]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="灏忕粍鎵规鐨勫彂鍖呮柟缂栫爜蹇呴』绛変簬鎵规鍖哄煙缂栫爜")
            if len(batch.region_code) < 14 and not payload["code"].startswith(batch.region_code):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鍙戝寘鏂圭紪鐮佷笉鍦ㄥ綋鍓嶈皟鏌ユ壒娆″尯鍩熷唴")

        base = db.scalars(
            select(SurveyFbfBase)
            .where(SurveyFbfBase.tenant_code == issuer.tenant_code, SurveyFbfBase.id == issuer.base_id)
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
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
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
            .where(SurveyCbfBase.tenant_code == result.tenant_code, SurveyCbfBase.id == result.base_id)
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
        return self._serialize_result(result, members, base, base_members, issuer, base_issuer)

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
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="调查成果不在当前数据权限范围内")
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
                item.disabled_reason = "鑷姩瑙勫垯褰撳墠涓嶅啀鍛戒腑"
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="鍒嗗悎鎴蜂笓椤逛笉瀛樺湪")
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="鍒嗗悎鎴蜂笓椤逛笉瀛樺湪")
        return self.save_restructure(db, item.batch_id, item.contractor_uid, payload, current_user, item_id=restructure_id)

    def delete_restructure(self, db: Session, restructure_id: int, current_user: User) -> None:
        item = db.get(SurveyHouseholdRestructure, restructure_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="鍒嗗悎鎴蜂笓椤逛笉瀛樺湪")
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
        return f"{item.authorization_no}_鎺堟潈濮旀墭涔?txt", content.encode("utf-8-sig")

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
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="璇ヨ皟鏌ユ垚鏋滃凡鐢熸垚涓氬姟鐢宠")
        request_type = payload.get("requestType") or self._infer_request_type(result)
        issuer_code = self._resolve_issuer_code(db, result.cbfbm)
        request_payload = {
            "requestType": request_type,
            "requestTitle": payload.get("requestTitle") or f"{request_type}-{result.cbfmc}-璋冩煡杞姙",
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
        task_filters = self._tenant_filters(SurveyContractorTask, current_user)
        task_filters.append(SurveyContractorTask.batch_id == batch_id)
        contractor_filters = self._tenant_filters(SurveyCbfResult, current_user)
        contractor_filters.extend(data_access_service.build_code_scope_filters(SurveyCbfResult.group_region_code, current_user))
        member_filters = self._tenant_filters(SurveyCbfJtcyResult, current_user)
        self._append_group_region_filter(contractor_filters, SurveyCbfResult.group_region_code, effective_region_code)

        tasks = db.scalars(
            select(SurveyContractorTask)
            .where(*task_filters)
            .order_by(SurveyContractorTask.cbfbm.asc())
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="璋冩煡鎵规宸茬粨鏉燂紝涓嶈兘缁х画缂栬緫")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="璋冩煡鎴愭灉宸茬‘璁わ紝涓嶈兘缁х画缂栬緫")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        data_access_service.ensure_code_in_scope(current_user, payload["code"], detail="out of scope")
        now = datetime.now(timezone.utc)
        data_batch_id = batch_id
        base = db.get(SurveyCbfBase, result.base_id)
        before_summary = self._summary_from_base(base) if base else self._summary_from_result(result)
        issuer_payload = None
        issuer = None
        base_issuer = None
        issuer_changed = False
        issuer_before_summary = None
        if issuer_payload:
            issuer, base_issuer = self._get_result_issuer(db, result)
            if issuer is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="鍙戝寘鏂硅皟鏌ユ垚鏋滀笉瀛樺湪")
            data_access_service.ensure_code_in_scope(current_user, issuer.fbfbm, detail="鍙戝寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴")
            data_access_service.ensure_code_in_scope(current_user, issuer_payload["code"], detail="鍙戝寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴")
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
        task = db.scalars(
            select(SurveyContractorTask).where(
                SurveyContractorTask.batch_id == batch_id,
                SurveyContractorTask.contractor_uid == contractor_uid,
            )
        ).first()
        if task is None:
            task = SurveyContractorTask(
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
            task.has_change = result.is_changed
            task.change_count = (1 if contractor_changed else 0) + (1 if issuer_changed else 0) + len(changed_members) + deleted_member_count
            task.investigated_at = now
            task.remark = result.remark

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
        self._rebuild_diffs(db, batch_id, contractor_uid, result, base, change_record.id if change_record else None, issuer, base_issuer)
        self.refresh_auto_tags(db, batch_id, contractor_uid, current_user, commit=False)
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def confirm_result(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="璋冩煡鎵规宸茬粨鏉燂紝涓嶈兘缁х画纭")
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        if result.survey_status not in {"surveyed", "changed", "unchanged"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="璇峰厛淇濆瓨璋冩煡缁撴灉鍚庡啀纭")
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
        if task is None:
            task = SurveyContractorTask(
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="璋冩煡鎵规宸茬粨鏉燂紝涓嶈兘缁х画鎿嶄綔")
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="璋冩煡鎴愭灉宸茬‘璁わ紝涓嶈兘璺宠繃")
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
        if task is None:
            task = SurveyContractorTask(
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
            select(func.count(SurveyContractorTask.id)).where(
                SurveyContractorTask.batch_id == batch_id,
                SurveyContractorTask.task_status.notin_(["confirmed", "skipped"]),
            )
        ) or 0
        if unfinished:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request failed")
        skipped_without_reason = db.scalar(
            select(func.count(SurveyContractorTask.id)).where(
                SurveyContractorTask.batch_id == batch_id,
                SurveyContractorTask.task_status == "skipped",
                or_(SurveyContractorTask.skip_reason.is_(None), SurveyContractorTask.skip_reason == ""),
            )
        ) or 0
        if skipped_without_reason:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"杩樻湁 {skipped_without_reason} 鎴疯烦杩囧師鍥犱负绌猴紝涓嶈兘缁撴潫鎵规")
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"杩樻湁 {missing_change_trace} 鎴锋湁鍙樺寲浣嗙己灏戝彉鍖栬褰曪紝涓嶈兘缁撴潫鎵规")
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
                errors.append("鎵垮寘鏂瑰瓨鍦ㄥ彉鍖栨椂蹇呴』濉啓鍙樺寲鍘熷洜")
            if not self._has_text(result.policy_basis):
                errors.append("鎵垮寘鏂瑰瓨鍦ㄥ彉鍖栨椂蹇呴』濉啓鏀跨瓥渚濇嵁")

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
        base = db.get(SurveyCbfBase, result.base_id) if result.base_id else None
        batch = self._ensure_batch(db, base.batch_id) if base else None
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="璋冩煡鎵规宸茬粨鏉燂紝涓嶈兘缁х画缂栬緫")
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="璋冩煡鎴愭灉宸茬‘璁わ紝涓嶈兘缁х画缂栬緫")

    async def _store_upload(self, directory: Path, upload_file: UploadFile) -> tuple[Path, int]:
        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="涓婁紶鏂囦欢涓虹┖")
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
            return "娉ㄩ攢鐧昏"
        return "鍙樻洿鐧昏"

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
        parts = [part.strip() for part in region_name.replace("，", "/").split("/") if part.strip()]
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

    def _result_from_base(self, base: SurveyCbfBase, now: datetime) -> SurveyCbfResult:
        return SurveyCbfResult(
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

    def _initialize_related_survey_data(self, db: Session, batch: SurveyBatch, contractors: list[SurveyCbfResult], now: datetime) -> None:
        cbfbms = {item.cbfbm for item in contractors if item.cbfbm}
        if not cbfbms:
            return
        cbdkxx_results = db.scalars(
            select(SurveyCbdkxxResult)
            .where(
                SurveyCbdkxxResult.tenant_code == batch.tenant_code,
                SurveyCbdkxxResult.cbfbm.in_(cbfbms),
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
            db.add(self._fbf_result_from_base(base, now))

        for dk in dk_by_code.values():
            base = self._dk_base_from_result(batch.id, dk, now)
            db.add(base)
            db.flush()
            result = self._dk_result_from_base(base, now)
            db.add(result)
            db.flush()
            self._copy_dk_geometry(db, dk.id, "survey_dk_base", base.id)
            self._copy_dk_geometry(db, dk.id, "survey_dk_result", result.id)

        for parcel_info in latest_cbdkxx.values():
            base = self._cbdkxx_base_from_result(batch.id, parcel_info, now)
            db.add(base)
            db.flush()
            db.add(self._cbdkxx_result_from_base(base, now))

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

    def _fbf_base_from_result(self, batch_id: int, item: SurveyFbfResult, now: datetime) -> SurveyFbfBase:
        return SurveyFbfBase(
            tenant_code=item.tenant_code,
            region_code=item.region_code,
            batch_id=batch_id,
            issuer_uid=str(uuid5(NAMESPACE_URL, f"survey:{batch_id}:fbf:{item.fbfbm}")),
            source_fbfbm=item.fbfbm,
            fbfbm=item.fbfbm,
            fbfmc=item.fbfmc,
            fbffzrxm=item.fbffzrxm,
            fzrzjlx=item.fzrzjlx,
            fzrzjhm=item.fzrzjhm,
            lxdh=item.lxdh,
            fbfdz=item.fbfdz,
            yzbm=item.yzbm,
            fbfdcy=item.fbfdcy,
            fbfdcrq=item.fbfdcrq,
            fbfdcjs=item.fbfdcjs,
            source_import_batch_id=item.source_import_batch_id,
            source_import_row_id=item.source_import_row_id,
            last_import_batch_id=item.last_import_batch_id,
            last_import_row_id=item.last_import_row_id,
            initialized_from_table="survey_fbf_result",
            initialized_from_key=item.fbfbm,
            initialized_at=now,
            snapshot_at=now,
        )

    def _fbf_result_from_base(self, base: SurveyFbfBase, now: datetime) -> SurveyFbfResult:
        return SurveyFbfResult(
            tenant_code=base.tenant_code,
            region_code=base.region_code,
            issuer_uid=base.issuer_uid,
            base_id=base.id,
            fbfbm=base.fbfbm,
            fbfmc=base.fbfmc,
            fbffzrxm=base.fbffzrxm,
            fzrzjlx=base.fzrzjlx,
            fzrzjhm=base.fzrzjhm,
            lxdh=base.lxdh,
            fbfdz=base.fbfdz,
            yzbm=base.yzbm,
            fbfdcy=base.fbfdcy,
            fbfdcrq=base.fbfdcrq,
            fbfdcjs=base.fbfdcjs,
            source_import_batch_id=base.source_import_batch_id,
            source_import_row_id=base.source_import_row_id,
            last_import_batch_id=base.last_import_batch_id,
            last_import_row_id=base.last_import_row_id,
            initialized_from_base_id=base.id,
            initialized_at=now,
        )

    def _cbdkxx_base_from_result(self, batch_id: int, item: SurveyCbdkxxResult, now: datetime) -> SurveyCbdkxxBase:
        return SurveyCbdkxxBase(
            tenant_code=item.tenant_code,
            region_code=item.region_code,
            batch_id=batch_id,
            parcel_info_uid=str(uuid5(NAMESPACE_URL, f"survey:{batch_id}:cbdkxx:{item.dkbm}:{item.cbfbm}")),
            source_dkbm=item.dkbm,
            dkbm=item.dkbm,
            fbfbm=item.fbfbm,
            cbfbm=item.cbfbm,
            cbjyqqdfs=item.cbjyqqdfs,
            htmj=item.htmj,
            cbhtbm=item.cbhtbm,
            lzhtbm=item.lzhtbm,
            cbjyqzbm=item.cbjyqzbm,
            yhtmj=item.yhtmj,
            htmjm=item.htmjm,
            yhtmjm=item.yhtmjm,
            sfqqqg=item.sfqqqg,
            source_import_batch_id=item.source_import_batch_id,
            source_import_row_id=item.source_import_row_id,
            last_import_batch_id=item.last_import_batch_id,
            last_import_row_id=item.last_import_row_id,
            initialized_from_table="survey_cbdkxx_result",
            initialized_from_key=f"{item.dkbm}:{item.cbfbm}",
            initialized_at=now,
            snapshot_at=now,
        )

    def _cbdkxx_result_from_base(self, base: SurveyCbdkxxBase, now: datetime) -> SurveyCbdkxxResult:
        return SurveyCbdkxxResult(
            tenant_code=base.tenant_code,
            region_code=base.region_code,
            parcel_info_uid=base.parcel_info_uid,
            base_id=base.id,
            dkbm=base.dkbm,
            fbfbm=base.fbfbm,
            cbfbm=base.cbfbm,
            cbjyqqdfs=base.cbjyqqdfs,
            htmj=base.htmj,
            cbhtbm=base.cbhtbm,
            lzhtbm=base.lzhtbm,
            cbjyqzbm=base.cbjyqzbm,
            yhtmj=base.yhtmj,
            htmjm=base.htmjm,
            yhtmjm=base.yhtmjm,
            sfqqqg=base.sfqqqg,
            source_import_batch_id=base.source_import_batch_id,
            source_import_row_id=base.source_import_row_id,
            last_import_batch_id=base.last_import_batch_id,
            last_import_row_id=base.last_import_row_id,
            initialized_from_base_id=base.id,
            initialized_at=now,
        )

    def _dk_base_from_result(self, batch_id: int, item: SurveyDkResult, now: datetime) -> SurveyDkBase:
        return SurveyDkBase(
            tenant_code=item.tenant_code,
            region_code=item.region_code,
            batch_id=batch_id,
            parcel_uid=str(uuid5(NAMESPACE_URL, f"survey:{batch_id}:dk:{item.dkbm}")),
            source_dkbm=item.dkbm,
            bsm=item.bsm,
            ysdm=item.ysdm,
            dkbm=item.dkbm,
            dkmc=item.dkmc,
            syqxz=item.syqxz,
            dklb=item.dklb,
            tdlylx=item.tdlylx,
            dldj=item.dldj,
            tdyt=item.tdyt,
            sfjbnt=item.sfjbnt,
            scmj=item.scmj,
            dkdz=item.dkdz,
            dkxz=item.dkxz,
            dknz=item.dknz,
            dkbz=item.dkbz,
            dkbzxx=item.dkbzxx,
            zjrxm=item.zjrxm,
            source_import_batch_id=item.source_import_batch_id,
            source_import_row_id=item.source_import_row_id,
            last_import_batch_id=item.last_import_batch_id,
            last_import_row_id=item.last_import_row_id,
            initialized_from_table="survey_dk_result",
            initialized_from_key=item.dkbm,
            initialized_at=now,
            snapshot_at=now,
        )

    def _dk_result_from_base(self, base: SurveyDkBase, now: datetime) -> SurveyDkResult:
        return SurveyDkResult(
            tenant_code=base.tenant_code,
            region_code=base.region_code,
            parcel_uid=base.parcel_uid,
            base_id=base.id,
            bsm=base.bsm,
            ysdm=base.ysdm,
            dkbm=base.dkbm,
            dkmc=base.dkmc,
            syqxz=base.syqxz,
            dklb=base.dklb,
            tdlylx=base.tdlylx,
            dldj=base.dldj,
            tdyt=base.tdyt,
            sfjbnt=base.sfjbnt,
            scmj=base.scmj,
            dkdz=base.dkdz,
            dkxz=base.dkxz,
            dknz=base.dknz,
            dkbz=base.dkbz,
            dkbzxx=base.dkbzxx,
            zjrxm=base.zjrxm,
            source_import_batch_id=base.source_import_batch_id,
            source_import_row_id=base.source_import_row_id,
            last_import_batch_id=base.last_import_batch_id,
            last_import_row_id=base.last_import_row_id,
            initialized_from_base_id=base.id,
            initialized_at=now,
        )

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
        filters = self._tenant_filters(SurveyContractorTask, current_user)
        filters.extend(data_access_service.build_code_scope_filters(SurveyContractorTask.region_code, current_user))
        if region_code:
            filters.append(SurveyContractorTask.region_code.like(f"{region_code}%"))
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
            select(func.count(SurveyContractorTask.id))
            .where(
                SurveyContractorTask.tenant_code == batch.tenant_code,
                SurveyContractorTask.batch_id == batch.id,
            )
            .execution_options(skip_tenant_scope=True)
        ) or 0
        code_prefix_count = 0
        region_prefix_count = 0
        if effective_region_code:
            code_prefix_count = db.scalar(
                select(func.count(SurveyContractorTask.id))
                .where(
                    SurveyContractorTask.tenant_code == batch.tenant_code,
                    SurveyContractorTask.batch_id == batch.id,
                    SurveyContractorTask.cbfbm.like(f"{effective_region_code}%"),
                )
                .execution_options(skip_tenant_scope=True)
            ) or 0
            region_prefix_count = db.scalar(
                select(func.count(SurveyContractorTask.id))
                .where(
                    SurveyContractorTask.tenant_code == batch.tenant_code,
                    SurveyContractorTask.batch_id == batch.id,
                    SurveyContractorTask.region_code.like(f"{effective_region_code}%"),
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
        task_filters = [SurveyContractorTask.tenant_code == item.tenant_code, SurveyContractorTask.batch_id == item.id]
        not_started_count = max(
            task_count - (db.scalar(select(func.count(SurveyContractorTask.id)).where(*task_filters).execution_options(skip_tenant_scope=True)) or 0),
            0,
        )
        surveyed_count = db.scalar(
            select(func.count(SurveyContractorTask.id)).where(
                *task_filters,
                SurveyContractorTask.task_status.in_(["surveyed", "changed", "unchanged", "confirmed"]),
            ).execution_options(skip_tenant_scope=True)
        ) or 0
        changed_count = db.scalar(
            select(func.count(SurveyChangeRecord.id)).where(SurveyChangeRecord.tenant_code == item.tenant_code, SurveyChangeRecord.batch_id == item.id)
            .execution_options(skip_tenant_scope=True)
        ) or 0
        confirmed_count = db.scalar(
            select(func.count(SurveyContractorTask.id)).where(*task_filters, SurveyContractorTask.task_status == "confirmed")
            .execution_options(skip_tenant_scope=True)
        ) or 0
        skipped_count = db.scalar(
            select(func.count(SurveyContractorTask.id)).where(*task_filters, SurveyContractorTask.task_status == "skipped")
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

    def _serialize_result_task(self, result: SurveyCbfResult, survey_batch_id: int, task: SurveyContractorTask | None = None) -> dict:
        result_task_status = "not_started" if result.survey_status == "not_surveyed" else (result.survey_status or "not_started")
        return {
            "id": task.id if task else result.id,
            "batchId": survey_batch_id,
            "contractorUid": result.contractor_uid,
            "cbfbm": result.cbfbm,
            "cbfmc": result.cbfmc,
            "regionCode": result.region_code,
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
        task: SurveyContractorTask | None = None,
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
            "taskStatus": task.task_status if task else result_task_status,
            "hasChange": task.has_change if task else bool(result and result.is_changed),
            "changeCount": task.change_count if task else 0,
            "investigatedAt": task.investigated_at if task else (result.investigated_at if result else None),
            "remark": task.remark if task else (result.remark if result else None),
        }

    def _serialize_issuer_row(self, item: SurveyFbfResult, survey_batch_id: int, related_count: int = 0, source_task: SurveyContractorTask | None = None) -> dict:
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
        issuer: SurveyFbfResult | None = None,
        base_issuer: SurveyFbfBase | None = None,
    ) -> None:
        db.execute(
            delete(SurveyChangeDiff).where(
                SurveyChangeDiff.batch_id == batch_id,
                SurveyChangeDiff.contractor_uid == contractor_uid,
            )
        )
        data_batch_id = batch_id
        if base is not None:
            contractor_fields = [
                ("cbfbm", "cbfbm"),
                ("cbflx", "cbflx"),
                ("cbfmc", "cbfmc"),
                ("cbfzjlx", "璇佷欢绫诲瀷"),
                ("cbfzjhm", "璇佷欢鍙风爜"),
                ("cbfdz", "鎵垮寘鏂瑰湴鍧€"),
                ("yzbm", "閭斂缂栫爜"),
                ("lxdh", "鑱旂郴鐢佃瘽"),
                ("cbfcysl", "cbfcysl"),
                ("group_region_code", "鎵€灞炵粍浠ｇ爜"),
                ("group_region_name", "鎵€灞炵粍鍚嶇О"),
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
                ("fbffzrxm", "鍙戝寘鏂硅礋璐ｄ汉"),
                ("fzrzjlx", "fzrzjlx"),
                ("fzrzjhm", "fzrzjhm"),
                ("lxdh", "鑱旂郴鐢佃瘽"),
                ("fbfdz", "鍙戝寘鏂瑰湴鍧€"),
                ("yzbm", "閭斂缂栫爜"),
                ("fbfdcy", "fbfdcy"),
                ("fbfdcrq", "璋冩煡鏃ユ湡"),
                ("fbfdcjs", "璋冩煡璁颁簨"),
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
            ("cyxm", "濮撳悕"),
            ("cyzjlx", "璇佷欢绫诲瀷"),
            ("cyzjhm", "璇佷欢鍙风爜"),
            ("cyxb", "鎬у埆"),
            ("yhzgx", "yhzgx"),
            ("cybz", "鎴愬憳澶囨敞浠ｇ爜"),
            ("sfgyr", "sfgyr"),
            ("cybzsm", "鎴愬憳澶囨敞璇存槑"),
            ("member_result_status", "member_result_status"),
            ("is_urban_settled", "鏄惁杩涘煄钀芥埛"),
            ("is_married_out_woman", "is_married_out_woman"),
            ("is_deceased", "鏄惁姝讳骸"),
            ("is_five_guarantees", "鏄惁浜斾繚"),
            ("rights_disposition", "鏉冪泭澶勭疆"),
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
                        field_label="鏂板鎴愬憳",
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
                        field_label="鍒犻櫎鎴愬憳",
                        before_value=f"{member_base.cyxm} / {member_base.cyzjhm}",
                        after_value=None,
                        change_reason=result.change_reason,
                    )
                )

    def _diff_value(self, value) -> str | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return "yes" if value else "no"
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
        return "yes" if value else "no"

    def _build_tasks_csv(self, tasks: list[SurveyContractorTask]) -> bytes:
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
                "鎵规鍐呭敮涓€鏍囪瘑",
                "field",
                "field",
                "field",
                "璇佷欢绫诲瀷",
                "璇佷欢鍙风爜",
                "鎵垮寘鏂瑰湴鍧€",
                "閭斂缂栫爜",
                "鑱旂郴鐢佃瘽",
                "field",
                "field",
                "field",
                "鏄惁鍙樺寲",
                "鍙樺寲绫诲瀷",
                "鍙樺寲鍘熷洜",
                "鏀跨瓥渚濇嵁",
                "渚濇嵁鏉愭枡鎽樿",
                "field",
                "璋冩煡鏃堕棿",
                "field",
                "纭鏃堕棿",
                "鏉ユ簮瀵煎叆鎵规ID",
                "鏉ユ簮瀵煎叆琛孖D",
                "鏈€杩戝鍏ユ壒娆D",
                "鏈€杩戝鍏ヨID",
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
                "鍙戝寘鏂瑰敮涓€鏍囪瘑",
                "field",
                "field",
                "field",
                "field",
                "field",
                "鑱旂郴鐢佃瘽",
                "鍙戝寘鏂瑰湴鍧€",
                "閭斂缂栫爜",
                "field",
                "璋冩煡鏃ユ湡",
                "璋冩煡璁颁簨",
                "field",
                "鏄惁鍙樺寲",
                "鍙樺寲绫诲瀷",
                "鍙樺寲鍘熷洜",
                "鏀跨瓥渚濇嵁",
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
                "鎵规鍐呮埛鍞竴鏍囪瘑",
                "鎴愬憳鍞竴鏍囪瘑",
                "field",
                "鎴愬憳濮撳悕",
                "璇佷欢绫诲瀷",
                "璇佷欢鍙风爜",
                "鎬у埆",
                "field",
                "field",
                "鏄惁鍙樺寲",
                "鏄惁鎴蜂富",
                "鏄惁杩涘煄钀芥埛",
                "field",
                "鏄惁姝讳骸",
                "鏄惁浜斾繚",
                "鍙樺寲鍘熷洜",
                "鏀跨瓥渚濇嵁",
                "鏉冪泭澶勭疆",
                "鏉ユ簮瀵煎叆鎵规ID",
                "鏉ユ簮瀵煎叆琛孖D",
                "鏈€杩戝鍏ユ壒娆D",
                "鏈€杩戝鍏ヨID",
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
            .where(SurveyFbfBase.tenant_code == result.tenant_code, SurveyFbfBase.id == issuer.base_id)
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="鍙戝寘鏂硅皟鏌ユ垚鏋滀笉瀛樺湪")
        return issuer

    def _serialize_result(
        self,
        item: SurveyCbfResult,
        members: list[SurveyCbfJtcyResult],
        base: SurveyCbfBase | None = None,
        base_members: list[SurveyCbfJtcyBase] | None = None,
        issuer: SurveyFbfResult | None = None,
        base_issuer: SurveyFbfBase | None = None,
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
            "issuer": self._serialize_issuer(issuer) if issuer else None,
            "baseIssuer": self._serialize_base_issuer(base_issuer) if base_issuer else None,
            "familyMembers": [self._serialize_member(member) for member in members],
        }

    def _serialize_issuer(self, item: SurveyFbfResult) -> dict:
        return {
            "id": item.id,
            "issuerUid": item.issuer_uid,
            "baseId": item.base_id,
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

    # 鈹€鈹€ 璋冩煡鎿嶄綔 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def change_household_head(
        self, db: Session, batch_id: int, contractor_uid: str,
        new_head_member_uid: str, reason: str | None, current_user: User,
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

        # 鏌ユ壘鏃ф埛涓?
        old_head = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
                SurveyCbfJtcyResult.is_household_head.is_(True),
            )
        ).first()

        # 鏌ユ壘鏂版埛涓?
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

        # repaired invalid string literal
        if old_head:
            old_head.is_household_head = False
            old_head.is_changed = True
        new_head.is_household_head = True
        new_head.is_changed = True
        new_head.yhzgx = "01"  # 璁句负鏈汉锛堟埛涓伙級

        # 鍒涘缓鍙樺寲璁板綍
        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="change_head",
            before_summary={"old_head": old_name, "old_head_uid": old_head.member_uid if old_head else None},
            after_summary={"new_head": new_head.cyxm, "new_head_uid": new_head_member_uid},
            reason=reason,
            current_user=current_user, now=now,
        )
        db.flush()

        # 鍒涘缓 diff 璁板綍
        db.add(SurveyChangeDiff(
            batch_id=batch_id, contractor_uid=contractor_uid, change_id=record.id,
            entity_type="member", entity_uid=new_head_member_uid, entity_name=new_head.cyxm,
            field_name="is_household_head", field_label="鏄惁鎴蜂富",
            before_value="no", after_value="yes", change_reason=reason,
        ))
        if old_head:
            db.add(SurveyChangeDiff(
                batch_id=batch_id, contractor_uid=contractor_uid, change_id=record.id,
                entity_type="member", entity_uid=old_head.member_uid, entity_name=old_name,
                field_name="is_household_head", field_label="鏄惁鎴蜂富",
                before_value="yes", after_value="no", change_reason=reason,
            ))

        # 鏇存柊浠诲姟
        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now

        result.investigated_at = now
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def maintain_members(
        self, db: Session, batch_id: int, contractor_uid: str,
        members_to_add: list[dict], members_to_update: list[dict],
        members_to_delete: list[str], reason: str | None, current_user: User,
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

        change_details = {"added": [], "updated": [], "deleted": []}

        # 鍒犻櫎
        for member_uid in members_to_delete:
            member = db.scalars(
                select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.contractor_uid == contractor_uid,
                    SurveyCbfJtcyResult.member_uid == member_uid,
                )
            ).first()
            if member is None:
                continue
            change_details["deleted"].append({
                "member_uid": member_uid, "name": member.cyxm,
                "id_no": member.cyzjhm, "relation": member.yhzgx,
            })
            db.delete(member)

        # 鏇存柊
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
            change_details["updated"].append(member_uid)
            member.cyxm = item.get("name", member.cyxm)
            member.cyxb = item.get("gender", member.cyxb)
            member.cyzjlx = item.get("idType", member.cyzjlx)
            member.cyzjhm = item.get("idNo", member.cyzjhm)
            member.yhzgx = item.get("relationToHead", member.yhzgx)
            member.cybz = item.get("noteCode", member.cybz)
            member.sfgyr = item.get("isCoOwner", member.sfgyr)
            member.cybzsm = item.get("note", member.cybzsm)
            member.is_household_head = bool(item.get("isHouseholdHead", member.is_household_head))
            member.is_changed = True

        # 鏂板
        for item in members_to_add:
            member_uid = item.get("memberUid") or str(uuid4())
            member = SurveyCbfJtcyResult(
                contractor_uid=contractor_uid,
                member_uid=member_uid, base_id=None,
                cbfbm=result.cbfbm,
                cyxm=item["name"], cyxb=item.get("gender", "1"),
                cyzjlx=item.get("idType", "1"), cyzjhm=item.get("idNo", ""),
                yhzgx=item.get("relationToHead", "09"),
                cybz=item.get("noteCode"), sfgyr=item.get("isCoOwner"),
                cybzsm=item.get("note"),
                member_result_status="added", survey_status="surveyed",
                is_household_head=bool(item.get("isHouseholdHead")),
                is_changed=True,
                initialized_at=now,
                investigator_id=current_user.id, investigator_name=current_user.real_name,
                investigated_at=now,
            )
            db.add(member)
            change_details["added"].append({"member_uid": member_uid, "name": item["name"]})

        # 鏇存柊鎴愬憳鏁伴噺
        member_count = db.scalar(
            select(func.count(SurveyCbfJtcyResult.id)).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
        ) or 0
        result.cbfcysl = member_count
        result.investigated_at = now

        # 鍙樺寲璁板綍
        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="member_maintain",
            before_summary={},
            after_summary=change_details,
            reason=reason,
            current_user=current_user, now=now,
        )

        # 浠诲姟鏇存柊
        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + len(members_to_add) + len(members_to_update) + len(members_to_delete)
            task.investigated_at = now

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
    ) -> dict:
        # repaired docstring
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(400, "璋冩煡鎴愭灉宸茬‘璁わ紝涓嶈兘娉ㄩ攢")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        now = datetime.now(timezone.utc)

        # 鏀堕泦鍒犻櫎鍓嶅畬鏁村揩鐓?
        members = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
        ).all()
        parcel_relations = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
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

        # 鍒涘缓鍙樺寲璁板綍锛堝厛鍒涘缓锛屽洜涓洪渶瑕?change_id 缁?diff锛?
        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="deregister",
            before_summary=before_summary,
            after_summary={"action": "deregistered", "reason": reason},
            reason=reason,
            current_user=current_user, now=now,
        )
        db.flush()

        # 鍒涘缓 diffs锛堥€愪釜瀹炰綋璁板綍鍒犻櫎锛?
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
                field_name="member", field_label="鍒犻櫎鎴愬憳",
                before_value=f"{m.cyxm} / {m.cyzjhm}", after_value=None, change_reason=reason,
            ))
        for p in parcel_relations:
            db.add(SurveyChangeDiff(
                batch_id=batch_id, contractor_uid=contractor_uid, change_id=record.id,
                entity_type="parcel_relation", entity_uid=p.parcel_info_uid, entity_name=p.dkbm,
                field_name="parcel_relation", field_label="鍒犻櫎鍦板潡鍏宠仈",
                before_value=f"{p.dkbm} (鍏宠仈 {result.cbfbm})", after_value=None, change_reason=reason,
            ))

        # 鐗╃悊鍒犻櫎
        for m in members:
            db.delete(m)
        for p in parcel_relations:
            db.delete(p)
        db.delete(result)

        # 鏇存柊浠诲姟鐘舵€?
        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.task_status = "deregistered"
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now

        db.commit()
        return {"contractorUid": contractor_uid, "status": "deregistered", "changeNo": record.change_no}

    def add_parcel(
        self, db: Session, batch_id: int, contractor_uid: str,
        payload: dict, current_user: User,
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

        # 鏌ユ壘鍙戝寘鏂癸紙浠庡凡鏈夊湴鍧楀叧绯讳腑鑾峰彇锛屾垨浠庢壙鍖呮柟浠ｇ爜鎺ㄥ锛?
        existing_parcel = db.scalars(
            select(SurveyCbdkxxResult.fbfbm).where(
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
            ).limit(1)
        ).first()
        fbfbm = existing_parcel or result.cbfbm[:14]

        parcel_uid = str(uuid4())
        parcel_info_uid = str(uuid4())
        scmj = payload["scmj"]

        # 鍒涘缓 SurveyDkResult
        dk_result = SurveyDkResult(
            parcel_uid=parcel_uid,
            base_id=0,  # 鏂板鍦板潡鏃?base
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

        # 鍒涘缓 SurveyCbdkxxResult
        cbdkxx = SurveyCbdkxxResult(
            parcel_info_uid=parcel_info_uid,
            base_id=0,
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

        # 鍙樺寲璁板綍
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

        # diffs
        db.add(SurveyChangeDiff(
            batch_id=batch_id, contractor_uid=contractor_uid, change_id=record.id,
            entity_type="parcel", entity_uid=parcel_uid, entity_name=payload["dkmc"],
            field_name="parcel", field_label="鏂板鍦板潡",
            before_value=None, after_value="changed",
            change_reason=payload.get("reason"),
        ))

        # 鏇存柊浠诲姟
        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now

        result.investigated_at = now
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def split_parcel(
        self, db: Session, batch_id: int, contractor_uid: str,
        payload: dict, current_user: User,
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

        # 鏌ユ壘鍘熷湴鍧楀叧鑱?
        dkbm = payload["dkbm"]
        old_relation = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm == dkbm,
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
            )
        ).first()
        if old_relation is None:
            raise HTTPException(404, "鍘熷湴鍧楀叧鑱斾笉瀛樺湪")

        # 鏌ユ壘鍘熷湴鍧?
        old_parcel = db.scalars(
            select(SurveyDkResult).where(
                SurveyDkResult.dkbm == old_relation.dkbm,
            )
        ).first()
        if old_parcel is None:
            raise HTTPException(404, "鍘熷湴鍧椾笉瀛樺湪")

        new_scmj = payload["newScmj"]
        old_area = float(old_parcel.scmj or 0)
        if new_scmj >= old_area:
            raise HTTPException(400, f"鍒囧壊闈㈢Н({new_scmj})涓嶈兘澶т簬绛変簬鍘熷湴鍧楅潰绉?{old_area})")

        # 鍑忓皬鍘熷湴鍧楅潰绉?
        remaining = round(old_area - new_scmj, 2)
        old_parcel.scmj = remaining
        old_parcel.is_changed = True
        old_parcel.change_type = "split_parcel"
        old_parcel.change_reason = payload.get("reason")

        # 鏇存柊鍘熷湴鍧楀叧鑱旂殑闈㈢Н
        if old_relation.htmj and float(old_relation.htmj) > 0:
            old_relation.htmj = remaining

        # 鍒涘缓鏂板湴鍧?
        new_parcel_uid = str(uuid4())
        new_parcel_info_uid = str(uuid4())
        new_dkbm = payload["newDkbm"]

        new_parcel = SurveyDkResult(
            parcel_uid=new_parcel_uid,
            base_id=0,
            ysdm=old_parcel.ysdm,
            dkbm=new_dkbm,
            dkmc=payload["newDkmc"],
            syqxz=old_parcel.syqxz,
            dklb=old_parcel.dklb,
            tdlylx=old_parcel.tdlylx,
            dldj=old_parcel.dldj,
            tdyt=old_parcel.tdyt,
            sfjbnt=old_parcel.sfjbnt,
            scmj=new_scmj,
            dkdz=old_parcel.dkdz,
            dkxz=old_parcel.dkxz,
            dknz=old_parcel.dknz,
            dkbz=f"浠?{old_parcel.dkbm} 鍒囧壊",
            survey_status="surveyed",
            result_status="added",
            is_changed=True,
            change_type="split_parcel",
            change_reason=payload.get("reason"),
            initialized_at=now,
        )
        db.add(new_parcel)
        db.flush()

        # 鍒涘缓鏂板湴鍧楀叧鑱?
        new_relation = SurveyCbdkxxResult(
            parcel_info_uid=new_parcel_info_uid,
            base_id=0,
            dkbm=new_dkbm,
            fbfbm=old_relation.fbfbm,
            cbfbm=result.cbfbm,
            cbjyqqdfs=old_relation.cbjyqqdfs,
            htmj=new_scmj,
            cbhtbm=old_relation.cbhtbm,
            lzhtbm=old_relation.lzhtbm,
            cbjyqzbm=old_relation.cbjyqzbm,
            sfqqqg=old_relation.sfqqqg,
            survey_status="surveyed",
            result_status="added",
            is_changed=True,
            change_type="split_parcel",
            change_reason=payload.get("reason"),
            initialized_at=now,
        )
        db.add(new_relation)

        # 鍙樺寲璁板綍
        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="split_parcel",
            before_summary={
                "dkbm": old_parcel.dkbm, "original_area": old_area,
            },
            after_summary={
                "action": "split_parcel",
                "original_dkbm": old_parcel.dkbm, "remaining_area": remaining,
                "new_dkbm": new_dkbm, "new_area": new_scmj,
            },
            reason=payload.get("reason"),
            current_user=current_user, now=now,
        )
        db.flush()

        # diffs
        db.add(SurveyChangeDiff(
            batch_id=batch_id, contractor_uid=contractor_uid, change_id=record.id,
            entity_type="parcel", entity_uid=old_parcel.parcel_uid, entity_name=old_parcel.dkmc,
            field_name="scmj", field_label="瀹炴祴闈㈢Н",
            before_value=str(old_area), after_value=str(remaining), change_reason=payload.get("reason"),
        ))
        db.add(SurveyChangeDiff(
            batch_id=batch_id, contractor_uid=contractor_uid, change_id=record.id,
            entity_type="parcel", entity_uid=new_parcel_uid, entity_name=new_parcel.dkmc,
            field_name="field", field_label="field",
            before_value=None, after_value="changed",
            change_reason=payload.get("reason"),
        ))

        # 鏇存柊浠诲姟
        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now

        result.investigated_at = now
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def swap_parcels(
        self, db: Session, batch_id: int, contractor_uid: str,
        payload: dict, current_user: User,
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
            raise HTTPException(400, "鐩爣鎵垮寘鏂瑰凡纭")
        if target_uid == contractor_uid:
            raise HTTPException(400, "invalid operation")

        source_dkbms = payload["sourceDkbms"]
        target_dkbms = payload["targetDkbms"]

        # 鎵ц浜掓崲
        swapped_source = []
        swapped_target = []
        for dkbm in source_dkbms:
            rel = db.scalars(
                select(SurveyCbdkxxResult).where(
                    SurveyCbdkxxResult.dkbm == dkbm,
                    SurveyCbdkxxResult.cbfbm == result.cbfbm,
                )
            ).first()
            if rel is None:
                raise HTTPException(404, f"婧愬湴鍧?{dkbm} 涓嶅睘浜庡綋鍓嶆壙鍖呮柟")
            swapped_source.append({"dkbm": dkbm, "from": result.cbfbm, "to": target_result.cbfbm})
            rel.cbfbm = target_result.cbfbm
            rel.is_changed = True
            rel.change_type = "swap_parcels"
            rel.change_reason = payload.get("reason")

        for dkbm in target_dkbms:
            rel = db.scalars(
                select(SurveyCbdkxxResult).where(
                    SurveyCbdkxxResult.dkbm == dkbm,
                    SurveyCbdkxxResult.cbfbm == target_result.cbfbm,
                )
            ).first()
            if rel is None:
                raise HTTPException(404, f"鐩爣鍦板潡 {dkbm} 涓嶅睘浜庣洰鏍囨壙鍖呮柟")
            swapped_target.append({"dkbm": dkbm, "from": target_result.cbfbm, "to": result.cbfbm})
            rel.cbfbm = result.cbfbm
            rel.is_changed = True
            rel.change_type = "swap_parcels"
            rel.change_reason = payload.get("reason")

        # 鍙樺寲璁板綍锛堟簮鏂癸級
        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="swap_parcels",
            before_summary={"swapped_out": source_dkbms},
            after_summary={"swapped_in": target_dkbms, "counterparty": target_result.cbfbm},
            reason=payload.get("reason"),
            current_user=current_user, now=now,
        )
        db.flush()
        for item in swapped_source:
            db.add(SurveyChangeDiff(
                batch_id=batch_id, contractor_uid=contractor_uid, change_id=record.id,
                entity_type="parcel_relation", entity_uid=item["dkbm"], entity_name=item["dkbm"],
                field_name="field", field_label="field",
                before_value=item["from"], after_value=item["to"], change_reason=payload.get("reason"),
            ))
        for item in swapped_target:
            db.add(SurveyChangeDiff(
                batch_id=batch_id, contractor_uid=contractor_uid, change_id=record.id,
                entity_type="parcel_relation", entity_uid=item["dkbm"], entity_name=item["dkbm"],
                field_name="field", field_label="field",
                before_value=item["from"], after_value=item["to"], change_reason=payload.get("reason"),
            ))

        # 鍙樺寲璁板綍锛堢洰鏍囨柟锛?
        target_record = self._create_change_record(
            db, batch_id, target_uid, target_result.cbfbm,
            change_type="swap_parcels",
            before_summary={"swapped_out": target_dkbms},
            after_summary={"swapped_in": source_dkbms, "counterparty": result.cbfbm},
            reason=payload.get("reason"),
            current_user=current_user, now=now,
        )

        # 鏇存柊鍙屾柟浠诲姟
        for uid in [contractor_uid, target_uid]:
            task = self._get_task(db, batch_id, uid)
            if task:
                task.has_change = True
                task.change_count = (task.change_count or 0) + 1
                task.investigated_at = now

        result.investigated_at = now
        target_result.investigated_at = now
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def remove_parcel(
        self, db: Session, batch_id: int, contractor_uid: str,
        payload: dict, current_user: User,
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

        # 鏌ユ壘鍦板潡鍏宠仈
        relation = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm == dkbm,
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
            )
        ).first()
        if relation is None:
            raise HTTPException(404, "鍦板潡鍏宠仈涓嶅瓨鍦ㄦ垨涓嶅睘浜庡綋鍓嶆壙鍖呮柟")

        # 鏌ユ壘鍦板潡璁板綍
        parcel = db.scalars(
            select(SurveyDkResult).where(
                SurveyDkResult.dkbm == dkbm,
            )
        ).first()

        before_parcels_count = db.scalar(
            select(func.count(SurveyCbdkxxResult.id)).where(
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
            )
        ) or 0

        # 杞垹闄わ細鏍囪鍏宠仈鍏崇郴涓哄凡绉婚櫎
        relation.result_status = "removed"
        relation.is_changed = True
        relation.change_type = "remove_parcel"
        relation.change_reason = payload.get("reason")

        if parcel:
            parcel.result_status = "removed"
            parcel.is_changed = True
            parcel.change_type = "remove_parcel"
            parcel.change_reason = payload.get("reason")

        # 鍙樺寲璁板綍
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

        # diffs
        db.add(SurveyChangeDiff(
            batch_id=batch_id, contractor_uid=contractor_uid, change_id=record.id,
            entity_type="parcel", entity_uid=dkbm, entity_name=dkbm,
            field_name="parcel", field_label="绉婚櫎鍦板潡",
            before_value=f"褰掑睘 {result.cbfbm} {result.cbfmc}",
            after_value=None,
            change_reason=payload.get("reason"),
        ))

        # 鏇存柊浠诲姟
        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now

        result.investigated_at = now
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def split_household(
        self, db: Session, batch_id: int, contractor_uid: str,
        payload: dict, current_user: User,
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

        member_uids = payload["memberUids"]
        parcel_dkbms = payload.get("parcelDkbms") or []
        new_cbfbm = payload["newCbfbm"]
        new_cbfmc = payload["newCbfmc"]

        # 鑾峰彇鎵€鏈夊綋鍓嶆垚鍛?
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

        # 鍒涘缓鏂版埛
        new_contractor_uid = str(uuid5(NAMESPACE_URL, f"survey:{batch_id}:cbf:{new_cbfbm}"))
        new_result = SurveyCbfResult(
            contractor_uid=new_contractor_uid,
            base_id=0,  # 鏂版埛鏃?base
            cbfbm=new_cbfbm,
            cbflx=result.cbflx,
            cbfmc=new_cbfmc,
            cbfzjlx=result.cbfzjlx,
            cbfzjhm="",  # 鏂版埛鐢辨埛涓昏瘉浠跺彿濉厖
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
            initialized_from_base_id=0,
            initialized_at=now,
            remark=f"鐢?{result.cbfbm} {result.cbfmc} 鍒嗘埛浜х敓",
        )
        db.add(new_result)
        db.flush()

        # 鍒涘缓鏂版埛浠诲姟
        db.add(SurveyContractorTask(
            batch_id=batch_id,
            contractor_uid=new_contractor_uid,
            cbfbm=new_cbfbm,
            cbfmc=new_cbfmc,
            task_status="surveyed",
            has_change=True,
            change_count=1,
            investigated_at=now,
            remark=f"鐢?{result.cbfbm} 鍒嗘埛浜х敓",
        ))

        # 杩佺Щ鎴愬憳
        moved_member_names = []
        for member in move_members:
            moved_member_names.append(member.cyxm)
            member.contractor_uid = new_contractor_uid
            member.cbfbm = new_cbfbm
            member.is_changed = True
        # 鏂版埛鐨勬埛涓昏涓虹涓€涓縼鍏ユ垚鍛?
        if move_members:
            # 鍙栨秷鍘熸埛涓绘爣璁?
            for m in stay_members:
                if m.is_household_head:
                    # 濡傛灉鎴蜂富琚縼鍑猴紝鍦ㄧ暀涓嬬殑鎴愬憳涓€変竴涓涓烘埛涓?
                    pass
            if not any(m.is_household_head for m in stay_members):
                stay_members[0].is_household_head = True
            if not any(m.is_household_head for m in move_members):
                move_members[0].is_household_head = True

        # 杩佺Щ鍦板潡
        moved_parcel_dkbms = []
        for dkbm in parcel_dkbms:
            rel = db.scalars(
                select(SurveyCbdkxxResult).where(
                    SurveyCbdkxxResult.dkbm == dkbm,
                    SurveyCbdkxxResult.cbfbm == result.cbfbm,
                )
            ).first()
            if rel is None:
                continue
            moved_parcel_dkbms.append(dkbm)
            rel.cbfbm = new_cbfbm
            rel.is_changed = True
            rel.change_type = "split_household"
            rel.change_reason = payload.get("reason")

        # 鏇存柊鍘熸埛鎴愬憳鏁伴噺
        result.cbfcysl = len(stay_members)
        result.is_changed = True
        result.change_type = "split_household"
        result.investigated_at = now

        # 鍘熸埛鍙樺寲璁板綍
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
        for m in move_members:
            db.add(SurveyChangeDiff(
                batch_id=batch_id, contractor_uid=contractor_uid, change_id=record.id,
                entity_type="member", entity_uid=m.member_uid, entity_name=m.cyxm,
                field_name="contractor", field_label="鎵€灞炴壙鍖呮柟",
                before_value=result.cbfbm, after_value=new_cbfbm, change_reason=payload.get("reason"),
            ))

        # 鏂版埛鍙樺寲璁板綍
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

        # 鏇存柊鍘熸埛浠诲姟
        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now
            task.cbfmc = result.cbfmc

        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def merge_household(
        self, db: Session, batch_id: int, source_contractor_uid: str,
        payload: dict, current_user: User,
    ) -> dict:
        # repaired docstring
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

        # 鑾峰彇鐩爣鎴?
        target_result = db.scalars(
            select(SurveyCbfResult).where(
                SurveyCbfResult.contractor_uid == target_contractor_uid,
            ).order_by(SurveyCbfResult.id.desc())
        ).first()
        if not target_result:
            raise HTTPException(400, "鐩爣鎵垮寘鏂逛笉瀛樺湪")
        if target_result.survey_status == "confirmed":
            raise HTTPException(400, "鐩爣鎴疯皟鏌ユ垚鏋滃凡纭")

        # 鑾峰彇婧愭埛鍏ㄩ儴鎴愬憳
        source_members = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == source_contractor_uid,
            )
        ).all()
        # 鑾峰彇婧愭埛鍏ㄩ儴鍦板潡鍏宠仈
        source_parcels = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.cbfbm == source_result.cbfbm,
            )
        ).all()

        # 鏀堕泦杩佺Щ鏄庣粏
        moved_member_names = [m.cyxm for m in source_members]
        moved_parcel_dkbms = [p.dkbm for p in source_parcels]

        # 鍒涘缓婧愭埛鍙樺寲璁板綍锛堟敞閿€锛?
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

        # 婧愭埛 diffs
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
                field_name="contractor", field_label="鎵€灞炴壙鍖呮柟",
                before_value=source_result.cbfbm, after_value=target_result.cbfbm, change_reason=payload.get("reason"),
            ))
        for p in source_parcels:
            db.add(SurveyChangeDiff(
                batch_id=batch_id, contractor_uid=source_contractor_uid, change_id=source_record.id,
                entity_type="parcel_relation", entity_uid=p.parcel_info_uid, entity_name=p.dkbm,
                field_name="field", field_label="field",
                before_value=source_result.cbfbm, after_value=target_result.cbfbm, change_reason=payload.get("reason"),
            ))

        # 鍒涘缓鐩爣鎴峰彉鍖栬褰曪紙鎺ユ敹鏂癸級
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

        # 杩佺Щ鎴愬憳锛氭洿鏂?contractor_uid 鍜?cbfbm锛屽彇娑堟埛涓绘爣璁?
        for member in source_members:
            member.contractor_uid = target_contractor_uid
            member.cbfbm = target_result.cbfbm
            member.is_household_head = False  # 杩佸叆鍚庝笉鍐嶆槸鎴蜂富
            member.is_changed = True

        # 杩佺Щ鍦板潡鍏宠仈
        for parcel in source_parcels:
            parcel.cbfbm = target_result.cbfbm
            parcel.is_changed = True
            parcel.change_type = "merge_household"
            parcel.change_reason = payload.get("reason")

        # 鏇存柊鐩爣鎴锋垚鍛樻暟閲?
        target_result.cbfcysl = (target_result.cbfcysl or 0) + len(source_members)
        target_result.is_changed = True
        target_result.change_type = "merge_household"
        target_result.investigated_at = now

        # 鍒犻櫎婧愭埛 result锛堟敞閿€锛?
        db.delete(source_result)

        # 鏇存柊婧愭埛浠诲姟涓哄凡娉ㄩ攢
        source_task = self._get_task(db, batch_id, source_contractor_uid)
        if source_task:
            source_task.task_status = "deregistered"
            source_task.has_change = True
            source_task.change_count = (source_task.change_count or 0) + 1
            source_task.investigated_at = now
            source_task.remark = f"鍚堝叆 {target_result.cbfbm} {target_result.cbfmc}"

        # 鏇存柊鐩爣鎴蜂换鍔?
        target_task = self._get_task(db, batch_id, target_contractor_uid)
        if target_task:
            target_task.has_change = True
            target_task.change_count = (target_task.change_count or 0) + 1
            target_task.investigated_at = now

        db.commit()
        return self.get_result(db, batch_id, target_contractor_uid, current_user)

    def _get_task(self, db: Session, batch_id: int, contractor_uid: str) -> SurveyContractorTask | None:
        return db.scalars(
            select(SurveyContractorTask).where(
                SurveyContractorTask.batch_id == batch_id,
                SurveyContractorTask.contractor_uid == contractor_uid,
            )
        ).first()

    def _next_no(self, db: Session, prefix: str, id_column) -> str:
        next_id = (db.scalar(select(func.max(id_column))) or 0) + 1
        return f"{prefix}{datetime.now():%Y%m%d}{next_id:04d}"


survey_service = SurveyService()
