"""调查任务的分配、改派与「谁能改这一户」的判定。

背景：``survey_cbf_base.assigned_to / assigned_to_name / assigned_at`` 三列
在 models 与 db/migrations.py 里早就建好了（``_upgrade_survey_base_result_refactor``
的 task_fields），但 services 层从未引用——是一组「预留但从未接线」的字段。
本模块把它们接上，并作为承包方调查结果写权限的唯一判据。

设计口径（与批次/区域两级权限的分工）：

1. **批次层** ``SurveyBatch.created_by`` → 管理权。谁能改派任务、谁能结束批次。
2. **任务层** ``SurveyCbfBase.assigned_to`` → 独占权。谁名下这一户，谁才能改。
3. **状态层** ``batch.status`` / ``result.survey_status`` → 生命周期。已有实现保留。

归属判定（2026-09-24 定稿）——**只有「我名下」的户才能录入**：

| 情形 | 结果 |
| --- | --- |
| `data_scope == "all"`（管理员） | 放行（救火口） |
| `assigned_to == 我` | 放行 |
| `assigned_to` 是别人 | 403「已分配给 X，如需修改请联系批次创建人改派」 |
| `assigned_to` 为空 | **403，只能查看详细信息** |
| 本批次创建人（但户不在我名下） | **403，同上两条** |

⛔ **「批次创建人」不是录入写权的豁免**（2026-09-24 摘掉）。它只豁免**分配 /
改派权**（``_ensure_batch_assigner``）。理由：创建人常常就是本批次的调查员，
若录入也豁免，他给自己分 2 户却能改全批 10 户，「分配」就失去意义了。
创建人想录某个户，先（改）派给自己 —— 改派权仍在他手上，所以不会死锁。

**兼容性说明（与旧铁律的差异）**：旧铁律是「``assigned_to`` 为空 = 不做归属限制」。
全县十七万余户不可能一次性分完；若把「未分配」解释成「谁都无权」，上线当天
所有调查员都会被锁死在自己的历史数据之外。现在敢改成拒绝，是因为上游已经把
口子堵住：新建批次时**管理员必须指派调查员、非管理员自动派给自己**
（``resolve_batch_create_assignees``）、批次内新增户默认落到操作人名下
（``default_new_task_assignee``）⇒「未分配」只剩历史批次与手工补录两种情形，
这两种由**管理员的批次级豁免**兜底（历史批次如 #40 的创建人就是管理员）。
"""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.models.survey import SurveyBatch, SurveyCbfBase, SurveyCbfResult
from app.models.user import User
from app.services.data_access_service import data_access_service

logger = logging.getLogger(__name__)

# 单次分配上限：与前端任务列表分页上限（500）对齐，
# 同时避开 PostgreSQL 绑定参数 65535 上限。
ASSIGN_BATCH_LIMIT = 500


class SurveyServiceAssignmentMixin:
    # ---- 管理权 ----

    def _ensure_batch_manager(self, batch: SurveyBatch, current_user: User) -> None:
        """批次级管理权：**结束批次**（以及其不可派生的强管控动作）。

        与 ``finish_batch`` 原先只校验 ``contractors.manage`` 相比，这里多一层
        「必须是本批次创建人（或全量数据权限角色）」的收口，否则任何有
        ``contractors.manage`` 的人都能结束别人建的批次。

        ⚠️ 2026-09-23 起**改派/分配任务不走这个闸门**了（见 ``_ensure_batch_assigner``）：
        批次按区域唯一，把分配也锁在创建人身上会让属地人员整片区域干不了活。
        """
        if current_user.role.data_scope == "all":
            return
        if batch.created_by and batch.created_by == current_user.id:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有该调查批次的创建人可以结束批次",
        )

    def _ensure_batch_assigner(self, batch: SurveyBatch, current_user: User) -> None:
        """分配权：谁能把本批次的承包户指派给调查员。

        ⛔ 与 ``_ensure_batch_manager``（**结束批次**用）刻意分开，别合并：

        分配是**日常派活**。批次按区域唯一（``create_batch`` 里同区域已有 active
        批次会 400），所以只要管理员先在某个镇建了批次，该镇的业务员就再也建不了
        新批次、若分配权也锁在创建人身上，这片区域就彻底干不了活——只能等管理员
        自己回来分完或结束。原口径（只看 ``created_by``）就是这么把属地人员卡住的。

        判据（任一命中即放行）：

        | 情形 | 结果 |
        | --- | --- |
        | ``data_scope == "all"``（管理员） | 放行（救火口） |
        | 本批次创建人 | 放行（与批次列表 `_my_batches_condition` 的可见性口径一致，<br>避免「列表里看得见、点开却 403」） |
        | 数据权限覆盖本批次区域 | 放行（``ensure_region_in_scope``：前缀匹配 + 同租户） |
        | 其余 | 403 |

        **没有放宽的是** ``finish_batch``：结束批次是制度性动作（结束后全批次锁死），
        仍只允许创建人 / 管理员。

        ⚠️ 这里必须复用 ``ensure_region_in_scope`` 而不是"能看见批次就算数"：
        列表口径是「区域授权 **∪** 与我相关」，只凭"看得见"会把「有户分给我、
        但我的授权不覆盖本区域」的人也算进来，等于给出跨区域改派权。
        """
        if self.is_batch_privileged(batch, current_user):
            return
        if not batch.region_code:
            # 区域码缺失时无法证明覆盖 ⇒ 不放行（不退回 manager 口径，避免文案张冠李戴）。
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="本调查批次缺少区域信息，无法判定分配权限",
            )
        data_access_service.ensure_region_in_scope(
            current_user,
            batch.region_code,
            detail="当前用户的数据权限区域不包含本调查批次，无法分配任务",
        )

    # ---- 写权限判定 ----

    @staticmethod
    def is_global_admin(current_user: User | None) -> bool:
        """是否全量数据权限（系统管理员）。

        单独抽出来是因为**新建批次时还没有 batch**，用不了 ``is_batch_privileged``；
        而「指派调查员必填、且可以指派他人」这条规则只对管理员成立。
        """
        if current_user is None:
            return False
        role = getattr(current_user, "role", None)
        return role is not None and role.data_scope == "all"

    @staticmethod
    def is_batch_privileged(batch: SurveyBatch, current_user: User) -> bool:
        """**分配 / 改派权**的批次级豁免：全量数据权限角色 / 本批次创建人。

        ⛔ 只服务 ``_ensure_batch_assigner``（谁能派活）。**不再管录入写权** ——
        录入那一侧请用 ``is_task_write_privileged``（2026-09-24 拆分）。

        这两个豁免口是故意留的，不是漏网：
        - ``data_scope == "all"``（系统管理员）要能进任何批次救火；
        - 批次创建人是本批次的管理者，改派必须能操作。去掉它会把「属地人员
          派不了活」变成死锁：批次按区域唯一（同区域已有 active 批次会 400），
          管理员先在某个镇建了批次，该镇业务员就再也建不了新批次，若分配权
          也锁在创建人身上，这片区域彻底干不了活。
        """
        if SurveyServiceAssignmentMixin.is_global_admin(current_user):
            return True
        return bool(batch is not None and batch.created_by and batch.created_by == current_user.id)

    @staticmethod
    def is_task_write_privileged(current_user: User | None) -> bool:
        """**录入写权**的批次级豁免：只认全量数据权限角色（系统管理员）。

        ⛔ 2026-09-24 口径收紧：这里**不再包含「批次创建人」**。

        原口径把创建人并入 ``is_batch_privileged``，而创建人往往就是本批次的
        调查员，导致「归属」对创建人完全失去约束力：他给自己分 2 户，却能改本批
        全部 10 户 —— 分配形同虚设。实测（batch 41，created_by=7 的组级测试员）：
        未分配户 ``321324100001020012`` 的列表 ``canWrite`` 为 True、保存接口也放行。

        收紧后创建人对「未分配 / 已分配给他人」的户只读，想录就先（改）派给自己。
        **改派权不受影响**（走 ``_ensure_batch_assigner``），所以不会死锁：
        - 批次创建时与批次内新增户都已自动归属（``resolve_batch_create_assignees`` /
          ``default_new_task_assignee``），正常批次不会出现无人可录的户；
        - 万一有（历史批次、手工收回分配），创建人有改派权自己分一下即可，
          管理员始终是全批豁免的兜底。
        """
        return SurveyServiceAssignmentMixin.is_global_admin(current_user)

    @staticmethod
    def task_row_can_write(task_row, is_privileged: bool, current_user: User) -> bool:
        """纯函数版判定：调用方已经把任务行读出来了，别再查一次库。

        列表是按 ``survey_cbf_base`` 行铺开的，每行都带着 ``assigned_to``，
        所以在 ``list_tasks`` 里逐行调它，零额外查询。

        ``is_privileged`` 必须由 ``is_task_write_privileged`` 求出（**只含管理员**），
        别传 ``is_batch_privileged``：那会把创建人豁免带进来，让分配对创建人失效。
        """
        if is_privileged:
            return True
        if current_user is None:
            return False
        owner_id = getattr(task_row, "assigned_to", None)
        return owner_id is not None and owner_id == current_user.id

    def _get_task_for_ownership(self, db, batch_id: int, contractor_uid: str):
        """只判归属的任务行查询：**不带全局区域过滤**。

        区域越权在调用本方法之前就已由 ``ensure_code_in_scope`` 拦掉；这里若再套
        一遍 loader criteria，会把「行被区域条件滤掉」误判成「未分配」，
        于是报错文案指向了错误的病因（去查分配，其实该查权限）。
        """
        if not contractor_uid:
            return None
        return db.scalars(
            select(SurveyCbfBase)
            .where(
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.contractor_uid == contractor_uid,
            )
            .execution_options(skip_tenant_scope=True)
        ).first()

    def can_write_task(self, db, batch: SurveyBatch, contractor_uid: str, current_user: User) -> bool:
        """``ensure_task_write_permission`` 的不抛异常版本（需要现查任务行时用）。

        ⛔ 与 ``ensure_task_write_permission`` 必须同口径：界面能点、接口 403
        是最典型的「按钮在但保存失败」体验事故。
        """
        if self.is_task_write_privileged(current_user):
            return True
        task = self._get_task_for_ownership(db, batch.id, contractor_uid)
        return self.task_row_can_write(task, False, current_user)

    def ensure_task_write_permission(
        self,
        db,
        batch: SurveyBatch,
        result: SurveyCbfResult,
        current_user: User,
    ) -> None:
        """判定 ``current_user`` 能否修改这一户的调查结果，不能改就抛 403。

        优先级：全量数据权限角色 > 任务归属人 > 拒绝。

        ⚠️ 口径演变（别回退）：
        - 2026-09-23：``assigned_to`` 为空时由「不做归属限制」改为**拒绝**
          （此前十七万户不可能一次分完，怕上线当天把调查员锁死；上游已把口子
          堵住：新建批次必须指派调查员、非管理员自动派给自己、批次内新增户
          落到操作人名下，所以「未分配」只剩历史批次与手工补录）；
        - 2026-09-24：把「批次创建人」从豁免里摘掉 —— 原先它跟着
          ``is_batch_privileged`` 一起豁免，创建人（往往就是本批次调查员）
          因此能改任意户，分配形同虚设。现改为只认管理员。
        """
        if self.is_task_write_privileged(current_user):
            return
        task = self._get_task_for_ownership(db, batch.id, result.contractor_uid)
        owner_id = task.assigned_to if task is not None else None
        if owner_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="该承包户尚未分配调查员，只能查看详细信息；请先分配调查员后再录入",
            )
        if owner_id == current_user.id:
            return
        owner = (task.assigned_to_name if task else None) or "其他调查员"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"该承包户已分配给{owner}，如需修改请联系批次创建人改派",
        )

    # ---- 分配 / 改派 ----

    def assign_tasks(self, db, batch_id: int, payload: dict, current_user: User) -> dict:
        """批量分配或改派承包方调查任务。

        ``assigneeId`` 为 ``None`` 表示收回分配（回到未分配状态）。
        """
        batch = self._ensure_batch(db, batch_id)
        self._ensure_batch_assigner(batch, current_user)
        if batch.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="调查批次已结束，不能继续分配任务",
            )

        contractor_uids = [
            uid for uid in dict.fromkeys(payload.get("contractorUids") or []) if uid
        ]
        if not contractor_uids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择要分配的承包方")
        if len(contractor_uids) > ASSIGN_BATCH_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"单次最多分配 {ASSIGN_BATCH_LIMIT} 户，请分批操作",
            )

        assignee_id = payload.get("assigneeId")
        assignee = None
        if assignee_id is not None:
            assignee = db.get(User, int(assignee_id))
            if assignee is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="指定的调查员不存在")
            if assignee.status != "active":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="指定的调查员已停用")
            if batch.tenant_code and assignee.tenant_code and assignee.tenant_code != batch.tenant_code:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="指定的调查员不属于本调查批次所在区县",
                )
            self._ensure_assignee_covers_batch(batch, assignee)

        tasks = db.scalars(
            select(SurveyCbfBase)
            .where(
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.contractor_uid.in_(contractor_uids),
            )
            .execution_options(skip_tenant_scope=True)
        ).all()
        found_uids = {item.contractor_uid for item in tasks}
        missing_uids = [uid for uid in contractor_uids if uid not in found_uids]

        now = datetime.now(timezone.utc)
        for task in tasks:
            task.assigned_to = assignee.id if assignee else None
            task.assigned_to_name = assignee.real_name if assignee else None
            task.assigned_at = now if assignee else None
        db.commit()

        logger.info(
            "Survey task assignment: batch_id=%s operator=%s assignee=%s updated=%s missing=%s",
            batch_id,
            current_user.id,
            assignee.id if assignee else None,
            len(tasks),
            len(missing_uids),
        )
        return {
            "batchId": batch_id,
            "assigneeId": assignee.id if assignee else None,
            "assigneeName": assignee.real_name if assignee else None,
            "updated": len(tasks),
            "missing": missing_uids,
        }

    def list_assignable_users(self, db, batch_id: int, current_user: User) -> list[dict]:
        """可被分配任务的调查员列表：同区县、在职。

        权限口径与 ``assign_tasks`` **必须一致**（都走 `_ensure_batch_assigner`）：
        否则会出现「能打开弹窗、却因为拿不到名单而误报"没有调查员"」——
        这个提示会把权限问题伪装成数据问题，是最难排查的一类误导。
        """
        batch = self._ensure_batch(db, batch_id)
        self._ensure_batch_assigner(batch, current_user)
        return [
            {**item, "coversBatch": item["coversRegion"]}
            for item in self.list_assignees(
                db,
                current_user,
                region_code=batch.region_code,
                tenant_code=batch.tenant_code,
            )
        ]

    def list_assignees(
        self,
        db,
        current_user: User,
        *,
        region_code: str | None = None,
        tenant_code: str | None = None,
    ) -> list[dict]:
        """租户内、在职的可指派调查员（**不绑定某个批次**）。

        批次列表的「按调查员筛选」和「新建批次时指派调查员」都还没拿到批次 id，
        所以需要一份与 ``list_assignable_users`` 同口径、但不依赖批次的候选名单。

        ``coversRegion`` 表示管辖范围是否覆盖给定区域；不传 region_code 时恒为 True。
        前端据此把不覆盖的人置灰——真正兜底的仍是
        ``_ensure_assignee_covers_batch`` / ``resolve_batch_assignees``，
        因为「分配成功但保存不了」的静默失败比直接报错更难排查。
        """
        if region_code:
            # 只读筛选值：允许传比授权范围更粗的区域码（见 ensure_region_filter_in_scope）。
            data_access_service.ensure_region_filter_in_scope(current_user, region_code)
        effective_tenant = tenant_code or data_access_service.get_tenant_code(current_user)
        filters = [User.status == "active"]
        if effective_tenant:
            filters.append(User.tenant_code == effective_tenant)
        users = db.scalars(select(User).where(*filters).order_by(User.real_name.asc())).all()
        items = []
        for item in users:
            items.append(
                {
                    "id": item.id,
                    "realName": item.real_name,
                    "username": item.username,
                    "roleName": item.role.name if item.role else None,
                    "regionCode": item.region.code if item.region else None,
                    "coversRegion": self._user_covers_region(item, region_code),
                }
            )
        return items

    # ---- 新建批次时指派 ----

    def resolve_batch_create_assignees(self, payload_assignee_ids, current_user: User) -> list[int]:
        """新建批次时「指派调查员」的名单按角色分流（越权在这里收口）。

        | 角色 | 行为 |
        | --- | --- |
        | 管理员（``data_scope == "all"``） | 可以指派他人；**必须**至少 1 人 |
        | 其他人 | **只能**建成「派给自己」：不传 / 传空 / 只传自己 → 归一成 ``[自己]``；<br>名单里出现别人 → 403 |

        ⛔ 为什么必填校验必须放服务层：它是**依赖当前用户**的约束，Pydantic schema
        拿不到 ``current_user``。若在 schema 上写 ``min_length=1``，非管理员
        （前端不显示选择器、也不传这个字段）的正常请求会被 422 拦死，
        而管理员那条"必填"反而可以在入口就挡——所以只能统一放这里按角色判。

        ⛔ 非管理员传别人时**报 403 而不是静默改回自己**：静默改回会让越权尝试
        看起来"成功了"（返回 200），前端拿到一个归属与自己预期不符的批次却无从察觉。
        返回名单顺序即最终分配顺序，交给 ``assign_round_robin`` 轮流均分。
        """
        requested: list[int] = []
        for item in payload_assignee_ids or []:
            if item is None:
                continue
            try:
                value = int(item)
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="指派调查员名单格式不正确",
                ) from exc
            if value not in requested:
                requested.append(value)

        if self.is_global_admin(current_user):
            if not requested:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="请先指派调查员：调查批次创建后每个承包户都必须有归属的调查员",
                )
            return requested

        # 非管理员（含未登录的防御分支）：只允许「派给自己」。
        current_id = getattr(current_user, "id", None)
        foreign = [item for item in requested if item != current_id]
        if foreign:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有管理员可以指派其他调查员；您创建的调查批次会自动指派给您本人",
            )
        return [current_id]

    def resolve_batch_assignees(
        self,
        db,
        assignee_ids,
        *,
        region_code: str | None,
        tenant_code: str | None,
    ) -> list[User]:
        """把新建批次请求里的 ``assigneeIds`` 解析成 User 列表并逐条校验。

        校验口径与 ``assign_tasks`` 完全一致（存在 / 在职 / 同区县 / 管辖范围覆盖批次），
        因为两者最终都写同一组 ``survey_cbf_base.assigned_to`` 字段，
        在新批次这一侧放松校验只会制造同一类「分了却干不了活」的静默失败。

        返回顺序与入参一致（去重后），供轮流分配使用。
        """
        ids = [int(item) for item in dict.fromkeys(assignee_ids or []) if item is not None]
        if not ids:
            return []
        users = db.scalars(select(User).where(User.id.in_(ids))).all()
        found = {item.id: item for item in users}
        missing = [item for item in ids if item not in found]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"指定的调查员不存在：{'、'.join(str(item) for item in missing)}",
            )
        ordered = [found[item] for item in ids]
        for assignee in ordered:
            if assignee.status != "active":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"调查员「{assignee.real_name}」已停用，无法分配",
                )
            if tenant_code and assignee.tenant_code and assignee.tenant_code != tenant_code:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"调查员「{assignee.real_name}」不属于本调查批次所在区县，无法分配",
                )
            if not self._user_covers_region(assignee, region_code):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"调查员「{assignee.real_name}」的管辖区域不包含本调查批次范围，无法分配",
                )
        return ordered

    @staticmethod
    def assign_round_robin(bases: list, assignees: list[User], now) -> int:
        """把 ``bases`` 按顺序轮流分给 ``assignees``，返回已分配户数。

        串户调查的典型形态是「一个组的户交给若干调查员」，轮流均分最直观，
        且结果可复现：同一批数据 + 同一份名单，分出来的结果完全一致
        （``bases`` 按 cbfbm 升序构造，顺序稳定）。
        """
        if not assignees or not bases:
            return 0
        total = len(assignees)
        for index, base in enumerate(bases):
            assignee = assignees[index % total]
            base.assigned_to = assignee.id
            base.assigned_to_name = assignee.real_name
            base.assigned_at = now
        return len(bases)

    def default_new_task_assignee(self, db, batch: SurveyBatch, current_user: User) -> User | None:
        """批次内**新增**承包户时，默认落到谁名下。

        批次创建时已经把当时的全部户分完；之后在批次里「新增承包方」、或补建任务行
        都会产生新的户，如果不给归属人，列表里立刻又冒出「未分配」，
        与「创建后每个承包户都有归属对象」的口径冲突。

        口径（不猜）：
        ① 操作人本身就是本批次的调查员 → 归他（谁录的谁负责）；
        ② 操作人是本批次创建人 → 归他；
        ③ 其余情况（典型是管理员在别人的批次里补录）→ 留空，由批次创建人再分配。
        """
        if current_user is None or batch is None:
            return None
        if batch.created_by and batch.created_by == current_user.id:
            return current_user
        mine = db.scalar(
            select(func.count(SurveyCbfBase.id))
            .where(
                SurveyCbfBase.batch_id == batch.id,
                SurveyCbfBase.assigned_to == current_user.id,
            )
            .execution_options(skip_tenant_scope=True)
        ) or 0
        return current_user if mine else None

    def _user_covers_region(self, user: User, region_code: str | None) -> bool:
        if not region_code:
            return True
        if user.role and user.role.data_scope == "all":
            return True
        try:
            data_access_service.ensure_region_in_scope(user, region_code, detail="out of scope")
        except HTTPException:
            return False
        return True

    def _ensure_assignee_covers_batch(self, batch: SurveyBatch, assignee: User) -> None:
        """调查员的管辖范围必须覆盖批次范围。

        否则户分下去了、对方却因 ``ensure_code_in_scope`` 保存不了——
        这种「分配成功但干不了活」的静默失败比直接报错更难排查。
        """
        if self._user_covers_region(assignee, batch.region_code):
            return
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"调查员「{assignee.real_name}」的管辖区域不包含本调查批次范围，无法分配",
        )
