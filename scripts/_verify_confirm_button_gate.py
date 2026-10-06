# -*- coding: utf-8 -*-
"""离实验收：「保存调查结果 → 状态推进 → 界面出现动作入口」这条链，四层都要证明。

覆盖**两侧**（承包方 + 发包方），被验收的改动（2026-09-27）：
  ① 后端保存时由**服务端**裁定成果状态（`base.py::resolve_saved_survey_status`），
     不再照单全收前端回传的旧值 —— 承包方 `result.py::update_result`、
     发包方 `issuer.py::update_issuer`、以及承包方录入顺带更新发包方的
     `result.py`（issuer_payload 分支）三处同源；
  ② 「确认 / 跳过」按钮的显示集合与后端准入集合**同源**
     （`frontend/src/config/surveyStatus.js` ⟷ `base.py` 的
     `confirmable_survey_statuses` / `terminal_survey_statuses` / `locked_survey_statuses`）；
  ③ 发包方 `issuer.py::create_issuer` 补回缺失的 result 构造 + 落库顺序（原为 NameError 500）；
  ④ 存量回填（6 行承包方 result / 4 行 base），由 `_backfill_survey_status_surveyed.py` 负责。
     发包方**零回填**：3707 行全库 change_type=none / is_changed=false，没有任何"被人工改过"
     的痕迹可作判据（见 `_probe_fbf_status.py`）。

四层（与 skill `backend-permission-verify` 同口径）：
  L1 静态核查 —— 调用点有没有漏改、还有没有残留硬编码字面量
  L2 服务层真值表 —— 每条分支都得有预期结果
  L3 跨语言同源 —— 前端常量与后端常量必须逐元素相等
  L4 集成（零落库）—— 用真实库、真实 service 跑一遍保存，**事务回滚**：
      L4a 承包方：库里 not_surveyed + 前端原样回传 not_surveyed → 落成 surveyed；
      L4b 发包方：同上，走 `update_issuer`。

用法：runtime/windows/python/python.exe scripts/_verify_confirm_button_gate.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.update({
    "DATABASE_HOST": "127.0.0.1",
    "DATABASE_PORT": "15432",
    "DATABASE_NAME": "erlunyanbao",
    "DATABASE_USER": "RurallandContractExtension",
    "DATABASE_PASSWORD": "dK9venBRbBRewDFAWYHRGdCM",
    "SECRET_KEY": "verify-only",
})
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal, set_current_user  # noqa: E402
from app.models.survey import (  # noqa: E402
    SurveyBatch,
    SurveyCbfBase,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyFbfBase,
    SurveyFbfResult,
)
from app.models.user import User  # noqa: E402
from app.services.survey import survey_service  # noqa: E402
from app.services.survey.base import SurveyServiceBase  # noqa: E402

RESULTS: list[tuple[bool, str, str]] = []
NOTES: list[str] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    RESULTS.append((bool(ok), name, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  —— {detail}" if detail else ""))


def note(text: str) -> None:
    NOTES.append(text)
    print(f"  [NOTE] {text}")


# ---------------------------------------------------------------- L1 静态核查
def strip_comments(text: str) -> str:
    """只留代码行，去掉整行注释。

    ⛔ 必须去注释再断言：本次改动**特意在注释里回引了旧写法**
    （「不能写成 `payload.get("surveyStatus") or "surveyed"`」），
    朴素子串匹配会把注释也算命中，产出假阳性 FAIL。
    """
    return "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith(("#", "//"))
    )


def l1_static() -> None:
    print("\n=== L1 静态核查：调用点有没有漏改 ===")

    view = strip_comments((ROOT / "frontend/src/views/SurveyView.vue").read_text(encoding="utf-8"))
    dialog = strip_comments(
        (ROOT / "frontend/src/components/survey/view/ContractorResultDialog.vue").read_text(encoding="utf-8")
    )
    issuer_dialog = strip_comments(
        (ROOT / "frontend/src/components/survey/view/IssuerSurveyDialog.vue").read_text(encoding="utf-8")
    )
    task_py = strip_comments((ROOT / "backend/app/services/survey/task.py").read_text(encoding="utf-8"))
    result_py = strip_comments((ROOT / "backend/app/services/survey/result.py").read_text(encoding="utf-8"))
    issuer_py = strip_comments((ROOT / "backend/app/services/survey/issuer.py").read_text(encoding="utf-8"))

    # ---- 承包方（上一轮） ----
    check("CONFIRMABLE_SURVEY_STATUSES.includes(row.taskStatus)" in view,
          "SurveyView 列表「确认」按钮已改用同源常量")
    check("row.taskStatus === 'surveyed'" not in view,
          "SurveyView 里已无 `=== 'surveyed'` 硬编码（残留=漏改）")
    check("CONFIRMABLE_SURVEY_STATUSES.includes(resultForm.surveyStatus)" in dialog,
          "ContractorResultDialog 弹窗「确认调查结果」已改用同源常量")
    check("resultForm.surveyStatus !== 'not_surveyed'" not in dialog,
          "弹窗里已无 `!== 'not_surveyed'` 硬编码（残留=漏改）")
    check("self.confirmable_survey_statuses" in task_py,
          "task.py::confirm_result 用类常量作准入集合")
    confirm_body = task_py.split("def confirm_result")[1][:2000] if "def confirm_result" in task_py else ""
    check('{"surveyed", "changed", "unchanged"}' not in confirm_body,
          "task.py::confirm_result 里已无内联状态集合字面量")
    check("resolve_saved_survey_status" in result_py,
          "result.py::update_result 走服务端裁定函数")
    # ⛔ 断言要带 `result.` 前缀限定：裸的 `payload.get("surveyStatus") or "surveyed"`
    #    是 `issuer_payload.get(...)` 的子串，会把发包方那行误报成承包方漏改。
    check('result.survey_status = self.resolve_saved_survey_status(' in result_py,
          "result.py 承包方那行已改为服务端裁定")
    check('result.survey_status = payload.get("surveyStatus") or "surveyed"' not in result_py,
          "result.py 承包方旧写法已移除")

    # ---- 承包方界面「跳过」按钮（上一轮漏改，本轮补） ----
    check("!TERMINAL_SURVEY_STATUSES.includes(row.taskStatus)" in view,
          "SurveyView「跳过」按钮改用定案态常量（原为 `!== 'confirmed' && !== 'skipped'`）")
    check("row.taskStatus !== 'confirmed'" not in view and "row.taskStatus !== 'skipped'" not in view,
          "SurveyView 里已无跳过按钮的状态硬编码（残留=漏改）")

    # ---- 发包方（本轮） ----
    check('issuer.survey_status = self.resolve_saved_survey_status(' in issuer_py,
          "issuer.py::update_issuer 走服务端裁定函数")
    check('issuer.survey_status = payload.get("surveyStatus") or "surveyed"' not in issuer_py,
          "issuer.py 发包方旧写法已移除")
    check("issuer.survey_status = self.resolve_saved_survey_status(" in result_py,
          "result.py：承包方录入顺带更新发包方的那处也已同源")
    check("LOCKED_SURVEY_STATUSES.includes(form.surveyStatus)" in issuer_dialog,
          "IssuerSurveyDialog 表单只读判定改用锁定态常量")
    check(issuer_dialog.count("LOCKED_SURVEY_STATUSES.includes(form.surveyStatus)") == 2,
          "IssuerSurveyDialog 两处（保存按钮 + formLocked）都已改",
          f"实际出现 {issuer_dialog.count('LOCKED_SURVEY_STATUSES.includes(form.surveyStatus)')} 次")
    check("form.surveyStatus !== 'confirmed'" not in issuer_dialog
          and 'form.surveyStatus === "confirmed"' not in issuer_dialog,
          "IssuerSurveyDialog 里已无 `'confirmed'` 硬编码（残留=漏改）")

    # ---- 编辑闸门：三处服务消费同一个类常量（不再是裸字面量） ----
    for label, text in (("result.py", result_py), ("task.py", task_py), ("issuer.py", issuer_py)):
        check("self.locked_survey_statuses" in text,
              f"{label} 的「已定案不许改」闸门走类常量")

    # ---- create_issuer 的构造与落库顺序 ----
    check("def create_issuer" in issuer_py, "issuer.py 存在 create_issuer")
    create_body = issuer_py.split("def create_issuer")[1].split("def get_issuer")[0]
    check("SurveyFbfResult(" in create_body,
          "create_issuer 里补回了 result 对象的构造（原为 NameError）")
    check("base.result_id = result.id" in create_body,
          "create_issuer 回填 base.result_id（该列非空，必须先落 result）")
    if "db.add(result)" in create_body and "db.add(base)" in create_body:
        check(create_body.index("db.add(result)") < create_body.index("db.add(base)"),
              "create_issuer 落库顺序正确：先 result 后 base")
    else:
        check(False, "create_issuer 落库顺序正确：先 result 后 base", "缺 db.add(...)")

    # ---- 幽灵赋值清理（发包方模型没有这几列） ----
    check("issuer.investigator_id =" not in result_py
          and "issuer.investigator_name =" not in result_py
          and "issuer.investigated_at =" not in result_py
          and "issuer.policy_basis =" not in result_py,
          "result.py 里给发包方写的 4 处未映射字段已清理（原为静默无效代码）")


# ---------------------------------------------------------- L2 服务层真值表
def l2_truth_table() -> None:
    print("\n=== L2 服务层真值表：resolve_saved_survey_status ===")
    resolve = SurveyServiceBase.resolve_saved_survey_status

    cases = [
        # (当前库值, 前端提交值, 期望结果, 说明)
        ("not_surveyed", "not_surveyed", "surveyed", "★核心：库里未调查+前端原样回传 → 推进"),
        ("not_surveyed", None, "surveyed", "前端漏传状态 → 推进"),
        ("not_surveyed", "", "surveyed", "前端传空串 → 推进"),
        ("not_started", "not_started", "surveyed", "旧值 not_started → 推进"),
        ("not_surveyed", "unknown-garbage", "surveyed", "未知脏值 → 推进（不许照抄）"),
        ("surveyed", "surveyed", "surveyed", "已是已调查 → 保持"),
        ("changed", "changed", "changed", "有变化 → 照收"),
        ("unchanged", "unchanged", "unchanged", "无变化 → 照收"),
        ("surveyed", "changed", "changed", "前端显式改成有变化 → 照收"),
        ("confirmed", "not_surveyed", "confirmed", "已确认不被回退"),
        ("confirmed", None, "confirmed", "已确认不被回退（空提交）"),
        ("skipped", "not_surveyed", "skipped", "已跳过不被回退"),
        ("skipped", "", "skipped", "已跳过不被回退（空提交）"),
        # 发包方语境：库内 3707 行全是 not_surveyed，前端回填的也是 not_surveyed
        (None, None, "surveyed", "发包方新增（无历史值、前端无该字段）→ 已调查"),
        ("not_surveyed", None, "surveyed", "发包方保存（schema 未给该字段）→ 已调查"),
    ]
    for current, submitted, expected, note_ in cases:
        got = resolve(current, submitted)
        check(got == expected, f"resolve({current!r}, {submitted!r}) → {got!r}", f"期望 {expected!r}；{note_}")


# -------------------------------------------------------- L3 跨语言同源核查
def l3_cross_language() -> None:
    print("\n=== L3 跨语言同源：前端常量 ⟷ 后端类常量 ===")
    js_path = ROOT / "frontend/src/config/surveyStatus.js"
    js = js_path.read_text(encoding="utf-8")

    def parse(name: str) -> set[str]:
        m = re.search(rf"export const {name}\s*=\s*\[([^\]]*)\]", js)
        assert m, f"未在 {js_path.name} 里找到 {name}"
        return set(re.findall(r'"([^"]+)"', m.group(1)))

    js_confirmable = parse("CONFIRMABLE_SURVEY_STATUSES")
    js_terminal = parse("TERMINAL_SURVEY_STATUSES")
    js_locked = parse("LOCKED_SURVEY_STATUSES")
    check(js_confirmable == SurveyServiceBase.confirmable_survey_statuses,
          "可确认集合前后端一致",
          f"前端 {sorted(js_confirmable)} / 后端 {sorted(SurveyServiceBase.confirmable_survey_statuses)}")
    check(js_terminal == SurveyServiceBase.terminal_survey_statuses,
          "定案态集合前后端一致",
          f"前端 {sorted(js_terminal)} / 后端 {sorted(SurveyServiceBase.terminal_survey_statuses)}")
    check(js_locked == SurveyServiceBase.locked_survey_statuses,
          "编辑闸门集合前后端一致",
          f"前端 {sorted(js_locked)} / 后端 {sorted(SurveyServiceBase.locked_survey_statuses)}")
    # ⛔ 编辑闸门必须是定案态的**真子集**：`skipped` 已定案但仍可补录，
    #    两个集合若相等，跳过的户会在前端被锁死、后端却仍放行。
    check(js_locked < js_terminal,
          "编辑闸门是定案态的真子集（skipped 可编辑，不许被锁死）",
          f"locked={sorted(js_locked)} ⊂ terminal={sorted(js_terminal)}")
    check(not (js_confirmable & js_terminal), "可确认集合与定案态集合不相交")


# -------------------------------------------------- L4 集成（真实库 + 事务回滚）
def _patch_commit(db) -> None:
    """⛔ 把 commit 换成 flush：service 内部会 commit，不拦就会污染真实库。"""
    db.commit = lambda *a, **k: db.flush()  # type: ignore[assignment]


def l4a_contractor(db, admin) -> None:
    print("\n=== L4a 集成（承包方）：库里 not_surveyed + 前端原样回传 → 落成 surveyed ===")

    # 动态挑夹具：挑一个「批次未结束 + 任务态 not_started + 成果 not_surveyed」的户
    row = db.execute(
        select(SurveyBatch.id, SurveyCbfBase.contractor_uid, SurveyCbfResult.id)
        .join(SurveyCbfBase, SurveyCbfBase.batch_id == SurveyBatch.id)
        .join(SurveyCbfResult, SurveyCbfResult.contractor_uid == SurveyCbfBase.contractor_uid)
        .where(
            SurveyBatch.status != "finished",
            SurveyCbfBase.task_status == "not_started",
            SurveyCbfResult.survey_status == "not_surveyed",
        )
        .order_by(SurveyBatch.id, SurveyCbfBase.id)
        .limit(1)
    ).first()
    if row is None:
        check(False, "找到承包方集成夹具", "没有 task_status=not_started 且 result=not_surveyed 的户")
        return

    batch_id, contractor_uid, _ = row
    base_before = db.scalars(
        select(SurveyCbfBase).where(SurveyCbfBase.contractor_uid == contractor_uid)
    ).first()
    result_before = db.scalars(
        select(SurveyCbfResult).where(SurveyCbfResult.contractor_uid == contractor_uid)
    ).first()
    print(f"  夹具：batch={batch_id} uid={contractor_uid} {result_before.cbfbm} {result_before.cbfmc}"
          f"  base.task_status={base_before.task_status}  result.survey_status={result_before.survey_status}")

    members = db.scalars(
        select(SurveyCbfJtcyResult).where(SurveyCbfJtcyResult.contractor_uid == contractor_uid)
    ).all()
    family_members = [
        {
            "memberUid": m.member_uid,
            "name": m.cyxm,
            "idType": m.cyzjlx,
            "idNo": m.cyzjhm,
            "gender": m.cyxb,
            "relationToHead": m.yhzgx,
            "memberResultStatus": m.member_result_status,
            "surveyStatus": "surveyed",
        }
        for m in members
    ]

    payload = {
        "code": result_before.cbfbm,
        "typeCode": result_before.cbflx,
        "name": result_before.cbfmc,
        "idType": result_before.cbfzjlx,
        "idNo": result_before.cbfzjhm,
        "address": result_before.cbfdz,
        "postcode": result_before.yzbm,
        "mobile": result_before.lxdh,
        "groupRegionCode": result_before.group_region_code,
        "groupRegionName": result_before.group_region_name,
        # ★ 这就是前端干的坏事：打开弹窗读到的旧状态，原样提交回来
        "surveyStatus": "not_surveyed",
        "resultStatus": "normal",
        "changeType": "none",
        "familyMembers": family_members,
        "deletedMembers": [],
        "pendingOperations": [],
    }

    survey_service.update_result(db, batch_id, contractor_uid, payload, admin)

    after_result = db.scalars(
        select(SurveyCbfResult).where(SurveyCbfResult.contractor_uid == contractor_uid)
    ).first()
    after_base = db.scalars(
        select(SurveyCbfBase).where(SurveyCbfBase.contractor_uid == contractor_uid)
    ).first()
    print(f"  保存后：result.survey_status={after_result.survey_status}"
          f"  base.task_status={after_base.task_status}  task.investigated_at={after_base.investigated_at}")

    check(after_result.survey_status == "surveyed",
          "保存后 result.survey_status 推进为 surveyed",
          f"实际 {after_result.survey_status!r}")
    check(after_base.task_status == "surveyed",
          "保存后 base.task_status 同步为 surveyed（前端据此显示确认按钮）",
          f"实际 {after_base.task_status!r}")
    check(after_base.task_status in SurveyServiceBase.confirmable_survey_statuses,
          "★结论：该户已进入「确认」按钮的显示集合",
          f"taskStatus={after_base.task_status!r} ∈ {sorted(SurveyServiceBase.confirmable_survey_statuses)}")


def l4b_issuer(db, admin) -> None:
    print("\n=== L4b 集成（发包方）：库里 not_surveyed + 前端原样回传 → 落成 surveyed ===")

    # ⛔ issuer_uid 必须取 **result 行的**：`survey_fbf_base.issuer_uid` 是另一套
    #   uuid5 值，`_get_issuer` 按 result 的 issuer_uid 查，用 base 的会 404。
    row = db.execute(
        select(SurveyFbfBase.batch_id, SurveyFbfResult.issuer_uid, SurveyFbfResult.id)
        .join(SurveyFbfResult, SurveyFbfResult.id == SurveyFbfBase.result_id)
        .join(SurveyBatch, SurveyBatch.id == SurveyFbfBase.batch_id)
        .where(SurveyBatch.status != "finished")
        .order_by(SurveyFbfBase.batch_id)
        .limit(1)
    ).first()
    if row is None:
        note("没有可用的发包方集成夹具（survey_fbf_base 里没有挂在未结束批次上的行）—— L4b 跳过")
        return

    batch_id, issuer_uid, fbf_result_id = row
    issuer = db.scalars(select(SurveyFbfResult).where(SurveyFbfResult.id == fbf_result_id)).first()
    print(f"  夹具：batch={batch_id} uid={issuer_uid} {issuer.fbfbm} {issuer.fbfmc}"
          f"  result.survey_status={issuer.survey_status}")

    payload = {
        "code": issuer.fbfbm,
        "name": issuer.fbfmc,
        "responsibleName": issuer.fbffzrxm,
        "responsibleIdType": issuer.fzrzjlx,
        "responsibleIdNo": issuer.fzrzjhm,
        "phone": issuer.lxdh,
        "address": issuer.fbfdz,
        "postcode": issuer.yzbm,
        "surveyorName": issuer.fbfdcy,
        "surveyDate": issuer.fbfdcrq.date().isoformat() if issuer.fbfdcrq else None,
        "surveyNote": issuer.fbfdcjs,
        # ★ 同样是前端回填的旧值原样回传
        "surveyStatus": "not_surveyed",
        "resultStatus": "normal",
        "changeType": "none",
    }

    survey_service.update_issuer(db, batch_id, issuer_uid, payload, admin)

    after = db.scalars(select(SurveyFbfResult).where(SurveyFbfResult.id == fbf_result_id)).first()
    print(f"  保存后：issuer.survey_status={after.survey_status}")
    check(after.survey_status == "surveyed",
          "保存后发包方 survey_status 推进为 surveyed（不再停在 not_surveyed）",
          f"实际 {after.survey_status!r}")


def l5_create_issuer(db, admin) -> None:
    print("\n=== L5 集成（发包方新增）：create_issuer 不再 NameError，且新行状态为 surveyed ===")
    # ⛔ 真实库构造不出"成功新增"的夹具：`batch 40/41` 的 region_code 是 **14 位**，
    #   而口径要求 `code == region_code[:14]`，也就是说一个批次只允许**同一个**发包方编码，
    #   而它已经在库里（再新增必然 409）。所以这里在**事务内**造一个临时批次，
    #   收尾统一 rollback ⇒ 零落库。
    src = db.get(SurveyBatch, 40)
    if src is None:
        note("找不到 batch 40，L5（新增发包方）跳过")
        return
    code = "32132410000199"
    dup = db.scalars(
        select(SurveyFbfResult).where(SurveyFbfResult.fbfbm == code).execution_options(skip_tenant_scope=True)
    ).first()
    if dup is not None:
        note(f"编码 {code} 已存在于真实库，L5 跳过（避免误伤）")
        return
    tmp_batch = SurveyBatch(
        batch_no="VERIFY-TMP-CREATE-ISSUER",
        batch_name="验收临时批次（事务内）",
        region_code="321324100001",  # 12 位：code 只需 startswith 即可
        tenant_code=src.tenant_code,
        status="active",
        survey_type=src.survey_type,
    )
    db.add(tmp_batch)
    db.flush()

    payload = {
        "code": code,
        "name": "验收临时发包方",
        "responsibleName": "验收员",
        "responsibleIdType": "1",
        "responsibleIdNo": "320324199001011234",
        "phone": "13800000000",
        "address": "验收临时地址",
        "postcode": "223900",
        "surveyorName": "组级测试员",
        "surveyDate": "2026-09-27",
        "surveyNote": "验收用",
    }
    data = survey_service.create_issuer(db, tmp_batch.id, payload, admin)
    check(isinstance(data, dict) and data.get("code") == code,
          "create_issuer 正常返回（原为 NameError 500）",
          f"返回 code={data.get('code')!r}")

    row = db.scalars(
        select(SurveyFbfResult).where(
            SurveyFbfResult.tenant_code == tmp_batch.tenant_code,
            SurveyFbfResult.fbfbm == code,
        ).execution_options(skip_tenant_scope=True)
    ).first()
    check(row is not None, "新增的发包方成果已落库")
    if row is None:
        return
    check(row.survey_status == "surveyed",
          "新增即「已调查」（服务端裁定，不是起点值 not_surveyed）",
          f"实际 {row.survey_status!r}")
    check(row.change_type == "add_issuer" and row.result_status == "added" and row.is_changed is True,
          "新增行标记为一条变化（add_issuer / added / is_changed）",
          f"chg={row.change_type} result={row.result_status} is_changed={row.is_changed}")
    base_row = db.scalars(
        select(SurveyFbfBase).where(SurveyFbfBase.result_id == row.id)
    ).first()
    check(base_row is not None and base_row.fbfbm == code,
          "快照行（base）已落库并回填 result_id",
          f"base#{getattr(base_row, 'id', None)} result_id={getattr(base_row, 'result_id', None)}")


def l4_integration() -> None:
    print("\n=== L4 集成：真实库上跑一次保存（事务回滚，不落库）===")
    db = SessionLocal()
    _patch_commit(db)
    try:
        admin = db.scalars(select(User).where(User.id == 1)).first()
        if admin is None:
            check(False, "取超级管理员用户", "users 表里没有 id=1")
            return
        _ = admin.role
        set_current_user(db, admin)
        l4a_contractor(db, admin)
        l4b_issuer(db, admin)
        l5_create_issuer(db, admin)
    finally:
        db.rollback()
        db.close()
        print("  [事务已回滚] 真实库未被修改。")


def main() -> None:
    l1_static()
    l2_truth_table()
    l3_cross_language()
    l4_integration()

    passed = sum(1 for ok, _, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n===== 验收结果：{passed}/{total} 通过 =====")
    for ok, name, detail in RESULTS:
        if not ok:
            print(f"  ✗ {name}  {detail}")
    if NOTES:
        print("（跳过项）")
        for text in NOTES:
            print(f"  · {text}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
