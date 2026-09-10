import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, object_session

from app.models.survey import (
    SurveyBatch,
    SurveyCbfBase,
    SurveyCbfResult,
    SurveyChangeDiff,
    SurveyChangeRecord,
)
from app.models.user import User
from app.services.data_access_service import data_access_service

logger = logging.getLogger(__name__)

class SurveyServiceTaskMixin:
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
        else:
            filters.append(SurveyCbfBase.task_status != "deregistered")

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


    def list_deregistered_contractors(
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
        normalized_region_code = data_access_service.normalize_region_code(region_code)
        effective_region_code = normalized_region_code or data_access_service.normalize_region_code(batch.region_code)
        if normalized_region_code:
            data_access_service.ensure_region_in_scope(current_user, normalized_region_code)

        filters = self._tenant_filters(SurveyCbfBase, current_user)
        filters.append(SurveyCbfBase.batch_id == batch_id)
        filters.append(SurveyCbfBase.task_status == "deregistered")
        filters.extend(data_access_service.build_code_scope_filters(SurveyCbfBase.cbfbm, current_user))
        if effective_region_code:
            filters.append(SurveyCbfBase.cbfbm.like(f"{effective_region_code}%"))

        rows = db.scalars(
            select(SurveyCbfBase)
            .where(*filters)
            .order_by(SurveyCbfBase.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        latest_tasks: dict[str, SurveyCbfBase] = {}
        for item in rows:
            latest_tasks.setdefault(item.contractor_uid, item)

        contractor_uids = list(latest_tasks)
        change_rows = db.scalars(
            select(SurveyChangeRecord)
            .where(
                SurveyChangeRecord.tenant_code == batch.tenant_code,
                SurveyChangeRecord.batch_id == batch_id,
                SurveyChangeRecord.contractor_uid.in_(contractor_uids or [""]),
                SurveyChangeRecord.change_type == "deregister",
                SurveyChangeRecord.change_status != "rolled_back",
            )
            .order_by(SurveyChangeRecord.contractor_uid.asc(), SurveyChangeRecord.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).all() if contractor_uids else []
        active_deregister_changes: dict[str, SurveyChangeRecord] = {}
        for item in change_rows:
            active_deregister_changes.setdefault(item.contractor_uid, item)

        result_map = self._latest_results_by_code(
            db,
            batch.tenant_code,
            {item.cbfbm for item in latest_tasks.values()},
        )

        items = []
        search_text = (keyword or "").strip().lower()
        for contractor_uid, task in latest_tasks.items():
            result = result_map.get(task.cbfbm)
            change = active_deregister_changes.get(contractor_uid)
            row = self._serialize_deregistered_task(
                task,
                batch_id,
                result,
                change,
                can_rollback=batch.status != "finished",
            )
            if search_text:
                haystacks = [
                    row["cbfbm"],
                    row["cbfmc"],
                    row["cbfdz"],
                    row["lxdh"],
                    row["groupRegionName"],
                    row["deregisterReason"],
                ]
                if not any(search_text in str(value or "").lower() for value in haystacks):
                    continue
            items.append(row)

        items.sort(
            key=lambda item: (
                item.get("deregisteredAt") or datetime.min.replace(tzinfo=timezone.utc),
                item["cbfbm"],
            ),
            reverse=True,
        )
        total = len(items)
        page_items = items[(page - 1) * page_size : page * page_size]
        return {"items": page_items, "total": total, "page": page, "pageSize": page_size}


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
        else:
            rows = [item for item in rows if item["taskStatus"] != "deregistered"]
        total = len(rows)
        rows = rows[(page - 1) * page_size : page * page_size]
        return {"items": rows, "total": total, "page": page, "pageSize": page_size}


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
            "cbfdz": item.cbfdz,
            "cbfcysl": item.cbfcysl,
            "lxdh": item.lxdh,
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
            "cbfdz": result.cbfdz,
            "cbfcysl": result.cbfcysl,
            "lxdh": result.lxdh,
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
            "cbfdz": task.cbfdz if task else base.cbfdz,
            "cbfcysl": task.cbfcysl if task else base.cbfcysl,
            "lxdh": task.lxdh if task else base.lxdh,
            "regionCode": task.region_code if task else base.region_code,
            "groupRegionCode": (result.group_region_code if result else None) or base.cbfbm[:14],
            "groupRegionName": result.group_region_name if result else None,
            "taskStatus": task.task_status if task else result_task_status,
            "hasChange": task.has_change if task else bool(result and result.is_changed),
            "changeCount": task.change_count if task else 0,
            "investigatedAt": task.investigated_at if task else (result.investigated_at if result else None),
            "remark": task.remark if task else (result.remark if result else None),
        }


    def _serialize_deregistered_task(
        self,
        task: SurveyCbfBase,
        survey_batch_id: int,
        result: SurveyCbfResult | None,
        change: SurveyChangeRecord | None,
        *,
        can_rollback: bool,
    ) -> dict:
        return {
            "id": task.id,
            "batchId": survey_batch_id,
            "contractorUid": task.contractor_uid,
            "cbfbm": task.cbfbm,
            "cbfmc": task.cbfmc,
            "cbfdz": task.cbfdz,
            "cbfcysl": task.cbfcysl,
            "lxdh": task.lxdh,
            "groupRegionCode": (result.group_region_code if result else None) or task.cbfbm[:14],
            "groupRegionName": result.group_region_name if result else None,
            "deregisterReason": (change.change_reason if change else None) or (result.change_reason if result else None) or task.remark,
            "deregisteredAt": (change.investigated_at if change else None) or task.investigated_at,
            "changeNo": change.change_no if change else None,
            "canRollback": can_rollback,
        }
