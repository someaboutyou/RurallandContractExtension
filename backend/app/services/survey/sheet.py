"""摸底表数据服务（包地变化 / 家庭成员变化）。

口径（2026-10-09 确认，2026-10-10 按用户要求简化）：

- **包地变化摸底表无独立存储**：全部字段从合同/地块/权证数据推导，
  ``build_land_change_context`` 渲染时实时计算。
- **成员变化摸底表**：填写入口在调查弹窗「承包方及其家庭成员」面板的
  成员行「摸底」按钮，随「保存调查结果」提交；本服务负责按 member_uid
  upsert（``upsert_member_sheets``）与读回（``attach_member_sheet_info``）。
- **事实类字段不做必填闸门**（本系统 required-field-gate 的教训）：变化原因、
  事件时间、公职人员属性等全部可空。
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cbht import Cbht
from app.models.survey import (
    SurveyCbdkxxResult,
    SurveyCbfJtcyBase,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyChangeRecord,
    SurveyDkResult,
)
from app.models.survey_sheet import SurveyCbfMemberChangeSheet

logger = logging.getLogger(__name__)

# ── 选项常量（摸底表新增口径，暂无国标码表；前端 config 与此同源） ─────────

#: 表1 地块/户级变化原因（七分类 + 登记错误）
LAND_CHANGE_REASONS: list[tuple[str, str]] = [
    ("transfer", "转让"),
    ("swap", "互换"),
    ("expropriation", "征收征占"),
    ("adjustment", "调整土地"),
    ("new_land", "新增耕地"),
    ("inheritance", "继承"),
    ("registration_error", "登记错误"),
    ("other", "其他"),
]
LAND_CHANGE_REASON_LABELS = dict(LAND_CHANGE_REASONS)

#: 增减事件类型（与纸质摸底表列一一对应，2026-10-15 按用户口径再修）：
#: 每个时段 = 增加 4 列（新生/婚入/迁入/其他）+ 减少 4 列（去世/婚出/迁出/其他）。
#: ⛔「已补地人口」「抽回或放弃承包地」**不是事件**，是每期两个独立复选框
#: （新增人口不一定补了地、减少人口不一定立即抽回），见模型 sr_/ext_ ×
#: compensated/withdraw 四列；旧码 compensated/sub_compensated/withdraw 已由
#: 迁移 _upgrade_member_sheet_flow_split 拆到复选列。
MEMBER_EVENT_TYPES: list[tuple[str, str]] = [
    ("add_birth", "新生"),
    ("add_married_in", "婚入"),
    ("add_move_in", "迁入"),
    ("add_other", "其他"),
    ("sub_death", "去世"),
    ("sub_married_out", "婚出"),
    ("sub_move_out", "迁出"),
    ("sub_other", "其他"),
]
MEMBER_EVENT_LABELS = dict(MEMBER_EVENT_TYPES)

#: 旧版事件类型 → 新口径（打印/展示时归一，库里原值不动）。
#: sub_compensated/withdraw 已由迁移清空事件码、拆进复选列，无需映射。
LEGACY_EVENT_MAP: dict[str, str] = {
    "add_restore": "add_other",      # 恢复 → 其他
}

#: 系统变更类型（survey_change_records.change_type，与地块关联行 change_type 同口径）
#: → 摸底表"变化原因"七分类码。户级变更（信息变更/户主变更/成员维护/注销）不落地块，不参与映射。
CHANGE_TYPE_TO_SHEET_REASON: dict[str, str] = {
    "swap_parcels": "swap",        # 地块互换 → 互换
    "split_parcel": "adjustment",  # 切割地块 → 调整土地
    "split_household": "adjustment",  # 分户（地块划出）→ 调整土地
    "merge_household": "adjustment",  # 合户 → 调整土地
    "add_parcel": "new_land",      # 新增地块 → 新增耕地
    "remove_parcel": "other",      # 移除地块 → 其他
}

#: 纸质摸底表"变化原因"8 个勾选列（2026-10-12 按原件核对，顺序即打印列序）：
#: 0征收 1互换 2转让 3退耕还林 4退耕还草 5实测增减 6登记错误 7其他
#: → 系统七分类码的落列下标；退耕还林/还草暂无系统数据源（只能打印后人工勾选）。
LAND_REASON_TARGET_INDEX: dict[str, int] = {
    "expropriation": 0,       # 征收征占 → 征收
    "swap": 1,                # 互换
    "transfer": 2,            # 转让
    "new_land": 5,            # 新增耕地 → 实测增减
    "registration_error": 6,  # 登记错误
    "adjustment": 7,          # 调整土地 → 其他
    "inheritance": 7,         # 继承 → 其他
    "other": 7,               # 其他
}

#: 合同面积（㎡）→ 亩
_MU_DIVISOR = Decimal("666.67")


def _fmt_mu(value) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return ""


#: 地力等级码 → 大写序数（摸底表"质量等级"列印 一/二/三…，不印 01 这类码值）
_DL_DJ_CN = {str(i): c for i, c in enumerate("一二三四五六七八九十", start=1)}


def _quality_grade_cn(value) -> str:
    """地力等级码转大写序数：1/01 → 一 … 10 → 十；非数字码值原样返回。"""
    text = str(value or "").strip()
    if not text:
        return ""
    return _DL_DJ_CN.get(text.lstrip("0") or "0", text)


def _fmt_num(value) -> str:
    """调查记事用数字：整数不带小数（24），小数保留实值（27.27）；空/非法 → 空。"""
    if value is None:
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return ""
    if num == int(num):
        return str(int(num))
    text = f"{num:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _mu(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)) / _MU_DIVISOR
    except Exception:  # noqa: BLE001
        return None


def _fmt_date(val) -> str:
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, date):
        return val.strftime("%Y-%m-%d")
    return str(val or "")


#: 增加类 / 减少类事件码（在户状态机"进/出"判定用；与前端 config/surveySheets.js
#: 的 ADD_EVENT_VALUES / SUB_EVENT_VALUES 同源）。已补地、抽回或放弃涉地不涉成员
#: 进出，不参与判定。
_SHEET_ADD_EVENTS = {"add_birth", "add_married_in", "add_move_in", "add_other"}
_SHEET_SUB_EVENTS = {"sub_death", "sub_married_out", "sub_move_out", "sub_other"}


def _sheet_presence_p1_start(sheet: dict) -> str | None:
    """二轮期期初（1996 年）在户状态："in"/"out"/None（列7 未填，不可判定不限制）。

    ⛔ 期初只看列 7：列 7=否时即便二轮期填了增加类，1996 时点也是"不在户"
    （人是在期内才进的）——否则会误杀"非 1996 成员婚入/迁入"这一最常见的
    合法场景。增加事件对状态的影响只体现在 _sheet_presence_p2_start。
    """
    if sheet.get("isSecondRoundMember") is True:
        return "in"
    if sheet.get("isSecondRoundMember") is False:
        return "out"
    return None


def _sheet_presence_p2_start(sheet: dict) -> str | None:
    """延包期期初（2018 年）在户状态：二轮期事件决定进/出，否则顺延 1996 状态。"""
    ev = sheet.get("srEventType") or ""
    if ev in _SHEET_ADD_EVENTS:
        return "in"
    if ev in _SHEET_SUB_EVENTS:
        return "out"
    return _sheet_presence_p1_start(sheet)


def validate_member_sheet_flow(
    entries: list[tuple[str, dict]], name_map: dict[str, str] | None = None
) -> list[str]:
    """成员摸底「在户状态机」校验（2026-10-15 用户口径）：

    可以为空，但**必须有进才有出，出了还可以再进**——
      ① 期初（1996）不在户 ⇒ 二轮期不能填减少类；
      ② 期初在户 ⇒ 二轮期不能填增加类；
      ③ 截至 2018 仍在户 ⇒ 延包期不能填增加类（先出后进的回迁除外）；
      ④ 截至 2018 已不在户 ⇒ 延包期不能填减少类（要回迁请填增加类）；
      ⑤ 事件时间边界：二轮期 ≤ 2018-12-31，延包期 ≥ 2019-01-01（ISO 字符串
         字典序 = 时间序）。
    返回违规文案列表（逐条点名成员），空列表 = 通过。
    """
    problems: list[str] = []
    for uid, sheet in entries:
        if not isinstance(sheet, dict):
            continue
        name = (name_map or {}).get(uid) or uid[:8] or "未命名成员"
        sr = sheet.get("srEventType") or ""
        ext = sheet.get("extEventType") or ""
        p1 = _sheet_presence_p1_start(sheet)
        p2 = _sheet_presence_p2_start(sheet)
        if p1 == "out" and sr in _SHEET_SUB_EVENTS:
            problems.append(f"{name}：1996 年不是家庭成员，二轮期（1996—2018）不能填减少类事件（必须有进才有出）")
        if p1 == "in" and sr in _SHEET_ADD_EVENTS:
            problems.append(f"{name}：1996 年已是家庭成员，二轮期（1996—2018）不能再填增加类事件")
        if p2 == "in" and ext in _SHEET_ADD_EVENTS:
            problems.append(f"{name}：截至 2018 年仍在户，延包期（2018—2026）不能填增加类事件；如系先迁出再回迁，请先在二轮期填减少类事件")
        if p2 == "out" and ext in _SHEET_SUB_EVENTS:
            problems.append(f"{name}：截至 2018 年已不在户，延包期（2018—2026）不能填减少类事件；如需回迁请填增加类事件")
        # ⑤ 事件时间边界（与前端 SR_EVENT_DATE_MAX / EXT_EVENT_DATE_MIN 同源）
        sr_date = str(sheet.get("srEventDate") or "")[:10]
        ext_date = str(sheet.get("extEventDate") or "")[:10]
        if sr_date and sr_date > "2018-12-31":
            problems.append(f"{name}：二轮承包期事件时间不能晚于 2018 年 12 月 31 日")
        if ext_date and ext_date < "2019-01-01":
            problems.append(f"{name}：延包期事件时间不能早于 2019 年 1 月 1 日")
    return problems


class SurveySheetService:
    """摸底表的读取 / 保存 / 打印数据拼装。"""

    # ── 数据定位 ──────────────────────────────────────────────────────────

    def load_contractor(self, db: Session, cbfbm: str) -> SurveyCbfResult | None:
        return db.scalar(
            select(SurveyCbfResult)
            .where(SurveyCbfResult.cbfbm == cbfbm)
            .order_by(SurveyCbfResult.id.desc())
        )

    def load_contract(self, db: Session, cbfbm: str) -> tuple[str | None, Cbht | None]:
        """现行合同编号 + 合同行。

        ⛔ 优先延包**现行合同**（contract_status=active）：合同页面填的承包方式
        （cbfs='001' 等）与起止日期（cbqxq/cbqxz）都在这条上；地块关联的
        ``cbhtbm`` 指向的是二轮**原合同**（history/imported，普遍 cbfs='110'
        且无起止日期），直接用它会把摸底表的承包方式错勾成"其他方式承包"、
        起止日期留空。无现行合同时（未生成延包合同）回落原定位。
        """
        current = db.scalar(
            select(Cbht)
            .where(Cbht.cbfbm == cbfbm, Cbht.contract_status == "active")
            .order_by(Cbht.cbhtbm.desc())
        )
        if current is not None:
            return current.cbhtbm, current
        relation = db.scalar(
            select(SurveyCbdkxxResult)
            .where(
                SurveyCbdkxxResult.cbfbm == cbfbm,
                SurveyCbdkxxResult.result_status != "removed",
            )
            .order_by(SurveyCbdkxxResult.dkbm.asc())
        )
        if relation is None or not relation.cbhtbm:
            return None, None
        return relation.cbhtbm, db.scalar(select(Cbht).where(Cbht.cbhtbm == relation.cbhtbm))

    def load_parcels(self, db: Session, cbfbm: str) -> list[dict]:
        """该户名下地块（排除 removed），带出摸底表地块明细需要的字段。"""
        relations = db.scalars(
            select(SurveyCbdkxxResult)
            .where(
                SurveyCbdkxxResult.cbfbm == cbfbm,
                SurveyCbdkxxResult.result_status != "removed",
            )
            .order_by(SurveyCbdkxxResult.dkbm.asc())
        ).all()
        dkbms = [row.dkbm for row in relations if row.dkbm]
        dk_map: dict[str, SurveyDkResult] = {}
        if dkbms:
            for row in db.scalars(
                select(SurveyDkResult)
                .where(SurveyDkResult.dkbm.in_(dkbms), SurveyDkResult.result_status != "removed")
                .order_by(SurveyDkResult.dkbm.asc(), SurveyDkResult.id.desc())
            ):
                dk_map.setdefault(row.dkbm, row)

        parcels: list[dict] = []
        for relation in relations:
            dk = dk_map.get(relation.dkbm)
            scmj = float(dk.scmj) if dk is not None and dk.scmj is not None else 0.0
            # 合同面积（亩）：htmjm 已是亩；否则 htmj（㎡）换算
            if relation.htmjm is not None:
                original_mu = float(relation.htmjm)
            elif relation.htmj is not None:
                original_mu = float(relation.htmj) / 666.67
            else:
                original_mu = 0.0
            parcels.append({
                "dkbm": relation.dkbm or "",
                "dkmc": (dk.dkmc if dk else "") or "",
                "east": (dk.dkdz if dk else "") or "",
                "south": (dk.dknz if dk else "") or "",
                "west": (dk.dkxz if dk else "") or "",
                "north": (dk.dkbz if dk else "") or "",
                "area_mu": scmj / 666.67 if scmj else None,
                "original_area_mu": original_mu or None,
                # 登记面积 = 确权登记的合同面积（亩）；现有面积暂同登记面积，调查后人工改
                "registered_area_mu": original_mu or None,
                "current_area_mu": original_mu or None,
                "has_certificate": bool(relation.cbjyqzbm),
                "certificate_no": relation.cbjyqzbm or "",
                # 地块关联行自身的变更类型（swap_parcels 等），无变更时为 "none"
                "change_type": relation.change_type or "none",
                # 质量等级（地力等级 dldj，码值转大写序数：01 → 一）
                "quality_grade": _quality_grade_cn(dk.dldj if dk else ""),
            })
        return parcels

    def _land_change_map(self, db: Session, contractor_uid: str) -> dict[str, dict]:
        """dkbm → {"reason_text", "change_time"}，来源 survey_change_records（变更表）。

        口径与 ``land_parcel_service._build_removed_parcel_change_map`` 一致：
        排除已回退（rolled_back）的记录，同一地块取最近一次（id 降序 setdefault）。
        变化原因 = change_type 映射到摸底表七分类；变化时间 = occurred_at。
        """
        if not contractor_uid:
            return {}
        change_map: dict[str, dict] = {}
        records = db.scalars(
            select(SurveyChangeRecord)
            .where(
                SurveyChangeRecord.contractor_uid == contractor_uid,
                SurveyChangeRecord.change_status != "rolled_back",
            )
            .order_by(SurveyChangeRecord.id.desc())
        ).all()
        for record in records:
            before = record.before_summary or {}
            after = record.after_summary or {}
            if record.change_type == "swap_parcels":
                dkbms = [str(c).strip() for c in (before.get("swapped_out") or []) if str(c).strip()]
            elif record.change_type == "remove_parcel":
                dkbm = str(after.get("dkbm") or "").strip()
                dkbms = [dkbm] if dkbm else []
            elif record.change_type == "split_parcel":
                dkbm = str(before.get("dkbm") or after.get("original_dkbm") or "").strip()
                dkbms = [dkbm] if dkbm else []
            elif record.change_type == "split_household":
                dkbms = [str(c).strip() for c in (after.get("moved_parcels") or []) if str(c).strip()]
            elif record.change_type == "add_parcel":
                dkbm = str(after.get("dkbm") or "").strip()
                dkbms = [dkbm] if dkbm else []
            else:
                dkbms = []
            reason_code = CHANGE_TYPE_TO_SHEET_REASON.get(record.change_type)
            # 变化时间：occurred_at（变化发生时间，现有流程未填）→ 回退 investigated_at（变更录入时间）
            occurred = record.occurred_at or record.investigated_at
            for dkbm in dkbms:
                change_map.setdefault(dkbm, {
                    "reason_code": reason_code,
                    "reason_text": LAND_CHANGE_REASON_LABELS.get(reason_code, "") if reason_code else "",
                    "change_time": _fmt_date(occurred),
                })
        return change_map

    # ── 表2：家庭成员变化摸底表 ──────────────────────────────────────────

    def _ensure_member_rows(
        self, db: Session, *, batch_id: int, contractor_uid: str, cbfbm: str,
        tenant_code: str, region_code: str, editor_name: str | None,
    ) -> list[SurveyCbfMemberChangeSheet]:
        members = db.scalars(
            select(SurveyCbfJtcyResult)
            .where(
                SurveyCbfJtcyResult.cbfbm == cbfbm,
                SurveyCbfJtcyResult.member_result_status != "removed",
            )
            .order_by(SurveyCbfJtcyResult.id.asc())
        ).all()
        base_uids = {
            uid
            for uid in db.scalars(
                select(SurveyCbfJtcyBase.member_uid).where(
                    SurveyCbfJtcyBase.cbfbm == cbfbm,
                    SurveyCbfJtcyBase.member_uid.isnot(None),
                )
            )
        }
        existing = {
            row.member_uid: row
            for row in db.scalars(
                select(SurveyCbfMemberChangeSheet).where(
                    SurveyCbfMemberChangeSheet.batch_id == batch_id,
                    SurveyCbfMemberChangeSheet.contractor_uid == contractor_uid,
                    SurveyCbfMemberChangeSheet.member_uid.isnot(None),
                )
            )
        }
        rows: list[SurveyCbfMemberChangeSheet] = []
        for member in members:
            row = existing.get(member.member_uid)
            if row is None:
                row = SurveyCbfMemberChangeSheet(
                    tenant_code=tenant_code,
                    region_code=region_code,
                    batch_id=batch_id,
                    contractor_uid=contractor_uid,
                    cbfbm=cbfbm,
                    member_uid=member.member_uid,
                    member_name=member.cyxm,
                    id_no=member.cyzjhm,
                    relation_to_head=member.yhzgx,
                    # 确权时点在册 ⇒ 预填"是二轮家庭成员"（1996 口径由调查员改）
                    is_second_round_member=member.member_uid in base_uids,
                    # 延包时段已知事实预填：死亡 / 婚出
                    ext_event_type=self._guess_ext_event(member),
                    updated_by_name=editor_name,
                )
                db.add(row)
                db.flush()
            # 身份四件套（姓名/证件号/电话/与户主关系）永远以成员调查结果表为准：
            # 摸底弹窗不允许编辑它们，且历史摸底行（如 upsert_member_sheets 只带
            # member_uid 建的行、旧版面板残留）可能为空 ⇒ 每次渲染前对齐自愈。
            row.member_name = member.cyxm
            row.id_no = member.cyzjhm
            row.phone = member.phone
            row.relation_to_head = member.yhzgx
            rows.append(row)
        return rows

    @staticmethod
    def _guess_ext_event(member: SurveyCbfJtcyResult) -> str | None:
        if getattr(member, "member_result_status", "") == "removed":
            if getattr(member, "is_deceased", False):
                return "sub_death"
            if getattr(member, "is_married_out_woman", False):
                return "sub_married_out"
        return None

    # ── 成员摸底数据与调查结果的合流（填写入口 = 家庭成员面板） ──────────

    #: 前端成员行 ``sheet`` 子对象的空值形态（v-model 需要确定的键）
    EMPTY_MEMBER_SHEET: dict = {
        "isSecondRoundMember": None,
        "srEventType": "",
        "srEventDate": None,
        "srCompensated": False,
        "srWithdraw": False,
        "extEventType": "",
        "extEventDate": None,
        "extCompensated": False,
        "extWithdraw": False,
        "hasChange": None,
        "economicRelation": "",
        "hukouPlace": "",
        "residencePlace": "",
        "isCivilServant": None,
        "isInstitutionStaff": None,
        "hasEstablishment": None,
        "isActiveMilitary": None,
        "hasBusinessLicense": None,
        "isPublicServant": None,
        "remark": "",
    }

    def member_sheet_payload(self, row: SurveyCbfMemberChangeSheet | None) -> dict:
        """一行摸底数据 → 前端成员行 sheet 子对象（缺省全空）。"""
        payload = dict(self.EMPTY_MEMBER_SHEET)
        if row is None:
            return payload
        payload.update({
            "isSecondRoundMember": row.is_second_round_member,
            "srEventType": row.sr_event_type or "",
            "srEventDate": _fmt_date(row.sr_event_date) or None,
            "srCompensated": bool(row.sr_compensated),
            "srWithdraw": bool(row.sr_withdraw),
            "extEventType": row.ext_event_type or "",
            "extEventDate": _fmt_date(row.ext_event_date) or None,
            "extCompensated": bool(row.ext_compensated),
            "extWithdraw": bool(row.ext_withdraw),
            "hasChange": row.has_change,
            "economicRelation": row.economic_relation or "",
            "hukouPlace": row.hukou_place or "",
            "residencePlace": row.residence_place or "",
            "isCivilServant": row.is_civil_servant,
            "isInstitutionStaff": row.is_institution_staff,
            "hasEstablishment": row.has_establishment,
            "isActiveMilitary": row.is_active_military,
            "hasBusinessLicense": row.has_business_license,
            "isPublicServant": row.is_public_servant,
            "remark": row.remark or "",
        })
        return payload

    def attach_member_sheet_info(
        self, db: Session, *, batch_id: int, contractor_uid: str,
        members_payload: list[dict],
    ) -> None:
        """get_result 序列化后调用：按 member_uid 把摸底数据并进 familyMembers。

        就地修改传入的成员 dict 列表（无摸底行的成员补全空 sheet 对象）。
        """
        if not members_payload:
            return
        rows = {
            row.member_uid: row
            for row in db.scalars(
                select(SurveyCbfMemberChangeSheet).where(
                    SurveyCbfMemberChangeSheet.batch_id == batch_id,
                    SurveyCbfMemberChangeSheet.contractor_uid == contractor_uid,
                )
            )
        }
        for member in members_payload:
            uid = member.get("memberUid") or ""
            row = rows.get(uid)
            payload = self.member_sheet_payload(row)
            if row is None:
                # 「是否二轮家庭成员」默认口径（2026-10-11 用户确认）：库里的成员是
                # 历史数据导入的 ⇒ 既有成员默认"是"；系统新增（状态仍为 added）默认"否"。
                # 只兜底"无摸底行"的成员；有行的保持落库原值（含显式"未填"）。
                payload["isSecondRoundMember"] = member.get("memberResultStatus") != "added"
            member["sheet"] = payload

    def upsert_member_sheets(
        self, db: Session, *, batch_id: int, contractor_uid: str, cbfbm: str,
        tenant_code: str, region_code: str,
        member_entries: list[tuple[str, dict]], editor_name: str | None = None,
    ) -> None:
        """保存调查结果时调用：把成员行携带的 sheet 子对象 upsert 进摸底表。

        ``member_entries``：[(member_uid, sheet_dict), ...]，只处理带 sheet
        dict 的条目（老客户端 / 合户分户等不带 sheet 的路径自然跳过）。
        """
        if not member_entries:
            return
        entries = [(uid, sheet) for uid, sheet in member_entries if isinstance(sheet, dict)]
        if not entries:
            return
        # 在户状态机闸门（与前端 validateMemberSheetFlow 同判据）：
        # 违规整单 400（含逐条点名），与这次保存一并回滚 —— 不许半截落库。
        uid_list = [uid for uid, _ in entries if uid]
        name_map: dict[str, str] = {}
        if uid_list:
            from fastapi import HTTPException

            name_map = dict(
                db.execute(
                    select(
                        SurveyCbfJtcyResult.member_uid, SurveyCbfJtcyResult.cyxm
                    ).where(SurveyCbfJtcyResult.member_uid.in_(uid_list))
                ).all()
            )
            problems = validate_member_sheet_flow(entries, name_map)
            if problems:
                raise HTTPException(status_code=400, detail="；".join(problems))
        existing = {
            row.member_uid: row
            for row in db.scalars(
                select(SurveyCbfMemberChangeSheet).where(
                    SurveyCbfMemberChangeSheet.batch_id == batch_id,
                    SurveyCbfMemberChangeSheet.contractor_uid == contractor_uid,
                    SurveyCbfMemberChangeSheet.member_uid.in_([uid for uid, _ in entries]),
                )
            )
        }
        for uid, sheet in entries:
            if not uid:
                continue
            row = existing.get(uid)
            if row is None:
                row = SurveyCbfMemberChangeSheet(
                    tenant_code=tenant_code,
                    region_code=region_code or "",
                    batch_id=batch_id,
                    contractor_uid=contractor_uid,
                    cbfbm=cbfbm,
                    member_uid=uid,
                )
                db.add(row)
            # 以下各项是现行摸底弹窗（2026-10-15：事件下拉只含进出 8 类，已补地/
            # 抽回拆为每期独立复选框，列 28 变动时间改推导）提交的字段，每次保存
            # 全量覆盖（未填 → None/空/False）。
            row.is_second_round_member = sheet.get("isSecondRoundMember")
            row.sr_event_type = sheet.get("srEventType") or None
            row.sr_event_date = self._parse_date(sheet.get("srEventDate"))
            row.sr_compensated = bool(sheet.get("srCompensated"))
            row.sr_withdraw = bool(sheet.get("srWithdraw"))
            row.ext_event_type = sheet.get("extEventType") or None
            row.ext_event_date = self._parse_date(sheet.get("extEventDate"))
            row.ext_compensated = bool(sheet.get("extCompensated"))
            row.ext_withdraw = bool(sheet.get("extWithdraw"))
            row.economic_relation = sheet.get("economicRelation") or None  # 列30："1"/"0"/""
            row.hukou_place = (sheet.get("hukouPlace") or "").strip() or None      # 列31 现户口所在地
            row.residence_place = (sheet.get("residencePlace") or "").strip() or None  # 列32 现居住地
            row.is_civil_servant = sheet.get("isCivilServant")             # 列34
            row.is_institution_staff = sheet.get("isInstitutionStaff")     # 列33
            row.remark = sheet.get("remark") or None
            # ⛔ restructure_time 不再写入（列 28 由两期事件时间取最后者推导），
            # 历史值保留在列里不动。
            # ⚠️ 以下字段已从弹窗移除（纸质原件无对应录入列）：只在客户端显式
            # 携带时才写，避免精简后的保存把历史值抹成 None。
            if "srNewPopulation" in sheet:
                row.sr_new_population = self._parse_int(sheet.get("srNewPopulation"))
            if "extNewPopulation" in sheet:
                row.ext_new_population = self._parse_int(sheet.get("extNewPopulation"))
            if "hasChange" in sheet:
                row.has_change = sheet.get("hasChange")
            if "hasEstablishment" in sheet:
                row.has_establishment = sheet.get("hasEstablishment")
            if "isActiveMilitary" in sheet:
                row.is_active_military = sheet.get("isActiveMilitary")
            if "hasBusinessLicense" in sheet:
                row.has_business_license = sheet.get("hasBusinessLicense")
            if "isPublicServant" in sheet:
                row.is_public_servant = sheet.get("isPublicServant")
            if editor_name:
                row.updated_by_name = editor_name

    @staticmethod
    def _norm_economic_relation(value: str | None) -> bool:
        """列 30「属本集体经济组织人口」归一为布尔。

        新版弹窗存 "1"/"0"/""；旧版自由文本（如"本户成员"）按非空=是 兼容，
        显式 "0"/"否" = 否，空 = 否。
        """
        raw = (value or "").strip()
        return bool(raw) and raw not in ("0", "否")

    # ── 打印模板上下文 ───────────────────────────────────────────────────

    def build_land_change_context(self, db: Session, *, cbfbm: str) -> dict:
        """表1 打印数据包 —— 纯现有数据推导，无独立存储（2026-10-10 简化）。

        户级人工字段（调查记事/审核意见等）输出空白，打印后手工填写。
        """
        contractor = self.load_contractor(db, cbfbm)
        cbhtbm, contract = self.load_contract(db, cbfbm)
        parcels = self.load_parcels(db, cbfbm)

        first = parcels[0] if parcels else {}
        mode_auto = ""
        if contract is not None and contract.cbfs:
            mode_auto = "family" if str(contract.cbfs) in {"001", "家庭承包"} else "other"
        sheet = {
            "contractNo": (contract.cbhtbm if contract else "") or "",
            "originalContractNo": (contract.ycbhtbm if contract else "") or "",
            "hasContract": bool(contract),
            "contractSignDate": _fmt_date(contract.qdsj if contract else None),
            "contractStartDate": _fmt_date(contract.cbqxq if contract else None),
            "contractEndDate": _fmt_date(contract.cbqxz if contract else None),
            "familyContractMode": mode_auto,
            "hasCertificate": bool(first.get("has_certificate")),
            "certificateNo": first.get("certificate_no") or "",
            # ── 调查/审核四项：优先调查任务字段，回落公示调查/公示审核字段，无值留空线 ──
            "surveyorName": (contractor.investigator_name if contractor else "")
            or (contractor.cbfdcy if contractor else "")
            or "",
            "surveyDate": _fmt_date(contractor.investigated_at if contractor else None)
            or _fmt_date(contractor.cbfdcrq if contractor else None),
            "auditorName": (contractor.reviewer_name if contractor else "")
            or (contractor.gsshr if contractor else "")
            or "",
            "auditDate": _fmt_date(contractor.reviewed_at if contractor else None)
            or _fmt_date(contractor.gsshrq if contractor else None),
            # ── 以下为人工字段，无存储 ⇒ 留空打印后手填 ──
            "originalRepresentative": "",
            "surveyNote": "",
            "auditNote": "",
            "remark": "",
        }

        item_rows = []
        total_area = 0.0
        total_original = 0.0
        total_registered = 0.0
        expropriation_area = 0.0
        expropriation_year = ""
        change_map = self._land_change_map(
            db, (contractor.contractor_uid if contractor else "") or ""
        )
        for parcel in parcels:
            area_mu = float(parcel["area_mu"] or 0)
            original_mu = float(parcel["original_area_mu"] or 0)
            registered_mu = float(parcel["registered_area_mu"] or 0)
            current_mu = float(parcel["current_area_mu"] or 0)
            total_area += current_mu
            total_original += original_mu
            total_registered += registered_mu
            # 变化原因/时间：优先变更表（survey_change_records）；无记录时回落
            # 地块关联行自身的 change_type（只有原因、无时间）
            info = change_map.get(parcel["dkbm"]) or {}
            reason_code = info.get("reason_code")
            if reason_code is None and parcel.get("change_type", "none") != "none":
                reason_code = CHANGE_TYPE_TO_SHEET_REASON.get(parcel["change_type"])
            reason_text = LAND_CHANGE_REASON_LABELS.get(reason_code, "") if reason_code else ""
            change_time = info.get("change_time") or ""
            # 勾选列落列下标（8 列：征收/互换/转让/退耕还林/退耕还草/实测增减/登记错误/其他）
            reason_index = LAND_REASON_TARGET_INDEX.get(reason_code) if reason_code else None
            if reason_index == 0:  # 征收：调查记事"合同耕地征收 __ 亩"自动带数
                expropriation_area += area_mu
                year = (change_time or "")[:4]
                if year.isdigit() and not expropriation_year:
                    expropriation_year = year
            item_rows.append({
                "dkbm": parcel["dkbm"],
                "dkmc": parcel["dkmc"],
                "east": parcel["east"],
                "south": parcel["south"],
                "west": parcel["west"],
                "north": parcel["north"],
                "areaMu": _fmt_mu(area_mu or None),
                "originalAreaMu": _fmt_mu(original_mu or None),
                "registeredAreaMu": _fmt_mu(registered_mu or None),
                "currentAreaMu": _fmt_mu(current_mu or None),
                "qualityGrade": parcel.get("quality_grade") or "",
                "changeReasonText": reason_text,
                "reasonIndex": reason_index,
                "changeTime": change_time,
                "remark": "",
            })

        # 调查记事预印句式所需的人口/面积数字
        member_count = contractor.cbfcysl if contractor and contractor.cbfcysl else 0
        per_capita = (total_original / member_count) if member_count and total_original else None
        note = {
            # 二轮延包分地人数 / 二轮承包耕地合计 / 人均（有数才印，无数留空线）
            "memberCount": str(member_count) if member_count else "",
            "secondRoundAreaMu": _fmt_num(total_original) if total_original else "",
            "perCapitaMu": _fmt_num(per_capita) if per_capita else "",
            # 2018 年确权面积 ≈ 登记颁证时面积合计
            "confirmAreaMu": _fmt_num(total_registered) if total_registered else "",
            # 合同耕地征收：征收地块面积合计 + 首个变更年份
            "expropriationAreaMu": _fmt_num(expropriation_area) if expropriation_area else "",
            "expropriationYear": expropriation_year,
        }
        issuer_parts = self._load_issuer_parts(db, cbfbm)
        return {
            "contractor": {
                "name": (contractor.cbfmc if contractor else "") or "",
                # 承包方代表身份证号（表头"承包方（代表）身份证号"栏）
                "repIdNo": (contractor.cbfzjhm if contractor else "") or "",
                "code": cbfbm,
                "groupName": (contractor.group_region_name if contractor else "") or "",
                # 发包方名称分段（贴合原件：旗县＿苏木（镇）＿嘎查（村）＿自然村）
                "issuerCounty": issuer_parts["county"],
                "issuerTown": issuer_parts["town"],
                "issuerVillage": issuer_parts["village"],
                "issuerHamlet": issuer_parts["hamlet"],
                "issuerCode": cbfbm[:14] if len(cbfbm) >= 14 else "",
            },
            "sheet": sheet,
            "items": item_rows,
            "totals": {
                "originalAreaMu": _fmt_mu(total_original or None),
                "currentAreaMu": _fmt_mu(total_area or None),
            },
            "memberCount": member_count,
            "note": note,
            "changeReasonOptions": [dict(code=c, label=l) for c, l in LAND_CHANGE_REASONS],
        }

    def build_member_change_context(self, db: Session, *, cbfbm: str) -> dict:
        """表2 打印数据包。"""
        contractor = self.load_contractor(db, cbfbm)
        contractor_uid = (contractor.contractor_uid if contractor else "") or cbfbm
        tenant_code = getattr(contractor, "tenant_code", None) or ""
        region_code = (contractor.group_region_code if contractor else None) or region_code_of(cbfbm)
        # 该户最新批次（SurveyCbfResult 没有 batch_id，从摸底行本身取）
        latest = db.scalar(
            select(SurveyCbfMemberChangeSheet.batch_id)
            .where(SurveyCbfMemberChangeSheet.contractor_uid == contractor_uid)
            .order_by(SurveyCbfMemberChangeSheet.batch_id.desc())
        )
        batch_id = int(latest or 0)
        if not batch_id:
            from app.models.survey import SurveyCbfBase

            latest_task = db.scalar(
                select(SurveyCbfBase.batch_id)
                .where(SurveyCbfBase.contractor_uid == contractor_uid)
                .order_by(SurveyCbfBase.batch_id.desc())
            )
            batch_id = int(latest_task or 0)
        rows = self._ensure_member_rows(
            db, batch_id=batch_id, contractor_uid=contractor_uid, cbfbm=cbfbm,
            tenant_code=tenant_code, region_code=region_code, editor_name=None,
        )
        db.commit()

        # 与户主关系：码值 → 文案（字典优先，兜底同一份常量，见 relation_codes）
        from app.services.relation_codes import relation_labels

        relations = relation_labels(db)

        # 是否"土地确权登记发证家庭成员"（列 6）：确权时点在册（base 表有此成员）
        base_uids = {
            uid
            for uid in db.scalars(
                select(SurveyCbfJtcyBase.member_uid).where(
                    SurveyCbfJtcyBase.cbfbm == cbfbm,
                    SurveyCbfJtcyBase.member_uid.isnot(None),
                )
            )
        }

        def _norm_event(value: str | None) -> str:
            raw = value or ""
            return LEGACY_EVENT_MAP.get(raw, raw)

        # 现是否在户（列 29 现有家庭成员人数：已去世/婚出/迁出等 removed 成员不点亮）
        # ⚠️ select(单列) 经 db.scalars 返回字符串本身，直接迭代，不能再取属性
        live_uids = {
            uid
            for uid in db.scalars(
                select(SurveyCbfJtcyResult.member_uid).where(
                    SurveyCbfJtcyResult.cbfbm == cbfbm,
                    SurveyCbfJtcyResult.member_result_status != "removed",
                    SurveyCbfJtcyResult.member_uid.isnot(None),
                )
            )
            if uid
        }

        member_rows = []
        for row in rows:
            sr_type = _norm_event(row.sr_event_type)
            ext_type = _norm_event(row.ext_event_type)
            in_base = (row.member_uid or "") in base_uids
            participated = bool(row.is_second_round_member)
            member_rows.append({
                "memberName": row.member_name or "",
                "idNo": row.id_no or "",
                "phone": row.phone or "",
                "relationText": relations.get(row.relation_to_head or "", row.relation_to_head or ""),
                # 列 5 参与二轮承包人口（模板注 1 行级口径：5=7-12-17-22-27，
                # 由打印宏按 列7 − 已补地 − 抽回 推导，这里给原始值）/
                # 列 6 土地确权登记家庭成员（确权时点在册，系统推导）/
                # 列 7 其中：1996 年二轮承包家庭成员 —— 调查员直填（isSecondRoundMember），
                # ⛔ 不与确权在册求交：1996 年在册但确权漏登的人也要点亮列 7。
                "participatedSecondRound": participated,
                "inRegister": in_base,
                "is1996Member": bool(row.is_second_round_member),
                "srEventType": sr_type,
                "srEventDate": _fmt_date(row.sr_event_date),
                "srCompensated": bool(row.sr_compensated),
                "srWithdraw": bool(row.sr_withdraw),
                "extEventType": ext_type,
                "extEventDate": _fmt_date(row.ext_event_date),
                "extCompensated": bool(row.ext_compensated),
                "extWithdraw": bool(row.ext_withdraw),
                # 列 28 成员增减变动时间：两期事件时间取最后者（ISO 日期字典序=时间序）
                "changeTime": max(
                    (_fmt_date(row.sr_event_date), _fmt_date(row.ext_event_date)),
                    default="",
                ),
                # 列 29 现有家庭成员人数（removed 成员不点亮）
                "inHousehold": (row.member_uid or "") in live_uids,
                # 列 30 为本集体经济组织成员人口：归一为布尔（"0"/"否" = 否，
                # 其余非空文本 = 是 —— 兼容旧版自由文本如"本户成员"）
                "economicRelation": self._norm_economic_relation(row.economic_relation),
                # 列 31 现户口所在地 / 列 32 现居住地（调查员填写）
                "hukouPlace": row.hukou_place or "",
                "residencePlace": row.residence_place or "",
                # 列 33 财政供养人员、国企正式编制人员、部队军官的人口
                "isFiscalSupported": bool(
                    row.is_institution_staff or row.has_establishment
                    or row.is_active_military or row.is_civil_servant
                ),
                # 列 34 其中：为国家公务员的
                "isCivilServant": bool(row.is_civil_servant),
                "remark": row.remark or "",
            })

        # 调查记事预印句的人口统计
        add_count = sum(
            1 for r in member_rows
            if r["srEventType"].startswith("add_") or r["extEventType"].startswith("add_")
        )
        sub_count = sum(
            1 for r in member_rows
            if r["srEventType"].startswith("sub_") or r["extEventType"].startswith("sub_")
        )
        compensated_count = sum(
            1 for r in member_rows if r["srCompensated"] or r["extCompensated"]
        )
        withdraw_count = sum(
            1 for r in member_rows if r["srWithdraw"] or r["extWithdraw"]
        )
        note_stats = {
            # 1996 年落实二轮延包时户代表（无数据源，留空手填）
            "rep1996": "",
            # 2018 年土地确权时户代表 = 承包方（户）代表
            "rep2018": (contractor.cbfmc if contractor else "") or "",
            # 1996 年落实二轮延包时户内人口 / 其中参与二轮延包
            "pop1996": sum(1 for r in member_rows if r["participatedSecondRound"]),
            "joinExt": sum(1 for r in member_rows if r["participatedSecondRound"]),
            "addCount": add_count,
            "subCount": sub_count,
            "currentCount": sum(1 for r in member_rows if r["inHousehold"]),
            "registerCount": sum(1 for r in member_rows if r["inRegister"]),
            "collectiveCount": sum(1 for r in member_rows if r["economicRelation"]),
            "fiscalCount": sum(1 for r in member_rows if r["isFiscalSupported"]),
            "civilCount": sum(1 for r in member_rows if r["isCivilServant"]),
            "compensatedCount": compensated_count,
            "withdrawCount": withdraw_count,
        }
        issuer_parts = self._load_issuer_parts(db, cbfbm)
        return {
            "contractor": {
                "name": (contractor.cbfmc if contractor else "") or "",
                "code": cbfbm,
                "groupName": (contractor.group_region_name if contractor else "") or "",
                # 表头栏"横线填值"：发包方（集体组织）名称/编码 + 邮政编码
                "postcode": (contractor.yzbm if contractor else "") or "",
                # 发包方名称分段（贴合原件：旗县＿苏木（镇）＿嘎查（村）＿自然村）
                "issuerCounty": issuer_parts["county"],
                "issuerTown": issuer_parts["town"],
                "issuerVillage": issuer_parts["village"],
                "issuerHamlet": issuer_parts["hamlet"],
                "issuerName": "".join(issuer_parts.values()),
                "issuerCode": cbfbm[:14] if len(cbfbm) >= 14 else "",
            },
            # 落款四项：调查员/调查日期（保存调查结果时写 investigated_at）、
            # 审核人/审核日期（确认调查结果时写 reviewer_*，撤回确认时清空）。
            # contractor 即该户最新 SurveyCbfResult；无 result 行（手工户）时留空手填。
            "signatures": {
                "investigatorName": (contractor.investigator_name if contractor else "") or "",
                "investigatedAt": _fmt_date(contractor.investigated_at if contractor else None),
                "reviewerName": (contractor.reviewer_name if contractor else "") or "",
                "reviewedAt": _fmt_date(contractor.reviewed_at if contractor else None),
            },
            "rows": member_rows,
            "noteStats": note_stats,
        }

    @staticmethod
    def _load_issuer_parts(db: Session, cbfbm: str) -> dict:
        """发包方名称分段（贴合纸质原件：「旗县 ＿ 苏木（镇） ＿ 嘎查（村） ＿ 自然村」）。

        从 ``regions`` 表按 6/9/12/14 位码逐级取名；区域表查不到时整体回退
        发包方调查记录的 ``fbfmc``（放进 county 段，其余留空）。
        """
        empty = {"county": "", "town": "", "village": "", "hamlet": ""}
        if len(cbfbm) < 14:
            return empty
        from app.models.region import Region
        from app.models.survey import SurveyFbfResult

        codes = [cbfbm[:6], cbfbm[:9], cbfbm[:12], cbfbm[:14]]
        names = dict(
            db.execute(select(Region.code, Region.name).where(Region.code.in_(codes))).all()
        )
        parts = dict(empty)
        found_any = False
        for key, code in zip(("county", "town", "village", "hamlet"), codes):
            if names.get(code):
                parts[key] = names[code]
                found_any = True
        if not found_any:
            issuer = db.scalar(
                select(SurveyFbfResult)
                .where(SurveyFbfResult.fbfbm == cbfbm[:14])
                .order_by(SurveyFbfResult.id.desc())
            )
            parts["county"] = (issuer.fbfmc if issuer else "") or ""
        return parts

    @classmethod
    def _load_issuer_name(cls, db: Session, cbfbm: str) -> str:
        """发包方全称（区域链拼接，兜底 fbfmc）—— 供非分段场景复用。"""
        parts = cls._load_issuer_parts(db, cbfbm)
        return "".join(parts.values())

    # ── 工具 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_date(value) -> date | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    @staticmethod
    def _parse_decimal(value) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _parse_int(value) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


def region_code_of(cbfbm: str) -> str:
    """从承包方编码推导区域码（12 位县级码前缀），兜底用。"""
    from app.services.data_access_service import data_access_service

    try:
        return data_access_service.normalize_region_code(cbfbm)
    except Exception:  # noqa: BLE001
        return (cbfbm or "")[:12]


survey_sheet_service = SurveySheetService()
