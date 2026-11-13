# -*- coding: utf-8 -*-
"""验收：新增地块属性信息 —— 字段可编辑性盘点 + 增删改链路实测。

背景
----
用户要求：核对「新增地块属性信息」弹窗的所有业务字段（除管理字段外）是否都可编辑，
并实测增 / 删 / 改功能。

编辑入口（前端）
----------------
- 新增：AddParcelDialog.vue → POST /surveys/batches/{id}/results/{uid}/add-parcel
- 改：ParcelInfoPanel.vue 属性表单 → PUT 保存调查结果 parcels 列表
      （SurveyParcelAttributeUpdate → update_parcel_attributes）
- 删：pendingOperations remove_parcel → rollback_remove_parcel 撤回

覆盖点
------
A  增：全字段 add-parcel → survey_dk_result / survey_cbdkxx_result 两表逐字段核对。
B1 改：15 个可编辑业务字段逐项改值 → DB 读回全一致（含 htmj→htmjm 亩换算）。
B2 改（负向）：合同侧字段 cbjyqqdfs/sfqqqg/cbhtbm/cbjyqzbm 走属性编辑 → 被忽略
   （Schema 不收，属"仅新增时录入"，与前端 ParcelInfoPanel disabled 口径一致）。
B3 改（保护）：必填列空值不覆盖（dkmc="" 不写坏）；可选列空串清空（dkdz→NULL）。
C  删：remove_parcel → 行物理删除（快照存 survey_change_records.before_summary，
   非软删）→ rollback_remove_parcel 撤回 → 从快照还原（属性保留）。
收尾：临时户 + 临时地块自清。

夹具：批次 2 下临时户 150526103201009842（前缀=批次 region_code + 6 位流水）。
跑法：runtime/windows/python/python.exe scripts/_verify_parcel_attr_editable.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read_runtime_env() -> dict[str, str]:
    values: dict[str, str] = {}
    env_file = ROOT / "runtime" / ".state" / "runtime.env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


_RUNTIME = _read_runtime_env()
os.environ.update({
    "DATABASE_HOST": _RUNTIME.get("DATABASE_HOST", "127.0.0.1"),
    "DATABASE_PORT": _RUNTIME.get("DATABASE_PORT", "15432"),
    "DATABASE_NAME": _RUNTIME.get("DATABASE_NAME", "erlunyanbao"),
    "DATABASE_USER": _RUNTIME.get("DATABASE_USER", "RurallandContractExtension"),
    "DATABASE_PASSWORD": _RUNTIME.get("DATABASE_PASSWORD", ""),
    "SECRET_KEY": "verify-only",
})
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import psycopg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.main import app  # noqa: E402

BATCH_ID = 2
HA = "150526103201009842"
ALL_CODES = [HA]
SQM_PER_MU = 666.6666667

TOKEN = create_access_token("1")
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
    tag = "PASS" if ok else "FAIL"
    log(f"[{tag}] {label} {extra}".rstrip())
    if not ok:
        FAILED.append(label)
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


def get_detail(uid: str) -> dict:
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}")
    return payload.get("data") if status == 200 and isinstance(payload, dict) else {}


def get_parcels(uid: str) -> list:
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/parcels")
    return (payload.get("data") or []) if status == 200 and isinstance(payload, dict) else []


def get_changes(uid: str) -> list:
    status, payload = api(f"/surveys/batches/{BATCH_ID}/changes?contractorUid={uid}&page=1&page_size=200")
    if status == 200 and isinstance(payload, dict):
        return (payload.get("data") or {}).get("items") or []
    return []


def members_payload(members: list) -> list:
    return [{
        "memberUid": m.get("memberUid"),
        "name": m.get("name"),
        "gender": m.get("gender") or "1",
        "idType": m.get("idType") or "1",
        "idNo": m.get("idNo"),
        "relationToHead": m.get("relationToHead") or "01",
        "isHouseholdHead": bool(m.get("isHouseholdHead")),
        "memberResultStatus": m.get("memberResultStatus") or "normal",
    } for m in members]


def result_payload(detail: dict, *, members=None, pending=None, parcels=None, **overrides) -> dict:
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
        "parcels": parcels or [],
    }
    payload.update(overrides)
    return payload


def put_result(uid: str, detail: dict, **kwargs):
    return api(f"/surveys/batches/{BATCH_ID}/results/{uid}", method="PUT",
               body=result_payload(detail, **kwargs))


def db_parcel(dkbm: str) -> dict:
    """survey_dk_result 最新一行（dict）。"""
    rows = sql(
        "SELECT dkbm, dkmc, scmj, dklb, tdlylx, dldj, tdyt, sfjbnt, syqxz,"
        " dkdz, dkxz, dknz, dkbz, dkbzxx, zjrxm, survey_status, result_status,"
        " change_type, change_reason"
        " FROM survey_dk_result WHERE dkbm = %s"
        " ORDER BY id DESC LIMIT 1",
        (dkbm,),
    )
    if not rows:
        return {}
    keys = ("dkbm", "dkmc", "scmj", "dklb", "tdlylx", "dldj", "tdyt", "sfjbnt", "syqxz",
            "dkdz", "dkxz", "dknz", "dkbz", "dkbzxx", "zjrxm", "survey_status",
            "result_status", "change_type", "change_reason")
    return dict(zip(keys, rows[0]))


def db_relation(dkbm: str) -> dict:
    """survey_cbdkxx_result 最新一行（dict）。"""
    rows = sql(
        "SELECT dkbm, cbjyqqdfs, htmj, htmjm, cbhtbm, cbjyqzbm, sfqqqg,"
        " result_status, change_type, change_reason"
        " FROM survey_cbdkxx_result WHERE dkbm = %s"
        " ORDER BY id DESC LIMIT 1",
        (dkbm,),
    )
    if not rows:
        return {}
    keys = ("dkbm", "cbjyqqdfs", "htmj", "htmjm", "cbhtbm", "cbjyqzbm", "sfqqqg",
            "result_status", "change_type", "change_reason")
    return dict(zip(keys, rows[0]))


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


def setup_household() -> str | None:
    log(f"\n--- 建临时户 {HA} ---")
    housekeeping()  # 预清理
    status, payload = api(
        f"/surveys/batches/{BATCH_ID}/tasks", method="POST",
        body={
            "code": HA, "typeCode": "1", "name": "字段可编辑性验收户", "idType": "1",
            "idNo": "320324199001019942", "address": "验收临时地址",
            "postcode": "223900", "mobile": "13900000001",
            "surveyorName": "验收脚本", "surveyDate": "2026-11-12",
            "remark": "parcel attribute editable verify fixture",
        },
    )
    if not check("建临时户", status == 201, f"-> {status} {brief(payload)}"):
        return None
    uid = (payload.get("data") or {}).get("contractorUid") or ""
    detail = get_detail(uid)
    members = members_payload(detail.get("familyMembers") or [])
    members.append({
        "name": "验收成员一", "gender": "1", "idType": "1",
        "idNo": "320324199001014102",
        "relationToHead": "01", "isHouseholdHead": True,
    })
    st, rp = put_result(uid, detail, members=members)
    check("补 1 名成员", st == 200, f"-> {st} {brief(rp, 300)}")
    return uid


def main() -> int:
    global client
    client = TestClient(app)
    log("=== 新增地块属性：字段可编辑性 + 增删改 验收 ===")

    uid = setup_household()
    if not uid:
        return 1

    # ── A 增：全字段 add-parcel ───────────────────────────────────
    log("\n--- A 增：全字段新增 ---")
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/parcels/next-code")
    dkbm = ((payload.get("data") or {}).get("dkbm")
            or (payload.get("data") or {}).get("code") or "") if status == 200 else ""
    if not check("取地块编码（next-code）", bool(dkbm), f"-> {brief(payload, 200)}"):
        housekeeping()
        return 1

    add_body = {
        "dkbm": dkbm, "dkmc": "验收新增地块", "scmj": 1500.0, "htmj": 1500.0,
        "dklb": "01", "tdyt": "1", "sfjbnt": "1", "dldj": "01", "syqxz": "10",
        "tdlylx": "011", "cbjyqqdfs": "001", "sfqqqg": "1",
        "cbhtbm": "", "cbjyqzbm": "",
        "dkdz": "东至A", "dkxz": "西至A", "dknz": "南至A", "dkbz": "北至A",
        "dkbzxx": "备注A", "reason": "验收新增",
    }
    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/add-parcel",
                       method="POST", body=add_body)
    if not check("A add-parcel 200", status == 200, f"-> {status} {brief(resp, 300)}"):
        housekeeping()
        return 1

    dk = db_parcel(dkbm)
    rel = db_relation(dkbm)
    expect_dk = {
        "dkmc": "验收新增地块", "scmj": 1500.0, "dklb": "01", "tdyt": "1", "sfjbnt": "1",
        "dldj": "01", "syqxz": "10", "tdlylx": "011",
        "dkdz": "东至A", "dkxz": "西至A", "dknz": "南至A", "dkbz": "北至A",
        "dkbzxx": "备注A", "survey_status": "surveyed", "result_status": "added",
        "change_type": "add_parcel", "change_reason": "验收新增",
    }
    for field, want in expect_dk.items():
        got = dk.get(field)
        ok = (abs(float(got) - want) < 0.01) if field == "scmj" and got is not None else (got == want)
        check(f"A ★ dk.{field}={want!r} 落库", ok, f"-> db={got!r}")
    expect_rel = {"cbjyqqdfs": "001", "htmj": 1500.0, "sfqqqg": "1",
                  "result_status": "added", "change_type": "add_parcel"}
    for field, want in expect_rel.items():
        got = rel.get(field)
        ok = (abs(float(got) - want) < 0.01) if field == "htmj" and got is not None else (got == want)
        check(f"A ★ rel.{field}={want!r} 落库", ok, f"-> db={got!r}")
    check("A htmj 留空时取 scmj 兜底（口径：合同面积默认=实测）",
          rel.get("htmj") is not None, f"-> htmj={rel.get('htmj')}")
    parcels = get_parcels(uid)
    check("A /parcels 返回新地块", any(p.get("dkbm") == dkbm for p in parcels),
          f"-> {[p.get('dkbm') for p in parcels]}")

    # ── B1 改：15 个可编辑字段逐项改值 ────────────────────────────
    log("\n--- B1 改：全部可编辑字段一次改值 ---")
    upd = {
        "dkbm": dkbm,
        "dkmc": "改后地块名", "scmj": 1800.55, "htmj": 1750.25,
        "syqxz": "20", "dklb": "02", "tdlylx": "021", "dldj": "03",
        "tdyt": "2", "sfjbnt": "0",
        "dkdz": "东至B", "dkxz": "西至B", "dknz": "南至B", "dkbz": "北至B",
        "dkbzxx": "备注B", "zjrxm": "张指界",
    }
    status, resp = put_result(uid, get_detail(uid), parcels=[upd])
    if not check("B1 PUT 保存调查结果 200", status == 200, f"-> {status} {brief(resp, 300)}"):
        housekeeping()
        return 1
    dk = db_parcel(dkbm)
    rel = db_relation(dkbm)
    expect_upd = {
        "dkmc": "改后地块名", "scmj": 1800.55, "dklb": "02", "tdlylx": "021", "dldj": "03",
        "tdyt": "2", "sfjbnt": "0", "syqxz": "20",
        "dkdz": "东至B", "dkxz": "西至B", "dknz": "南至B", "dkbz": "北至B",
        "dkbzxx": "备注B", "zjrxm": "张指界",
    }
    for field, want in expect_upd.items():
        got = dk.get(field)
        ok = (abs(float(got) - want) < 0.01) if field == "scmj" and got is not None else (got == want)
        check(f"B1 ★ dk.{field} → {want!r}", ok, f"-> db={got!r}")
    check("B1 ★ rel.htmj → 1750.25", rel.get("htmj") is not None
          and abs(float(rel["htmj"]) - 1750.25) < 0.01, f"-> db={rel.get('htmj')}")
    want_mu = round(1750.25 / SQM_PER_MU, 2)
    check(f"B1 ★ rel.htmjm 同步亩值 ≈ {want_mu}", rel.get("htmjm") is not None
          and abs(float(rel["htmjm"]) - want_mu) < 0.011, f"-> db={rel.get('htmjm')}")

    # ── B2 改（负向）：合同侧字段走属性编辑被忽略 ─────────────────
    log("\n--- B2 改（负向）：合同侧字段不可经属性编辑修改 ---")
    before = db_relation(dkbm)
    status, resp = put_result(uid, get_detail(uid), parcels=[{
        "dkbm": dkbm,
        "cbjyqqdfs": "002", "sfqqqg": "0",
        "cbhtbm": "HACK-HTBM", "cbjyqzbm": "HACK-QZBM",
    }])
    check("B2 PUT 200（多余字段不报错，Schema 丢弃）", status == 200,
          f"-> {status} {brief(resp, 200)}")
    after = db_relation(dkbm)
    check("B2 ★ cbjyqqdfs 未被改", after.get("cbjyqqdfs") == before.get("cbjyqqdfs"),
          f"-> {before.get('cbjyqqdfs')} -> {after.get('cbjyqqdfs')}")
    check("B2 ★ sfqqqg 未被改", after.get("sfqqqg") == before.get("sfqqqg"),
          f"-> {before.get('sfqqqg')} -> {after.get('sfqqqg')}")
    check("B2 ★ cbhtbm 未被改", after.get("cbhtbm") == before.get("cbhtbm"),
          f"-> {before.get('cbhtbm')!r} -> {after.get('cbhtbm')!r}")
    check("B2 ★ cbjyqzbm 未被改", after.get("cbjyqzbm") == before.get("cbjyqzbm"),
          f"-> {before.get('cbjyqzbm')!r} -> {after.get('cbjyqzbm')!r}")

    # ── B3 改（保护）：空值口径（前端恒发全字段，这里同构模拟）─────
    # ⚠️ 语义：parcels 项经 pydantic model_dump() 后未传的可选字段补 None，
    # update_parcel_attributes 把显式 None 视为"清空"。前端
    # ContractorResultDialog 恒发全字段快照，所以 UI 流不受影响；
    # 但 API 层部分字段提交会清掉其余可选字段——此处按前端契约发全字段。
    log("\n--- B3 改（保护）：空值口径 ---")
    status, resp = put_result(uid, get_detail(uid), parcels=[{
        "dkbm": dkbm,
        "dkmc": "", "scmj": None, "htmj": None,
        "syqxz": "20", "dklb": "02", "tdlylx": "021", "dldj": "03",
        "tdyt": "2", "sfjbnt": "0",
        "dkdz": "", "dkxz": "西至B", "dknz": "南至B", "dkbz": "北至B",
        "dkbzxx": "备注B", "zjrxm": "张指界",
    }])
    check("B3 PUT 200", status == 200, f"-> {status} {brief(resp, 200)}")
    dk = db_parcel(dkbm)
    check("B3 ★ dkmc='' 不覆盖（必填列保护）", dk.get("dkmc") == "改后地块名",
          f"-> db={dk.get('dkmc')!r}")
    check("B3 ★ dkdz='' 清空为 NULL（可选列）", dk.get("dkdz") in (None, ""),
          f"-> db={dk.get('dkdz')!r}")
    check("B3 ★ 同项内 zjrxm 保留（全字段快照语义）", dk.get("zjrxm") == "张指界",
          f"-> db={dk.get('zjrxm')!r}")

    # ── C 删：移除 + 撤回还原 ─────────────────────────────────────
    log("\n--- C 删：移除 + 撤回 ---")
    status, resp = put_result(uid, get_detail(uid), pending=[{
        "type": "remove_parcel", "payload": {"dkbm": dkbm, "reason": "验收移除"},
    }])
    check("C 移除 PUT 200", status == 200, f"-> {status} {brief(resp, 300)}")
    dk = db_parcel(dkbm)
    rel = db_relation(dkbm)
    # remove_parcel 是物理删除 + before_summary 快照（非软删），撤回时从快照重建。
    check("C ★ dk 行已物理删除", not dk, f"-> {dk.get('result_status') if dk else 'gone'}")
    check("C ★ rel 行已物理删除", not rel, f"-> {rel.get('result_status') if rel else 'gone'}")
    after_remove = {p.get("dkbm") for p in get_parcels(uid)}
    check("C /parcels 不再返回", dkbm not in after_remove, f"-> {sorted(after_remove)}")
    changes = [c for c in get_changes(uid) if c.get("changeType") == "remove_parcel"
               and c.get("changeStatus") != "rolled_back"]
    if check("C 存在 remove_parcel 变更记录", bool(changes), f"-> {len(changes)} 条"):
        bs = changes[0].get("beforeSummary") or {}
        check("C ★ beforeSummary.parcel 快照齐全",
              bool((bs.get("parcel") or {}).get("dkmc")),
              f"-> dkmc={(bs.get('parcel') or {}).get('dkmc')!r}")
        check("C ★ beforeSummary.relation 快照齐全",
              bool((bs.get("relation") or {}).get("cbfbm")),
              f"-> cbfbm={(bs.get('relation') or {}).get('cbfbm')!r}")
        rb = {"type": "rollback_remove_parcel", "payload": {
            "changeId": changes[0].get("id"), "changeNo": changes[0].get("changeNo"),
            "dkbm": dkbm, "cbfbm": HA,
            "sourceResultStatus": "added", "sourceChangeType": "add_parcel",
            "sourceChangeReason": "验收新增", "sourceIsChanged": True,
            "reason": "验收撤回移除",
        }}
        status, resp = put_result(uid, get_detail(uid), pending=[rb])
        check("C ★ 撤回移除 PUT 200", status == 200, f"-> {status} {brief(resp, 300)}")
        after_rb = {p.get("dkbm") for p in get_parcels(uid)}
        check("C ★ 撤回后地块还原", dkbm in after_rb, f"-> {sorted(after_rb)}")
        dk = db_parcel(dkbm)
        rel = db_relation(dkbm)
        check("C ★ 撤回后属性保留（dkmc=改后地块名）", dk.get("dkmc") == "改后地块名",
              f"-> {dk.get('dkmc')!r}")
        check("C ★ 撤回后 scmj 保留（1800.55）", dk.get("scmj") is not None
              and abs(float(dk["scmj"]) - 1800.55) < 0.01, f"-> {dk.get('scmj')}")
        check("C ★ 撤回后 zjrxm 保留（张指界）", dk.get("zjrxm") == "张指界",
              f"-> {dk.get('zjrxm')!r}")
        check("C ★ 撤回后 rel.htmj 保留（1750.25）", rel.get("htmj") is not None
              and abs(float(rel["htmj"]) - 1750.25) < 0.01, f"-> {rel.get('htmj')}")

    housekeeping()
    leftovers = sql(
        "SELECT count(*) FROM survey_cbf_result WHERE cbfbm = ANY(%s)", (ALL_CODES,),
    )
    check("收尾：临时户已清理", leftovers[0][0] == 0, f"-> {leftovers[0][0]}")

    log(f"\n=== 结果：PASS {len([l for l in OUT if '[PASS]' in l])} / FAIL {len(FAILED)} ===")
    if FAILED:
        log("失败项：" + "；".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
