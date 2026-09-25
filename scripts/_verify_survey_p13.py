# -*- coding: utf-8 -*-
"""P1-3 彻底修复 + 分户/合户「承包方状态」差异不对称 复测。

背景
----
P1-3（半修）：上一轮把 result.py 里「把 task.cbfbm/cbfmc 覆写成当前值」下移到
diff 重建之后，改名终于能进 survey_change_diffs 了，但**净差异语义仍不成立**：
改名产生 1 条差异，改回原值不是"差异消失"，而是又比出一条（before/after 互换）。
根因是 survey_cbf_base 一张表既是批次基线快照、又被当任务表用，保存时基线被
就地推进 ⇒ 初始基线丢失。

本轮修复：
  A1 result.py::update_result —— **删掉** task.cbfbm/cbfmc 的覆写（只回写任务态字段）；
  A2 task.py::_serialize_task  —— 列表显示改取 result 当前值（base 仅兜底）；
  A3 task.py::list_tasks       —— keyword 搜索同时覆盖 base 与 result 两侧
                                 （先取 Python 列表再 in_()，避免 loader criteria 二次注入）。

差异不对称：
  deregister_contractor 会手工补一条「承包方状态」diff，而 split/merge_household 不补
  ⇒ 分户/合户后原户的 cancelled 状态在差异表里不可见。
  修复：在 split/merge 的 _rebuild_contractor_diffs **之后**各补一条
  （survey_cbf_base 没有 result_status 列，无法自动比对；提前插会被重建的 DELETE 清掉）。

本脚本验证（进程内 TestClient，验的一定是当前源码）：
  T1 ★  改名 → 产生 cbfmc 差异 → **改回原值 → 差异行消失**（净差异语义成立）
  T2 ★  base 基线未被推进（DB 实测 base.cbfmc 仍是初始值，result 是新值）
  T3 ★  任务列表显示当前名、且按新名可搜到
  T4 ★  分户后原户 diffs 含「承包方状态」→ 撤回分户后消失
  T5 ★  合户后各原户 diffs 含「承包方状态」→ 撤回合户后消失

夹具：批次 41 下建 3 个临时户（HA 改名+分户 / HB+HC 合户），编码段 …985x，
      跑完自清（housekeeping 幂等）。
跑法：runtime/windows/python/python.exe scripts/_verify_survey_p13.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote

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
HA = "321324100001029851"        # 改名（T1-T3）+ 分户（T4）
HB = "321324100001029852"        # 合户参与方（T5）
HC = "321324100001029853"        # 合户参与方（T5）
SPLIT_CHILDREN = ["321324100001029854", "321324100001029855"]   # T4 分户产物
MERGE_CHILD = "321324100001029856"                              # T5 合户产物
ALL_CODES = [HA, HB, HC, *SPLIT_CHILDREN, MERGE_CHILD]

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
    line = f"[{tag}] {label}"
    if extra and (not ok or gap):
        line += f" {extra}"
    elif extra and ok:
        line += f" {extra}"
    OUT.append(line)
    print(line)
    if not ok:
        (KNOWN_GAPS if gap else FAILED).append(label)
    return ok


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


def get_parcels(uid: str) -> list:
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/parcels")
    return (payload.get("data") or []) if status == 200 and isinstance(payload, dict) else []


def get_diffs(uid: str) -> list:
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/diffs?page=1&page_size=500")
    if status == 200 and isinstance(payload, dict):
        return (payload.get("data") or {}).get("items") or []
    return []


def diff_labels(diffs: list) -> list[str]:
    return [f"{d.get('entityType')}:{d.get('fieldName')}" for d in diffs]


def get_changes(uid: str) -> list:
    status, payload = api(f"/surveys/batches/{BATCH_ID}/changes?contractorUid={uid}&page=1&page_size=200")
    if status == 200 and isinstance(payload, dict):
        return (payload.get("data") or {}).get("items") or []
    return []


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


def box_geometry(lon: float, lat: float, dlon: float, dlat: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon, lat], [lon + dlon, lat],
            [lon + dlon, lat + dlat], [lon, lat + dlat],
            [lon, lat],
        ]],
    }


def add_parcel(uid: str, dkbm: str, label: str, scmj: str = "1000", geometry=None):
    detail = get_detail(uid)
    body = {
        "dkbm": dkbm, "dkmc": label, "dklb": "01", "dldj": "01", "tdyt": "1",
        "tdlylx": "011", "syqxz": "10", "scmj": scmj, "sfjbnt": "1",
        "reason": "P1-3 复测新增地块",
    }
    if geometry is not None:
        body["geometry"] = geometry
        body["geometrySourceSrid"] = 4326
    return put_result(uid, detail, pending=[{"type": "add_parcel", "payload": body}])


# ────────────────────────── 收尾清理 ──────────────────────────
def housekeeping() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT contractor_uid FROM survey_cbf_result WHERE cbfbm = ANY(%s)",
                (ALL_CODES,),
            )
            uids = [r[0] for r in cur.fetchall()]
            cur.execute(
                "SELECT DISTINCT dkbm FROM survey_cbdkxx_result WHERE cbfbm = ANY(%s)"
                " UNION SELECT DISTINCT dkbm FROM survey_cbdkxx_base WHERE cbfbm = ANY(%s)",
                (ALL_CODES, ALL_CODES),
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
            # 兜底：分户/合户的台账可能挂在新生成户的 uid 上，而该户行随后被删除
            # ⇒ 上面按 cbfbm 取到的 uids 覆盖不到。必须在删完 survey_cbf_result
            # 之后再判"孤儿"，否则判据失效。
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
def setup_household(code: str, name: str, location: str) -> str:
    log(f"\n--- 建临时户 {code}（{name}）---")
    status, payload = api(
        f"/surveys/batches/{BATCH_ID}/tasks", method="POST",
        body={
            "code": code, "typeCode": "1", "name": name, "idType": "1",
            "idNo": "3203241990010198" + code[-2:], "address": f"P1-3 复测地址{location}",
            "postcode": "223900", "mobile": "13900000000",
            "surveyorName": "复测脚本", "surveyDate": "2026-09-24",
            "remark": "survey p1-3 verify fixture",
        },
    )
    if status != 201:
        check(f"建户 {code}", False, f"-> {status} {brief(payload)}")
        return ""
    uid = (payload.get("data") or {}).get("contractorUid") or ""
    if not check(f"建户 {code} 成功", bool(uid), f"-> uid={uid}"):
        return ""

    detail = get_detail(uid)
    members = members_payload(detail.get("familyMembers") or [])
    suffix = code[-2:]
    for idx in range(2):
        members.append({
            "name": f"复测{location}{idx + 1}", "gender": "1", "idType": "1",
            "idNo": f"3203241990010{suffix}{idx}",
            "relationToHead": "01" if idx == 0 else "02",
            "isHouseholdHead": idx == 0,
        })
    st, resp = put_result(uid, detail, members=members)
    check(f"{code} 补 2 名成员", st == 200, f"-> {st} {brief(resp, 300)}")
    return uid


# ────────────────────────── T1/T2/T3 改名净差异 ──────────────────────────
def case_rename(uid: str) -> None:
    log("\n=== T1/T2/T3 改名净差异 + 基线未被推进 + 列表显示与搜索 ===")
    detail = get_detail(uid)
    name0 = detail.get("name")
    code = detail.get("code")
    name1 = f"{name0}-改名验证"
    log(f"  初始名称={name0!r}  编码={code}")

    # ── 改名前：cbfmc 差异行应为 0
    before_rows = [d for d in get_diffs(uid) if d.get("fieldName") == "cbfmc"]
    check("T1 改名前无 cbfmc 差异行", not before_rows, f"-> {before_rows}")

    # ── 改名
    st, resp = put_result(uid, detail, name=name1)
    if not check("T1 改名 PUT 200", st == 200, f"-> {st} {brief(resp, 400)}"):
        return

    after = get_detail(uid)
    check("T1 结果表已是新名", after.get("name") == name1, f"-> {after.get('name')!r}")

    diffs = get_diffs(uid)
    rows = [d for d in diffs if d.get("fieldName") == "cbfmc"]
    check("T1 ★ 改名产生 cbfmc 差异行", len(rows) == 1, f"-> {diff_labels(diffs)}")
    if rows:
        check("T1 差异行 before/after 指向正确的两端",
              str(rows[0].get("beforeValue")) == str(name0) and str(rows[0].get("afterValue")) == str(name1),
              f"-> {rows[0].get('beforeValue')!r} -> {rows[0].get('afterValue')!r}")

    # ── T2 base 基线未被推进（直连 DB 实测）
    brows = sql("SELECT cbfmc FROM survey_cbf_base WHERE contractor_uid = %s", (uid,))
    base_name = brows[0][0] if brows else None
    check("T2 ★ base.cbfmc 未被推进（仍是初始基线值）", base_name == name0,
          f"-> base={base_name!r} 期望 {name0!r}")
    rrows = sql("SELECT cbfmc FROM survey_cbf_result WHERE contractor_uid = %s", (uid,))
    result_name = rrows[0][0] if rrows else None
    check("T2 result.cbfmc 保持当前值", result_name == name1, f"-> result={result_name!r}")

    # ── T3 列表显示 + 搜索
    st, payload = api(f"/surveys/batches/{BATCH_ID}/tasks?page=1&page_size=200")
    items = ((payload.get("data") or {}).get("items") or []) if st == 200 else []
    row = next((i for i in items if i.get("contractorUid") == uid), None)
    check("T3 ★ 任务列表显示当前（新）名称",
          bool(row) and row.get("cbfmc") == name1, f"-> {(row or {}).get('cbfmc')!r}")
    check("T3 任务列表显示当前编码",
          bool(row) and row.get("cbfbm") == code, f"-> {(row or {}).get('cbfbm')!r}")

    st, payload = api(f"/surveys/batches/{BATCH_ID}/tasks?page=1&page_size=200&keyword={quote(name1)}")
    hits = ((payload.get("data") or {}).get("items") or []) if st == 200 else []
    check("T3 ★ 按新名可搜到本户",
          any(i.get("contractorUid") == uid for i in hits),
          f"-> 命中 {len(hits)} 行：{[i.get('cbfmc') for i in hits[:5]]}")

    st, payload = api(f"/surveys/batches/{BATCH_ID}/tasks?page=1&page_size=200&keyword={quote(name0)}")
    hits_old = ((payload.get("data") or {}).get("items") or []) if st == 200 else []
    check("T3 按旧名也能搜到（base 基线侧仍可命中）",
          any(i.get("contractorUid") == uid for i in hits_old),
          f"-> 命中 {len(hits_old)} 行")

    # ── T1b 改回原值 → 差异行必须消失（核心）
    st, resp = put_result(uid, get_detail(uid), name=name0)
    check("T1b 改回原名 PUT 200", st == 200, f"-> {st} {brief(resp, 400)}")
    back = get_detail(uid)
    check("T1b 结果表已恢复原名", back.get("name") == name0, f"-> {back.get('name')!r}")

    rows2 = [d for d in get_diffs(uid) if d.get("fieldName") == "cbfmc"]
    check("T1b ★★ 改回原值后 cbfmc 差异行消失（净差异语义成立）", not rows2,
          f"-> 仍剩 {[(d.get('beforeValue'), d.get('afterValue')) for d in rows2]}")

    brows2 = sql("SELECT cbfmc FROM survey_cbf_base WHERE contractor_uid = %s", (uid,))
    check("T1b base 基线始终是初始值", (brows2[0][0] if brows2 else None) == name0,
          f"-> {brows2[0][0] if brows2 else None!r}")


# ────────────────────────── T4 分户状态差异 ──────────────────────────
def case_split_status(uid: str) -> None:
    log("\n=== T4 分户后原户 diffs 含「承包方状态」===")
    for idx, label in enumerate(["P13分户地甲", "P13分户地乙"]):
        code = next_parcel_code(uid)
        if not code:
            check(f"T4 取地块编码 #{idx + 1}", False, "-> next-code 未返回")
            return
        # 不传 geometry：分户只校验"有效地块 ≥2"与"所有地块必须分配"，不依赖几何。
        # 传固定坐标反而会与批次内**真实地块**在空间上重叠，被后端的
        # "parcel geometry overlaps existing parcels" 校验挡下——那是夹具问题，不是缺陷。
        st, resp = add_parcel(uid, code, label, "1200")
        if not check(f"T4 新增地块 {code}", st == 200, f"-> {st} {brief(resp, 300)}"):
            return

    detail = get_detail(uid)
    members = detail.get("familyMembers") or []
    active = [p for p in get_parcels(uid) if p.get("resultStatus") not in ("removed", "split_source")]
    log(f"  成员 {len(members)} / 有效地块 {len(active)}")
    if len(members) < 2 or len(active) < 2:
        check("T4 分户前置条件（≥2 成员 ≥2 地块）", False, f"-> 成员 {len(members)} 地块 {len(active)}")
        return

    status_before = detail.get("resultStatus")
    log(f"  分户前 resultStatus={status_before}")

    op = {"type": "split_household", "payload": {
        "newHouseholds": [
            {"newCbfbm": SPLIT_CHILDREN[0], "newCbfmc": "P13分户甲",
             "memberUids": [members[0].get("memberUid")],
             "parcelDkbms": [active[0].get("dkbm")],
             "householdHeadMemberUid": members[0].get("memberUid")},
            {"newCbfbm": SPLIT_CHILDREN[1], "newCbfmc": "P13分户乙",
             "memberUids": [m.get("memberUid") for m in members[1:]],
             "parcelDkbms": [p.get("dkbm") for p in active[1:]],
             "householdHeadMemberUid": members[1].get("memberUid")},
        ],
        "reason": "P1-3 复测分户",
    }}
    st, resp = put_result(uid, detail, pending=[op])
    if not check("T4 分户 PUT 200", st == 200, f"-> {st} {brief(resp, 600)}"):
        return

    src = get_detail(uid)
    diffs = get_diffs(uid)
    rows = [d for d in diffs if d.get("entityType") == "contractor" and d.get("fieldName") == "result_status"]
    log(f"  分户后 原户 resultStatus={src.get('resultStatus')}  diffs={diff_labels(diffs)}")
    check("T4 原户 resultStatus 已转 cancelled", src.get("resultStatus") == "cancelled",
          f"-> {src.get('resultStatus')!r}")
    check("T4 ★ 原户 diffs 含「承包方状态」行（修复前缺失）", len(rows) == 1,
          f"-> {diff_labels(diffs)}")
    if rows:
        check("T4 状态差异 before/after 正确",
              str(rows[0].get("beforeValue")) == str(status_before) and rows[0].get("afterValue") == "cancelled",
              f"-> {rows[0].get('beforeValue')!r} -> {rows[0].get('afterValue')!r}")

    # ── 撤回分户
    st, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/split-household/rollback", method="POST")
    check("T4 撤回分户 200", st == 200, f"-> {st} {brief(resp, 400)}")
    if st != 200:
        return
    restored = get_detail(uid)
    check("T4 撤回后 resultStatus 复原", restored.get("resultStatus") == status_before,
          f"-> {restored.get('resultStatus')!r} 期望 {status_before!r}")
    rows2 = [d for d in get_diffs(uid)
             if d.get("entityType") == "contractor" and d.get("fieldName") == "result_status"]
    check("T4 ★ 撤回分户后「承包方状态」行消失（净差异成立）", not rows2,
          f"-> 仍剩 {[(d.get('beforeValue'), d.get('afterValue')) for d in rows2]}")


# ────────────────────────── T5 合户状态差异 ──────────────────────────
def case_merge_status(uid_b: str, uid_c: str) -> None:
    log("\n=== T5 合户后各原户 diffs 含「承包方状态」===")
    head = (get_detail(uid_b).get("familyMembers") or [{}])[0].get("memberUid")
    if not check("T5 取户主 memberUid", bool(head), f"-> head={head}"):
        return
    status_before = {uid: get_detail(uid).get("resultStatus") for uid in (uid_b, uid_c)}
    log(f"  合户前 resultStatus={status_before}")

    st, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid_b}/merge-household", method="POST", body={
        "sourceContractorUids": [uid_b, uid_c],
        "newCbfbm": MERGE_CHILD, "newCbfmc": "P13合并户",
        "householdHeadMemberUid": head,
        "newAddress": "P13 复测合并地址", "reason": "P1-3 复测合户",
    })
    if not check("T5 合户 200", st == 200, f"-> {st} {brief(resp, 600)}"):
        return

    for uid in (uid_b, uid_c):
        d = get_detail(uid)
        diffs = get_diffs(uid)
        rows = [x for x in diffs
                if x.get("entityType") == "contractor" and x.get("fieldName") == "result_status"]
        log(f"  原户 {uid[-6:]} resultStatus={d.get('resultStatus')} diffs={diff_labels(diffs)}")
        check(f"T5 原户 …{uid[-6:]} 已转 cancelled", d.get("resultStatus") == "cancelled",
              f"-> {d.get('resultStatus')!r}")
        check(f"T5 ★ 原户 …{uid[-6:]} diffs 含「承包方状态」行", len(rows) == 1,
              f"-> {diff_labels(diffs)}")

    # ── 撤回合户
    st, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid_b}/merge-household/rollback", method="POST")
    check("T5 撤回合户 200", st == 200, f"-> {st} {brief(resp, 400)}")
    if st != 200:
        return
    for uid in (uid_b, uid_c):
        d = get_detail(uid)
        rows2 = [x for x in get_diffs(uid)
                 if x.get("entityType") == "contractor" and x.get("fieldName") == "result_status"]
        check(f"T5 原户 …{uid[-6:]} 状态复原", d.get("resultStatus") == status_before[uid],
              f"-> {d.get('resultStatus')!r} 期望 {status_before[uid]!r}")
        check(f"T5 ★ 撤回合户后 …{uid[-6:]} 「承包方状态」行消失", not rows2,
              f"-> 仍剩 {[(x.get('beforeValue'), x.get('afterValue')) for x in rows2]}")


def main() -> int:
    global client
    log("清理上次可能残留的夹具 ...")
    housekeeping()

    with TestClient(app) as c:
        client = c
        uid_a = setup_household(HA, "P13净差异验证户", "甲")
        uid_b = setup_household(HB, "P13合户乙", "乙")
        uid_c = setup_household(HC, "P13合户丙", "丙")
        if uid_a:
            case_rename(uid_a)
            case_split_status(uid_a)
        if uid_b and uid_c:
            case_merge_status(uid_b, uid_c)

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

    out_path = ROOT / "runtime" / ".state" / "_verify_survey_p13.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(OUT), encoding="utf-8")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
