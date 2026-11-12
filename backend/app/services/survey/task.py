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
    SurveyFbfBase,
    SurveyFbfResult,
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
        mine: bool = False,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        normalized_region_code = data_access_service.normalize_region_code(region_code)
        effective_region_code = normalized_region_code or data_access_service.normalize_region_code(batch.region_code)
        if normalized_region_code:
            data_access_service.ensure_region_filter_in_scope(current_user, normalized_region_code)
        filters = self._tenant_filters(SurveyCbfBase, current_user)
        filters.append(SurveyCbfBase.batch_id == batch_id)
        filters.extend(data_access_service.build_code_scope_filters(SurveyCbfBase.cbfbm, current_user))
        if effective_region_code:
            filters.append(SurveyCbfBase.cbfbm.like(f"{effective_region_code}%"))
        if keyword:
            pattern = f"%{keyword.strip()}%"
            # base 保持"批次基线"，改名/改码后它仍是旧值 —— 只按 base 搜会让
            # 用户按新名搜不到自己的户。因此 result（当前值）侧命中的也要算。
            # ⛔ 先取成 Python 列表再 in_()，不要写成 in_(select(...)) 子查询：
            # 全局 with_loader_criteria（区域/租户 scope）会二次注入到子查询里，
            # 命中集合会被静默缩小。见 skill sqlalchemy-loader-criteria-subquery。
            matched_uids = db.scalars(
                select(SurveyCbfResult.contractor_uid)
                .where(
                    SurveyCbfResult.tenant_code == batch.tenant_code,
                    or_(
                        SurveyCbfResult.cbfbm.ilike(pattern),
                        SurveyCbfResult.cbfmc.ilike(pattern),
                        SurveyCbfResult.group_region_name.ilike(pattern),
                    ),
                )
                .execution_options(skip_tenant_scope=True)
            ).all()
            # 发包方名称/编码命中 → 该发包方下所有承包方都算命中。
            # 先取批次内快照；快照缺失时用主表结果兜底（只导入过承包方的批次）。
            issuer_codes = set(
                db.scalars(
                    select(SurveyFbfBase.fbfbm)
                    .where(
                        SurveyFbfBase.batch_id == batch_id,
                        or_(
                            SurveyFbfBase.fbfbm.ilike(pattern),
                            SurveyFbfBase.fbfmc.ilike(pattern),
                        ),
                    )
                    .execution_options(skip_tenant_scope=True)
                ).all()
            )
            issuer_codes.update(
                db.scalars(
                    select(SurveyFbfResult.fbfbm)
                    .where(
                        SurveyFbfResult.tenant_code == batch.tenant_code,
                        or_(
                            SurveyFbfResult.fbfbm.ilike(pattern),
                            SurveyFbfResult.fbfmc.ilike(pattern),
                        ),
                    )
                    .execution_options(skip_tenant_scope=True)
                ).all()
            )
            conditions = [
                SurveyCbfBase.cbfbm.ilike(pattern),
                SurveyCbfBase.cbfmc.ilike(pattern),
                SurveyCbfBase.group_region_name.ilike(pattern),
                SurveyCbfBase.contractor_uid.in_(matched_uids or [""]),
            ]
            if issuer_codes:
                conditions.append(
                    or_(*[
                        SurveyCbfBase.cbfbm.like(f"{code}%")
                        for code in sorted(code for code in issuer_codes if code)
                    ])
                )
            filters.append(or_(*conditions))
        if task_status:
            filters.append(SurveyCbfBase.task_status == task_status)
        else:
            filters.append(SurveyCbfBase.task_status != "deregistered")
        if mine:
            # 串户调查场景：外业调查员只看自己名下的户。
            filters.append(SurveyCbfBase.assigned_to == current_user.id)

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
            "Survey task query params: batch_id=%s requested_region=%s effective_region=%s page=%s page_size=%s keyword=%s task_status=%s mine=%s",
            batch.id,
            normalized_region_code,
            effective_region_code,
            page,
            page_size,
            keyword,
            task_status,
            mine,
        )
        self._log_sql(db, "survey_tasks.count", task_count_stmt)
        self._log_sql(db, "survey_tasks.list", task_list_stmt)
        total = db.scalar(task_count_stmt) or 0
        tasks = db.scalars(task_list_stmt).all()
        # 「能否录入」对整个请求只算一次。⛔ 批次级豁免**只有管理员**：
        # 2026-09-24 起创建人不再豁免（他往往就是本批次调查员，若也豁免则
        # 「分配」对他失效），所以创建人也逐行比 assigned_to。
        privileged = self.is_task_write_privileged(current_user)
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
                mine,
                privileged=privileged,
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
        rows = [
            self._serialize_task(item, can_write=self.task_row_can_write(item, privileged, current_user))
            for item in tasks
        ]
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
            data_access_service.ensure_region_filter_in_scope(current_user, normalized_region_code)

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
        # 「让户离开待办」的终态操作有**三种**：注销 / 合户 / 分户。
        # 这里必须一次取全，且与 `terminal_operation_types` 同源 —— 列表上的「撤回」
        # 按钮要按 changeType 分流到各自的撤回接口。只认 deregister 会让合户/分户的户
        # 渲染出一个**必然 400** 的按钮：列表的 canRollback 判据与撤回接口的判据不同源
        # （2026-09-25 修，实证见 scripts/_verify_survey_merge_rollback.py）。
        change_rows = db.scalars(
            select(SurveyChangeRecord)
            .where(
                SurveyChangeRecord.tenant_code == batch.tenant_code,
                SurveyChangeRecord.batch_id == batch_id,
                SurveyChangeRecord.contractor_uid.in_(contractor_uids or [""]),
                SurveyChangeRecord.change_type.in_(sorted(self.terminal_operation_types)),
                SurveyChangeRecord.change_status != "rolled_back",
            )
            .order_by(SurveyChangeRecord.contractor_uid.asc(), SurveyChangeRecord.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).all() if contractor_uids else []
        active_terminal_changes: dict[str, SurveyChangeRecord] = {}
        for item in change_rows:
            # 合户/分户还会给"新户"写一条同类型记录（after_summary.action = created*）。
            # 那条不属于"退出待办的原户"，挂上来会让新户冒充可撤回项。
            if item.change_type != "deregister":
                action = (item.after_summary or {}).get("action")
                if action not in self.terminal_source_actions:
                    continue
            active_terminal_changes.setdefault(item.contractor_uid, item)

        result_map = self._latest_results_by_code(
            db,
            batch.tenant_code,
            {item.cbfbm for item in latest_tasks.values()},
        )

        items = []
        search_text = (keyword or "").strip().lower()
        for contractor_uid, task in latest_tasks.items():
            result = result_map.get(task.cbfbm)
            change = active_terminal_changes.get(contractor_uid)
            # ⛔ 判据必须**与撤回接口同源**：接口能不能撤回，取决于"取不取得到那条未撤回的
            # 终态变更记录"（rollback_deregistered_contractor / rollback_split_household /
            # rollback_merge_household 三个接口开头都在查它）。所以这里不能只看 batch.status，
            # 那样会渲染出一个**必然 400** 的按钮 —— 历史事故（2026-09-25 修）。
            row = self._serialize_deregistered_task(
                task,
                batch_id,
                result,
                change,
                can_rollback=batch.status != "finished" and change is not None,
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
        mine: bool = False,
        privileged: bool = False,
    ) -> dict:
        base_filters = self._tenant_filters(SurveyCbfBase, current_user)
        base_filters.append(SurveyCbfBase.batch_id == batch.id)
        base_filters.extend(data_access_service.build_code_scope_filters(SurveyCbfBase.cbfbm, current_user))
        if effective_region_code:
            base_filters.append(SurveyCbfBase.cbfbm.like(f"{effective_region_code}%"))
        if keyword:
            pattern = f"%{keyword.strip()}%"
            base_filters.append(or_(SurveyCbfBase.cbfbm.ilike(pattern), SurveyCbfBase.cbfmc.ilike(pattern)))
        if mine:
            base_filters.append(SurveyCbfBase.assigned_to == current_user.id)

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
            self._serialize_base_task(
                item,
                batch.id,
                task_overlays.get(item.cbfbm),
                result_overlays.get(item.cbfbm),
                can_write=self.task_row_can_write(task_overlays.get(item.cbfbm), privileged, current_user),
            )
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
        self._ensure_batch_editable_status(batch, action="继续操作")
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        # 跳过同样改变成果状态，按任务归属判定，口径与 update_result 一致。
        self.ensure_task_write_permission(db, batch, result, current_user)
        if result.survey_status in self.locked_survey_statuses:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调查成果已确认，不能跳过")
        if bool(getattr(result, "is_locked", False)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="承包方已锁定，不能跳过")
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
            # 补建任务行：默认归到操作人名下（他是本批次调查员时），否则留空，
            # 避免批次里的户停在「未分配」。
            assignee = self.default_new_task_assignee(db, batch, current_user)
            task = SurveyCbfBase(
                tenant_code=result.tenant_code,
                region_code=result.group_region_code or result.region_code,
                batch_id=batch_id,
                contractor_uid=contractor_uid,
                cbfbm=result.cbfbm,
                cbfmc=result.cbfmc,
                assigned_to=assignee.id if assignee else None,
                assigned_to_name=assignee.real_name if assignee else None,
                assigned_at=now if assignee else None,
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
        # 走到这里说明归属校验已经过了（ensure_task_write_permission 在上面），
        # 返回给前端的行必须标成可写，否则刚跳过的户立刻变只读。
        return self._serialize_task(task, can_write=True) if task else {}


    def confirm_result(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        self._ensure_batch_editable_status(batch, action="继续确认")
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        if bool(getattr(result, "is_locked", False)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="承包方已锁定，不能确认")
        # 注意：确认是「复核」动作，语义上不属于「修改调查数据」，
        # 因此这里刻意不做任务归属校验——区域审核人仍可确认归属他人的户。
        # ⛔ 准入集合的唯一来源：`base.py::confirmable_survey_statuses`。
        # 前端列表 / 弹窗的「确认」按钮显示条件必须与之完全一致，改这里要改那里。
        if result.survey_status not in self.confirmable_survey_statuses:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先保存调查结果后再确认")
        # 变化原因不再是硬闸门：为空的行先按变更类型写系统默认值（人工填过的不动），
        # 再走其余校验（户主、证件号重复等）。见 base.py 的 `_ensure_change_reasons`。
        filled_reasons = self._ensure_change_reasons(db, result)
        if filled_reasons:
            logger.info(
                "确认 %s：自动补齐变化原因 %d 项（%s）",
                result.cbfbm,
                len(filled_reasons),
                "；".join(filled_reasons),
            )
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
            # 补建任务行：默认归到操作人名下（他是本批次调查员时），否则留空，
            # 避免批次里的户停在「未分配」。
            assignee = self.default_new_task_assignee(db, batch, current_user)
            task = SurveyCbfBase(
                tenant_code=result.tenant_code,
                region_code=result.group_region_code or result.region_code,
                batch_id=batch_id,
                contractor_uid=contractor_uid,
                cbfbm=result.cbfbm,
                cbfmc=result.cbfmc,
                assigned_to=assignee.id if assignee else None,
                assigned_to_name=assignee.real_name if assignee else None,
                assigned_at=now if assignee else None,
            )
            db.add(task)
        if task:
            task.task_status = "confirmed"
            # ⛔ 不要在这里写 task.confirmed_at：任务表(SurveyCbfBase)没有该列，
            #    赋值只会成为 Python 属性、从不落库（曾误导 exports.py 误用）。
            #    确认时间唯一落点在 result 表（上方 result.confirmed_at = now）。
            task.reviewed_at = now
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def unconfirm_result(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> dict:
        """撤回已确认的调查成果，使其回到可编辑状态。

        由端点层的 ``require_permission("survey_result.unconfirm")`` 保护，
        这里只做业务校验与状态回退。**仅当当前为 confirmed 才允许**。

        回退到 ``surveyed``（可编辑态之一），并清掉确认时写入的
        ``reviewer_id / reviewer_name / reviewed_at / confirmed_at / change_reason``；
        ``survey_cbf_base.task_status`` 同步由 ``confirmed`` 退回 ``surveyed`` 并清 ``reviewed_at``。

        ⛔ 只动状态，不撤销确认时可能已发生的业务动作（互换 / 合户 / 分户 / 变更登记等）。
           若误确认还连带触发了别的业务，撤回后需用界面对应的「撤回」功能另行处理。
        ⛔ 与 ``confirm_result`` 同款前置：批次须为 active（编辑闸门），且必须在当前用户
           区域 scope 内（复核类动作不做任务归属校验，但跨区越权仍拦）。
        """
        batch = self._ensure_batch(db, batch_id)
        self._ensure_batch_editable_status(batch, action="撤回确认")
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        if result.survey_status != "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="本户调查成果尚未确认，无需撤回")
        now = datetime.now(timezone.utc)
        result.survey_status = "surveyed"
        result.reviewer_id = None
        result.reviewer_name = None
        result.reviewed_at = None
        result.confirmed_at = None
        result.change_reason = None
        result.updated_at = now
        task = db.scalars(
            select(SurveyCbfBase).where(
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.contractor_uid == contractor_uid,
            )
        ).first()
        if task:
            task.task_status = "surveyed"
            task.reviewed_at = None
            task.updated_at = now
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


    def _serialize_task(self, item: SurveyCbfBase, *, can_write: bool = False) -> dict:
        result = None
        session = object_session(item)
        if session and item.contractor_uid:
            result = session.scalar(
                select(SurveyCbfResult).where(SurveyCbfResult.contractor_uid == item.contractor_uid).order_by(SurveyCbfResult.id.desc())
            )
        # 当前值以 result 为准、base 仅作兜底：base 是批次基线快照，录入改名/改码/
        # 改地址后它保持原值。列表若继续读 base，就会和调查录入详情（读 result）
        # 显示成两个不同的地址。
        current = result if result is not None else item
        return {
            "id": item.id,
            "batchId": item.batch_id,
            "contractorUid": item.contractor_uid,
            "cbfbm": current.cbfbm or item.cbfbm,
            "cbfmc": current.cbfmc or item.cbfmc,
            "cbfdz": current.cbfdz,
            "cbfcysl": current.cbfcysl,
            "lxdh": current.lxdh,
            "regionCode": item.region_code,
            "groupRegionCode": (result.group_region_code if result else None) or item.cbfbm[:14],
            "groupRegionName": result.group_region_name if result else None,
            "taskStatus": item.task_status,
            "hasChange": item.has_change,
            "changeCount": item.change_count,
            "investigatedAt": item.investigated_at,
            "remark": item.remark,
            "assignedTo": item.assigned_to,
            "assignedToName": item.assigned_to_name,
            "assignedAt": item.assigned_at,
            "investigatorName": result.investigator_name if result else None,
            "isLocked": bool(result.is_locked) if result is not None else False,
            "canWrite": can_write and not (bool(result.is_locked) if result is not None else False),
        }


    def _serialize_result_task(
        self,
        result: SurveyCbfResult,
        survey_batch_id: int,
        task: SurveyCbfBase | None = None,
        *,
        can_write: bool = False,
    ) -> dict:
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
            # 与 _serialize_task / _serialize_base_task 保持一致：新增承包方的接口返回值
            # 也要带上归属人，否则前端拿到响应直接插进列表就会显示「未分配」
            # （库里有值、响应里没有 ⇒ 又是「调查员列空了」那类误报）。
            "assignedTo": task.assigned_to if task else None,
            "assignedToName": task.assigned_to_name if task else None,
            "assignedAt": task.assigned_at if task else None,
            "investigatorName": result.investigator_name,
            "isLocked": bool(result.is_locked),
            "canWrite": can_write and not bool(result.is_locked),
        }


    def _serialize_base_task(
        self,
        base: SurveyCbfBase,
        survey_batch_id: int,
        task: SurveyCbfBase | None = None,
        result: SurveyCbfResult | None = None,
        *,
        can_write: bool = False,
    ) -> dict:
        result_task_status = "not_started"
        if result is not None and result.survey_status:
            result_task_status = "not_started" if result.survey_status == "not_surveyed" else result.survey_status
        current = result if result is not None else (task if task is not None else base)
        return {
            "id": task.id if task else base.id,
            "batchId": survey_batch_id,
            "contractorUid": task.contractor_uid if task else base.contractor_uid,
            "cbfbm": current.cbfbm,
            "cbfmc": current.cbfmc,
            "cbfdz": current.cbfdz,
            "cbfcysl": current.cbfcysl,
            "lxdh": current.lxdh,
            "regionCode": task.region_code if task else base.region_code,
            "groupRegionCode": (result.group_region_code if result else None) or base.cbfbm[:14],
            "groupRegionName": result.group_region_name if result else None,
            "taskStatus": task.task_status if task else result_task_status,
            "hasChange": task.has_change if task else bool(result and result.is_changed),
            "changeCount": task.change_count if task else 0,
            "investigatedAt": task.investigated_at if task else (result.investigated_at if result else None),
            "remark": task.remark if task else (result.remark if result else None),
            "assignedTo": task.assigned_to if task else None,
            "assignedToName": task.assigned_to_name if task else None,
            "assignedAt": task.assigned_at if task else None,
            "investigatorName": result.investigator_name if result else None,
            "isLocked": bool(result.is_locked) if result is not None else False,
            "canWrite": can_write and not (bool(result.is_locked) if result is not None else False),
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
        """已注销列表的一行。

        ``change`` 是**让该户离开待办的终态变更记录**（`deregister` / `merge_household` /
        `split_household` 三选一，由调用方按 `terminal_operation_types` 取活跃行）。

        必须把 ``changeType`` 透出去 —— 前端据此把「撤回」按钮分流到对应的撤回接口。
        ``changeNo`` 为空即表示"按钮挂不上台账"，历史上（只认 deregister 时）正是这种情况
        渲染出了一个**必然 400** 的按钮。
        """
        current = result if result is not None else task
        return {
            "id": task.id,
            "batchId": survey_batch_id,
            "contractorUid": task.contractor_uid,
            "cbfbm": current.cbfbm,
            "cbfmc": current.cbfmc,
            "cbfdz": current.cbfdz,
            "cbfcysl": current.cbfcysl,
            "lxdh": current.lxdh,
            "groupRegionCode": (result.group_region_code if result else None) or task.cbfbm[:14],
            "groupRegionName": result.group_region_name if result else None,
            "deregisterReason": (change.change_reason if change else None) or (result.change_reason if result else None) or task.remark,
            "deregisteredAt": (change.investigated_at if change else None) or task.investigated_at,
            "changeNo": change.change_no if change else None,
            "changeType": change.change_type if change else None,
            "canRollback": can_rollback,
        }
