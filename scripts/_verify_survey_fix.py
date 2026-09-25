# -*- coding: utf-8 -*-
"""验收：承包方调查录入 4 项修复的端到端回归。

与 _verify_survey_rollback*.py 的区别：那两个走 HTTP 打运行中的 8000 实例，
必须重启后端才会加载新代码；本脚本用**进程内 TestClient**（会跑 lifespan +
bootstrap），因此验的一定是当前工作区里的源码，不需要重启用户的实例。

覆盖的修复点：
  F1  P0-1  「移除地块 → 撤回移除」全链路：期望 200，且地块/关联/变更记录完整还原
            （修复前 100% NameError → 500，整次保存事务回滚）
  F2  P1-3  改 cbfmc：survey_change_diffs 必须出现 cbfmc 行
            （修复前 base 快照被就地覆写 ⇒ 比对恒等 ⇒ 永远进不了差异表）
  F3  P1-2  分户（pending 队列路径，commit=False）：原户与新户的 diffs 都要被重建
            （修复前 "if not commit: return" 排在重建之前 ⇒ 两边都不刷新）
  F4  P1-4  删除临时户：地块/关联/变更记录/差异行/标签全部清空，同一 dkbm 可复用
            （修复前地块残留 ⇒ 编码被永久占用）

跑法：runtime/windows/python/python.exe scripts/_verify_survey_fix.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "runtime" / ".state" / "_verify_survey_fix.txt"

# 必须先注入 DB 配置再 import app：config.py 里 database_port 默认 5432 是错的，
# 真实实例在 15432；连不上时 psycopg 会让进程静默退出（exit 1，无输出）。
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
TEMP_A = "321324100001029801"          # F1 / F2 共用
TEMP_D = "321324100001029802"          # F4 删户清理
TEMP_E = "321324100001029803"          # F4 编码复用
SPLIT_CHILDREN = ["321324100001029811", "321324100001029812"]  # F3 分户产物
ALL_TEMP_CODES = [TEMP_A, TEMP_D, TEMP_E, *SPLIT_CHILDREN]

TOKEN = create_access_token("1")
DSN = (
    f"host={settings.database_host} port={settings.database_port} "
    f"dbname={settings.database_name} user={settings.database_user} "
    f"password={settings.database_password}"
)

OUT: list[str] = []
FAILED: list[str] = []
ERRORS: list[str] = []
client: TestClient | None = None


# ────────────────────────── 基础设施 ──────────────────────────
def log(*parts) -> None:
    line = " ".join(str(p) for p in parts)
    OUT.append(line)
    print(line)


KNOWN_GAPS: list[str] = []


def check(label: str, ok: bool, extra: str = "", *, gap: bool = False) -> bool:
    """gap=True 表示「已知残留缺陷」：断言按设计意图写，失败不阻断本次验收，
    但会单独列出——避免把设计意图没达成的项目混进 PASS 里。"""
    tag = "PASS" if ok else ("GAP " if gap else "FAIL")
    log(f"[{tag}] {label} {extra}".rstrip())
    if not ok:
        (KNOWN_GAPS if gap else FAILED).append(label)
    return ok


def api(path: str, method: str = "GET", body=None):
    assert client is not None
    resp = client.request(
        method,
        f"/api/v1{path}",
        json=body,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    try:
        return resp.status_code, resp.json()
    except Exception:  # noqa: BLE001
        return resp.status_code, resp.text


def brief(payload, limit: int = 400) -> str:
    return str(payload)[:limit]


def sql(sql_text: str, params=None):
    """只读查询，直连 PG（脚本已注入 DATABASE_* 环境变量）。"""
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text, params)
            return cur.fetchall()


# ────────────────────────── 状态读取 ──────────────────────────
def get_detail(uid: str, bid: int = BATCH_ID) -> dict:
    status, payload = api(f"/surveys/batches/{bid}/results/{uid}")
    return payload.get("data") if status == 200 and isinstance(payload, dict) else {}


def get_parcels(uid: str, bid: int = BATCH_ID) -> list:
    status, payload = api(f"/surveys/batches/{bid}/results/{uid}/parcels")
    return (payload.get("data") or []) if status == 200 and isinstance(payload, dict) else []


def get_diffs(uid: str, bid: int = BATCH_ID) -> list:
    status, payload = api(f"/surveys/batches/{bid}/results/{uid}/diffs?page=1&page_size=500")
    if status == 200 and isinstance(payload, dict):
        return (payload.get("data") or {}).get("items") or []
    return []


def get_changes(uid: str, bid: int = BATCH_ID) -> list:
    status, payload = api(f"/surveys/batches/{bid}/changes?contractorUid={uid}&page=1&page_size=200")
    if status == 200 and isinstance(payload, dict):
        return (payload.get("data") or {}).get("items") or []
    return []


def diff_labels(diffs: list) -> list[str]:
    return [f"{d.get('entityType')}:{d.get('fieldLabel')}" for d in diffs]


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


def result_payload(detail: dict, *, members=None, deleted=None, pending=None, **overrides) -> dict:
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
        "deletedMembers": deleted or [],
        "pendingOperations": pending or [],
    }
    payload.update(overrides)
    return payload


def put_result(uid: str, detail: dict, **kwargs):
    return api(f"/surveys/batches/{BATCH_ID}/results/{uid}", method="PUT",
               body=result_payload(detail, **kwargs))


def housekeeping() -> None:
    """幂等收尾：按临时编码前缀清掉本轮夹具（含分户派生户）。"""
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT contractor_uid FROM survey_cbf_result WHERE cbfbm = ANY(%s)",
                (ALL_TEMP_CODES,),
            )
            uids = [r[0] for r in cur.fetchall()]
            if uids:
                # 连带清掉这些户新增出来的地块（按关联定位）
                cur.execute(
                    "SELECT DISTINCT dkbm FROM survey_cbdkxx_result WHERE cbfbm = ANY(%s)",
                    (ALL_TEMP_CODES,),
                )
                dkbms = [r[0] for r in cur.fetchall()]
                for table, column in (
                    ("survey_change_diffs", "contractor_uid"),
                    ("survey_change_records", "contractor_uid"),
                    ("survey_household_tags", "contractor_uid"),
                    ("survey_cbf_jtcy_result", "contractor_uid"),
                ):
                    cur.execute(f"DELETE FROM {table} WHERE {column} = ANY(%s)", (uids,))
                for table in ("survey_cbf_jtcy_base", "survey_cbf_base"):
                    cur.execute(f"DELETE FROM {table} WHERE contractor_uid = ANY(%s)", (uids,))
                cur.execute("DELETE FROM survey_cbdkxx_result WHERE cbfbm = ANY(%s)", (ALL_TEMP_CODES,))
                cur.execute("DELETE FROM survey_cbdkxx_base WHERE cbfbm = ANY(%s)", (ALL_TEMP_CODES,))
                if dkbms:
                    cur.execute("DELETE FROM survey_dk_result WHERE dkbm = ANY(%s)", (dkbms,))
                    cur.execute("DELETE FROM survey_dk_base WHERE dkbm = ANY(%s)", (dkbms,))
                cur.execute("DELETE FROM survey_cbf_result WHERE cbfbm = ANY(%s)", (ALL_TEMP_CODES,))


def setup_household(code: str, name: str, member_name: str) -> tuple[str, dict]:
    log(f"\n--- 建临时户 {code} ({name}) ---")
    status, payload = api(
        f"/surveys/batches/{BATCH_ID}/tasks",
        method="POST",
        body={
            "code": code, "typeCode": "1", "name": name, "idType": "1",
            "idNo": "3203241990010188" + code[-2:], "address": "验收临时地址",
            "postcode": "223900", "mobile": "13900000000",
            "surveyorName": "验收脚本", "surveyDate": "2026-09-24",
            "remark": "survey fix verify fixture",
        },
    )
    if status != 201:
        check(f"建户 {code}", False, f"-> {status} {brief(payload)}")
        return "", {}
    uid = (payload.get("data") or {}).get("contractorUid") or ""
    check(f"建户 {code} 成功", bool(uid), f"uid={uid}")
    if not uid:
        return "", {}
    detail = get_detail(uid)
    members = members_payload(detail.get("familyMembers") or [])
    suffix = code[-2:]
    # 建 2 名成员：F3 分户要求「≥2 成员 ≥2 地块」，且每名成员必须且只能落到一个新户。
    for idx in range(2):
        members.append({
            "name": f"{member_name}{idx + 1}", "gender": "1", "idType": "1",
            "idNo": f"3203241990010{suffix}{idx}",
            "relationToHead": "01" if idx == 0 else "02",
            "isHouseholdHead": idx == 0,
        })
    status, resp = put_result(uid, detail, members=members)
    check("建户后补 2 名成员", status == 200, f"-> {status} {brief(resp, 300)}")
    return uid, get_detail(uid)


def add_parcel(uid: str, dkbm: str, label: str):
    detail = get_detail(uid)
    op = {"type": "add_parcel", "payload": {
        "dkbm": dkbm, "dkmc": label, "dklb": "01", "dldj": "01", "tdyt": "1",
        "tdlylx": "011", "syqxz": "10", "scmj": "1000", "sfjbnt": "1",
        "reason": "验收新增地块",
    }}
    return put_result(uid, detail, pending=[op])


# ────────────────────────── F4 用的小查询 ──────────────────────────
def count_by_uid(table: str, uid: str, column: str = "contractor_uid") -> int:
    return sql(f"SELECT count(*) FROM {table} WHERE {column} = %s", (uid,))[0][0]


def count_dk(table: str, dkbm: str) -> int:
    return sql(f"SELECT count(*) FROM {table} WHERE dkbm = %s", (dkbm,))[0][0]


# ────────────────────────── 用例 ──────────────────────────
def case_f1_remove_rollback(uid: str) -> None:
    """P0-1：移除地块 → 撤回移除，全链路必须 200 且状态还原。"""
    log("\n=== F1 (P0-1) 移除地块 → 撤回移除 ===")
    codes = []
    for i in range(2):
        code = next_parcel_code(uid)
        if not code:
            check("取地块编码（F1）", False, "-> next-code 未返回")
            return
        status, resp = add_parcel(uid, code, f"F1地块{i+1}")
        if status != 200:
            check(f"新增地块 {code}", False, f"-> {status} {brief(resp, 400)}")
            return
        codes.append(code)
    check("F1 新增 2 个地块", len(codes) == 2, f"-> {codes}")

    victim = codes[0]
    detail = get_detail(uid)
    status, resp = put_result(
        uid, detail,
        pending=[{"type": "remove_parcel", "payload": {"dkbm": victim, "reason": "F1 移除地块"}}],
    )
    check("移除地块 PUT 200", status == 200, f"-> {status} {brief(resp, 400)}")
    active = [p for p in get_parcels(uid) if p.get("resultStatus") not in ("removed", "split_source")]
    check("地块已从有效列表移除", not any(p.get("dkbm") == victim for p in active),
          f"-> 剩余 {[p.get('dkbm') for p in active]}")

    changes = [c for c in get_changes(uid)
               if c.get("changeType") == "remove_parcel" and c.get("changeStatus") != "rolled_back"]
    if not check("存在未撤回的 remove_parcel 记录", bool(changes),
                 f"-> {[(c.get('id'), c.get('changeNo')) for c in changes]}"):
        return
    change = changes[0]

    detail2 = get_detail(uid)
    rollback_op = {"type": "rollback_remove_parcel", "payload": {
        "changeId": change.get("id"), "changeNo": change.get("changeNo"),
        "dkbm": victim, "cbfbm": detail2.get("code"),
        "sourceResultStatus": "normal", "sourceChangeType": "none",
        "sourceChangeReason": None, "sourceIsChanged": False,
        "reason": f"撤回移除 {change.get('changeNo')}",
    }}
    status, resp = put_result(uid, detail2, pending=[rollback_op])

    # ← 这一条就是本次修复的核心断言：修复前必然 500
    check("★ 撤回移除返回 200（修复前 100% 500）", status == 200,
          f"-> 实际 {status} {brief(resp, 400)}")
    if status != 200:
        return

    active2 = [p for p in get_parcels(uid) if p.get("resultStatus") not in ("removed", "split_source")]
    check("★ 撤回后地块回到有效列表", any(p.get("dkbm") == victim for p in active2),
          f"-> {[p.get('dkbm') for p in active2]}")
    all_changes = get_changes(uid)
    rolled = [c for c in all_changes if c.get("id") == change.get("id")]
    check("★ 原 remove_parcel 记录已标记 rolled_back",
          bool(rolled) and rolled[0].get("changeStatus") == "rolled_back",
          f"-> {[(c.get('id'), c.get('changeStatus')) for c in rolled]}")
    check("★ 生成 rollback_remove_parcel 留痕记录",
          any(c.get("changeType") == "rollback_remove_parcel" for c in all_changes),
          f"-> {[c.get('changeType') for c in all_changes]}")
    err = sql(
        "SELECT before_summary, after_summary FROM survey_change_records "
        "WHERE change_type = 'rollback_remove_parcel' AND contractor_uid = %s "
        "ORDER BY id DESC LIMIT 1", (uid,),
    )
    check("★ 撤回记录的 restored_* 快照已正确落库（修复前这里是 NameError 点）",
          bool(err) and (err[0][1] or {}).get("restored_result_status") is not None,
          f"-> {err[0][1] if err else None}")


def case_f2_rename_diff(uid: str) -> None:
    """P1-3：改 cbfmc 必须进 survey_change_diffs。"""
    log("\n=== F2 (P1-3) 改 cbfmc → diffs ===")
    detail = get_detail(uid)
    origin = detail.get("name")
    base_n = len(get_diffs(uid))
    parcel_diff_before = len([d for d in get_diffs(uid) if d.get("fieldLabel") == "新增地块关联"])
    log(f"  起始 name={origin} diffs={base_n} 新增地块关联={parcel_diff_before}")

    status, resp = put_result(uid, detail, name=f"{origin}-改名验证")
    check("改名 PUT 200", status == 200, f"-> {status} {brief(resp, 300)}")
    after = get_detail(uid)
    check("改名已生效", after.get("name") == f"{origin}-改名验证", f"-> {after.get('name')}")

    diffs = get_diffs(uid)
    hit = [d for d in diffs if d.get("fieldName") == "cbfmc"]
    check("★ diffs 出现 cbfmc 变更行（修复前为 0 条）", bool(hit),
          f"-> {[(d.get('beforeValue'), d.get('afterValue')) for d in hit]}")
    if hit:
        check("★ cbfmc 行的 before/after 都有值且不同",
              hit[0].get("beforeValue") and hit[0].get("afterValue")
              and hit[0].get("beforeValue") != hit[0].get("afterValue"),
              f"-> {hit[0].get('beforeValue')} -> {hit[0].get('afterValue')}")

    parcel_diff_after = len([d for d in get_diffs(uid) if d.get("fieldLabel") == "新增地块关联"])
    check("★ 改名不污染地块差异（base.cbfbm 未被就地覆写）",
          parcel_diff_after == parcel_diff_before,
          f"-> {parcel_diff_before} -> {parcel_diff_after}")

    # 还原名字，回到净零
    detail2 = get_detail(uid)
    status, resp = put_result(uid, detail2, name=origin)
    check("改回原名 PUT 200", status == 200, f"-> {status} {brief(resp, 300)}")
    hit2 = [d for d in get_diffs(uid) if d.get("fieldName") == "cbfmc"]
    # 净差异语义要求 diff 的 before 取「批次基线」。2026-09-24 起 update_result
    # 收尾**不再**把 survey_cbf_base.cbfbm/cbfmc 同步成当前值（base 只同步任务态
    # 字段），批次基线不再被推进 ⇒ 改回原值时比对恒等、差异行消失。
    check("★ 改回原值后 cbfmc 行消失（净差异语义保持）", not hit2,
          f"-> {[(d.get('beforeValue'), d.get('afterValue')) for d in hit2]}")


def case_f3_split_diff(uid: str) -> None:
    """P1-2：分户（pending 队列路径）后原户与新户 diffs 都要重建。"""
    log("\n=== F3 (P1-2) 分户 → diffs 重建 ===")
    detail = get_detail(uid)
    members = detail.get("familyMembers") or []
    active = [p for p in get_parcels(uid) if p.get("resultStatus") not in ("removed", "split_source")]
    log(f"  成员 {len(members)} / 有效地块 {len(active)}")
    if len(members) < 2 or len(active) < 2:
        check("分户前置条件（≥2 成员 ≥2 地块）", False, f"-> 成员 {len(members)} 地块 {len(active)}")
        return

    op = {"type": "split_household", "payload": {
        "newHouseholds": [
            {"newCbfbm": SPLIT_CHILDREN[0], "newCbfmc": "验收分户甲",
             "memberUids": [members[0].get("memberUid")],
             "parcelDkbms": [active[0].get("dkbm")],
             "householdHeadMemberUid": members[0].get("memberUid")},
            {"newCbfbm": SPLIT_CHILDREN[1], "newCbfmc": "验收分户乙",
             "memberUids": [m.get("memberUid") for m in members[1:]],
             "parcelDkbms": [p.get("dkbm") for p in active[1:]],
             "householdHeadMemberUid": members[1].get("memberUid")},
        ],
        "reason": "验收分户",
    }}
    before_src_diffs = len(get_diffs(uid))
    status, resp = put_result(uid, detail, pending=[op])
    check("分户 PUT 200", status == 200, f"-> {status} {brief(resp, 500)}")
    if status != 200:
        return

    src = get_detail(uid)
    src_diffs = get_diffs(uid)
    log(f"  原户 resultStatus={src.get('resultStatus')} changeType={src.get('changeType')} "
        f"分户前 diffs={before_src_diffs} -> 分户后 {len(src_diffs)}: {diff_labels(src_diffs)}")
    # 分户后原户必须按「批次基线」重算。临时户的基线里既没有成员也没有地块
    # （成员是建户后新增的、地块由 add_parcel 新增，两者都不写 base），
    # 所以重算结果为空集——这与「停在分户前的旧快照」是两种完全不同的结果。
    # P1-2 未修时这里会原样保留分户前的 diffs（旧值），断言据此区分修复前后。
    check("★ 原户 diffs 已被重建（不再是分户前的旧快照）",
          before_src_diffs > 0 and len(src_diffs) != before_src_diffs,
          f"-> 分户前 {before_src_diffs} 条 -> 分户后 {len(src_diffs)} 条")

    for code in SPLIT_CHILDREN:
        rows = sql("SELECT contractor_uid FROM survey_cbf_result WHERE cbfbm = %s", (code,))
        if not rows:
            check(f"新户 {code} 已生成", False)
            continue
        n_uid = rows[0][0]
        n_diffs = get_diffs(n_uid)
        log(f"  新户 {code} diffs={len(n_diffs)}: {diff_labels(n_diffs)}")
        check(f"★ 新户 {code} 的 diffs 非空（修复前恒为 0）", len(n_diffs) > 0, f"-> {len(n_diffs)} 条")


def case_f4_delete_cleanup() -> None:
    """P1-4：删户必须清干净地块/关联/变更/差异/标签，且编码可复用。"""
    log("\n=== F4 (P1-4) 删户清理 ===")
    uid, _ = setup_household(TEMP_D, "验收临时户D", "D户成员")
    if not uid:
        return
    code = next_parcel_code(uid)
    status, resp = add_parcel(uid, code, "D户地块")
    check(f"D 户新增地块 {code}", status == 200, f"-> {status} {brief(resp, 400)}")
    if status != 200:
        return

    before = {
        "diff": count_by_uid("survey_change_diffs", uid),
        "record": count_by_uid("survey_change_records", uid),
        "tag": count_by_uid("survey_household_tags", uid),
        "rel": count_by_uid("survey_cbdkxx_result", TEMP_D, column="cbfbm"),
        "dk": count_dk("survey_dk_result", code),
    }
    log(f"  删除前: {before}")
    check("删除前确实存在派生数据（否则本用例无意义）",
          before["diff"] > 0 and before["rel"] > 0 and before["dk"] > 0, f"-> {before}")

    status, resp = api(f"/contractors/{TEMP_D}", method="DELETE")
    check("DELETE /contractors 200", status in (200, 204), f"-> {status} {brief(resp, 300)}")

    after = {
        "cbf": sql("SELECT count(*) FROM survey_cbf_result WHERE cbfbm = %s", (TEMP_D,))[0][0],
        "cbf_base": count_by_uid("survey_cbf_base", uid),
        "rel": count_by_uid("survey_cbdkxx_result", TEMP_D, column="cbfbm"),
        "rel_base": count_by_uid("survey_cbdkxx_base", TEMP_D, column="cbfbm"),
        "dk": count_dk("survey_dk_result", code),
        "dk_base": count_dk("survey_dk_base", code),
        "diff": count_by_uid("survey_change_diffs", uid),
        "record": count_by_uid("survey_change_records", uid),
        "tag": count_by_uid("survey_household_tags", uid),
        "member": count_by_uid("survey_cbf_jtcy_result", uid),
    }
    log(f"  删除后: {after}")
    for key, value in after.items():
        check(f"★ 删户后 {key} 残留为 0", value == 0, f"-> {value}")

    # 编码复用：修 P1-4 之前这里必然 400 already exists
    uid_e, _ = setup_household(TEMP_E, "验收临时户E", "E户成员")
    if not uid_e:
        return
    status, resp = add_parcel(uid_e, code, "E户复用编码地块")
    check("★ 同一 dkbm 可被新户复用（修复前 400 already exists）", status == 200,
          f"-> {status} {brief(resp, 400)}")


def main() -> None:
    global client
    log("=" * 72)
    log("承包方调查录入 —— 4 项修复端到端验收（进程内 TestClient）")
    log("=" * 72)

    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, status FROM survey_batches WHERE id = %s", (BATCH_ID,))
            row = cur.fetchone()
    log(f"批次 {BATCH_ID}: {row}")
    if row is None or row[1] != "active":
        log("批次不可用（需 active），终止。")
        OUT_PATH.write_text("\n".join(OUT), encoding="utf-8")
        return

    housekeeping()

    with TestClient(app, raise_server_exceptions=False) as c:
        client = c

        uid, _ = setup_household(TEMP_A, "验收临时户A", "A户成员")
        if uid:
            case_f2_rename_diff(uid)
            case_f1_remove_rollback(uid)
            case_f3_split_diff(uid)

        case_f4_delete_cleanup()

        log("\n--- 收尾清理 ---")
        for code in ALL_TEMP_CODES:
            status, _ = api(f"/contractors/{code}", method="DELETE")
            log(f"  DELETE {code} -> {status}")
        housekeeping()

    log("\n" + "=" * 72)
    log(f"结果：{'全部通过' if not FAILED else '存在失败'}  |  "
        f"FAIL {len(FAILED)} / 已知残留 {len(KNOWN_GAPS)}")
    if FAILED:
        for item in FAILED:
            log(f"  ✗ {item}")
    if KNOWN_GAPS:
        for item in KNOWN_GAPS:
            log(f"  ~ [已知残留] {item}")
    if ERRORS:
        for item in ERRORS:
            log(f"  ! {item}")
    log("=" * 72)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(OUT), encoding="utf-8")
    log(f"输出已写入 {OUT_PATH}")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
