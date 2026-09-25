import logging
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException, status
from sqlalchemy import String, any_, bindparam, func, or_, select, text
from sqlalchemy.dialects.postgresql import ARRAY
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


def _any_of(column, param_name: str, values):
    """按一组编码过滤，用单个数组参数下发。

    镇/县级批次的承包方数量可达十万级，若直接用 ``column.in_(codes)``，
    PostgreSQL 会因绑定参数超过 65535 上限而报
    "number of parameters must be between 0 and 65535"。
    """
    return column == any_(bindparam(param_name, value=list(values), type_=ARRAY(String)))

class SurveyServiceBatchMixin:
    def _my_batches_condition(self, current_user: User):
        """「与我相关」的批次：我创建的，或批次里有户分派给我。

        调查员登录后要能同时看到这两类批次（自己创建的 + 别人创建但分给自己的），
        而区域数据权限只表达「我管这片区域」，表达不了「这批活是我的」。
        典型错位：运维后来收窄了我的数据权限区域，我创建的批次从列表里消失了，
        但批次管理权仍然在（``_ensure_batch_manager`` 只看 created_by）
        ⇒「接口能操作、列表里却找不到这一批」。

        ⚠️ 这里刻意用原生 SQL，而不是 ORM ``exists(select(SurveyCbfBase...))``：
        会话级的 ``with_loader_criteria``（app/db/session.py）会把当前用户的**区域**
        条件一并注入子查询，「分给我的户」若不在我当前的数据权限区域内就会查不到，
        这条兜底等于失效。用户 id 全局唯一，按 ``assigned_to`` 判定不会跨租户误命中。
        """
        return or_(
            SurveyBatch.created_by == current_user.id,
            text(
                f"""
                EXISTS (
                    SELECT 1 FROM {SurveyCbfBase.__tablename__} AS scb
                    WHERE scb.batch_id = {SurveyBatch.__tablename__}.id
                      AND scb.assigned_to = :my_batch_user_id
                )
                """
            ).bindparams(my_batch_user_id=current_user.id),
        )

    def list_batches(
        self,
        db: Session,
        page: int,
        page_size: int,
        keyword: str | None,
        batch_status: str | None,
        region_code: str | None,
        current_user: User,
        assignee_id: int | None = None,
        mine_only: bool = False,
    ) -> dict:
        normalized_region_code = data_access_service.normalize_region_code(region_code)
        if normalized_region_code:
            data_access_service.ensure_region_filter_in_scope(current_user, normalized_region_code)
        filters = [SurveyBatch.survey_type == "household_survey"]
        scope_filter = data_access_service.build_scoped_filter(SurveyBatch, current_user)
        # 管理员（data_scope=all）本来就看得见全部批次，不需要这层兜底。
        my_filter = None if current_user.role.data_scope == "all" else self._my_batches_condition(current_user)
        if mine_only and my_filter is not None:
            # 调查员主动切到「只看我相关」：只列我创建 / 有户分给我的批次。
            filters.append(my_filter)
        elif scope_filter is not None:
            # 默认口径：**授权区域内的批次 ∪ 与我相关的批次**。
            # 用并集而不是交集，是为了让「我创建 / 分给我的」批次在任何情况下都不会被
            # 区域条件挤掉（口径详见 _my_batches_condition）。
            filters.append(or_(scope_filter, my_filter) if my_filter is not None else scope_filter)
        if normalized_region_code:
            filters.append(SurveyBatch.region_code.like(f"{normalized_region_code}%"))
        if batch_status:
            filters.append(SurveyBatch.status == batch_status)
        if assignee_id:
            # 按调查员筛批次 = 该批次下有任一户分派给了他。
            # 用相关子查询而不是 join：批次与任务是 1:N，join 会把 total 放大成任务数。
            filters.append(
                select(SurveyCbfBase.id)
                .where(
                    SurveyCbfBase.batch_id == SurveyBatch.id,
                    SurveyCbfBase.assigned_to == assignee_id,
                )
                .exists()
            )
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
        # 调查员汇总一次算完，避免每张卡片各查一轮（N+1）。
        assignee_stats = self._load_batch_assignee_stats(
            db, [item.id for item in batches], viewer_id=current_user.id
        )
        return {
            "items": [
                self._serialize_batch(db, item, assignee_stats, current_user=current_user)
                for item in batches
            ],
            "total": db.scalar(total_stmt) or 0,
            "page": page,
            "pageSize": page_size,
        }


    def list_active_regions(self, db: Session, current_user: User) -> list[dict]:
        """进行中的调查批次（含区域码与创建人），供「新建调查批次」把已初始化区域置灰。

        这里**刻意不套用用户区域权限之外的东西**：查询保持默认的租户 + 数据权限过滤，
        与 create_batch 里的冲突校验口径完全一致（同样只看得见自己范围内的批次）。
        否则会出现「树上是可选的、一点就报已存在」的错位。

        创建人只在管理员（data_scope=all）视角返回，普通用户只知道自己范围内
        「该区域已初始化」，看不到是谁做的。
        """
        show_owner = current_user.role.data_scope == "all"
        rows = db.scalars(
            select(SurveyBatch)
            .where(SurveyBatch.survey_type == "household_survey", SurveyBatch.status == "active")
            .order_by(SurveyBatch.id.desc())
        ).all()
        creator_names: dict[int, str] = {}
        if show_owner:
            creator_ids = {item.created_by for item in rows if item.created_by}
            if creator_ids:
                creator_names = {
                    user.id: (user.real_name or user.username)
                    for user in db.scalars(select(User).where(User.id.in_(creator_ids))).all()
                }
        return [
            {
                "id": item.id,
                "batchNo": item.batch_no,
                "batchName": item.batch_name,
                "regionCode": item.region_code,
                "regionName": item.region_name,
                "createdAt": item.created_at,
                "mine": item.created_by == current_user.id,
                "createdByName": creator_names.get(item.created_by) if show_owner else None,
                "createdById": item.created_by if show_owner else None,
            }
            for item in rows
        ]

    def create_batch(self, db: Session, payload: dict, current_user: User) -> dict:
        now = datetime.now(timezone.utc)
        region_code = data_access_service.normalize_region_code(payload.get("regionCode"))
        if not region_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择调查区域")
        data_access_service.ensure_region_in_scope(current_user, region_code)
        tenant_code = data_access_service.get_tenant_code(current_user) or data_access_service.derive_tenant_code(region_code)
        # 检查同区域是否有未结束的调查批次
        active_batch = db.scalars(
            select(SurveyBatch).where(
                SurveyBatch.region_code.like(f"{region_code}%"),
                SurveyBatch.survey_type == "household_survey",
                SurveyBatch.status == "active",
            ).limit(1)
        ).first()
        if active_batch:
            detail = (
                f"该区域已存在进行中的调查批次：{active_batch.batch_no}"
                f"（{active_batch.batch_name or active_batch.region_name or active_batch.region_code}）"
            )
            if self.is_global_admin(current_user) and active_batch.created_by:
                creator = db.get(User, active_batch.created_by)
                if creator is not None:
                    detail += f"，创建人：{creator.real_name or creator.username}"
            detail += "。请先结束该批次，或改选其他区域。"
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
        # 新建即指派：名单先按**角色**分流（非管理员只能派给自己，传别人在这里 403），
        # 再逐条校验（存在 / 在职 / 同区县 / 管辖范围覆盖批次），避免「批次建好了、户也分了，
        # 对方却因管辖范围保存不了」这种静默失败。
        # 必填只对管理员成立，所以不能靠入口 schema 的 min_length —— 见
        # assignment.py::resolve_batch_create_assignees 的说明。
        assignees = self.resolve_batch_assignees(
            db,
            self.resolve_batch_create_assignees(payload.get("assigneeIds"), current_user),
            region_code=region_code,
            tenant_code=tenant_code,
        )
        if not assignees:
            # 兜一层：服务层还能被脚本 / 内部直接调用，漏了这一关就会造出
            # 「每户都没归属人」的批次。
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请先指派调查员：调查批次创建后每个承包户都必须有归属的调查员",
            )
        batch_no = self._next_no(db, "SUR", SurveyBatch.id)
        # 本轮新建的承包方快照，循环结束后统一做轮流分配。
        bases: list[SurveyCbfBase] = []
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该区域暂无可用于初始化的承包方数据")

        for contractor in latest_by_code.values():
            # contractor_uid 沿用源结果行的 uid：调查结果表 survey_cbf_result 是按承包方
            # 全局唯一的一条记录，不随批次复制；整个调查模块都用它读取结果。
            # 批次自己的快照存在 survey_cbf_base，通过 result_id 指回该结果行。
            contractor_uid = contractor.contractor_uid or str(uuid5(NAMESPACE_URL, f"survey:{batch.id}:cbf:{contractor.cbfbm}"))
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
            bases.append(base)
            db.add(base)
            db.flush()
            members = db.scalars(
                select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.tenant_code == contractor.tenant_code,
                    SurveyCbfJtcyResult.cbfbm == contractor.cbfbm,
                )
                .execution_options(skip_tenant_scope=True)
            ).all()
            for member in members:
                member_uid = member.member_uid or str(uuid5(NAMESPACE_URL, f"survey:{batch.id}:member:{contractor.cbfbm}:{member.cyzjhm}"))
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

        # 新建即指派：把本批次全部户按承包方编码顺序轮流均分给指定调查员。
        self.assign_round_robin(bases, assignees, now)
        unassigned = [item for item in bases if item.assigned_to is None]
        if unassigned:
            # 理论上不会发生（assign_round_robin 覆盖全部 bases）。真发生了宁可整批不落库，
            # 也不要留下「批次建好了、一部分户却没人负责」的半成品。
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"有 {len(unassigned)} 户未能分配调查员，批次未创建，请重试",
            )
        self._initialize_related_survey_data(db, batch, list(latest_by_code.values()), now)
        db.commit()
        db.refresh(batch)
        return self._serialize_batch(db, batch, current_user=current_user)


    def finish_batch(self, db: Session, batch_id: int, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        # 原先只靠路由层的 contractors.manage 兜底，任何有该权限的人都能结束
        # 别人创建的批次；这里收口到「批次创建人（或全量数据权限角色）」。
        # ⚠️ 结束批次**刻意不跟着分配权一起放宽**（分配见 `_ensure_batch_assigner`）：
        # 分配是日常派活、属地人员就该能做；结束是全批次锁死的制度性动作。
        self._ensure_batch_manager(batch, current_user)
        if batch.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该调查批次已结束")
        unfinished = db.scalar(
            select(func.count(SurveyCbfBase.id)).where(
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.task_status.notin_(["confirmed", "skipped"]),
            )
        ) or 0
        if unfinished:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"还有 {unfinished} 户调查任务未完成，不能结束批次")
        skipped_without_reason = db.scalar(
            select(func.count(SurveyCbfBase.id)).where(
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.task_status == "skipped",
                or_(SurveyCbfBase.skip_reason.is_(None), SurveyCbfBase.skip_reason == ""),
            )
        ) or 0
        if skipped_without_reason:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"还差 {skipped_without_reason} 户跳过原因为空，不能结束批次")
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"还差 {missing_change_trace} 户有变化但缺少变化记录，不能结束批次")
        batch.status = "finished"
        batch.ended_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(batch)
        return self._serialize_batch(db, batch, current_user=current_user)


    def _batch_assignee_names(self, db: Session, user_ids: set[int]) -> dict[int, str]:
        """用户 id → 展示名。归属人改名后批次列表要跟着变，所以按 id 现查，
        只在用户已被删除时才退回 ``assigned_to_name`` 里冻结的快照。"""
        if not user_ids:
            return {}
        return {
            item.id: (item.real_name or item.username)
            for item in db.scalars(select(User).where(User.id.in_(user_ids))).all()
        }

    def _load_batch_assignee_stats(
        self, db: Session, batch_ids: list[int], viewer_id: int | None = None
    ) -> dict[int, dict]:
        """批量汇总各批次的调查员：``{batch_id: {"names": [...], "count": n, "unassigned": m, "mineCount": k}}``。

        批次本身不存调查员字段，这里按任务归属（``survey_cbf_base.assigned_to``）现算，
        避免「批次上的调查员」与「任务实际分给了谁」两处真相。
        两个聚合查询覆盖整页批次，不做 N+1。

        ``viewer_id`` 是当前登录人：顺带统计他名下的户数，卡片据此标「分给我 N 户」。
        """
        stats: dict[int, dict] = {
            batch_id: {"names": [], "count": 0, "unassigned": 0, "mineCount": 0}
            for batch_id in batch_ids
        }
        if not batch_ids:
            return stats
        totals = db.execute(
            select(
                SurveyCbfBase.batch_id,
                func.count(SurveyCbfBase.id),
                func.count(SurveyCbfBase.assigned_to),
            )
            .where(SurveyCbfBase.batch_id.in_(batch_ids))
            .group_by(SurveyCbfBase.batch_id)
            .execution_options(skip_tenant_scope=True)
        ).all()
        for batch_id, total, assigned in totals:
            bucket = stats.setdefault(batch_id, {"names": [], "count": 0, "unassigned": 0, "mineCount": 0})
            bucket["unassigned"] = int(total or 0) - int(assigned or 0)
        rows = db.execute(
            select(
                SurveyCbfBase.batch_id,
                SurveyCbfBase.assigned_to,
                func.max(SurveyCbfBase.assigned_to_name),
                func.count(SurveyCbfBase.id),
            )
            .where(SurveyCbfBase.batch_id.in_(batch_ids), SurveyCbfBase.assigned_to.is_not(None))
            .group_by(SurveyCbfBase.batch_id, SurveyCbfBase.assigned_to)
            # 名下户数多的排前面，卡片上先显示主力调查员。
            .order_by(SurveyCbfBase.batch_id.asc(), func.count(SurveyCbfBase.id).desc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        name_map = self._batch_assignee_names(db, {row[1] for row in rows if row[1]})
        for batch_id, user_id, snapshot, count in rows:
            bucket = stats.setdefault(batch_id, {"names": [], "count": 0, "unassigned": 0, "mineCount": 0})
            bucket["count"] += 1
            bucket["names"].append(name_map.get(user_id) or snapshot or f"用户 {user_id}")
            if viewer_id is not None and user_id == viewer_id:
                bucket["mineCount"] += int(count or 0)
        return stats

    def _serialize_batch(
        self,
        db: Session,
        item: SurveyBatch,
        assignee_stats: dict[int, dict] | None = None,
        scope_filters: list | None = None,
        current_user: User | None = None,
    ) -> dict:
        result_filters = [SurveyCbfBase.tenant_code == item.tenant_code, SurveyCbfBase.batch_id == item.id]
        if item.region_code:
            self._append_group_region_filter(result_filters, SurveyCbfBase.group_region_code, item.region_code)
        task_count = db.scalar(
            select(func.count(func.distinct(SurveyCbfBase.cbfbm))).where(*result_filters).execution_options(skip_tenant_scope=True)
        ) or 0
        task_filters = [SurveyCbfBase.tenant_code == item.tenant_code, SurveyCbfBase.batch_id == item.id]
        # 任务状态字段已合并到 survey_cbf_base，每户一行，按状态直接统计。
        # （原写法 task_count - count(*) 在"每户一行"后恒为 0。）
        not_started_count = db.scalar(
            select(func.count(SurveyCbfBase.id))
            .where(*task_filters, SurveyCbfBase.task_status == "not_started")
            .execution_options(skip_tenant_scope=True)
        ) or 0
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
        stats = (assignee_stats or {}).get(item.id)
        if stats is None:
            # 单条场景（新建 / 结束批次）：只算这一条，省掉整页预取。
            stats = self._load_batch_assignee_stats(
                db, [item.id], viewer_id=current_user.id if current_user else None
            ).get(item.id) or {
                "names": [],
                "count": 0,
                "unassigned": 0,
                "mineCount": 0,
            }
        my_task_count = int(stats.get("mineCount") or 0)
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
            "assigneeNames": stats["names"],
            "assigneeCount": stats["count"],
            "unassignedCount": stats["unassigned"],
            # 「与我相关」：我创建 / 有户分给我。调查员登录后据此在列表里认出自己的批次。
            "createdByMe": bool(current_user and item.created_by == current_user.id),
            "assignedToMe": my_task_count > 0,
            "myTaskCount": my_task_count,
        }


    def _initialize_related_survey_data(self, db: Session, batch: SurveyBatch, contractors: list[SurveyCbfResult], now: datetime) -> None:
        cbfbms = {item.cbfbm for item in contractors if item.cbfbm}
        if not cbfbms:
            return
        cbdkxx_results = db.scalars(
            select(SurveyCbdkxxResult)
            .where(
                SurveyCbdkxxResult.tenant_code == batch.tenant_code,
                _any_of(SurveyCbdkxxResult.cbfbm, "batch_cbfbm_scope", cbfbms),
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
            .where(SurveyFbfResult.tenant_code == tenant_code, _any_of(SurveyFbfResult.fbfbm, "batch_fbfbm_scope", fbfbms))
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
            result_id=item.id,
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
            result_id=item.id,
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
            result_id=item.id,
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

