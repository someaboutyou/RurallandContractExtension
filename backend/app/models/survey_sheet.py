"""家庭成员变化摸底表数据模型（2026-10-10，礼泉试点《二轮到期后再延长三十年》摸底表）。

``survey_cbf_member_change_sheets``    承包农户家庭成员变化情况摸底表（一行一成员）

设计要点：

1. **不动现有 result 表**。摸底事件（二轮 1996~2018 / 延包 2018~2026 增减、
   公职人员属性……）是报表口径，与调查主数据的枚举/语义不同，混进去会污染
   主流程。
2. 《包地变化摸底表》不需要独立存储 —— 全部字段从合同/地块/权证数据推导，
   渲染时实时计算（2026-10-10 按用户要求去掉独立表与录入界面）。
3. 成员摸底数据的**填写入口在调查弹窗的「承包方及其家庭成员」面板**（每个
   成员行的「摸底」按钮），随「保存调查结果」一起提交，服务端在此表 upsert。
4. 增减事件按"时段 + 类型 + 时间"建模：二轮（1996~2018）与延包（2018~2026）
   各一组 ``event_type``（add_*=增加 / sub_*=减少）+ ``event_date``，
   模板按类型点亮对应列、把时间写进格子 —— 与纸质表的分列一一对应。
"""

from datetime import date
from sqlalchemy import Boolean, Date, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin, TimestampMixin


class SurveyCbfMemberChangeSheet(TenantScopedMixin, TimestampMixin, Base):
    """承包农户家庭成员变化情况摸底表（一行一成员，35 列宽表的存储形态）。"""

    __tablename__ = "survey_cbf_member_change_sheets"
    __table_args__ = (
        UniqueConstraint("tenant_code", "batch_id", "contractor_uid", "member_uid", name="uq_member_change_sheet_member"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    contractor_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    cbfbm: Mapped[str] = mapped_column(String(18), nullable=False, index=True)
    #: 关联 survey_cbf_jtcy_result.member_uid；手工补录的历史成员可为空（用证件号判重）
    member_uid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # ── 基础信息（生成时带出，可覆盖） ──
    member_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    id_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    #: 与户主关系（覆盖值；None=按成员 yhzgx 推导）
    relation_to_head: Mapped[str | None] = mapped_column(String(2), nullable=True)
    #: 是否二轮承包家庭成员（None=按 1996 口径由调查员判断；生成时按确权在册预填）
    is_second_round_member: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # ── 二轮承包 1996~2018 增减（一次事件：类型 + 时间） ──
    #: MEMBER_EVENT_TYPES 之一（add_birth/add_married_in/add_move_in/add_other/
    #: sub_death/sub_married_out/sub_move_out/sub_other；旧码 compensated/
    #: sub_compensated/withdraw 已由迁移拆到下方复选列并清空）
    sr_event_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    sr_event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: 该成员在二轮期已补地（独立复选框，与事件正交：新增人口不一定补了地）
    sr_compensated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: 该成员在二轮期被抽回或放弃承包地（独立复选框）
    sr_withdraw: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: 二轮期满后新增家庭人口（注1 勾稽列 16）
    sr_new_population: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── 延包 2018~2026 增减 ──
    ext_event_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    ext_event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: 该成员在延包期已补地（独立复选框）
    ext_compensated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: 该成员在延包期被抽回或放弃承包地（独立复选框）
    ext_withdraw: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: 延包或减并新增家庭人口
    ext_new_population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: ⚠️ 已废弃（2026-10-15）：列 28「成员增减变动时间」改由两期事件时间取
    #: 最后者推导（build_member_change_context），不再单独录入；列保留兼容历史数据。
    restructure_time: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: 有无增减家庭成员（None=按事件是否填写推导）
    has_change: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # ── 成员属性（全人工） ──
    #: 与本户经济关系（列30 是否本集体经济组织成员："1"/"0"/旧版自由文本）
    economic_relation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: 现户口所在地（列31，调查员填写）
    hukou_place: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: 现居住地（列32，调查员填写）
    residence_place: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: 现家庭成员中：国家机关工作人员
    is_civil_servant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    #: 事业单位人员
    is_institution_staff: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    #: 现有正式编制
    has_establishment: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    #: 现役军人
    is_active_military: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    #: 持有企业营业执照
    has_business_license: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    #: 其他：为国家公职人员的
    is_public_servant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    #: 公职人员现工作单位等备注（注4）
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: 最后一次编辑人
    updated_by_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
