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
from app.services.data_access_service import data_access_service
from app.services.relation_codes import (
    HEAD_RELATION_VALUE,
    is_head_relation,
    pick_household_head,
    sync_household_head_flags,
)

logger = logging.getLogger(__name__)

class SurveyServiceBase:
    attachment_root = Path(__file__).resolve().parents[3] / "storage" / "survey_attachments"
    authorization_root = Path(__file__).resolve().parents[3] / "storage" / "survey_authorizations"
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
                errors.append("承包方存在变化时必须填写变化原因")
            if not self._has_text(result.policy_basis):
                errors.append("承包方存在变化时必须填写政策依据")

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
