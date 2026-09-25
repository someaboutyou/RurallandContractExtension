# -*- coding: utf-8 -*-
"""合户后「新户能不能改」的浏览器端验收：夹具准备 / 清理（配合
`runtime/.state/e2e_merge_editable.mjs`）。

用法：
    runtime/windows/python/python.exe scripts/_e2e_merge_editable.py setup
    runtime/windows/python/python.exe scripts/_e2e_merge_editable.py cleanup

夹具（批次 41，同一村组 32132410000102）：
  · 88-1 / 88-2 两户 → 分给 user 7（真实调查员）→ 合户成 88-3（新户）
  · 88-4 单独一户 → 确认调查结果（作为「只读渲染仍然生效」的反向对照）
token 用 `create_access_token("7")` 铸（sub=user_id，无需密码）。
"""
from __future__ import annotations

import json
import os
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

import psycopg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.main import app  # noqa: E402

BATCH_ID = 41
HA, HB, HM, HC = ("321324100001029881", "321324100001029882",
                  "321324100001029883", "321324100001029884")
ALL_CODES = [HA, HB, HM, HC]
OWNER_ID = 7
TOKEN = create_access_token(str(OWNER_ID))
CTX_PATH = ROOT / "runtime" / ".state" / "_e2e_merge_editable_ctx.json"
DSN = (f"host={settings.database_host} port={settings.database_port} "
       f"dbname={settings.database_name} user={settings.database_user} "
       f"password={settings.database_password}")

client: TestClient | None = None


def api(path: str, method: str = "GET", body=None):
    assert client is not None
    resp = client.request(method, f"/api/v1{path}", json=body,
                          headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        return resp.status_code, resp.json()
    except Exception:  # noqa: BLE001
        return resp.status_code, resp.text


def sql(text: str, params=None):
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(text, params)
            return cur.fetchall()


def get_detail(uid: str) -> dict:
    st, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}")
    return payload.get("data") if st == 200 and isinstance(payload, dict) else {}


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


def result_payload(detail: dict, *, members=None, **overrides) -> dict:
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
        "deletedMembers": [], "pendingOperations": [],
    }
    payload.update(overrides)
    return payload


def put_result(uid: str, detail: dict, **kwargs):
    return api(f"/surveys/batches/{BATCH_ID}/results/{uid}", method="PUT",
               body=result_payload(detail, **kwargs))


def wipe_fixtures() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT contractor_uid FROM survey_cbf_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
            uids = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT contractor_uid FROM survey_cbf_base WHERE batch_id = %s AND cbfbm = ANY(%s)",
                        (BATCH_ID, ALL_CODES))
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
            cur.execute("DELETE FROM survey_change_diffs WHERE batch_id = %s AND contractor_uid NOT IN"
                        " (SELECT contractor_uid FROM survey_cbf_result)", (BATCH_ID,))
            cur.execute("DELETE FROM survey_change_records WHERE batch_id = %s AND contractor_uid NOT IN"
                        " (SELECT contractor_uid FROM survey_cbf_result)", (BATCH_ID,))
    print("fixtures wiped")


def valid_id(prefix17: str) -> str:
    """补校验位，生成一个形式合法的 18 位身份证号（前端加严校验会拦下不合法的值）。"""
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check = "10X98765432"
    return prefix17 + check[sum(int(prefix17[i]) * weights[i] for i in range(17)) % 11]


def build_household(code: str, name: str) -> str:
    st, payload = api(f"/surveys/batches/{BATCH_ID}/tasks", method="POST", body={
        "code": code, "typeCode": "1", "name": name, "idType": "1",
        "idNo": valid_id("32032419900101" + code[-2:] + "0"), "address": "实证临时地址",
        "postcode": "223900", "mobile": "13900000000",
        "surveyorName": "实证脚本", "surveyDate": "2026-09-25",
        "remark": "e2e merge-editable fixture",
    })
    if st != 201:
        raise SystemExit(f"建户 {code} 失败: {st} {payload}")
    uid = payload["data"]["contractorUid"]
    detail = get_detail(uid)
    members = members_payload(detail.get("familyMembers") or [])
    for idx in range(2):
        members.append({"name": f"实{code[-2:]}{idx + 1}", "gender": "1", "idType": "1",
                        "idNo": valid_id("32032419900101" + code[-2:] + str(idx + 1)),
                        "relationToHead": "02" if idx == 0 else "20",
                        "isHouseholdHead": idx == 0})
    st, resp = put_result(uid, detail, members=members, surveyStatus="surveyed")
    if st != 200:
        raise SystemExit(f"{code} 补成员失败: {st} {resp}")
    return uid


def setup() -> None:
    global client
    wipe_fixtures()
    with TestClient(app) as c:
        client = c
        uid_a = build_household(HA, "实证浏览器户A")
        uid_b = build_household(HB, "实证浏览器户B")
        uid_c = build_household(HC, "实证浏览器对照户")

        st, resp = api(f"/surveys/batches/{BATCH_ID}/tasks/assign", method="PUT",
                       body={"contractorUids": [uid_a, uid_b], "assigneeId": OWNER_ID})
        if st != 200:
            raise SystemExit(f"分配失败: {st} {resp}")

        head = next((m.get("memberUid") for m in (get_detail(uid_a).get("familyMembers") or [])
                     if m.get("isHouseholdHead")), None)
        st, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid_a}/merge-household",
                       method="POST", body={
                           "sourceContractorUids": [uid_a, uid_b], "newCbfbm": HM,
                           "newCbfmc": "实证浏览器合户新户", "householdHeadMemberUid": head,
                           "newAddress": "实证合并地址", "reason": "E2E 合户",
                       })
        if st != 200:
            raise SystemExit(f"合户失败: {st} {resp}")
        new_uid = resp["data"]["newHousehold"]["contractorUid"]

        # 反向对照：把对照户**收回分配**（assigneeId=null）⇒ 当前用户对它只读
        # （批次 41 的 created_by=7，新增户默认就落到 7 名下，所以要显式收回）。
        st, resp = api(f"/surveys/batches/{BATCH_ID}/tasks/assign", method="PUT",
                       body={"contractorUids": [uid_c], "assigneeId": None})
        if st != 200:
            raise SystemExit(f"收回对照户分配失败: {st} {resp}")
        ctrl_owner = sql("SELECT assigned_to FROM survey_cbf_base WHERE batch_id = %s AND cbfbm = %s",
                         (BATCH_ID, HC))
        if ctrl_owner and ctrl_owner[0][0] is not None:
            raise SystemExit(f"对照户不应有归属人，实际 assigned_to={ctrl_owner[0][0]}")

        batch_rows = sql("SELECT batch_no, batch_name FROM survey_batches WHERE id = %s", (BATCH_ID,))
        ctx = {
            "base": "http://127.0.0.1:8010",
            "batchId": BATCH_ID,
            "batchNo": (batch_rows[0][0] if batch_rows else "") or "",
            "batchName": (batch_rows[0][1] if batch_rows else "") or "",
            "ownerId": OWNER_ID,
            "ownerName": sql("SELECT real_name FROM users WHERE id = %s", (OWNER_ID,))[0][0],
            "token": TOKEN,
            "newHousehold": {"code": HM, "name": "实证浏览器合户新户", "uid": new_uid},
            "sourceCodes": [HA, HB],
            "control": {"code": HC, "name": "实证浏览器对照户", "uid": uid_c},
        }
        CTX_PATH.write_text(json.dumps(ctx, ensure_ascii=False, indent=2), encoding="utf-8")
        # ⛔ 不要把 ctx 整体打出来：里面含 token，日志会被当成凭据拦掉。
        print("ctx 已写入:", CTX_PATH)
        print("  批次:", ctx["batchNo"], ctx["batchName"], "| 归属人:", ctx["ownerId"], ctx["ownerName"])
        print("  新户:", ctx["newHousehold"]["code"], ctx["newHousehold"]["name"])
        print("  原户:", ctx["sourceCodes"], "| 对照户(未分配):", ctx["control"]["code"])


def cleanup() -> None:
    global client
    with TestClient(app) as c:
        client = c
        # 先撤回合户（把原户恢复），再硬删夹具
        src = sql("SELECT contractor_uid FROM survey_cbf_result WHERE cbfbm = %s", (HA,))
        if src:
            st, resp = api(f"/surveys/batches/{BATCH_ID}/results/{src[0][0]}/merge-household/rollback",
                           method="POST")
            print("撤回合户:", st, str(resp)[:160])
    wipe_fixtures()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "setup"
    if mode == "setup":
        setup()
    elif mode == "cleanup":
        cleanup()
    else:
        raise SystemExit("用法: setup | cleanup")
