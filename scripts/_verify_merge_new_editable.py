# -*- coding: utf-8 -*-
"""端到端实证：**合户/分户生成的「新户」被当成"已终结户"，保存被 400 拦死**（2026-09-25）。

现象（用户报）
--------------
批次 41 里把 321324100001020010（刘乃高）与 321324100001020011（刘修连）合户、指定刘乃高为户主，
合户完成后打开新户，界面上「不能修改」。

根因（本脚本逐环证明）
----------------------
`merge_household` / `split_household` 给**新户**写的 `survey_cbf_result` 是：

    result_status = "added"          ← 方向：新增
    change_type   = "merge_household" / "split_household"   ← 与**原户**写的是同一个值

而两处判据都只认 `change_type`、不看方向：

  1. 后端 `result.py:69`
     `if result.result_status in {"cancelled","extinct"} or result.change_type in terminal_operation_types`
     ⇒ 新户 change_type 命中终态集合 ⇒ PUT 保存直接 **400「该承包户已注销，撤回注销、分户或合并操作后才能修改」**。
  2. 前端 `ContractorResultDialog.vue:228` `savedTerminated`
     `resultStatus === "cancelled" || ["deregister","split_household","merge_household"].includes(changeType)`
     ⇒ 新户被判为「已终结」⇒ `dataReadOnly=true` ⇒ 整个表单只读、按钮消失。

判别方向的信息本来就在库里：原户 `result_status="cancelled"`，新户 `result_status="added"`
（`base.py:46-50` 的注释也写明「新户那边写的是 created*，不属于退出待办的原户」）。

本脚本断言
----------
· 合户前：两原户可正常保存（PUT 200）；
· 合户后：**新户** PUT 200（修复目标）、原户 PUT 400（必须保持拦截）；
· 前端 `savedTerminated` 的等价表达式在「新户」上必须为 False、在「原户」上为 True。

跑法：runtime/windows/python/python.exe scripts/_verify_merge_new_editable.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 必须先注入 DB 配置再 import app（config.py 的 database_port 默认 5432 是错的，真实 15432）。
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
HA = "321324100001029871"   # 户 A（合户发起方，户主所在一侧）
HB = "321324100001029872"   # 户 B（合户参与方）
HM = "321324100001029873"   # 合户生成的新户
ALL_CODES = [HA, HB, HM]
NAMES = {HA: "实证新户A", HB: "实证新户B", HM: "实证合并新户"}

TOKEN = create_access_token("1")    # sub=user_id；管理员口径
TOKEN_7 = create_access_token("7")  # 组级测试员：批次 41 里 010/011 的真实归属人（owner_id=7）
DSN = (
    f"host={settings.database_host} port={settings.database_port} "
    f"dbname={settings.database_name} user={settings.database_user} "
    f"password={settings.database_password}"
)

OUT: list[str] = []
FAILED: list[str] = []
client: TestClient | None = None


def log(*parts) -> None:
    line = " ".join(str(p) for p in parts)
    OUT.append(line)
    print(line)


def check(label: str, ok: bool, extra: str = "") -> bool:
    log(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" {extra}" if extra else ""))
    if not ok:
        FAILED.append(label)
    return ok


def note(label: str, extra: str = "") -> None:
    log(f"      · {label}" + (f" {extra}" if extra else ""))


def api(path: str, method: str = "GET", body=None, token: str | None = None):
    assert client is not None
    resp = client.request(
        method, f"/api/v1{path}", json=body,
        headers={"Authorization": f"Bearer {token or TOKEN}"},
    )
    try:
        return resp.status_code, resp.json()
    except Exception:  # noqa: BLE001
        return resp.status_code, resp.text


def brief(payload, limit: int = 300) -> str:
    return str(payload)[:limit]


def sql(sql_text: str, params=None):
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text, params)
            return cur.fetchall()


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
        "memberUid": m.get("memberUid"), "name": m.get("name"),
        "gender": m.get("gender") or "1", "idType": m.get("idType") or "1",
        "idNo": m.get("idNo"), "relationToHead": m.get("relationToHead") or "01",
        "noteCode": m.get("noteCode"), "isCoOwner": m.get("isCoOwner"),
        "note": m.get("note"),
        "memberResultStatus": m.get("memberResultStatus") or "normal",
        "isHouseholdHead": bool(m.get("isHouseholdHead")),
        "changeReason": m.get("changeReason"),
    } for m in members]


def result_payload(detail: dict, *, members=None, pending=None, **overrides) -> dict:
    payload = {
        "code": detail.get("code"), "typeCode": detail.get("typeCode") or "1",
        "name": detail.get("name"), "idType": detail.get("idType") or "1",
        "idNo": detail.get("idNo"), "address": detail.get("address"),
        "postcode": detail.get("postcode") or "000000", "mobile": detail.get("mobile"),
        "surveyDate": detail.get("surveyDate"), "surveyorName": detail.get("surveyorName"),
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


def saved_terminated(result_status: str | None, change_type: str | None, *, fixed: bool) -> bool:
    """前端 `savedTerminated` 的等价表达式（各时期的写法）。

    ``fixed=False`` 复刻修复前的写法（只要 changeType 命中终态集合就只读）；
    ``fixed=True`` 复刻修复后的口径（走 ``isTerminal``：先看 result_status 的方向）。
    """
    if fixed:
        if result_status in ("cancelled", "extinct"):
            return True
        return (change_type in ("deregister", "split_household", "merge_household")
                and result_status != "added")
    return (result_status == "cancelled"
            or change_type in ("deregister", "split_household", "merge_household"))


# ────────────────────────── 夹具 ──────────────────────────
def housekeeping() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT contractor_uid FROM survey_cbf_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
            uids = [r[0] for r in cur.fetchall()]
            cur.execute(
                "SELECT contractor_uid FROM survey_cbf_base WHERE batch_id = %s AND cbfbm = ANY(%s)",
                (BATCH_ID, ALL_CODES),
            )
            uids += [r[0] for r in cur.fetchall()]
            uids = list(dict.fromkeys(uids))
            cur.execute("SELECT DISTINCT dkbm FROM survey_cbdkxx_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
            dkbms = [r[0] for r in cur.fetchall()]
            if uids:
                for table in ("survey_change_diffs", "survey_change_records", "survey_household_tags",
                              "survey_cbf_jtcy_result", "survey_cbf_jtcy_base", "survey_cbf_base"):
                    cur.execute(f"DELETE FROM {table} WHERE contractor_uid = ANY(%s)", (uids,))
            cur.execute("DELETE FROM survey_cbdkxx_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
            cur.execute("DELETE FROM survey_cbdkxx_base WHERE cbfbm = ANY(%s)", (ALL_CODES,))
            if dkbms:
                cur.execute("DELETE FROM survey_dk_result WHERE dkbm = ANY(%s)", (dkbms,))
                cur.execute("DELETE FROM survey_dk_base WHERE dkbm = ANY(%s)", (dkbms,))
            cur.execute("DELETE FROM survey_cbf_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
            cur.execute(
                "DELETE FROM survey_change_diffs WHERE batch_id = %s AND contractor_uid NOT IN"
                " (SELECT contractor_uid FROM survey_cbf_result)", (BATCH_ID,))
            cur.execute(
                "DELETE FROM survey_change_records WHERE batch_id = %s AND contractor_uid NOT IN"
                " (SELECT contractor_uid FROM survey_cbf_result)", (BATCH_ID,))


def setup_household(code: str, name: str, prefix: str) -> tuple[str, list[str]]:
    log(f"\n--- 建临时户 {code}（{name}）---")
    status, payload = api(
        f"/surveys/batches/{BATCH_ID}/tasks", method="POST",
        body={
            "code": code, "typeCode": "1", "name": name, "idType": "1",
            "idNo": "3203241990010199" + code[-2:], "address": "实证临时地址",
            "postcode": "223900", "mobile": "13900000000",
            "surveyorName": "实证脚本", "surveyDate": "2026-09-25",
            "remark": "merge new-household editable verify fixture",
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
            "name": f"{prefix}{idx + 1}", "gender": "1", "idType": "1",
            "idNo": f"3203241990010{suffix}{idx}",
            "relationToHead": "02" if idx == 0 else "20",
            "isHouseholdHead": idx == 0,
        })
    status, resp = put_result(uid, detail, members=members)
    check(f"{code} 补 2 名成员", status == 200, f"-> {status} {brief(resp)}")

    codes = []
    for i in range(2):
        pc = next_parcel_code(uid)
        if not pc:
            check(f"{code} 取地块编码", False, "-> next-code 未返回")
            break
        st, rp = put_result(uid, get_detail(uid), pending=[{
            "type": "add_parcel",
            "payload": {"dkbm": pc, "dkmc": f"{name}地块{i + 1}", "dklb": "01", "dldj": "01",
                        "tdyt": "1", "tdlylx": "011", "syqxz": "10", "scmj": "1000",
                        "sfjbnt": "1", "reason": "实证新增地块"},
        }])
        if st != 200:
            check(f"{code} 新增地块 {pc}", False, f"-> {st} {brief(rp)}")
            break
        codes.append(pc)
    check(f"{code} 新增 2 个地块", len(codes) == 2, f"-> {codes}")
    return uid, codes


# ────────────────────────── 主流程 ──────────────────────────
def main() -> int:
    global client
    log("清理上次可能残留的夹具 ...")
    housekeeping()

    with TestClient(app) as c:
        client = c
        uid_a, _ = setup_household(HA, NAMES[HA], "实甲")
        uid_b, _ = setup_household(HB, NAMES[HB], "实乙")
        if not (uid_a and uid_b):
            log("夹具未建成功，终止")
        else:
            log("\n=== 1 把两户分给组级测试员（user 7）——批次 41 里 010/011 的真实归属人 ===")
            st_as, rp_as = api(f"/surveys/batches/{BATCH_ID}/tasks/assign", method="PUT",
                               body={"contractorUids": [uid_a, uid_b], "assigneeId": 7})
            check("分配 A、B 给 user 7", st_as == 200, f"-> {st_as} {brief(rp_as)}")

            log("\n=== 2 合户前：两原户都能保存（基线） ===")
            for uid, code in ((uid_a, HA), (uid_b, HB)):
                st, rp = put_result(uid, get_detail(uid))
                check(f"合户前 {code} PUT 200", st == 200, f"-> {st} {brief(rp)}")

            log("\n=== 3 合户 A + B → 新户 HM ===")
            da = get_detail(uid_a)
            head = next((m.get("memberUid") for m in (da.get("familyMembers") or [])
                         if m.get("isHouseholdHead")), None)
            check("找到户主成员 uid", bool(head), f"-> {head}")
            st, rp = api(f"/surveys/batches/{BATCH_ID}/results/{uid_a}/merge-household", method="POST", body={
                "sourceContractorUids": [uid_a, uid_b], "newCbfbm": HM, "newCbfmc": NAMES[HM],
                "householdHeadMemberUid": head, "newAddress": "实证合并地址", "reason": "实证合户",
            })
            if not check("合户 POST 200", st == 200, f"-> {st} {brief(rp, 600)}"):
                log("合户未成功，终止")
            else:
                rows = sql(
                    "SELECT cbfbm, result_status, change_type, remark FROM survey_cbf_result "
                    "WHERE cbfbm = ANY(%s) ORDER BY cbfbm", (ALL_CODES,))
                log("\n=== 4 合户后三户的结果态 / 归属继承 ===")
                for r in rows:
                    note(f"{r[0]}", f"result_status={r[1]!r} change_type={r[2]!r}")

                hm_rows = sql("SELECT contractor_uid FROM survey_cbf_result WHERE cbfbm = %s", (HM,))
                new_uid = hm_rows[0][0] if hm_rows else ""
                base_rows = sql(
                    "SELECT cbfbm, task_status, assigned_to, assigned_to_name FROM survey_cbf_base "
                    "WHERE batch_id = %s AND cbfbm = ANY(%s) ORDER BY cbfbm", (BATCH_ID, ALL_CODES))
                for r in base_rows:
                    note(f"base {r[0]}", f"task_status={r[1]!r} assigned_to={r[2]} {r[3]!r}")

                hm_detail = get_detail(new_uid) if new_uid else {}
                note("新户详情", f"resultStatus={hm_detail.get('resultStatus')!r} "
                                f"changeType={hm_detail.get('changeType')!r} "
                                f"code={hm_detail.get('code')!r} name={hm_detail.get('name')!r}")
                check("新户 resultStatus='added'（方向=新增）",
                      hm_detail.get("resultStatus") == "added", f"-> {hm_detail.get('resultStatus')!r}")
                check("新户 changeType='merge_household'（与原户同值，这就是误判来源）",
                      hm_detail.get("changeType") == "merge_household", f"-> {hm_detail.get('changeType')!r}")

                log("\n=== 5 只读判据：后端 isTerminal + 前端等价表达式 ===")
                hm_detail_raw = get_detail(new_uid)
                note("新户 isTerminal", f"{hm_detail_raw.get('isTerminal')!r}（接口字段）")
                check("★ 新户接口 isTerminal=False（可以继续录入）",
                      hm_detail_raw.get("isTerminal") is False, f"-> {hm_detail_raw.get('isTerminal')!r}")
                for uid, code in ((uid_a, HA), (uid_b, HB)):
                    src = get_detail(uid)
                    note(f"原户 {code} isTerminal", f"{src.get('isTerminal')!r}")
                    check(f"★ 原户 {code} 接口 isTerminal=True（只读 + 可撤回）",
                          src.get("isTerminal") is True, f"-> {src.get('isTerminal')!r}")

                log("      （对照）修复前后 savedTerminated 的等价表达式逐情形求值：")
                for label, rs, ct, want in [
                    ("新户（added + merge_household）", "added", "merge_household", False),
                    ("原户（cancelled + merge_household）", "cancelled", "merge_household", True),
                    ("正常户（normal + none）", "normal", "none", False),
                ]:
                    before = saved_terminated(rs, ct, fixed=False)
                    after = saved_terminated(rs, ct, fixed=True)
                    note(f"{label}", f"修复前自算只读={before} 修复后={after}（期望 {want}）")
                    check(f"修复后「{label}」只读判定正确", after is want, f"-> {after}")
                    if label.startswith("新户"):
                        check("★ 修复前「新户」被自算成已终结（只读）——即用户看到的'不能修改'",
                              before is True, f"-> {before}")

                log("\n=== 6 关键断言：新户能不能保存 ===")
                st_new, rp_new = put_result(new_uid, hm_detail_raw)
                detail_new = rp_new.get("detail") if isinstance(rp_new, dict) else rp_new
                note("新户 PUT 响应", f"HTTP {st_new} detail={detail_new!r}")
                check("★ 合户生成的新户 PUT 200（管理员口径，可以继续录入）", st_new == 200,
                      f"-> {st_new} {brief(rp_new)}")

                base_new = sql(
                    "SELECT task_status, assigned_to, assigned_to_name FROM survey_cbf_base "
                    "WHERE batch_id = %s AND cbfbm = %s", (BATCH_ID, HM))
                note("新户 task 行", f"{base_new}")
                check("★ 新户继承了原户的调查员（assigned_to=7，否则调查员本人也改不了）",
                      bool(base_new) and base_new[0][1] == 7, f"-> {base_new}")

                st_cw, rp_cw = api(
                    f"/surveys/batches/{BATCH_ID}/tasks?keyword={HM}&page=1&page_size=20", token=TOKEN_7)
                items = ((rp_cw or {}).get("data") or {}).get("items") or []
                row = next((i for i in items if i.get("cbfbm") == HM), {}) if st_cw == 200 else {}
                note("user 7 视角的列表行", f"canWrite={row.get('canWrite')} assignedTo={row.get('assignedTo')}")
                # ⛔ 本项目接口统一包一层 {"data": …}：先剥 data 再取字段。
                check("★ user 7（真实调查员）看到新户 canWrite=True（界面不会只读）",
                      row.get("canWrite") is True, f"-> {row.get('canWrite')}")

                st_u7, rp_u7 = api(
                    f"/surveys/batches/{BATCH_ID}/results/{new_uid}", method="PUT",
                    body=result_payload(get_detail(new_uid)), token=TOKEN_7)
                detail_u7 = rp_u7.get("detail") if isinstance(rp_u7, dict) else rp_u7
                note("user 7 保存新户", f"HTTP {st_u7} detail={detail_u7!r}")
                check("★ user 7（真实调查员）保存新户 200", st_u7 == 200, f"-> {st_u7} {brief(rp_u7)}")

                log("\n=== 7 回归断言：原户必须仍然被拦 ===")
                for uid, code in ((uid_a, HA), (uid_b, HB)):
                    st_old, rp_old = put_result(uid, get_detail(uid))
                    det = rp_old.get("detail") if isinstance(rp_old, dict) else rp_old
                    note(f"原户 {code} PUT 响应", f"HTTP {st_old} detail={det!r}")
                    check(f"★ 原户 {code} PUT 400（已注销，不可改）", st_old == 400,
                          f"-> {st_old} {brief(rp_old)}")

                log("\n=== 8 撤回合户并复核 ===")
                st, rp = api(f"/surveys/batches/{BATCH_ID}/results/{uid_a}/merge-household/rollback",
                             method="POST")
                check("撤回合户 200", st == 200, f"-> {st} {brief(rp)}")
                a_after = get_detail(uid_a)
                check("撤回后原户 A 恢复可写（PUT 200）",
                      put_result(uid_a, a_after)[0] == 200,
                      f"-> resultStatus={a_after.get('resultStatus')!r}")

    log("\n清理本轮夹具 ...")
    housekeeping()

    log("\n" + "=" * 72)
    passed = len([x for x in OUT if x.startswith("[PASS]")])
    log(f"结果：{'全部通过' if not FAILED else '存在失败'}  |  PASS {passed} / FAIL {len(FAILED)}")
    for item in FAILED:
        log(f"  ✗ {item}")

    out_path = ROOT / "runtime" / ".state" / "_verify_merge_new_editable.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(OUT), encoding="utf-8")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
