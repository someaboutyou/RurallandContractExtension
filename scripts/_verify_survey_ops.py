# -*- coding: utf-8 -*-
"""验收补测：承包方调查录入 —— 此前**完全没测过**的 3 类可撤回操作。

背景
----
`_verify_survey_fix.py` 只覆盖了：移除地块/撤回移除、改名称、分户、删户。
但 `base.py::operation_change_types` 里登记了 13 种操作类型，其中：

  已测（fix 脚本）：remove_parcel / rollback_remove_parcel / split_household /
                    deregister / rollback_deregister / add_parcel / member_maintain / change_head
  本脚本补齐（此前 0 覆盖）：
      S1 地块互换  swap_parcels            → 撤回互换 rollback_swap_parcels
      S2 切割地块  split_parcel            → 撤回切割 rollback_split_parcel
      S3 合并户    merge_household         → 撤回合户 rollback_merge_household

这三类都是"页面修改可撤回"承诺的一部分，且此前从未跑过任何端到端断言。

夹具：批次 41 下建两个临时户（同 cbfbm 前缀 ⇒ 同村组，满足互换/合户的
      "只能选择本组承包方 / 只能合并同一村组"约束），各 2 成员 2 地块。
      跑完自清（housekeeping 幂等）。

跑法：runtime/windows/python/python.exe scripts/_verify_survey_ops.py
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
HA = "321324100001029821"        # 户 A（互换/切割/合户的发起方）
HB = "321324100001029822"        # 户 B（互换对手户 / 合户参与方）
HM = "321324100001029831"        # 合户生成的新户
ALL_CODES = [HA, HB, HM]

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
    log(f"[{tag}] {label} {extra}".rstrip())
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
    """当前有效地块编码集合（排除已移除 / 已成为切割源的）。"""
    return {
        p.get("dkbm") for p in get_parcels(uid)
        if p.get("resultStatus") not in ("removed", "split_source")
    }


def get_diffs(uid: str) -> list:
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/diffs?page=1&page_size=500")
    if status == 200 and isinstance(payload, dict):
        return (payload.get("data") or {}).get("items") or []
    return []


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
        "reason": "验收新增地块",
    }
    # 依赖图形的操作（按方向切割等）要求 survey_dk_result.geom 非空 ⇒ 需要时一并提交
    if geometry is not None:
        body["geometry"] = geometry
        body["geometrySourceSrid"] = 4326
    return put_result(uid, detail, pending=[{"type": "add_parcel", "payload": body}])


def box_geometry(lon: float, lat: float, dlon: float, dlat: float) -> dict:
    """构造一个矩形 GeoJSON Polygon（EPSG:4326）。"""
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
            # 兜底：合并户/分户的台账挂在新户 uid 上，而撤回合户后新户行已不在
            # survey_cbf_result ⇒ 上面按 cbfbm 取到的 uids 覆盖不到，会留下测试痕迹。
            # 必须在删完 survey_cbf_result 之后再判“孤儿”。
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
            "idNo": "3203241990010199" + code[-2:], "address": "验收临时地址",
            "postcode": "223900", "mobile": "13900000000",
            "surveyorName": "验收脚本", "surveyDate": "2026-09-24",
            "remark": "survey ops verify fixture",
        },
    )
    if status != 201:
        check(f"建户 {code}", False, f"-> {status} {brief(payload)}")
        return "", []
    uid = (payload.get("data") or {}).get("contractorUid") or ""
    if not check(f"建户 {code} 成功", bool(uid), f"uid={uid}"):
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


# ────────────────────────── S1 地块互换 / 撤回互换 ──────────────────────────
def case_s1_swap(uid_a: str, uid_b: str, pa: list[str], pb: list[str]) -> None:
    log("\n=== S1 地块互换 → 撤回互换 ===")
    if len(pa) < 1 or len(pb) < 1:
        check("S1 前置条件（双方各有地块）", False, f"-> A {pa} / B {pb}")
        return

    before_a, before_b = active_codes(uid_a), active_codes(uid_b)
    log(f"  互换前 A={sorted(before_a)}  B={sorted(before_b)}")

    op = {"type": "swap_parcels", "payload": {
        "targetContractorUid": uid_b,
        "sourceDkbms": [pa[0]], "targetDkbms": [pb[0]],
        "sourceParcels": [{"dkbm": pa[0]}], "targetParcels": [{"dkbm": pb[0]}],
        "reason": "验收地块互换",
    }}
    status, resp = put_result(uid_a, get_detail(uid_a), pending=[op])
    check("S1 互换 PUT 200", status == 200, f"-> {status} {brief(resp, 500)}")
    if status != 200:
        return

    after_a, after_b = active_codes(uid_a), active_codes(uid_b)
    log(f"  互换后 A={sorted(after_a)}  B={sorted(after_b)}")
    check("★ A 换出 pa[0]", pa[0] not in after_a, f"-> {sorted(after_a)}")
    check("★ A 换入 pb[0]", pb[0] in after_a, f"-> {sorted(after_a)}")
    check("★ B 换出 pb[0]", pb[0] not in after_b, f"-> {sorted(after_b)}")
    check("★ B 换入 pa[0]", pa[0] in after_b, f"-> {sorted(after_b)}")

    changes = [c for c in get_changes(uid_a)
               if c.get("changeType") == "swap_parcels" and c.get("changeStatus") != "rolled_back"]
    if not check("S1 存在未撤回的 swap_parcels 记录", bool(changes),
                 f"-> {[(c.get('id'), c.get('changeNo')) for c in changes]}"):
        return
    change = changes[0]
    # 互换是两户同时被改：对手户也应留痕
    cp_changes = [c for c in get_changes(uid_b) if c.get("changeType") == "swap_parcels"]
    check("S1 对手户也留下 swap_parcels 记录（两户同时被改）", bool(cp_changes),
          f"-> {[(c.get('id'), c.get('changeNo')) for c in cp_changes]}")

    rb = {"type": "rollback_swap_parcels", "payload": {
        "changeId": change.get("id"), "changeNo": change.get("changeNo"),
        "reason": f"撤回互换 {change.get('changeNo')}",
    }}
    status, resp = put_result(uid_a, get_detail(uid_a), pending=[rb])
    check("★ S1 撤回互换 PUT 200", status == 200, f"-> {status} {brief(resp, 500)}")
    if status != 200:
        return

    back_a, back_b = active_codes(uid_a), active_codes(uid_b)
    log(f"  撤回后 A={sorted(back_a)}  B={sorted(back_b)}")
    check("★ 撤回后 A 地块集合完全还原", back_a == before_a, f"-> {sorted(back_a)} vs {sorted(before_a)}")
    check("★ 撤回后 B 地块集合完全还原", back_b == before_b, f"-> {sorted(back_b)} vs {sorted(before_b)}")

    rolled = [c for c in get_changes(uid_a) if c.get("id") == change.get("id")]
    check("★ 原 swap_parcels 记录已标记 rolled_back",
          bool(rolled) and rolled[0].get("changeStatus") == "rolled_back",
          f"-> {[(c.get('id'), c.get('changeStatus')) for c in rolled]}")

    # P2-1：_collect_diff_rebuild_uids 只认 swap_parcels / split_household，
    # 不认 rollback_swap_parcels ⇒ 撤回时对手户 diff 不重建。
    b_diffs = [f"{d.get('entityType')}:{d.get('fieldLabel')}" for d in get_diffs(uid_b)]
    check("（P2-1）撤回互换后对手户 B 的 diffs 应回到基线",
          not b_diffs, f"-> B diffs={b_diffs}", gap=True)


# ────────────────────────── S2 切割地块 / 撤回切割 ──────────────────────────
def case_s2_split(uid_a: str, _pa: list[str]) -> None:
    log("\n=== S2 切割地块 → 撤回切割 ===")
    # 按方向切割要求 survey_dk_result.geom 非空（要沿图形切）；真实场景中地块
    # 都由地图绘制 / SHP 上传带来图形，所以这里先建一个带 GeoJSON 的源地块。
    src = next_parcel_code(uid_a)
    if not check("S2 取源地块编码", bool(src), "-> next-code 未返回"):
        return
    geom = box_geometry(119.90, 34.90, 0.008943, 0.007335)  # ≈1000 亩，远离既有地块避免重叠
    st, rp = add_parcel(uid_a, src, "验收切割源地块", scmj="1000", geometry=geom)
    if not check("S2 新增带图形的地块", st == 200, f"-> {st} {brief(rp, 400)}"):
        return

    new_code = next_parcel_code(uid_a)
    if not check("S2 取新地块编码", bool(new_code), "-> next-code 未返回"):
        return

    before = active_codes(uid_a)
    op = {"type": "split_parcel", "payload": {
        "dkbm": src, "newDkbm": new_code, "newDkmc": "验收切割产出",
        "splitMode": "area", "newScmj": 300, "splitDirection": "east",
        "reason": "验收切割地块",
    }}
    status, resp = put_result(uid_a, get_detail(uid_a), pending=[op])
    check("S2 切割 PUT 200", status == 200, f"-> {status} {brief(resp, 500)}")
    if status != 200:
        return

    after = active_codes(uid_a)
    all_after = {p.get("dkbm"): p.get("resultStatus") for p in get_parcels(uid_a)}
    log(f"  切割后 A 有效={sorted(after)}  接口全量状态={all_after}")
    # 取证：原地块在库里到底怎么了。⛔ 后端**不会**把 result_status 写成
    # "split_source"：split_parcel 收尾直接 db.delete(old_relation) /
    # db.delete(old_parcel) **物理删除**原地块行（见 parcel_ops.py），
    # 所以 DB 侧查不到该行是设计使然，不能当作断言。
    dk_state = sql("SELECT result_status FROM survey_dk_result WHERE dkbm = %s ORDER BY id DESC LIMIT 1", (src,))
    rel_state = sql("SELECT result_status FROM survey_cbdkxx_result WHERE dkbm = %s", (src,))
    log(f"  DB survey_dk_result[{src}].result_status      = {dk_state}  （物理删除 ⇒ 查无此行）")
    log(f"  DB survey_cbdkxx_result[{src}].result_status  = {rel_state}")
    check("★ 新地块已生成", new_code in after, f"-> {sorted(after)}")
    check("★ 原地块已退出有效地块列表", src not in after, f"-> {sorted(after)}")
    # 前端 handleRollbackSavedSplit 靠 parcels.find(resultStatus === "split_source")
    # 定位可撤回的源地块。"split_source" 只是 get_survey_parcels **组装返回时的
    # 虚拟标记**：基线地块走 base 行分支、本批次新增地块走变更快照兜底分支
    #（P1-5 修复点，2026-09-24）。这里只断言接口契约。
    check("（接口契约）原地块以 split_source 虚拟条目被 /parcels 返回",
          all_after.get(src) == "split_source",
          f"-> DB={dk_state}  接口={all_after.get(src)!r}")

    changes = [c for c in get_changes(uid_a)
               if c.get("changeType") == "split_parcel" and c.get("changeStatus") != "rolled_back"]
    if not check("S2 存在未撤回的 split_parcel 记录", bool(changes),
                 f"-> {[(c.get('id'), c.get('changeNo')) for c in changes]}"):
        return
    change = changes[0]

    rb = {"type": "rollback_split_parcel", "payload": {
        "changeId": change.get("id"), "changeNo": change.get("changeNo"),
        "sourceDkbm": src, "generatedDkbms": [new_code],
        "reason": f"撤回切割 {change.get('changeNo')}",
    }}
    status, resp = put_result(uid_a, get_detail(uid_a), pending=[rb])
    check("★ S2 撤回切割 PUT 200", status == 200, f"-> {status} {brief(resp, 500)}")
    if status != 200:
        return

    back = active_codes(uid_a)
    log(f"  撤回后 A 有效={sorted(back)}")
    check("★ 撤回后有效地块集合完全还原", back == before, f"-> {sorted(back)} vs {sorted(before)}")
    check("★ 撤回后新地块已失效", new_code not in back, f"-> {sorted(back)}")


# ────────────────────────── S3 合并户 / 撤回合户 ──────────────────────────
def case_s3_merge(uid_a: str, uid_b: str) -> None:
    log("\n=== S3 合并户 → 撤回合户 ===")
    da = get_detail(uid_a)
    members_a = da.get("familyMembers") or []
    head = next((m.get("memberUid") for m in members_a if m.get("isHouseholdHead")), None)
    if not head and members_a:
        head = members_a[0].get("memberUid")
    if not check("S3 找到户主成员 uid", bool(head), f"-> {head}"):
        return

    status, resp = put_result(uid_a, da, pending=[{
        "type": "merge_household",
        "payload": {
            "sourceContractorUids": [uid_a, uid_b],
            "newCbfbm": HM, "newCbfmc": "验收合并户",
            "householdHeadMemberUid": head,
            "newAddress": "验收合并地址", "reason": "验收合并户",
        },
    }])
    check("S3 合并户 PUT 200", status == 200, f"-> {status} {brief(resp, 600)}")
    if status != 200:
        return

    a_after, b_after = get_detail(uid_a), get_detail(uid_b)
    log(f"  合并后 A.resultStatus={a_after.get('resultStatus')}  B.resultStatus={b_after.get('resultStatus')}")
    check("★ 原户 A 已注销(cancelled)", a_after.get("resultStatus") == "cancelled",
          f"-> {a_after.get('resultStatus')}")
    check("★ 原户 B 已注销(cancelled)", b_after.get("resultStatus") == "cancelled",
          f"-> {b_after.get('resultStatus')}")

    rows = sql("SELECT contractor_uid, result_status FROM survey_cbf_result WHERE cbfbm = %s", (HM,))
    check("★ 新户 HM 已生成", bool(rows), f"-> {rows}")
    new_uid = rows[0][0] if rows else ""
    if new_uid:
        merged = sql("SELECT count(*) FROM survey_cbf_jtcy_result WHERE contractor_uid = %s", (new_uid,))
        check("★ 新户继承了两户成员（4 人）", merged and merged[0][0] == 4, f"-> {merged}")

    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid_a}/merge-household/rollback", method="POST")
    check("★ 撤回合户 200", status == 200, f"-> {status} {brief(resp, 500)}")
    if status != 200:
        return

    a_ok, b_ok = get_detail(uid_a), get_detail(uid_b)
    log(f"  撤回后 A.resultStatus={a_ok.get('resultStatus')}  B.resultStatus={b_ok.get('resultStatus')}")
    check("★ 撤回后原户 A 恢复正常", a_ok.get("resultStatus") in ("normal", "added"),
          f"-> {a_ok.get('resultStatus')}")
    check("★ 撤回后原户 B 恢复正常", b_ok.get("resultStatus") in ("normal", "added"),
          f"-> {b_ok.get('resultStatus')}")
    hb_row = sql("SELECT count(*) FROM survey_cbf_result WHERE cbfbm = %s AND result_status <> 'cancelled'", (HM,))
    check("★ 撤回后新户 HM 已失效", not hb_row or hb_row[0][0] == 0, f"-> {hb_row}")


# ────────────────────────── 主流程 ──────────────────────────
def main() -> int:
    global client
    log("清理上次可能残留的夹具 ...")
    housekeeping()

    with TestClient(app) as c:
        client = c
        uid_a, pa = setup_household(HA, "验收互换户A", "甲")
        uid_b, pb = setup_household(HB, "验收互换户B", "乙")
        if uid_a and uid_b:
            case_s1_swap(uid_a, uid_b, pa, pb)
            case_s2_split(uid_a, pa)
            case_s3_merge(uid_a, uid_b)

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

    out_path = ROOT / "runtime" / ".state" / "_verify_survey_ops.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(OUT), encoding="utf-8")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
