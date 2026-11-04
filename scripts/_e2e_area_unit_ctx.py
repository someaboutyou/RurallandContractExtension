# -*- coding: utf-8 -*-
"""给「面积单位统一 + 已保存移除撤回入口」的浏览器端到端验收准备上下文。

做三件事（与 _verify_area_unit_unify.py 同一套口径）：
  1. 建临时户 150526103220009842（1 成员）；
  2. 新增 1 个带图形的地块（scmj = 1333.33 ㎡，即 2 亩）；
  3. **已保存移除**该地块（PUT pending remove_parcel 直接提交）——
     前端要验的就是"已保存移除的行按变更记录快照合成 + 撤回移除按钮可达"。

输出：runtime/.state/_e2e_area_unit_ctx.json
清理：python scripts/_e2e_area_unit_ctx.py --cleanup
跑法：runtime/windows/python/python.exe scripts/_e2e_area_unit_ctx.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "runtime" / ".state" / "_e2e_area_unit_ctx.json"


def load_env() -> dict[str, str]:
    data: dict[str, str] = {}
    for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


for _key, _value in load_env().items():
    os.environ.setdefault(_key, _value)
os.environ.setdefault("SECRET_KEY", "verify-only")

sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import psycopg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.main import app  # noqa: E402

BATCH_ID = 2
HA = "150526103220009842"
ALL_CODES = [HA]
SCMJ_SQM = 1333.33  # 2 亩


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
    dsn = (
        f"host={settings.database_host} port={settings.database_port} "
        f"dbname={settings.database_name} user={settings.database_user} "
        f"password={settings.database_password}"
    )
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT contractor_uid FROM survey_cbf_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
            uids = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT dkbm FROM survey_cbdkxx_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
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
            cur.execute("DELETE FROM survey_change_diffs WHERE batch_id = %s AND contractor_uid NOT IN"
                        " (SELECT contractor_uid FROM survey_cbf_result)", (BATCH_ID,))
            cur.execute("DELETE FROM survey_change_records WHERE batch_id = %s AND contractor_uid NOT IN"
                        " (SELECT contractor_uid FROM survey_cbf_result)", (BATCH_ID,))


def main() -> int:
    if "--cleanup" in sys.argv:
        housekeeping()
        print("cleanup done")
        if OUT_PATH.exists():
            OUT_PATH.unlink()
        return 0

    housekeeping()  # 预清理
    token = create_access_token("1")
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    def api(path, method="GET", body=None):
        resp = client.request(method, f"/api/v1{path}", json=body, headers=headers)
        try:
            return resp.status_code, resp.json()
        except Exception:  # noqa: BLE001
            return resp.status_code, resp.text

    status, payload = api(f"/surveys/batches/{BATCH_ID}/tasks", method="POST", body={
        "code": HA, "typeCode": "1", "name": "面积口径演示户", "idType": "1",
        "idNo": "320324199001019946", "address": "验收临时地址",
        "postcode": "223900", "mobile": "13900000000",
        "surveyorName": "验收脚本", "surveyDate": "2026-11-04",
        "remark": "area unit e2e fixture",
    })
    if status != 201:
        print(f"建户失败: {status} {str(payload)[:300]}")
        return 1
    uid = (payload.get("data") or {}).get("contractorUid")
    print(f"household created uid={uid}")

    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/parcels/next-code")
    dkbm = (payload.get("data") or {}).get("dkbm") or (payload.get("data") or {}).get("code")
    print(f"parcel code={dkbm}")

    detail = api(f"/surveys/batches/{BATCH_ID}/results/{uid}")[1].get("data") or {}
    members = detail.get("familyMembers") or []
    members.append({"name": "演示成员", "gender": "1", "idType": "1", "idNo": "320324199001014205",
                    "relationToHead": "01", "isHouseholdHead": True})
    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid}", method="PUT", body={
        **{k: detail.get(k) for k in (
            "code", "typeCode", "name", "idType", "idNo", "address", "postcode", "mobile",
            "surveyDate", "surveyorName", "surveyNote", "publicNoticeNote", "publicNoticeRecorder",
            "publicNoticeReviewDate", "publicNoticeReviewer", "groupRegionCode", "groupRegionName",
            "surveyStatus", "resultStatus", "changeType", "changeReason", "policyBasis",
            "evidenceSummary", "remark")},
        "surveyStatus": detail.get("surveyStatus") or "surveyed",
        "resultStatus": detail.get("resultStatus") or "normal",
        "changeType": detail.get("changeType") or "none",
        "familyMembers": members, "deletedMembers": [], "pendingOperations": [],
    })
    print(f"member added: {status}")

    body = {
        "dkbm": dkbm, "dkmc": "口径演示地块", "dklb": "01", "dldj": "01", "tdyt": "1",
        "tdlylx": "011", "syqxz": "10", "scmj": SCMJ_SQM, "sfjbnt": "1",
        "reason": "口径演示新增", "geometry": box_geometry(119.95, 34.95, 0.004, 0.003),
        "geometrySourceSrid": 4326,
    }
    detail = api(f"/surveys/batches/{BATCH_ID}/results/{uid}")[1].get("data") or {}
    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid}", method="PUT", body={
        **{k: detail.get(k) for k in (
            "code", "typeCode", "name", "idType", "idNo", "address", "postcode", "mobile",
            "surveyDate", "surveyorName", "surveyNote", "publicNoticeNote", "publicNoticeRecorder",
            "publicNoticeReviewDate", "publicNoticeReviewer", "groupRegionCode", "groupRegionName",
            "surveyStatus", "resultStatus", "changeType", "changeReason", "policyBasis",
            "evidenceSummary", "remark")},
        "surveyStatus": detail.get("surveyStatus") or "surveyed",
        "resultStatus": detail.get("resultStatus") or "normal",
        "changeType": detail.get("changeType") or "none",
        "familyMembers": detail.get("familyMembers") or [], "deletedMembers": [],
        "pendingOperations": [{"type": "add_parcel", "payload": body}],
    })
    print(f"parcel added: {status}")
    if status != 200:
        return 1

    # 已保存移除（这是前端要撤回的对象）
    detail = api(f"/surveys/batches/{BATCH_ID}/results/{uid}")[1].get("data") or {}
    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid}", method="PUT", body={
        **{k: detail.get(k) for k in (
            "code", "typeCode", "name", "idType", "idNo", "address", "postcode", "mobile",
            "surveyDate", "surveyorName", "surveyNote", "publicNoticeNote", "publicNoticeRecorder",
            "publicNoticeReviewDate", "publicNoticeReviewer", "groupRegionCode", "groupRegionName",
            "surveyStatus", "resultStatus", "changeType", "changeReason", "policyBasis",
            "evidenceSummary", "remark")},
        "surveyStatus": detail.get("surveyStatus") or "surveyed",
        "resultStatus": detail.get("resultStatus") or "normal",
        "changeType": detail.get("changeType") or "none",
        "familyMembers": detail.get("familyMembers") or [], "deletedMembers": [],
        "pendingOperations": [{"type": "remove_parcel", "payload": {"dkbm": dkbm, "reason": "口径演示移除"}}],
    })
    print(f"parcel removed(saved): {status}")
    if status != 200:
        return 1

    status, payload = api(f"/surveys/batches/{BATCH_ID}/changes?contractorUid={uid}&page=1&page_size=50")
    items = ((payload.get("data") or {}).get("items") or []) if status == 200 else []
    removes = [c for c in items if c.get("changeType") == "remove_parcel" and c.get("changeStatus") != "rolled_back"]
    print(f"remove change records: {len(removes)}")

    OUT_PATH.write_text(json.dumps({
        "token": token, "batchId": BATCH_ID, "batchName": "SUR202611030002",
        "contractorUid": uid, "code": HA, "name": "面积口径演示户", "dkbm": dkbm,
        "scmjSqm": SCMJ_SQM, "expectedMu": "2", "hasRemoveRecord": bool(removes),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"ctx written: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
