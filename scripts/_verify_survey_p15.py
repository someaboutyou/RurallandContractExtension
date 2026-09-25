# -*- coding: utf-8 -*-
"""P1-5 修复复测：切割「本批次新增的地块」后，「撤回已保存切割」能否在界面上被定位。

背景
----
P1-5 现象：切割本批次**新增**的地块后，前端 `handleRollbackSavedSplit` 靠
`parcels.find(p => p.resultStatus === "split_source")` 定位源地块，但接口不返回该条目
⇒ 点「撤回已保存切割」只弹"地块状态已变化"。

根因（已定位）：
  split_parcel 收尾 `db.delete(old_relation); db.delete(old_parcel)` 物理删除源行；
  而 `land_parcel_service.get_survey_parcels` 的兜底循环 `if relation_source is None: continue`
  直接跳过 —— 基线里没有它（本批次新增），result 里也没有（已删）⇒ 条目丢失。

修复：
  兜底分支在 `changeType == "split_parcel"` 时改用变更快照
  （`before_summary.source_relation / source_parcel / source_geometry`）还原条目；
  其余场景保持原 `continue` 行为。

本脚本验证（进程内 TestClient，验的一定是当前源码）：
  R1 ★ 切割新增地块 → /parcels 返回 split_source 条目（修复点）+ 撤回切割完全还原
  R2    回归：移除新增地块 → 不产生条目（快照兜底不得扩散到非切割场景）
  R3    回归：切割基线地块 → 仍返回 split_source（原有 base 分支未被破坏）

夹具：批次 41 下建一个临时户 HC（自建自清，编码段 …984x）。
跑法：runtime/windows/python/python.exe scripts/_verify_survey_p15.py
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
HC = "321324100001029841"        # 复测专用临时户
ALL_CODES = [HC]

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
    # extra 只在失败时输出：它承载的是诊断信息，成功时拼接会让人误读
    suffix = f" {extra}" if (extra and not ok) else ""
    log(f"[{tag}] {label}{suffix}".rstrip())
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


def active_codes(uid: str) -> set[str]:
    return {
        p.get("dkbm") for p in get_parcels(uid)
        if p.get("resultStatus") not in ("removed", "split_source")
    }


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


def add_parcel(uid: str, dkbm: str, label: str, scmj: str = "1000", geometry=None):
    detail = get_detail(uid)
    body = {
        "dkbm": dkbm, "dkmc": label, "dklb": "01", "dldj": "01", "tdyt": "1",
        "tdlylx": "011", "syqxz": "10", "scmj": scmj, "sfjbnt": "1",
        "reason": "P1-5 复测新增地块",
    }
    if geometry is not None:
        body["geometry"] = geometry
        body["geometrySourceSrid"] = 4326
    return put_result(uid, detail, pending=[{"type": "add_parcel", "payload": body}])


def box_geometry(lon: float, lat: float, dlon: float, dlat: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon, lat], [lon + dlon, lat],
            [lon + dlon, lat + dlat], [lon, lat + dlat],
            [lon, lat],
        ]],
    }


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
            # 兜底：切割/合并产生的台账可能挂在新生成户的 uid 上，而该户行随后被
            # 删除 ⇒ 上面按 cbfbm 取到的 uids 覆盖不到。必须在删完 survey_cbf_result
            # 之后再判“孤儿”，否则判据失效。
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
def setup_household(code: str, name: str) -> str:
    log(f"\n--- 建临时户 {code}（{name}）---")
    status, payload = api(
        f"/surveys/batches/{BATCH_ID}/tasks", method="POST",
        body={
            "code": code, "typeCode": "1", "name": name, "idType": "1",
            "idNo": "3203241990010199" + code[-2:], "address": "P1-5 复测临时地址",
            "postcode": "223900", "mobile": "13900000000",
            "surveyorName": "复测脚本", "surveyDate": "2026-09-24",
            "remark": "survey p1-5 verify fixture",
        },
    )
    if status != 201:
        check(f"建户 {code}", False, f"-> {status} {brief(payload)}")
        return ""
    uid = (payload.get("data") or {}).get("contractorUid") or ""
    if not check(f"建户 {code} 成功", bool(uid), f"uid={uid}"):
        return ""

    detail = get_detail(uid)
    members = members_payload(detail.get("familyMembers") or [])
    suffix = code[-2:]
    for idx in range(2):
        members.append({
            "name": f"复测{idx + 1}", "gender": "1", "idType": "1",
            "idNo": f"3203241990010{suffix}{idx}",
            "relationToHead": "01" if idx == 0 else "02",
            "isHouseholdHead": idx == 0,
        })
    st, resp = put_result(uid, detail, members=members)
    check(f"{code} 补 2 名成员", st == 200, f"-> {st} {brief(resp, 300)}")
    return uid


def seed_base_rows(dkbm: str) -> bool:
    """把 result 中的地块复制成 base 基线行，模拟『切割基线地块』场景。"""
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO survey_cbdkxx_base (
                  batch_id, parcel_info_uid, source_dkbm, dkbm, fbfbm, cbfbm, cbjyqqdfs, htmj, cbhtbm,
                  lzhtbm, cbjyqzbm, yhtmj, htmjm, yhtmjm, sfqqqg, initialized_at,
                  initialized_from_table, initialized_from_key, snapshot_at,
                  task_status, has_change, change_count,
                  result_id, tenant_code, region_code)
                SELECT %s, parcel_info_uid, dkbm, dkbm, fbfbm, cbfbm, cbjyqqdfs, htmj, cbhtbm,
                  lzhtbm, cbjyqzbm, yhtmj, htmjm, yhtmjm, sfqqqg, initialized_at,
                  'survey_cbdkxx_result', parcel_info_uid, now(),
                  'not_started', false, 0,
                  id, tenant_code, region_code
                FROM survey_cbdkxx_result WHERE dkbm = %s
                """,
                (BATCH_ID, dkbm),
            )
            rel_inserted = cur.rowcount
            cur.execute(
                """
                INSERT INTO survey_dk_base (
                  batch_id, parcel_uid, source_dkbm, bsm, ysdm, dkbm, dkmc, syqxz, dklb, tdlylx, dldj,
                  tdyt, sfjbnt, scmj, dkdz, dkxz, dknz, dkbz, dkbzxx, zjrxm, initialized_at,
                  initialized_from_table, initialized_from_key, snapshot_at,
                  task_status, has_change, change_count,
                  result_id, tenant_code, region_code, geom)
                SELECT %s, parcel_uid, dkbm, bsm, ysdm, dkbm, dkmc, syqxz, dklb, tdlylx, dldj,
                  tdyt, sfjbnt, scmj, dkdz, dkxz, dknz, dkbz, dkbzxx, zjrxm, initialized_at,
                  'survey_dk_result', parcel_uid, now(),
                  'not_started', false, 0,
                  id, tenant_code, region_code, geom
                FROM survey_dk_result WHERE dkbm = %s
                """,
                (BATCH_ID, dkbm),
            )
            dk_inserted = cur.rowcount
            return bool(rel_inserted) and bool(dk_inserted)


def split_parcel(uid: str, src: str, new_code: str, label: str, reason: str):
    return put_result(uid, get_detail(uid), pending=[{
        "type": "split_parcel", "payload": {
            "dkbm": src, "newDkbm": new_code, "newDkmc": label,
            "splitMode": "area", "newScmj": 300, "splitDirection": "east",
            "reason": reason,
        },
    }])


def rollback_split(uid: str, change: dict, src: str, new_code: str):
    return put_result(uid, get_detail(uid), pending=[{
        "type": "rollback_split_parcel", "payload": {
            "changeId": change.get("id"), "changeNo": change.get("changeNo"),
            "sourceDkbm": src, "generatedDkbms": [new_code],
            "reason": f"撤回切割 {change.get('changeNo')}",
        },
    }])


def find_split_change(uid: str) -> dict | None:
    changes = [c for c in get_changes(uid)
               if c.get("changeType") == "split_parcel" and c.get("changeStatus") != "rolled_back"]
    return changes[0] if changes else None


# ────────────────────────── R1 切割新增地块（核心） ──────────────────────────
def case_r1_split_added(uid: str) -> None:
    log("\n=== R1 ★ 切割本批次新增地块 → /parcels 应返回 split_source（P1-5 修复点）===")
    src = next_parcel_code(uid)
    if not check("R1 取源地块编码", bool(src), "-> next-code 未返回"):
        return
    label = "P1-5复测源地块"
    geom = box_geometry(120.10, 35.10, 0.008943, 0.007335)
    st, rp = add_parcel(uid, src, label, scmj="1234", geometry=geom)
    if not check("R1 新增带图形的源地块（本批次新增）", st == 200, f"-> {st} {brief(rp, 400)}"):
        return
    # 关键前置：确认它**不在** base 基线里（否则测不到 P1-5 的路径）
    in_base = sql("SELECT count(*) FROM survey_cbdkxx_base WHERE batch_id=%s AND dkbm=%s", (BATCH_ID, src))
    check("R1 前置：源地块不在 base 基线中（确属本批次新增）", in_base and in_base[0][0] == 0, f"-> base行数={in_base}")

    new_code = next_parcel_code(uid)
    if not check("R1 取新地块编码", bool(new_code), "-> next-code 未返回"):
        return
    before = active_codes(uid)

    status, resp = split_parcel(uid, src, new_code, "P1-5切割产出", "P1-5 复测切割新增地块")
    check("R1 切割 PUT 200", status == 200, f"-> {status} {brief(resp, 500)}")
    if status != 200:
        return

    parcels = get_parcels(uid)
    status_map = {p.get("dkbm"): p for p in parcels}
    after = active_codes(uid)
    log(f"  切割后 A 有效={sorted(after)}")
    log(f"  接口返回条目状态={ {k: v.get('resultStatus') for k, v in status_map.items()} }")
    check("R1 新地块已生成", new_code in after, f"-> {sorted(after)}")
    check("R1 源地块已退出有效列表", src not in after, f"-> {sorted(after)}")

    entry = status_map.get(src)
    # ── 修复点：修复前 entry is None（接口直接不返回该 dkbm）──
    check("★ R1 源地块仍被 /parcels 返回（修复前完全缺失）", entry is not None,
          f"-> 返回的 dkbm={sorted(status_map)}")
    check("★ R1 其 resultStatus == split_source",
          bool(entry) and entry.get("resultStatus") == "split_source",
          f"-> {entry.get('resultStatus') if entry else None}")
    # 快照兜底构造：字段应来自变更快照而非空值
    check("★ R1 条目字段来自变更快照（dkmc 还原）",
          bool(entry) and entry.get("dkmc") == label,
          f"-> dkmc={entry.get('dkmc') if entry else None}")
    check("★ R1 条目字段来自变更快照（scmj 还原）",
          bool(entry) and entry.get("scmj") is not None and abs(float(entry["scmj"]) - 1234) < 0.01,
          f"-> scmj={entry.get('scmj') if entry else None}")
    check("★ R1 split_source 条目带上 changeType=split_parcel",
          bool(entry) and entry.get("changeType") == "split_parcel",
          f"-> {entry.get('changeType') if entry else None}")

    # ── 撤回切割 ──
    change = find_split_change(uid)
    if not check("R1 存在未撤回的 split_parcel 记录", change is not None,
                 f"-> {[(c.get('id'), c.get('changeNo')) for c in get_changes(uid)]}"):
        return
    assert change is not None
    st, resp = rollback_split(uid, change, src, new_code)
    check("★ R1 撤回切割 PUT 200", st == 200, f"-> {st} {brief(resp, 500)}")
    if st != 200:
        return

    back = active_codes(uid)
    log(f"  撤回后 A 有效={sorted(back)}")
    check("★ R1 撤回后有效地块集合完全还原", back == before, f"-> {sorted(back)} vs {sorted(before)}")
    check("★ R1 撤回后新地块已失效", new_code not in back, f"-> {sorted(back)}")
    rolled = [c for c in get_changes(uid) if c.get("id") == change.get("id")]
    check("★ R1 原 split_parcel 记录已标记 rolled_back",
          bool(rolled) and rolled[0].get("changeStatus") == "rolled_back",
          f"-> {[(c.get('id'), c.get('changeStatus')) for c in rolled]}")


# ────────────────────────── R2 回归：移除新增地块 ──────────────────────────
def case_r2_remove_added(uid: str) -> None:
    log("\n=== R2 回归：移除本批次新增地块 → 不得残留条目 ===")
    src = next_parcel_code(uid)
    if not check("R2 取地块编码", bool(src), "-> next-code 未返回"):
        return
    st, rp = add_parcel(uid, src, "P1-5复测移除地块", scmj="500")
    if not check("R2 新增地块", st == 200, f"-> {st} {brief(rp, 300)}"):
        return
    before = active_codes(uid)

    st, resp = put_result(uid, get_detail(uid), pending=[{
        "type": "remove_parcel", "payload": {"dkbm": src, "reason": "P1-5 复测移除"},
    }])
    check("R2 移除 PUT 200", st == 200, f"-> {st} {brief(resp, 500)}")
    if st != 200:
        return

    parcels = get_parcels(uid)
    status_map = {p.get("dkbm"): p.get("resultStatus") for p in parcels}
    after = active_codes(uid)
    log(f"  移除后 A 有效={sorted(after)}  接口全量状态={status_map}")
    check("R2 地块已退出有效列表", src not in after, f"-> {sorted(after)}")
    # 快照兜底必须只对 split_parcel 生效；移除新增地块应保持原有 continue 行为
    check("★ R2 移除场景不产生残留条目（未误伤）", src not in status_map,
          f"-> {status_map}")


# ────────────────────────── R3 回归：切割基线地块 ──────────────────────────
def case_r3_split_baseline(uid: str) -> None:
    log("\n=== R3 回归：切割『基线地块』→ 仍应返回 split_source（原路径未破坏）===")
    src = next_parcel_code(uid)
    if not check("R3 取源地块编码", bool(src), "-> next-code 未返回"):
        return
    label = "P1-5复测基线地块"
    geom = box_geometry(120.30, 35.30, 0.008943, 0.007335)
    st, rp = add_parcel(uid, src, label, scmj="2000", geometry=geom)
    if not check("R3 新增带图形的地块", st == 200, f"-> {st} {brief(rp, 400)}"):
        return
    if not check("R3 复制成 base 基线行（模拟既有基线地块）", seed_base_rows(src), "-> 复制失败"):
        return

    new_code = next_parcel_code(uid)
    if not check("R3 取新地块编码", bool(new_code), "-> next-code 未返回"):
        return
    before = active_codes(uid)

    status, resp = split_parcel(uid, src, new_code, "P1-5基线切割产出", "P1-5 复测切割基线地块")
    check("R3 切割 PUT 200", status == 200, f"-> {status} {brief(resp, 500)}")
    if status != 200:
        return

    parcels = get_parcels(uid)
    status_map = {p.get("dkbm"): p for p in parcels}
    after = active_codes(uid)
    log(f"  切割后 A 有效={sorted(after)}")
    log(f"  接口返回条目状态={ {k: v.get('resultStatus') for k, v in status_map.items()} }")
    entry = status_map.get(src)
    check("R3 新地块已生成", new_code in after, f"-> {sorted(after)}")
    check("★ R3 基线地块源行仍以 split_source 返回",
          bool(entry) and entry.get("resultStatus") == "split_source",
          f"-> {entry.get('resultStatus') if entry else None}")
    # 基线路径走 base_relation，字段应来自 base/result 而非快照 —— 此处只验非空
    check("★ R3 条目关键字段非空", bool(entry) and entry.get("dkmc") is not None,
          f"-> dkmc={entry.get('dkmc') if entry else None}")

    change = find_split_change(uid)
    if not check("R3 存在未撤回的 split_parcel 记录", change is not None, "-> 无记录"):
        return
    assert change is not None
    st, resp = rollback_split(uid, change, src, new_code)
    check("★ R3 撤回切割 PUT 200", st == 200, f"-> {st} {brief(resp, 500)}")
    if st != 200:
        return
    back = active_codes(uid)
    check("★ R3 撤回后有效地块集合完全还原", back == before, f"-> {sorted(back)} vs {sorted(before)}")


# ────────────────────────── 主流程 ──────────────────────────
def main() -> int:
    global client
    log("清理上次可能残留的夹具 ...")
    housekeeping()

    with TestClient(app) as c:
        client = c
        uid = setup_household(HC, "P1-5复测户")
        if uid:
            case_r1_split_added(uid)
            case_r2_remove_added(uid)
            case_r3_split_baseline(uid)

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

    out_path = ROOT / "runtime" / ".state" / "_verify_survey_p15.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(OUT), encoding="utf-8")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
