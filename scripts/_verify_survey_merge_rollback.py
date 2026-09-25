# -*- coding: utf-8 -*-
"""端到端实证：**合户后原户的「撤回」入口是否断裂**（2026-09-25）。

待证命题
--------
`merge_household` 会把参与合户的原户置为：
  · `survey_cbf_result.result_status = "cancelled"`   （承包方结果状态：已注销）
  · `survey_cbf_base.task_status  = "deregistered"`   （调查任务状态：已注销）
而 `split_household` **只改 result_status，不动 task_status**。

这带来一条可疑链路（本次用接口逐环证实）：
  1. 主任务列表 `list_tasks` 默认过滤 `task_status != "deregistered"`（task.py:69-71）
     ⇒ 原户被摘出主列表；
  2. 前端状态筛选下拉（SurveyView.vue:8-12 / :97-98）只有
     未调查/调查中/已调查/已确认/已跳过，**没有「已注销」** ⇒ 主列表里根本选不出原户；
  3. 唯一还能看到原户的是「已注销承包方」弹窗（DeregisteredContractorsDialog），
     它只有「撤回注销」一个按钮（:42-50，条件 canManage && row.canRollback），
     **没有打开录入对话框的入口**（只 emit "restored"，无 emit 给父组件开 result dialog）；
  4. 该按钮调的接口是 `rollback-deregister`（api/survey.js:282），
     而它只认 `change_type == "deregister"`（household.py:506）
     ⇒ 合户写的是 `merge_household` ⇒ **400「未找到可撤回的注销记录」**；
  5. 真正的「撤回合户」按钮在 ContractorResultDialog.vue:8，
     显示条件 `resultStatus === "cancelled" && changeType === "merge_household"`
     —— 可前提是**得先打开那个原户**，而从列表里已经找不到它了。

本脚本要证的是：**上面每一环都成立**，并且第 5 环的接口 `merge-household/rollback`
本身是好的（直发 200 且完整还原）⇒ 断的只是「界面能不能走到」。

跑法：runtime/windows/python/python.exe scripts/_verify_survey_merge_rollback.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 必须先注入 DB 配置再 import app（config.py 的 database_port 默认 5432 是错的，
# 真实实例在 15432；连不上时 psycopg 会让进程静默退出）。
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

import psycopg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.main import app  # noqa: E402

BATCH_ID = 41
HA = "321324100001029861"        # 户 A（合户发起方）
HB = "321324100001029862"        # 户 B（合户参与方）
HM = "321324100001029863"        # 合户生成的新户
ALL_CODES = [HA, HB, HM]
NAMES = {HA: "实证合户户A", HB: "实证合户户B", HM: "实证合并户"}

TOKEN = create_access_token("1")
DSN = (
    f"host={settings.database_host} port={settings.database_port} "
    f"dbname={settings.database_name} user={settings.database_user} "
    f"password={settings.database_password}"
)

OUT: list[str] = []
FAILED: list[str] = []
KNOWN_GAPS: list[str] = []
client: TestClient | None = None


# ────────────────────────── 基础设施 ──────────────────────────
def log(*parts) -> None:
    line = " ".join(str(p) for p in parts)
    OUT.append(line)
    print(line)


def check(label: str, ok: bool, extra: str = "", *, gap: bool = False) -> bool:
    tag = "PASS" if ok else ("GAP " if gap else "FAIL")
    log(f"[{tag}] {label}" + (f" {extra}" if extra else ""))
    if not ok:
        (KNOWN_GAPS if gap else FAILED).append(label)
    return ok


def note(label: str, extra: str = "") -> None:
    """纯取证：不算断言成败，只把事实打出来。"""
    log(f"      · {label}" + (f" {extra}" if extra else ""))


def api(path: str, method: str = "GET", body=None):
    assert client is not None
    resp = client.request(
        method, f"/api/v1{path}", json=body,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    try:
        return resp.status_code, resp.json()
    except Exception:  # noqa: BLE001
        return resp.status_code, resp.text


def brief(payload, limit: int = 400) -> str:
    return str(payload)[:limit]


def sql(sql_text: str, params=None):
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text, params)
            return cur.fetchall()


# ────────────────────────── 状态读取 ──────────────────────────
def get_detail(uid: str) -> dict:
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}")
    return payload.get("data") if status == 200 and isinstance(payload, dict) else {}


def next_parcel_code(uid: str) -> str:
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/parcels/next-code")
    if status == 200 and isinstance(payload, dict):
        data = payload.get("data") or {}
        if isinstance(data, dict):
            return data.get("code") or data.get("dkbm") or ""
        return str(data)
    return ""


def members_payload(members: list) -> list:
    return [{
        "memberUid": m.get("memberUid"),
        "name": m.get("name"),
        "gender": m.get("gender") or "1",
        "idType": m.get("idType") or "1",
        "idNo": m.get("idNo"),
        "relationToHead": m.get("relationToHead") or "01",
        "noteCode": m.get("noteCode"),
        "isCoOwner": m.get("isCoOwner"),
        "note": m.get("note"),
        "memberResultStatus": m.get("memberResultStatus") or "normal",
        "isHouseholdHead": bool(m.get("isHouseholdHead")),
        "changeReason": m.get("changeReason"),
    } for m in members]


def result_payload(detail: dict, *, members=None, pending=None, **overrides) -> dict:
    payload = {
        "code": detail.get("code"),
        "typeCode": detail.get("typeCode") or "1",
        "name": detail.get("name"),
        "idType": detail.get("idType") or "1",
        "idNo": detail.get("idNo"),
        "address": detail.get("address"),
        "postcode": detail.get("postcode") or "000000",
        "mobile": detail.get("mobile"),
        "surveyDate": detail.get("surveyDate"),
        "surveyorName": detail.get("surveyorName"),
        "surveyNote": detail.get("surveyNote"),
        "publicNoticeNote": detail.get("publicNoticeNote"),
        "publicNoticeRecorder": detail.get("publicNoticeRecorder"),
        "publicNoticeReviewDate": detail.get("publicNoticeReviewDate"),
        "publicNoticeReviewer": detail.get("publicNoticeReviewer"),
        "groupRegionCode": detail.get("groupRegionCode"),
        "groupRegionName": detail.get("groupRegionName"),
        "surveyStatus": detail.get("surveyStatus") or "surveyed",
        "resultStatus": detail.get("resultStatus") or "normal",
        "changeType": detail.get("changeType") or "none",
        "changeReason": detail.get("changeReason"),
        "policyBasis": detail.get("policyBasis"),
        "evidenceSummary": detail.get("evidenceSummary"),
        "remark": detail.get("remark"),
        "familyMembers": members if members is not None else members_payload(detail.get("familyMembers") or []),
        "deletedMembers": [],
        "pendingOperations": pending or [],
    }
    payload.update(overrides)
    return payload


def put_result(uid: str, detail: dict, **kwargs):
    return api(f"/surveys/batches/{BATCH_ID}/results/{uid}", method="PUT",
               body=result_payload(detail, **kwargs))


def add_parcel(uid: str, dkbm: str, label: str, scmj: str = "1000"):
    detail = get_detail(uid)
    body = {
        "dkbm": dkbm, "dkmc": label, "dklb": "01", "dldj": "01", "tdyt": "1",
        "tdlylx": "011", "syqxz": "10", "scmj": scmj, "sfjbnt": "1",
        "reason": "实证新增地块",
    }
    return put_result(uid, detail, pending=[{"type": "add_parcel", "payload": body}])


def list_tasks(*, keyword=None, task_status=None, page_size=200) -> dict:
    """主任务列表 GET /batches/{id}/tasks。不传 taskStatus 即默认口径（排除已注销）。"""
    params = [f"page=1", f"page_size={page_size}"]
    if keyword:
        params.append(f"keyword={keyword}")
    if task_status:
        params.append(f"taskStatus={task_status}")
    status, payload = api(f"/surveys/batches/{BATCH_ID}/tasks?" + "&".join(params))
    if status == 200 and isinstance(payload, dict):
        return payload.get("data") or {}
    return {"items": [], "total": None, "httpStatus": status, "raw": brief(payload)}


def list_deregistered(*, keyword=None, page_size=200) -> dict:
    # ⛔ page_size 上限 200（Query(le=200)），传 500 会直接 422。
    assert page_size <= 200, "page_size 上限 200"
    params = ["page=1", f"page_size={page_size}"]
    if keyword:
        params.append(f"keyword={keyword}")
    status, payload = api(f"/surveys/batches/{BATCH_ID}/deregistered-contractors?" + "&".join(params))
    if status == 200 and isinstance(payload, dict):
        return payload.get("data") or {}
    return {"items": [], "total": None, "httpStatus": status, "raw": brief(payload)}


# ────────────────────────── 收尾清理 ──────────────────────────
def housekeeping() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT contractor_uid FROM survey_cbf_result WHERE cbfbm = ANY(%s)",
                (ALL_CODES,),
            )
            uids = [r[0] for r in cur.fetchall()]
            # 合户生成的新户 uid 由 uuid5 派生，撤回合户后其 result 行会消失，
            # 所以还要按 remark 里的 merge_group 兜一次。
            cur.execute(
                "SELECT contractor_uid FROM survey_cbf_base "
                "WHERE batch_id = %s AND initialized_from_table = 'merge_household' AND cbfbm = ANY(%s)",
                (BATCH_ID, ALL_CODES),
            )
            uids += [r[0] for r in cur.fetchall()]
            uids = list(dict.fromkeys(uids))

            cur.execute(
                "SELECT DISTINCT dkbm FROM survey_cbdkxx_result WHERE cbfbm = ANY(%s)",
                (ALL_CODES,),
            )
            dkbms = [r[0] for r in cur.fetchall()]

            if uids:
                for table in (
                    "survey_change_diffs", "survey_change_records", "survey_household_tags",
                    "survey_cbf_jtcy_result", "survey_cbf_jtcy_base", "survey_cbf_base",
                ):
                    cur.execute(f"DELETE FROM {table} WHERE contractor_uid = ANY(%s)", (uids,))
            cur.execute("DELETE FROM survey_cbdkxx_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
            cur.execute("DELETE FROM survey_cbdkxx_base WHERE cbfbm = ANY(%s)", (ALL_CODES,))
            if dkbms:
                cur.execute("DELETE FROM survey_dk_result WHERE dkbm = ANY(%s)", (dkbms,))
                cur.execute("DELETE FROM survey_dk_base WHERE dkbm = ANY(%s)", (dkbms,))
            cur.execute("DELETE FROM survey_cbf_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
            # 兜底：撤回合户后新户行已不在 survey_cbf_result ⇒ 按 cbfbm 取到的 uids
            # 覆盖不到挂在它 uid 上的台账。必须在删完 survey_cbf_result 之后再判「孤儿」。
            cur.execute(
                "DELETE FROM survey_change_diffs WHERE batch_id = %s AND contractor_uid NOT IN"
                " (SELECT contractor_uid FROM survey_cbf_result)",
                (BATCH_ID,),
            )
            cur.execute(
                "DELETE FROM survey_change_records WHERE batch_id = %s AND contractor_uid NOT IN"
                " (SELECT contractor_uid FROM survey_cbf_result)",
                (BATCH_ID,),
            )


# ────────────────────────── 夹具 ──────────────────────────
def setup_household(code: str, name: str, member_prefix: str) -> tuple[str, list[str]]:
    log(f"\n--- 建临时户 {code}（{name}）---")
    status, payload = api(
        f"/surveys/batches/{BATCH_ID}/tasks", method="POST",
        body={
            "code": code, "typeCode": "1", "name": name, "idType": "1",
            "idNo": "3203241990010199" + code[-2:], "address": "实证临时地址",
            "postcode": "223900", "mobile": "13900000000",
            "surveyorName": "实证脚本", "surveyDate": "2026-09-25",
            "remark": "merge rollback verify fixture",
        },
    )
    if status != 201:
        check(f"建户 {code}", False, f"-> {status} {brief(payload)}")
        return "", []
    uid = (payload.get("data") or {}).get("contractorUid") or ""
    if not check(f"建户 {code} 成功", bool(uid), f"uid={uid[:8]}…"):
        return "", []

    detail = get_detail(uid)
    members = members_payload(detail.get("familyMembers") or [])
    suffix = code[-2:]
    for idx in range(2):
        members.append({
            "name": f"{member_prefix}{idx + 1}", "gender": "1", "idType": "1",
            "idNo": f"3203241990010{suffix}{idx}",
            "relationToHead": "01" if idx == 0 else "02",
            "isHouseholdHead": idx == 0,
        })
    status, resp = put_result(uid, detail, members=members)
    check(f"{code} 补 2 名成员", status == 200, f"-> {status} {brief(resp, 300)}")

    codes = []
    for i in range(2):
        pc = next_parcel_code(uid)
        if not pc:
            check(f"{code} 取地块编码", False, "-> next-code 未返回")
            break
        st, rp = add_parcel(uid, pc, f"{name}地块{i + 1}")
        if st != 200:
            check(f"{code} 新增地块 {pc}", False, f"-> {st} {brief(rp, 400)}")
            break
        codes.append(pc)
    check(f"{code} 新增 2 个地块", len(codes) == 2, f"-> {codes}")
    return uid, codes


# ────────────────────────── M2 合户 ──────────────────────────
def case_m2_merge(uid_a: str, uid_b: str) -> bool:
    log("\n=== M2 合户（A + B → 新户 HM） ===")
    da = get_detail(uid_a)
    members_a = da.get("familyMembers") or []
    head = next((m.get("memberUid") for m in members_a if m.get("isHouseholdHead")), None)
    if not head and members_a:
        head = members_a[0].get("memberUid")
    if not check("M2 找到户主成员 uid", bool(head), f"-> {head}"):
        return False

    status, resp = put_result(uid_a, da, pending=[{
        "type": "merge_household",
        "payload": {
            "sourceContractorUids": [uid_a, uid_b],
            "newCbfbm": HM, "newCbfmc": NAMES[HM],
            "householdHeadMemberUid": head,
            "newAddress": "实证合并地址", "reason": "实证合户",
        },
    }])
    if not check("M2 合户 PUT 200", status == 200, f"-> {status} {brief(resp, 600)}"):
        return False

    a_after, b_after = get_detail(uid_a), get_detail(uid_b)
    check("M2 原户 A result_status=cancelled", a_after.get("resultStatus") == "cancelled",
          f"-> {a_after.get('resultStatus')}")
    check("M2 原户 B result_status=cancelled", b_after.get("resultStatus") == "cancelled",
          f"-> {b_after.get('resultStatus')}")

    rows = sql(
        "SELECT result_status, change_type FROM survey_cbf_result WHERE cbfbm = ANY(%s) ORDER BY cbfbm",
        (ALL_CODES,),
    )
    note("DB result_status / change_type", f"{rows}")

    tasks = sql(
        "SELECT cbfbm, task_status FROM survey_cbf_base WHERE batch_id = %s AND cbfbm = ANY(%s) ORDER BY cbfbm",
        (BATCH_ID, ALL_CODES),
    )
    note("DB base.task_status", f"{tasks}")
    task_map = {r[0]: r[1] for r in tasks}
    check("★ 原户 A 的 task_status 被置为 deregistered（合户副作用）",
          task_map.get(HA) == "deregistered", f"-> {task_map.get(HA)}")
    check("★ 原户 B 的 task_status 被置为 deregistered",
          task_map.get(HB) == "deregistered", f"-> {task_map.get(HB)}")

    new_rows = sql("SELECT contractor_uid FROM survey_cbf_result WHERE cbfbm = %s", (HM,))
    new_uid = new_rows[0][0] if new_rows else ""
    if check("M2 新户 HM 已生成", bool(new_uid), f"-> uid={new_uid[:8]}…"):
        merged = sql("SELECT count(*) FROM survey_cbf_jtcy_result WHERE contractor_uid = %s", (new_uid,))
        check("M2 新户继承两户成员（4 人）", merged and merged[0][0] == 4, f"-> {merged}")
    return True


# ────────────────────────── M3 主列表是否还能看到原户 ──────────────────────────
def case_m3_main_list() -> None:
    log("\n=== M3 主任务列表：原户是否可见（前端主入口） ===")
    for code in (HA, HB):
        got = list_tasks(keyword=code)
        total = got.get("total")
        codes = [i.get("cbfbm") for i in (got.get("items") or [])]
        check(f"★ 主列表（默认口径）按关键字 {code} 查不到原户",
              (total == 0) and (code not in codes),
              f"-> total={total} codes={codes}")

    # 前端下拉里没有「已注销」选项，但接口本身支持 ⇒ 证明数据在、只是界面走不到
    got = list_tasks(keyword=HA, task_status="deregistered")
    codes = [i.get("cbfbm") for i in (got.get("items") or [])]
    check("（对照）显式传 taskStatus=deregistered 时接口能返回原户 ⇒ 数据在、缺的是界面入口",
          HA in codes, f"-> total={got.get('total')} codes={codes}")

    # 前端下拉的全部选项逐个试，确认都不含原户
    for status in ("not_started", "in_progress", "surveyed", "confirmed", "skipped"):
        got = list_tasks(keyword=HA, task_status=status)
        codes = [i.get("cbfbm") for i in (got.get("items") or [])]
        check(f"主列表 taskStatus={status} 不含原户 A", HA not in codes, f"-> {codes}")


# ────────────────────────── M4 已注销列表给出什么 ──────────────────────────
def case_m4_deregistered_list() -> None:
    log("\n=== M4 已注销承包方列表：原户在列，且带「可撤回」标记 ===")
    got = list_deregistered(page_size=200)
    if got.get("total") is None:
        note("已注销列表调用失败", f"HTTP {got.get('httpStatus')} raw={got.get('raw')}")
    items = got.get("items") or []
    by_code = {i.get("cbfbm"): i for i in items}
    check("★ 已注销列表含原户 A", HA in by_code, f"-> total={got.get('total')}")
    check("★ 已注销列表含原户 B", HB in by_code, f"-> total={got.get('total')}")

    for code in (HA, HB):
        row = by_code.get(code) or {}
        note(f"{code} 已注销行", f"changeType={row.get('changeType')!r} "
                                f"canRollback={row.get('canRollback')} "
                                f"changeNo={row.get('changeNo')!r} "
                                f"reason={row.get('deregisterReason')!r}")
        # ★ 2026-09-25 修复后：列表会把"让户离开待办的终态类型"一并透出，
        #   前端据此把按钮**分流**到正确的撤回接口（不再一律打 rollback-deregister）。
        check(f"★ {code} changeType='merge_household' ⇒ 前端会渲染「撤回合户」按钮",
              row.get("changeType") == "merge_household", f"-> {row.get('changeType')!r}")
        check(f"★ {code} canRollback=true（与撤回接口同源：存在未撤回的终态记录）",
              row.get("canRollback") is True, f"-> {row.get('canRollback')}")
        check(f"★ {code} changeNo 非空（按钮挂得上台账；修复前为 null）",
              bool(row.get("changeNo")), f"-> {row.get('changeNo')!r}")

    chg = sql(
        "SELECT cbfbm, change_type FROM survey_change_records "
        "WHERE batch_id = %s AND cbfbm = ANY(%s) AND change_status <> 'rolled_back' ORDER BY cbfbm, id",
        (BATCH_ID, [HA, HB]),
    )
    note("DB change_records（原户，未撤回）", f"{chg}")
    for code in (HA, HB):
        types = {r[1] for r in chg if r[0] == code}
        check(f"★ {code} 有 merge_household 记录、且没有 deregister 记录（这就是 400 的根因）",
              "merge_household" in types and "deregister" not in types, f"-> types={sorted(types)}")


# ────────────────────────── M5 点「撤回注销」会怎样 ──────────────────────────
def case_m5_rollback_deregister(uid_a: str) -> None:
    log("\n=== M5 直发「撤回注销」接口：语义未变、仍应被拒 ===")
    log("      （这条同时反证：本次修复在**入口选择**——按 changeType 分流——")
    log("        而不是放宽接口判据。若这里变成 200，说明是把接口改松了，属于错误的修法。）")
    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid_a}/rollback-deregister", method="POST")
    detail = (resp or {}).get("detail") if isinstance(resp, dict) else resp
    note("rollback-deregister 响应", f"HTTP {status} detail={detail!r}")
    check("★ 合户原户调「撤回注销」被拒（400「未找到可撤回的注销记录」）",
          status == 400 and isinstance(detail, str) and "未找到可撤回的注销记录" in detail,
          f"-> {status} {brief(resp, 200)}")

    after = get_detail(uid_a)
    check("（拒绝对状态无副作用）原户 A 仍为 cancelled",
          after.get("resultStatus") == "cancelled", f"-> {after.get('resultStatus')}")


# ────────────────────────── M6 后端能力本身是否正常 ──────────────────────────
def case_m6_merge_rollback(uid_a: str, uid_b: str) -> None:
    log("\n=== M6 直发正确的接口：POST merge-household/rollback（证明后端能力在） ===")
    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid_a}/merge-household/rollback", method="POST")
    if not check("★ 撤回合户 200", status == 200, f"-> {status} {brief(resp, 500)}"):
        return

    a_ok, b_ok = get_detail(uid_a), get_detail(uid_b)
    note("撤回后 A/B resultStatus", f"A={a_ok.get('resultStatus')} B={b_ok.get('resultStatus')}")
    check("★ 撤回后原户 A 恢复正常", a_ok.get("resultStatus") in ("normal", "added"),
          f"-> {a_ok.get('resultStatus')}")
    check("★ 撤回后原户 B 恢复正常", b_ok.get("resultStatus") in ("normal", "added"),
          f"-> {b_ok.get('resultStatus')}")

    tasks = sql(
        "SELECT cbfbm, task_status FROM survey_cbf_base WHERE batch_id = %s AND cbfbm = ANY(%s) ORDER BY cbfbm",
        (BATCH_ID, [HA, HB]),
    )
    note("撤回后 base.task_status", f"{tasks}")
    check("★ 撤回后原户 task_status 已恢复（不再是 deregistered）",
          all(r[1] != "deregistered" for r in tasks) if tasks else False, f"-> {tasks}")

    hb_row = sql(
        "SELECT count(*) FROM survey_cbf_result WHERE cbfbm = %s AND result_status <> 'cancelled'", (HM,)
    )
    check("★ 撤回后新户 HM 已失效", (not hb_row) or hb_row[0][0] == 0, f"-> {hb_row}")

    got = list_tasks(keyword=HA)
    codes = [i.get("cbfbm") for i in (got.get("items") or [])]
    check("★ 撤回后原户 A 重新出现在主任务列表", HA in codes, f"-> total={got.get('total')} codes={codes}")


# ────────────────────────── 主流程 ──────────────────────────
def main() -> int:
    global client
    log("清理上次可能残留的夹具 ...")
    housekeeping()

    with TestClient(app) as c:
        client = c
        uid_a, _pa = setup_household(HA, NAMES[HA], "实甲")
        uid_b, _pb = setup_household(HB, NAMES[HB], "实乙")
        if uid_a and uid_b:
            if case_m2_merge(uid_a, uid_b):
                case_m3_main_list()
                case_m4_deregistered_list()
                case_m5_rollback_deregister(uid_a)
                case_m6_merge_rollback(uid_a, uid_b)

    log("\n清理本轮夹具 ...")
    housekeeping()

    log("\n" + "=" * 72)
    passed = len([x for x in OUT if x.startswith("[PASS]")])
    log(f"结果：{'全部通过' if not FAILED else '存在失败'}  |  "
        f"PASS {passed} / FAIL {len(FAILED)} / 已知残留 {len(KNOWN_GAPS)}")
    if FAILED:
        for item in FAILED:
            log(f"  ✗ {item}")
    if KNOWN_GAPS:
        for item in KNOWN_GAPS:
            log(f"  ~ {item}")

    out_path = ROOT / "runtime" / ".state" / "_verify_survey_merge_rollback.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(OUT), encoding="utf-8")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
