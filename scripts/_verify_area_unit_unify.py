# -*- coding: utf-8 -*-
"""验收：面积单位口径统一（2026-11-04）+ 已保存移除撤回链路回归。

口径定案
--------
- 库内与所有 API 的 scmj / htmj / newScmj 一律 ㎡（历史导入、打印、导出同口径）；
- 界面用「亩」输入/显示，边界换算；
- 切割写库此前把 areaMu（亩）直接写进 scmj（㎡ 列）——本脚本钉住修复；
- "按面积切割"的 newScmj 现按 ㎡ 解释（此前混用亩/㎡：与 scmj 列直接比较是错的）。

覆盖点
------
U1 新增地块：payload ㎡ 原样落库，/parcels 原样返回。
U2 按方向切割预览：newScmj=1333.33㎡（2亩）→ 切出块 scmj≈1333.33（㎡ 而非亩值）。
U3 按边切割预览回归：edgeIndex=0 + ㎡ → 200 且切出块 scmj≈1333.33。
U4 纯面积模式校验：newScmj(㎡) >= 源 scmj(㎡) → 400，两值同单位比较。
U5 切割保存落库：DB 中生成行 scmj 为 ㎡ 口径。
U6 移除 → 变更记录快照（parcel/relation/geometry）齐全（前端"已移除行合成"数据源）
   → 撤回移除 → 地块还原（回归）。

夹具：批次 41 下 1 个临时户（…9841），收尾自清。
跑法：runtime/windows/python/python.exe scripts/_verify_area_unit_unify.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read_runtime_env() -> dict[str, str]:
    """DB 随机密码只存 runtime/.state/runtime.env（start-postgres.ps1 写入），别硬编码。"""
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

BATCH_ID = 2                       # 当前库（扎鲁特旗）的 active 批次：region 150526103220
HA = "150526103220009841"          # 临时户（批次区域前缀 + 6 位流水）
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
            "code": HA, "typeCode": "1", "name": "单位口径验收户", "idType": "1",
            "idNo": "320324199001019941", "address": "验收临时地址",
            "postcode": "223900", "mobile": "13900000000",
            "surveyorName": "验收脚本", "surveyDate": "2026-11-04",
            "remark": "area unit verify fixture",
        },
    )
    if not check("建临时户", status == 201, f"-> {status} {brief(payload)}"):
        return None
    uid = (payload.get("data") or {}).get("contractorUid") or ""
    detail = get_detail(uid)
    members = members_payload(detail.get("familyMembers") or [])
    members.append({
        "name": "验收成员一", "gender": "1", "idType": "1",
        "idNo": "320324199001014101",
        "relationToHead": "01", "isHouseholdHead": True,
    })
    st, rp = put_result(uid, detail, members=members)
    check("补 1 名成员", st == 200, f"-> {st} {brief(rp, 300)}")
    return uid


def main() -> int:
    global client
    client = TestClient(app)
    log("=== 面积单位口径统一 + 移除撤回 验收 ===")

    uid = setup_household()
    if not uid:
        return 1

    # ── U1 新增带图形地块（scmj ㎡ 口径）────────────────────────────
    src_geom = box_geometry(119.90, 34.90, 0.008943, 0.007335)
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/parcels/next-code")
    src = ((payload.get("data") or {}).get("dkbm")
           or (payload.get("data") or {}).get("code") or "") if status == 200 else ""
    if not check("取源地块编码", bool(src), f"-> {brief(payload, 200)}"):
        housekeeping()
        return 1
    # 新增地块提交口径 ㎡：1333.33（2 亩）
    body = {
        "dkbm": src, "dkmc": "口径验收源地块", "dklb": "01", "dldj": "01", "tdyt": "1",
        "tdlylx": "011", "syqxz": "10", "scmj": 1333.33, "sfjbnt": "1",
        "reason": "验收新增", "geometry": src_geom, "geometrySourceSrid": 4326,
    }
    status, resp = put_result(uid, get_detail(uid), pending=[{"type": "add_parcel", "payload": body}])
    if not check("U1 新增带图形地块 PUT 200", status == 200, f"-> {status} {brief(resp, 400)}"):
        housekeeping()
        return 1
    rows = sql(
        "SELECT scmj FROM survey_dk_result WHERE dkbm = %s AND result_status = 'added'",
        (src,),
    )
    check("U1 ★ DB scmj 原样落库（㎡ 口径）", bool(rows) and abs(float(rows[0][0] or 0) - 1333.33) < 0.01,
          f"-> db scmj={rows[0][0] if rows else None}")
    parcels = get_parcels(uid)
    src_row = next((p for p in parcels if p.get("dkbm") == src), None)
    check("U1 /parcels 返回 scmj ㎡ 原值", bool(src_row) and abs(float(src_row.get("scmj") or 0) - 1333.33) < 0.01,
          f"-> {src_row.get('scmj') if src_row else None}")

    # 源地块几何面积（㎡），用于 U2 断言"剩余块"
    geo_rows = sql(
        "SELECT ROUND(ST_Area(geom)::numeric, 2) FROM survey_dk_result WHERE dkbm = %s",
        (src,),
    )
    source_sqm = float(geo_rows[0][0]) if geo_rows and geo_rows[0][0] is not None else 0.0
    check("U1 源地块几何面积 > 4 亩（可切 2 亩）", source_sqm > 4 * SQM_PER_MU, f"-> {source_sqm} ㎡")
    target_sqm = 1333.33  # 2 亩

    # ── U2 按方向切割预览：newScmj ㎡ 语义 ────────────────────────
    preview_body = {
        "dkbm": src, "splitMode": "area", "splitDirection": "east",
        "newScmj": target_sqm,
        "sourceGeometry": src_geom, "sourceGeometrySrid": 4326,
    }
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/parcels/preview-split",
                          method="POST", body=preview_body)
    if not check("U2 方向切割预览 200", status == 200, f"-> {status} {brief(payload, 400)}"):
        housekeeping()
        return 1
    gen = ((payload.get("data") or {}).get("generatedParcels") or [])
    check("U2 预览生成 2 块", len(gen) == 2, f"-> {[g.get('dkbm') for g in gen]}")
    if len(gen) == 2:
        areas = sorted(float(g.get("scmj") or 0) for g in gen)
        cut, remain = areas[0], areas[1]
        check("U2 ★ 切出块 scmj ≈ 1333.33（㎡ 口径，而非 2.0 亩值）",
              abs(cut - target_sqm) < 3.0, f"-> scmj={cut}")
        check("U2 ★ 剩余块 scmj ≈ 源几何面积 - 1333.33（同口径相加）",
              abs((cut + remain) - source_sqm) < 5.0, f"-> sum={cut + remain} vs geom={source_sqm}")

    # ── U3 按边切割回归：edgeIndex=0 + ㎡ ─────────────────────────
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/parcels/preview-split",
                          method="POST", body={**preview_body, "splitDirection": None, "edgeIndex": 0})
    check("U3 按边切割预览 200（edgeIndex=0）", status == 200, f"-> {status} {brief(payload, 300)}")
    gen3 = ((payload.get("data") or {}).get("generatedParcels") or []) if status == 200 else []
    if len(gen3) == 2:
        cut3 = min(float(g.get("scmj") or 0) for g in gen3)
        check("U3 ★ 按边切出块 scmj ≈ 1333.33（㎡）", abs(cut3 - target_sqm) < 3.0, f"-> scmj={cut3}")

    # ── U4 纯面积模式（无方向/无边）：保存路径 newScmj(㎡) >= 源 scmj(㎡) → 400 ──
    # 注意：预览路径对 direction=None 直接报 "invalid split direction"，
    # 同单位比较的闸门在保存路径（split_parcel 的 fallback 分支）。
    status, resp = put_result(uid, get_detail(uid), pending=[{
        "type": "split_parcel",
        "payload": {"dkbm": src, "splitMode": "area", "newScmj": 10 ** 9, "reason": "口径验收超面积"},
    }])
    check("U4 ★ 纯面积模式 newScmj(㎡) ≥ 源 scmj(㎡) → 400（同单位比较）",
          status == 400 and "不能大于等于" in brief(resp, 300),
          f"-> {status} {brief(resp, 200)}")

    # ── U5 切割保存落库：DB scmj ㎡ ───────────────────────────────
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/parcels/preview-split",
                          method="POST", body=preview_body)
    gen = ((payload.get("data") or {}).get("generatedParcels") or []) if status == 200 else []
    if len(gen) == 2:
        op = {"type": "split_parcel", "payload": {
            "dkbm": src, "splitMode": "area", "splitDirection": "east",
            "newScmj": target_sqm,
            "sourceGeometry": src_geom, "sourceGeometrySrid": 4326,
            "generatedParcels": [
                {"dkbm": g["dkbm"], "dkmc": f"切割生成{i + 1}", "scmj": g.get("scmj"), "htmj": g.get("htmj"),
                 "geometry": g.get("geometry")}
                for i, g in enumerate(gen)
            ],
            "reason": "口径验收切割",
        }}
        status, resp = put_result(uid, get_detail(uid), pending=[op])
        check("U5 切割 PUT 200", status == 200, f"-> {status} {brief(resp, 400)}")
        if status == 200:
            new_dkbms = [g["dkbm"] for g in gen]
            rows = sql(
                "SELECT dkbm, scmj FROM survey_dk_result WHERE dkbm = ANY(%s) AND result_status = 'split_generated'",
                (new_dkbms,),
            )
            ok_ump = len(rows) == 2 and all(
                abs(float(r[1] or 0) - target_sqm) < 3.0 or float(r[1] or 0) > target_sqm for r in rows
            )
            total = sum(float(r[1] or 0) for r in rows)
            check("U5 ★ DB 生成行 2 条且 scmj 合计 ≈ 源几何面积（㎡ 口径）",
                  ok_ump and abs(total - source_sqm) < 5.0,
                  f"-> {[(r[0], float(r[1] or 0)) for r in rows]} sum={total} vs geom={source_sqm}")
            # 撤回切割（回归：撤回后源地块还原）
            changes = [c for c in get_changes(uid) if c.get("changeType") == "split_parcel"
                       and c.get("changeStatus") != "rolled_back"]
            if changes:
                change = changes[0]
                rb = {"type": "rollback_split_parcel", "payload": {
                    "changeId": change.get("id"), "changeNo": change.get("changeNo"),
                    "sourceDkbm": src,
                    "sourceResultStatus": "added", "sourceChangeType": "add_parcel",
                    "sourceChangeReason": "验收新增", "sourceIsChanged": True,
                    "generatedDkbms": new_dkbms,
                    "reason": "口径验收撤回切割",
                }}
                status, resp = put_result(uid, get_detail(uid), pending=[rb])
                check("U5 撤回切割 PUT 200", status == 200, f"-> {status} {brief(resp, 300)}")
                after = {p.get("dkbm") for p in get_parcels(uid)}
                check("U5 撤回后源地块回到列表、生成块消失",
                      src in after and not (set(new_dkbms) & after), f"-> {sorted(after)}")
        # 为 U6 重新准备：源地块还在（撤回过了）
    else:
        check("U5 切割预览可用", False, f"-> {brief(payload, 300)}")

    # ── U6 移除 → 变更快照齐全（前端合成行数据源）→ 撤回移除还原 ──
    status, resp = put_result(uid, get_detail(uid), pending=[{
        "type": "remove_parcel", "payload": {"dkbm": src, "reason": "口径验收移除"},
    }])
    check("U6 移除 PUT 200", status == 200, f"-> {status} {brief(resp, 300)}")
    after_remove = {p.get("dkbm") for p in get_parcels(uid)}
    check("U6 /parcels 不再返回已移除行（前端需按快照合成）", src not in after_remove, f"-> {sorted(after_remove)}")
    changes = [c for c in get_changes(uid) if c.get("changeType") == "remove_parcel"
               and c.get("changeStatus") != "rolled_back"]
    if check("U6 存在 remove_parcel 变更记录", bool(changes), f"-> {len(changes)} 条"):
        bs = changes[0].get("beforeSummary") or {}
        parcel_snap = bs.get("parcel") or {}
        relation_snap = bs.get("relation") or {}
        check("U6 ★ beforeSummary.parcel 带 dkmc/scmj（合成行展示用）",
              bool(parcel_snap.get("dkmc")) and parcel_snap.get("scmj") is not None,
              f"-> dkmc={parcel_snap.get('dkmc')} scmj={parcel_snap.get('scmj')}")
        check("U6 ★ beforeSummary.relation 带 cbfbm（合成行归属用）",
              bool(relation_snap.get("cbfbm")), f"-> {relation_snap.get('cbfbm')}")
        check("U6 ★ beforeSummary.geometry 带源图形（撤回预览绘图用）",
              isinstance(bs.get("geometry"), dict)
              and bs["geometry"].get("type") in ("Polygon", "MultiPolygon"),
              f"-> {bs.get('geometry', {}).get('type') if isinstance(bs.get('geometry'), dict) else type(bs.get('geometry')).__name__}")
        rb = {"type": "rollback_remove_parcel", "payload": {
            "changeId": changes[0].get("id"), "changeNo": changes[0].get("changeNo"),
            "dkbm": src, "cbfbm": HA,
            "sourceResultStatus": "added", "sourceChangeType": "add_parcel",
            "sourceChangeReason": "验收新增", "sourceIsChanged": True,
            "reason": "口径验收撤回移除",
        }}
        status, resp = put_result(uid, get_detail(uid), pending=[rb])
        check("U6 ★ 撤回移除 PUT 200（不依赖 parcels 里存在 removed 行）",
              status == 200, f"-> {status} {brief(resp, 300)}")
        after_rollback = {p.get("dkbm") for p in get_parcels(uid)}
        check("U6 撤回后地块还原", src in after_rollback, f"-> {sorted(after_rollback)}")

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
