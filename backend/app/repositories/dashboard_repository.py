import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.fbf import Fbf
from app.models.region import Region
from app.models.request_case import RequestCase
from app.models.survey import (
    SurveyAttachment,
    SurveyBatch,
    SurveyCbdkxxBase,
    SurveyCbdkxxResult,
    SurveyCbfBase,
    SurveyCbfJtcyBase,
    SurveyCbfResult,
    SurveyChangeRecord,
    SurveyFbfBase,
)
from app.models.user import User
from app.services.data_access_service import data_access_service

logger = logging.getLogger(__name__)

#: 「已调查」口径：与 `services/survey/batch.py::_serialize_batch` 保持同源。
#: changed / unchanged 是调查完成后的两种结论，confirmed 是复核通过，都属于"调查已落地"。
SURVEYED_TASK_STATUSES = ("surveyed", "changed", "unchanged", "confirmed")

#: 任务状态展示顺序与配色（tone 由前端映射成具体色值）。
TASK_STATUS_META = [
    ("not_started", "未调查", "slate"),
    ("surveyed", "已调查", "blue"),
    ("changed", "有变更", "orange"),
    ("unchanged", "无变化", "green"),
    ("confirmed", "已确认", "teal"),
    ("skipped", "已跳过", "purple"),
    ("deregistered", "已注销", "gray"),
]
_TASK_STATUS_LABELS = {key: (label, tone) for key, label, tone in TASK_STATUS_META}

#: 变更类型中文名，取自 `services/survey/*` 里写入 `survey_change_records.change_type` 的字面量。
CHANGE_TYPE_LABELS = {
    "info_change": "信息变更",
    "change_head": "户主变更",
    "member_maintain": "成员维护",
    "deregister": "承包方注销",
    "split_household": "分户",
    "merge_household": "合户",
    "add_parcel": "新增地块",
    "split_parcel": "切割地块",
    "remove_parcel": "移除地块",
    "swap_parcels": "地块互换",
}
_ROLLBACK_LABEL = "回退操作"

MU_PER_SQUARE_METER = 666.67

REGION_LEVEL_META = {
    "town": ("镇级", 9),
    "village": ("村级", 12),
}


def _rate(part: int, total: int) -> float:
    if not total:
        return 0.0
    return round(part / total * 100, 1)


class DashboardRepository:
    def get_summary(self, db: Session, current_user: User) -> dict:
        user_count_stmt = select(func.count(User.id)).join(Region, Region.id == User.region_id)
        issuer_count_stmt = select(func.count(Fbf.fbfbm))
        request_count_stmt = select(func.count(RequestCase.id))
        todo_count_stmt = select(func.count(RequestCase.id)).where(RequestCase.status != "已办结")

        if current_user.role.data_scope != "all":
            # ⛔ 原实现调用 `data_access_service.get_region_scope_prefix()` —— 该方法不存在，
            # 非管理员访问 `/dashboard/summary` 直接 500（管理员走 data_scope == "all" 分支，
            # 永远碰不到这行，所以一直没暴露）。改为与其它模块一致的授权前缀过滤：
            # 无任何区域授权时 `build_code_scope_filters` 返回 [false()]，结果自然是 0 而不是报错。
            user_count_stmt = user_count_stmt.where(
                *data_access_service.build_code_scope_filters(Region.code, current_user)
            )
            issuer_count_stmt = issuer_count_stmt.where(
                *data_access_service.build_code_scope_filters(Fbf.fbfbm, current_user)
            )
            request_filters = data_access_service.build_request_case_filters(current_user)
            request_count_stmt = request_count_stmt.where(*request_filters)
            todo_count_stmt = todo_count_stmt.where(*request_filters)

        return {
            "userCount": db.scalar(user_count_stmt) or 0,
            "issuerCount": db.scalar(issuer_count_stmt) or 0,
            "requestCount": db.scalar(request_count_stmt) or 0,
            "todoCount": db.scalar(todo_count_stmt) or 0,
        }

    # ------------------------------------------------------------------ 大屏

    def list_bigscreen_batches(self, db: Session, current_user: User, limit: int = 30) -> list[SurveyBatch]:
        """大屏批次下拉的候选项（管理员=全部，其余按数据权限过滤）。"""
        stmt = select(SurveyBatch).where(SurveyBatch.survey_type == "household_survey")
        scope_filter = data_access_service.build_scoped_filter(SurveyBatch, current_user)
        if scope_filter is not None:
            stmt = stmt.where(scope_filter)
        return list(db.scalars(stmt.order_by(SurveyBatch.id.desc()).limit(limit)).all())

    def resolve_bigscreen_batch(self, db: Session, current_user: User, batch_id: int | None) -> SurveyBatch | None:
        batches = self.list_bigscreen_batches(db, current_user, limit=1 if batch_id else 50)
        if batch_id:
            return next((item for item in batches if item.id == batch_id), None)
        # 默认取最近一个"进行中"的批次；都在草稿/已结束状态时退化为最新批次。
        return next((item for item in batches if item.status == "in_progress"), batches[0] if batches else None)

    def serialize_batch_option(self, batch: SurveyBatch) -> dict:
        return {
            "id": batch.id,
            "batchNo": batch.batch_no,
            "batchName": batch.batch_name,
            "status": batch.status,
            "regionCode": batch.region_code,
            "regionName": batch.region_name,
            "startedAt": batch.started_at,
        }

    #: 每张随批次走的结果表，用一个"编码列"表达区域归属（承包方码 / 发包方码 / 地块码）。
    #: 数据权限（非管理员）就是按这个列的前缀过滤的，必须与 `SurveyCbfBase.cbfbm` 口径一致，
    #: 否则同一块大屏上"承包方总数"是权限内的、"地块总数"却是整批的，两个数对不上账。
    _SCOPE_COLUMN_BY_MODEL = {
        SurveyCbfBase: "cbfbm",
        SurveyCbfJtcyBase: "cbfbm",
        SurveyCbdkxxBase: "cbfbm",
        SurveyFbfBase: "fbfbm",
        SurveyChangeRecord: "cbfbm",
        SurveyAttachment: "cbfbm",
    }

    def _scope_filters(self, batch: SurveyBatch, current_user: User, model=SurveyCbfBase):
        """批次 + 租户 + 数据权限三重过滤。

        ⛔ 所有聚合查询都必须带 `execution_options(skip_tenant_scope=True)`：
        全局 `with_loader_criteria` 会按**登录用户**再注入一次 tenant/region 条件，
        和这里显式写的条件取交集后会把结果集静默缩小（见 skill
        `sqlalchemy-loader-criteria-subquery`）。所以这里自己写全条件、显式关掉自动注入。
        """
        filters = [model.batch_id == batch.id, model.tenant_code == batch.tenant_code]
        column_name = self._SCOPE_COLUMN_BY_MODEL.get(model)
        if column_name:
            filters.extend(data_access_service.build_code_scope_filters(getattr(model, column_name), current_user))
        return filters

    def get_bigscreen(
        self,
        db: Session,
        current_user: User,
        batch: SurveyBatch,
        *,
        trend_days: int = 15,
        top_n: int = 8,
        region_level: str = "town",
    ) -> dict:
        filters = self._scope_filters(batch, current_user)
        live_filters = [*filters, SurveyCbfBase.task_status != "deregistered"]

        overview = self._overview(db, batch, current_user, filters, live_filters)
        # 状态分布用**未排除注销**的口径（"已注销"本身也是要看的一格），
        # 其余指标统一用 live_filters（排除 deregistered），两者不能混。
        task_status = self._task_status_distribution(db, filters)
        assignees = self._assignee_stats(db, live_filters)
        region_board = self._region_board(db, current_user, batch, filters, region_level, top_n)
        change_types = self._change_type_distribution(db, batch, current_user)
        trend = self._trend(db, filters, trend_days)
        request_generated = overview["requestGeneratedCount"]
        funnel = self._funnel(overview, request_generated)
        alerts = self._alerts(overview, assignees, region_board, task_status, db, batch, live_filters)

        return {
            "batch": self.serialize_batch_option(batch),
            "overview": overview,
            "funnel": funnel,
            "taskStatus": task_status,
            "assignees": assignees,
            "regionBoard": region_board,
            "changeTypes": change_types,
            "trend": trend,
            "alerts": alerts,
        }

    def _count(self, db: Session, filters: list, *extra) -> int:
        stmt = (
            select(func.count(SurveyCbfBase.id))
            .where(*filters, *extra)
            .execution_options(skip_tenant_scope=True)
        )
        return int(db.scalar(stmt) or 0)

    def _overview(self, db: Session, batch: SurveyBatch, current_user: User, filters: list, live_filters: list) -> dict:
        total = self._count(db, live_filters)
        assigned = self._count(db, live_filters, SurveyCbfBase.assigned_to.is_not(None))
        surveyed = self._count(db, live_filters, SurveyCbfBase.task_status.in_(SURVEYED_TASK_STATUSES))
        confirmed = self._count(db, live_filters, SurveyCbfBase.task_status == "confirmed")
        changed = self._count(db, live_filters, SurveyCbfBase.has_change.is_(True))

        # 地块"是否已移除"记在成果表上（base 是快照，没有 result_status），
        # 所以这里 join 回 result 排除 removed。base.result_id → result.id 是 1:1，不会放大行数。
        parcel_filters = self._scope_filters(batch, current_user, SurveyCbdkxxBase)
        parcel_stmt = (
            select(
                func.count(func.distinct(SurveyCbdkxxBase.dkbm)),
                func.coalesce(func.sum(SurveyCbdkxxBase.htmj), 0),
            )
            .select_from(SurveyCbdkxxBase)
            .join(SurveyCbdkxxResult, SurveyCbdkxxResult.id == SurveyCbdkxxBase.result_id)
            .where(*parcel_filters, SurveyCbdkxxResult.result_status != "removed")
            .execution_options(skip_tenant_scope=True)
        )
        parcel_total, contract_area = db.execute(parcel_stmt).one()

        issuer_filters = self._scope_filters(batch, current_user, SurveyFbfBase)
        issuer_total = db.scalar(
            select(func.count(func.distinct(SurveyFbfBase.fbfbm)))
            .where(*issuer_filters)
            .execution_options(skip_tenant_scope=True)
        )
        member_filters = self._scope_filters(batch, current_user, SurveyCbfJtcyBase)
        member_total = db.scalar(
            select(func.count(SurveyCbfJtcyBase.id))
            .where(*member_filters)
            .execution_options(skip_tenant_scope=True)
        )
        change_filters = self._scope_filters(batch, current_user, SurveyChangeRecord)
        change_records = db.scalar(
            select(func.count(SurveyChangeRecord.id))
            .where(*change_filters)
            .execution_options(skip_tenant_scope=True)
        )
        attachment_filters = self._scope_filters(batch, current_user, SurveyAttachment)
        attachments = db.scalar(
            select(func.count(SurveyAttachment.id))
            .where(*attachment_filters)
            .execution_options(skip_tenant_scope=True)
        )
        # 已生成业务申请：结果表上有 generated_request_id，用 base.result_id 关联回批次。
        request_generated = db.scalar(
            select(func.count(SurveyCbfBase.id))
            .select_from(SurveyCbfBase)
            .join(SurveyCbfResult, SurveyCbfResult.id == SurveyCbfBase.result_id)
            .where(*live_filters, SurveyCbfResult.generated_request_id.is_not(None))
            .execution_options(skip_tenant_scope=True)
        )

        return {
            "contractorTotal": total,
            "parcelTotal": int(parcel_total or 0),
            "issuerTotal": int(issuer_total or 0),
            "memberTotal": int(member_total or 0),
            "contractAreaMu": round(float(contract_area or 0) / MU_PER_SQUARE_METER, 2),
            "assignedCount": assigned,
            "assignedRate": _rate(assigned, total),
            "surveyedCount": surveyed,
            "surveyedRate": _rate(surveyed, total),
            "confirmedCount": confirmed,
            "confirmedRate": _rate(confirmed, total),
            "changedCount": changed,
            "changeRecordCount": int(change_records or 0),
            "requestGeneratedCount": int(request_generated or 0),
            "attachmentCount": int(attachments or 0),
        }

    def _funnel(self, overview: dict, request_generated: int) -> list[dict]:
        total = overview["contractorTotal"]
        steps = [
            ("baseline", "调查基线", total),
            ("assigned", "已分配到人", overview["assignedCount"]),
            ("surveyed", "已调查录入", overview["surveyedCount"]),
            ("confirmed", "已复核确认", overview["confirmedCount"]),
            ("request", "已生成申请", request_generated),
        ]
        return [
            {"key": key, "label": label, "count": count, "rate": _rate(count, total)}
            for key, label, count in steps
        ]

    def _task_status_distribution(self, db: Session, filters: list) -> list[dict]:
        rows = db.execute(
            select(SurveyCbfBase.task_status, func.count(SurveyCbfBase.id))
            .where(*filters)
            .group_by(SurveyCbfBase.task_status)
            .execution_options(skip_tenant_scope=True)
        ).all()
        counted = {str(status or ""): int(count or 0) for status, count in rows}
        items = [
            {"key": key, "label": label, "count": counted.get(key, 0), "tone": tone}
            for key, label, tone in TASK_STATUS_META
        ]
        known = set(_TASK_STATUS_LABELS)
        for status, count in counted.items():
            if status not in known and count:
                items.append({"key": status, "label": status or "未知", "count": count, "tone": "gray"})
        return items

    def _assignee_stats(self, db: Session, filters: list) -> list[dict]:
        rows = db.execute(
            select(
                SurveyCbfBase.assigned_to,
                func.max(SurveyCbfBase.assigned_to_name),
                func.count(SurveyCbfBase.id),
                func.sum(case((SurveyCbfBase.task_status.in_(SURVEYED_TASK_STATUSES), 1), else_=0)),
                func.sum(case((SurveyCbfBase.task_status == "confirmed", 1), else_=0)),
            )
            .where(*filters, SurveyCbfBase.assigned_to.is_not(None))
            .group_by(SurveyCbfBase.assigned_to)
            .order_by(func.count(SurveyCbfBase.id).desc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        # assigned_to_name 是分配当时的快照，用户改名后就不准了；优先取 users 表的当前姓名。
        ids = [int(row[0]) for row in rows if row[0]]
        name_map: dict[int, str] = {}
        if ids:
            name_map = {
                int(user_id): name
                for user_id, name in db.execute(
                    select(User.id, User.real_name).where(User.id.in_(ids))
                ).all()
                if name
            }
        items = []
        for index, (user_id, snapshot_name, total, surveyed, confirmed) in enumerate(rows, start=1):
            items.append(
                {
                    "userId": int(user_id),
                    "name": name_map.get(int(user_id)) or snapshot_name or f"用户 {user_id}",
                    "total": int(total or 0),
                    "surveyed": int(surveyed or 0),
                    "confirmed": int(confirmed or 0),
                    "surveyedRate": _rate(int(surveyed or 0), int(total or 0)),
                    "rank": index,
                }
            )
        return items

    def _region_board(
        self,
        db: Session,
        current_user: User,
        batch: SurveyBatch,
        filters: list,
        region_level: str,
        top_n: int,
    ) -> dict:
        level, length = REGION_LEVEL_META.get(region_level, REGION_LEVEL_META["town"])
        code_col = func.substr(SurveyCbfBase.cbfbm, 1, length)
        rows = db.execute(
            select(
                code_col,
                func.count(SurveyCbfBase.id),
                func.sum(case((SurveyCbfBase.assigned_to.is_not(None), 1), else_=0)),
                func.sum(case((SurveyCbfBase.task_status.in_(SURVEYED_TASK_STATUSES), 1), else_=0)),
                func.sum(case((SurveyCbfBase.task_status == "confirmed", 1), else_=0)),
            )
            .where(*filters, SurveyCbfBase.task_status != "deregistered")
            .group_by(code_col)
            .execution_options(skip_tenant_scope=True)
        ).all()

        codes = [str(row[0]) for row in rows if row[0]]
        name_map: dict[str, str] = {}
        if codes:
            name_map = {
                str(code): name
                for code, name in db.execute(
                    select(Region.code, Region.name).where(Region.code.in_(codes))
                ).all()
                if name
            }

        items = []
        for code, total, assigned, surveyed, confirmed in rows:
            if not code:
                continue
            code_text = str(code)
            total_int = int(total or 0)
            if not total_int:
                continue
            surveyed_int = int(surveyed or 0)
            confirmed_int = int(confirmed or 0)
            items.append(
                {
                    "code": code_text,
                    "name": name_map.get(code_text) or code_text,
                    "total": total_int,
                    "assigned": int(assigned or 0),
                    "surveyed": surveyed_int,
                    "confirmed": confirmed_int,
                    "assignedRate": _rate(int(assigned or 0), total_int),
                    "surveyedRate": _rate(surveyed_int, total_int),
                    "confirmedRate": _rate(confirmed_int, total_int),
                }
            )
        leading = sorted(items, key=lambda item: (item["surveyedRate"], item["total"]), reverse=True)[:top_n]
        lagging = sorted(items, key=lambda item: (item["surveyedRate"], -item["total"]))[:top_n]
        return {"level": region_level, "levelLabel": level, "leading": leading, "lagging": lagging}

    def _change_type_distribution(self, db: Session, batch: SurveyBatch, current_user: User) -> list[dict]:
        filters = self._scope_filters(batch, current_user, SurveyChangeRecord)
        rows = db.execute(
            select(SurveyChangeRecord.change_type, func.count(SurveyChangeRecord.id))
            .where(*filters)
            .group_by(SurveyChangeRecord.change_type)
            .execution_options(skip_tenant_scope=True)
        ).all()
        buckets: dict[str, dict] = {}
        for change_type, count in rows:
            key = str(change_type or "unknown")
            if key.startswith("rollback"):
                key = "rollback"
            label = _ROLLBACK_LABEL if key == "rollback" else CHANGE_TYPE_LABELS.get(key, key)
            bucket = buckets.setdefault(key, {"key": key, "label": label, "count": 0})
            bucket["count"] += int(count or 0)
        return sorted(buckets.values(), key=lambda item: item["count"], reverse=True)

    def _trend(self, db: Session, filters: list, trend_days: int) -> list[dict]:
        today = date.today()
        start = today - timedelta(days=trend_days - 1)

        def group_by_day(column) -> dict[str, int]:
            rows = db.execute(
                select(func.date(column), func.count(SurveyCbfBase.id))
                .where(*filters, column.is_not(None), func.date(column) >= start)
                .group_by(func.date(column))
                .execution_options(skip_tenant_scope=True)
            ).all()
            return {str(day): int(count or 0) for day, count in rows if day}

        assigned = group_by_day(SurveyCbfBase.assigned_at)
        investigated = group_by_day(SurveyCbfBase.investigated_at)
        confirmed = group_by_day(SurveyCbfBase.reviewed_at)

        points = []
        for offset in range(trend_days):
            day = start + timedelta(days=offset)
            key = day.isoformat()
            points.append(
                {
                    "date": key,
                    "assigned": assigned.get(key, 0),
                    "investigated": investigated.get(key, 0),
                    "confirmed": confirmed.get(key, 0),
                }
            )
        return points

    def _alerts(
        self,
        overview: dict,
        assignees: list[dict],
        region_board: dict,
        task_status: list[dict],
        db: Session,
        batch: SurveyBatch,
        live_filters: list,
    ) -> list[dict]:
        alerts: list[dict] = []
        unassigned = overview["contractorTotal"] - overview["assignedCount"]
        if unassigned > 0:
            alerts.append(
                {
                    "level": "high" if unassigned / max(overview["contractorTotal"], 1) > 0.1 else "medium",
                    "title": "尚未分配任务",
                    "detail": f"{unassigned} 户还没有指定调查员，工作不会自动开始。",
                    "count": unassigned,
                    "actionKey": "unassigned",
                }
            )

        # 分配了但一直没开工：分配时间早于 3 天前、状态仍是 not_started。
        stale_cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        stale = self._count(
            db,
            live_filters,
            SurveyCbfBase.assigned_to.is_not(None),
            SurveyCbfBase.task_status == "not_started",
            SurveyCbfBase.assigned_at.is_not(None),
            SurveyCbfBase.assigned_at < stale_cutoff,
        )
        if stale:
            alerts.append(
                {
                    "level": "high",
                    "title": "分配后超 3 天未开工",
                    "detail": f"{stale} 户已分配但调查状态仍未开始，需要现场核实。",
                    "count": stale,
                    "actionKey": "stale_assigned",
                }
            )

        pending_confirm = overview["surveyedCount"] - overview["confirmedCount"]
        if pending_confirm > 0:
            alerts.append(
                {
                    "level": "medium",
                    "title": "待复核确认积压",
                    "detail": f"{pending_confirm} 户已录入但还没确认，会阻塞后续业务申请生成。",
                    "count": pending_confirm,
                    "actionKey": "pending_confirm",
                }
            )

        if region_board["lagging"]:
            worst = region_board["lagging"][0]
            if worst["surveyedRate"] < 60:
                alerts.append(
                    {
                        "level": "high" if worst["surveyedRate"] < 30 else "medium",
                        "title": f"{worst['name']}进度靠后",
                        "detail": (
                            f"{worst['name']}调查完成率 {worst['surveyedRate']}%"
                            f"（{worst['surveyed']}/{worst['total']} 户），排在末位。"
                        ),
                        "count": worst["total"] - worst["surveyed"],
                        "actionKey": "region_lagging",
                    }
                )

        idle = [item for item in assignees if item["total"] >= 10 and item["surveyedRate"] == 0]
        if idle:
            alerts.append(
                {
                    "level": "medium",
                    "title": "有调查员名下零进度",
                    "detail": f"{len(idle)} 人名下各 10 户以上但一户都没录入：" + "、".join(item["name"] for item in idle[:5]),
                    "count": len(idle),
                    "actionKey": "idle_assignee",
                }
            )

        skipped = next((item["count"] for item in task_status if item["key"] == "skipped"), 0)
        if skipped:
            alerts.append(
                {
                    "level": "low",
                    "title": "存在跳过调查的户",
                    "detail": f"{skipped} 户被标记为跳过，结束批次前必须逐户填跳过原因。",
                    "count": skipped,
                    "actionKey": "skipped",
                }
            )

        changed = overview["changedCount"]
        if changed:
            alerts.append(
                {
                    "level": "low",
                    "title": "变更户待跟踪",
                    "detail": (
                        f"本批次 {changed} 户发生变更，累计 {overview['changeRecordCount']} 条变更记录，"
                        "需确认是否能流转业务申请。"
                    ),
                    "count": changed,
                    "actionKey": "changed",
                }
            )

        order = {"high": 0, "medium": 1, "low": 2}
        return sorted(alerts, key=lambda item: order.get(item["level"], 9))


dashboard_repository = DashboardRepository()
