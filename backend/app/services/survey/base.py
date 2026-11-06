import logging
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyBatch,
    SurveyCbfBase,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
)
from app.db.sequences import next_no as generate_business_no
from app.models.user import User
from app.paths import STORAGE_DIR
from app.services.data_access_service import data_access_service
from app.services.relation_codes import (
    HEAD_RELATION_VALUE,
    is_head_relation,
    pick_household_head,
    sync_household_head_flags,
)

logger = logging.getLogger(__name__)

# ---- 「变化原因」的默认值（2026-09-27 定） ----
# 背景：`change_reason` 曾被当成**硬闸门**（"承包方/成员有变化就必须填写变化原因"），
# 但全库非空值 0 条 —— 也就是说**每一个有变化的户都卡死在「确认调查结果」之前，
# 而界面上（成员表之外）连个录入控件都没有**。用户报的「合户之后确认不了」就是这个。
# 语义上「变化原因」对系统操作（合户/分户/注销）本来就是**系统已知的事实**，
# 对调查员手改字段也能从差异表看出来，没有理由要求人工再补写一遍。
# 现在改为：确认前若为空，按变更类型 / 成员自身标记**自动写入默认值**；
# 人工填了则以人工为准（`resolve_change_reason` 同口径）。
# ⛔ 与前端 `ContractorResultDialog.collectConfirmBlockers` 同源：改这里要改那里。
GENERIC_CHANGE_REASON = "调查数据发生变更"

CONTRACTOR_CHANGE_REASON_DEFAULTS = {
    "merge_household": "因合户发生变更",
    "split_household": "因分户发生变更",
    "deregister": "因注销承包方",
    "add_contractor": "新增承包方",
    "swap_parcels": GENERIC_CHANGE_REASON,
    "add_parcel": GENERIC_CHANGE_REASON,
    "remove_parcel": GENERIC_CHANGE_REASON,
    "split_parcel": GENERIC_CHANGE_REASON,
    "change_head": GENERIC_CHANGE_REASON,
    "member_maintain": GENERIC_CHANGE_REASON,
}


def default_contractor_change_reason(change_type: str | None) -> str:
    """承包方级「变化原因」的默认值。"""
    return CONTRACTOR_CHANGE_REASON_DEFAULTS.get(
        str(change_type or "none").strip(), GENERIC_CHANGE_REASON
    )


def default_member_change_reason(contractor_change_type: str | None, member) -> str:
    """成员级「变化原因」的默认值：先看户级操作，再看成员自身标记。"""
    change_type = str(contractor_change_type or "none").strip()
    if change_type == "merge_household":
        return "因合户转入新户"
    if change_type == "split_household":
        return "因分户转入新户"
    if getattr(member, "is_deceased", False):
        return "去世"
    if getattr(member, "is_married_out_woman", False):
        return "婚出"
    if getattr(member, "is_urban_settled", False):
        return "全家进城落户"
    if getattr(member, "is_five_guarantees", False):
        return "五保户"
    if str(getattr(member, "member_result_status", "") or "") == "added":
        return "新增家庭成员"
    if str(getattr(member, "member_result_status", "") or "") == "removed":
        return "成员迁出"
    return GENERIC_CHANGE_REASON


class SurveyServiceBase:
    attachment_root = STORAGE_DIR / "survey_attachments"
    authorization_root = STORAGE_DIR / "survey_authorizations"
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
        "rollback_remove_parcel",
        "split_household",
        "merge_household",
    }
    terminal_operation_types = {"deregister", "merge_household", "split_household"}
    # ---- 「这一户已被终结」的方向判据（2026-09-25 修） ----
    # 终态操作一次动两拨行，**change_type 写的是同一个值**，方向只能看 result_status：
    #   · 原户（被注销 / 被并走 / 被拆走）：result_status = "cancelled"
    #   · 新户（分户/合户**新生成**的户）：result_status = "added"
    # ⛔ 只按 `change_type in terminal_operation_types` 判，会把新生成的户一起判成"已注销"
    #   ⇒ 保存 400「该承包户已注销…」+ 前端整个表单只读。
    #   2026-09-25 用户报「合户之后刘乃高不能修改」就是这么来的。
    terminal_result_statuses = {"cancelled", "extinct"}
    new_result_statuses = {"added"}
    # 「让户离开待办」的终态操作，其**原户**那条变更记录会带这个 action
    # （合户：cancelled_after_merge；分户：cancelled_after_split）。
    # 新户那边写的是 created*，不属于"退出待办的原户"。
    # ⛔ 与 `terminal_operation_types` 同源：已注销列表要按 changeType 分流撤回接口。
    terminal_source_actions = {"cancelled_after_merge", "cancelled_after_split"}
    form_diff_entity_types = {"contractor", "issuer", "member"}
    parcel_diff_entity_types = {"parcel", "parcel_relation"}
    tag_names = {
        "whole_family_urbanized": "全家进城落户",
        "household_extinct": "整户消亡",
        "five_guarantees": "五保户",
        "little_or_no_land": "无地少地",
    }
    # ---- 调查成果状态集合（唯一来源，2026-09-27 定） ----
    # 同一个集合被三处消费，必须同源，否则就会重现两类经典事故：
    #   · 「界面能点、保存 403」—— 前端比后端宽；
    #   · 「后端放行、界面不给点」—— 前端比后端窄。用户 2026-09-27 报的
    #     「保存完调查结果，列表里没有确认按钮」就是后一类：前端只认 `surveyed`，
    #     后端 `confirm_result` 却认 `{surveyed, changed, unchanged}`，
    #     有变化（changed）的户后端放行、界面根本不给点。
    # 消费方：`task.py::confirm_result`（服务端准入）、`SurveyView.vue`（列表按钮）、
    #        `ContractorResultDialog.vue`（弹窗按钮）。
    # ⛔ 别和「已调查」的**统计**口径混用：统计口径还包含 `confirmed`
    #   （见 `repositories/dashboard_repository.SURVEYED_TASK_STATUSES` 与
    #    `batch.py` 的 surveyed_count），那是"录过了"，这里是"录了但还没定案"。
    confirmable_survey_statuses = {"surveyed", "changed", "unchanged"}
    # 定案态：只能由「确认调查结果」「跳过」两个动作写入，保存不得回退。
    terminal_survey_statuses = {"confirmed", "skipped"}
    # ---- 「已定案 ⇒ 不许再改数据」的编辑闸门（2026-09-27 定） ----
    # ⛔ 注意它**不等于** `terminal_survey_statuses`：`skipped`（跳过）属于定案态，
    #   但跳过之后仍然允许补录（现有口径：`task.skip_task` 只拒 `confirmed`），
    #   所以编辑闸门只有 `confirmed` 一个元素。两个集合别互相替换。
    # 消费方（同一判据，四处）：`result.py::update_result`（承包方保存）、
    #   `task.py::skip_task`（跳过前置检查）、`issuer.py::update_issuer`（发包方保存）、
    #   前端 `config/surveyStatus.js::LOCKED_SURVEY_STATUSES`（表单只读判定）。
    locked_survey_statuses = {"confirmed"}

    @classmethod
    def resolve_saved_survey_status(cls, current: str | None, submitted: str | None) -> str:
        """保存调查结果时，这一户的成果状态该落成什么（由**服务端**裁定）。

        ⛔ 为什么不能写成 `payload.get("surveyStatus") or "surveyed"`：
        前端录入弹窗把表单**整体展开提交**，而 `surveyStatus` 是打开弹窗时从库里
        回填的旧值 —— 界面上根本没有能改它的控件。于是"照单全收"等于把**起点值**
        原样写回：全库 `survey_status = 'surveyed'` 一度是 **0 行**，
        `SurveyCbfBase.task_status` 永远停在 `not_surveyed`，
        普通户（非合户/分户新生成）**永远拿不到「确认」按钮**。
        保存动作本身就意味着"这一户已经录过了"，所以这个推进由服务端负责，
        前端回传的状态值只当"用户显式选择"看。
        """
        current_status = str(current or "").strip()
        submitted_status = str(submitted or "").strip()
        # ① 已在定案态：保持不动（确认 / 跳过各自由自己的动作写入）
        if current_status in cls.terminal_survey_statuses:
            return current_status
        # ② 前端显式给了可确认集合里的状态：照收
        if submitted_status in cls.confirmable_survey_statuses:
            return submitted_status
        # ③ 其余（空 / not_surveyed / not_started / 未知脏值）：推进为"已调查"
        return "surveyed"

    @classmethod
    def is_terminal_result(cls, result: SurveyCbfResult) -> bool:
        """这一户是不是**已被终结**（已注销 / 被合户并走 / 被分户拆走）。

        ⛔ 唯一的"终结判据"，后端保存闸门与详情接口的 ``isTerminal`` 都由它求出；
        前端只消费接口给的 ``isTerminal``，不自己拿 ``changeType`` 算一遍
        （否则又是「界面能点、保存 403」那类同源性问题）。

        方向看 ``result_status``：原户 ``cancelled``、分户/合户新生成的户 ``added``，
        两边 ``change_type`` 相同 ⇒ **不能**只按 change_type 判（见上方注释）。
        第二个分支只为兜历史行：早期数据只写了 ``change_type``、``result_status`` 没维护。
        """
        if result.result_status in cls.terminal_result_statuses:
            return True
        return (
            result.change_type in cls.terminal_operation_types
            and result.result_status not in cls.new_result_statuses
        )

    def _ensure_batch(self, db: Session, batch_id: int) -> SurveyBatch:
        batch = db.get(SurveyBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调查批次不存在")
        return batch

    @staticmethod

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

    @staticmethod
    def _ensure_batch_editable_status(batch: SurveyBatch, *, action: str = "继续编辑") -> None:
        """批次生命周期口径：只有 active 才算「调查中」。

        原先是黑名单写法 ``if batch.status == "finished"``，等价于「非 finished
        一律放行」。create_batch 只会写 active，两种写法行为一致，但白名单
        写法才准确表达「必须是调查中」这一业务口径。
        """
        if batch.status == "active":
            return
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"调查批次已结束，不能{action}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"调查批次不在调查中，不能{action}")

    def _ensure_editable_batch_and_result(
        self,
        db: Session,
        result: SurveyCbfResult,
        current_user: User | None = None,
    ) -> None:
        """「这一户现在还能不能改」的总闸：批次生命周期 + 成果状态 + **任务归属**。

        传 ``current_user`` 时顺带做归属校验 —— 附件、委托书、权属调整、标签
        这些子资源的写接口全部经过这里，所以归属校验只在这一个地方加，
        就同时覆盖了它们；漏传等于放行，故调用方一律要传（见
        ``grep -rn "_ensure_editable_batch_and_result" backend/app``）。
        """
        base = db.scalar(select(SurveyCbfBase).where(SurveyCbfBase.contractor_uid == result.contractor_uid).order_by(SurveyCbfBase.id.desc())) if result else None
        batch = self._ensure_batch(db, base.batch_id) if base else None
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调查批次已结束，不能继续编辑")
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调查成果已确认，不能继续编辑")
        if bool(getattr(result, "is_locked", False)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="承包方已锁定，不能继续编辑")
        if current_user is not None and batch is not None:
            self.ensure_task_write_permission(db, batch, result, current_user)

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
            # 户主判定必须走统一口径（relation_codes：优先 户主 02 → 本人 01 → 兜底第一条）。
            # 只要这一户有成员就一定能判出唯一户主，所以"一个成员都没有"才是唯一错误。
            #
            # ⛔ 历史事故（2026-09-25 修）：这里曾写 `len(household_heads) != 1` 且判据取
            # `member.yhzgx == "01"`，而字典与真实数据里**户主是 "02"**
            # （`survey_cbf_jtcy_result.yhzgx='02'` 17.98 万条、每户恰好一条）⇒
            # 179,788 个 cbflx=1 的户里**只有 1 户**能通过 ⇒ 「确认调查结果」对真实户
            # 几乎全部返回 400 "request failed"。验收：scripts/_verify_survey_rollback_entry.py H1/H2。
            if pick_household_head(members) is None:
                errors.append("未指定户主：请在家庭成员中指定一名户主")

        seen_id_nos: set[str] = set()
        for member in members:
            id_no = (member.cyzjhm or "").strip()
            if id_no:
                if id_no in seen_id_nos:
                    errors.append(f"家庭成员证件号码重复：{id_no}")
                    break
                seen_id_nos.add(id_no)

        # ⛔ `change_reason`（变化原因）**不再是硬闸门**（2026-09-27 用户决定）：
        # 空值由下面的 `_ensure_change_reasons` 在确认前按变更类型**自动写入默认值**。
        # 曾经这里拦 `not self._has_text(result.change_reason)`，结果是全库 0 条非空的
        # 字段把每一个有变化的户都卡死（用户报「合户之后刘乃高确认不了」根因之一）。
        # `policy_basis`（政策依据）**不设必填**（2026-09-26 用户决定）：
        # 它是 NY/T 2539 规范外的扩展字段，甲方合同模板里没有这一栏，
        # 且全库非空值 0 条 —— 强制必填只会把户卡死在确认前。字段保留、可自愿填。

        # 成员「变化原因」同口径：也不再拦，由 `_ensure_change_reasons` 兜底。

        if errors:
            # ⛔ 逐条点名缺哪一项，不要退回笼统的 "request failed"：
            # 前端（含只读展示的手机端）直接展示 detail，笼统文案会让用户
            # 点「确认调查结果」后完全不知道要补什么（2026-09-26 改）。
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="；".join(errors),
            )

    def _member_change_requires_reason(self, member: SurveyCbfJtcyResult) -> bool:
        """这一名成员是不是「有变化」——只有有变化的成员才需要变化原因。"""
        return bool(
            member.is_changed
            or member.member_result_status != "normal"
            or member.is_urban_settled
            or member.is_married_out_woman
            or member.is_deceased
            or member.is_five_guarantees
            or self._has_text(member.rights_disposition)
        )

    def _ensure_change_reasons(self, db: Session, result: SurveyCbfResult) -> list[str]:
        """给「有变化却没写原因」的行补上系统默认值，返回补了什么（供日志）。

        ⛔ 为什么在**确认时补**而不是**保存时补**：既要覆盖存量行（用户报的这一户是
        早先做的合户，保存路径早已走完），又要保证「点确认」不会被自己拦下。
        这里直接改 ORM 对象，随 `confirm_result` 末尾的 `db.commit()` 一起落库。
        """
        filled: list[str] = []
        if (result.is_changed or (result.change_type or "none") != "none") and not self._has_text(
            result.change_reason
        ):
            result.change_reason = default_contractor_change_reason(result.change_type)
            filled.append(f"承包方={result.change_reason}")
        members = db.scalars(
            select(SurveyCbfJtcyResult)
            .where(SurveyCbfJtcyResult.contractor_uid == result.contractor_uid)
            .order_by(SurveyCbfJtcyResult.id.asc())
        ).all()
        for member in members:
            if not self._member_change_requires_reason(member):
                continue
            if self._has_text(member.change_reason):
                continue
            member.change_reason = default_member_change_reason(result.change_type, member)
            filled.append(f"{member.cyxm or '未命名成员'}={member.change_reason}")
        return filled

    async def _store_upload(self, directory: Path, upload_file: UploadFile) -> tuple[Path, int]:
        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传文件为空")
        directory.mkdir(parents=True, exist_ok=True)
        suffix = Path(upload_file.filename or "").suffix
        storage_path = directory / f"{uuid4().hex}{suffix}"
        with storage_path.open("wb") as target:
            target.write(content)
        return storage_path, len(content)

    def _tenant_filters(self, model, current_user: User) -> list:
        tenant_code = data_access_service.get_tenant_code(current_user)
        if tenant_code and hasattr(model, "tenant_code"):
            return [model.tenant_code == tenant_code]
        tenant_filter = data_access_service.build_tenant_filter(model, current_user)
        return [] if tenant_filter is None else [tenant_filter]

    @staticmethod

    def _build_task_scope_filters(self, current_user: User, region_code: str | None = None) -> list:
        filters = self._tenant_filters(SurveyCbfBase, current_user)
        filters.extend(data_access_service.build_code_scope_filters(SurveyCbfBase.region_code, current_user))
        if region_code:
            filters.append(SurveyCbfBase.region_code.like(f"{region_code}%"))
        return filters

    @staticmethod
    def _append_group_region_filter(filters: list, column, region_code: str | None) -> None:
        if not region_code:
            return
        if len(region_code) >= 14:
            filters.append(column == region_code)
        else:
            filters.append(column.like(f"{region_code}%"))

    @staticmethod

    @staticmethod
    def _log_sql(db: Session, label: str, stmt) -> None:
        try:
            compiled = stmt.compile(bind=db.get_bind(), compile_kwargs={"literal_binds": True})
            logger.info("SQL[%s]: %s", label, compiled)
        except Exception:
            logger.exception("Failed to compile SQL[%s]", label)
            logger.info("SQL[%s]: %s", label, stmt)

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

    def _has_text(self, value: str | None) -> bool:
        return bool(str(value or "").strip())

    def _next_no(self, db: Session, prefix: str, id_column=None) -> str:
        # 编号列（batch_no / change_no / restructure_no / authorization_no）都带唯一约束。
        # 旧实现取 max(id)+1，删行后会回退（"删批次再建"拿到用过的编号）、并发会撞号；
        # 现在统一走 PostgreSQL 序列（app.db.sequences），nextval 原子递增、不回退。
        # 序列在程序初始化时建好，编号格式不变：<prefix><yyyymmdd><流水号>。
        # id_column 参数只为兼容旧调用点保留。
        return generate_business_no(db, prefix, id_column)

    def _get_task(self, db: Session, batch_id: int, contractor_uid: str) -> SurveyCbfBase | None:
        return db.scalars(
            select(SurveyCbfBase).where(
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.contractor_uid == contractor_uid,
            )
        ).first()
