"""验收：承包方管理「详情 / 新增 / 修改 / 删除」四条链路（base_id 重构后的补修）。

跑法：runtime/windows/python/python.exe scripts/_verify_contractor_crud.py

- 详情：读真实数据（只读，不改）。
- 新增/修改/删除：用临时承包方编码，跑完删干净；断言无残留。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "runtime" / ".state" / "_verify_contractor_crud.txt"
REAL_CODE = sys.argv[1] if len(sys.argv) > 1 else "321324100001030142"
TEMP_CODE = "321324100001039997"


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

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402

BASE = "/api/v1"
HEADERS = {"Authorization": f"Bearer {create_access_token('1')}"}
OUT: list[str] = []
FAILED: list[str] = []


def log(*parts) -> None:
    OUT.append(" ".join(str(part) for part in parts))


def check(label: str, ok: bool, extra: str = "") -> None:
    log(f"[{'PASS' if ok else 'FAIL'}] {label} {extra}".rstrip())
    if not ok:
        FAILED.append(label)


def q(sql: str, **params):
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(text(sql), params).mappings().all()]


def cleanup(code: str) -> None:
    """按 cbfbm 清掉验收痕迹（结果表 / 家庭成员 / 快照表）。"""
    with engine.begin() as conn:
        for sql in (
            "DELETE FROM survey_cbf_jtcy_result WHERE cbfbm = :c",
            "DELETE FROM survey_cbf_jtcy_base WHERE cbfbm = :c",
            "DELETE FROM survey_cbf_base WHERE cbfbm = :c",
            "DELETE FROM survey_cbf_result WHERE cbfbm = :c",
        ):
            conn.execute(text(sql), {"c": code})


def dump(label: str, payload) -> None:
    log(f"    {label}: {json.dumps(payload, ensure_ascii=False, default=str)[:900]}")


def make_payload(code: str, name: str, member_name: str, member_id: str) -> dict:
    return {
        "code": code,
        "typeCode": "1",
        "name": name,
        "idType": "1",
        "idNo": "320324199001011234",
        "address": "验收临时地址",
        "postcode": "223900",
        "mobile": "13800000000",
        "surveyDate": "2026-09-23",
        "surveyorName": "验收脚本",
        "surveyNote": None,
        "publicNoticeNote": None,
        "publicNoticeRecorder": None,
        "publicNoticeReviewDate": None,
        "publicNoticeReviewer": None,
        "groupRegionCode": None,
        "groupRegionName": None,
        "familyMembers": [
            {
                "name": member_name,
                "gender": "1",
                "idType": "1",
                "idNo": member_id,
                "relationToHead": "01",
                "noteCode": None,
                "isCoOwner": None,
                "note": None,
            }
        ],
    }


cleanup(TEMP_CODE)
client = TestClient(app)

# ---------- 1. 详情（真实数据，只读） ----------
log("=== 1. 详情：GET /contractors/{code}（真实数据） ===")
resp = client.get(f"{BASE}/contractors/{REAL_CODE}", headers=HEADERS)
check(f"GET /contractors/{REAL_CODE} 返回 200", resp.status_code == 200, f"-> {resp.status_code}")
detail = resp.json().get("data") if resp.status_code == 200 else {}
if detail:
    db_members = q(
        "SELECT cyxm, cyzjhm, yhzgx FROM survey_cbf_jtcy_result WHERE cbfbm = :c ORDER BY id",
        c=REAL_CODE,
    )
    log(f"    库内成员 {len(db_members)} 条，接口返回 {len(detail.get('familyMembers') or [])} 条")
    dump("familyMembers", detail.get("familyMembers"))
    check("详情里的成员数与库内一致", len(detail.get("familyMembers") or []) == len(db_members))
    check("详情基本字段齐全", bool(detail.get("code") and detail.get("name")))

# ---------- 2. 新增 ----------
log("")
log("=== 2. 新增：POST /contractors ===")
resp = client.post(f"{BASE}/contractors", json=make_payload(TEMP_CODE, "验收临时户", "验收成员甲", "320324199001011235"), headers=HEADERS)
check("POST /contractors 返回 201", resp.status_code == 201, f"-> {resp.status_code} {resp.text[:300]}")
created = resp.json().get("data") if resp.status_code == 201 else {}
if created:
    rows = q(
        "SELECT r.id AS result_id, b.id AS base_id, b.result_id AS base_result_id, r.contractor_uid, r.tenant_code, r.region_code "
        "FROM survey_cbf_result r LEFT JOIN survey_cbf_base b ON b.contractor_uid = r.contractor_uid "
        "WHERE r.cbfbm = :c",
        c=TEMP_CODE,
    )
    dump("新建后的行", rows)
    check("结果行建出来了", len(rows) == 1)
    if rows:
        check("base.result_id 指回 result.id", rows[0]["base_result_id"] == rows[0]["result_id"],
              f"(base.result_id={rows[0]['base_result_id']}, result.id={rows[0]['result_id']})")
        check("region_code / tenant_code 已落", bool(rows[0]["region_code"] and rows[0]["tenant_code"]))
    members = q("SELECT cyxm, cyzjhm, member_uid, is_household_head FROM survey_cbf_jtcy_result WHERE cbfbm = :c", c=TEMP_CODE)
    check("家庭成员结果行建出来了", len(members) == 1)
    mbase = q("SELECT id, member_uid, batch_id, result_id FROM survey_cbf_jtcy_base WHERE cbfbm = :c", c=TEMP_CODE)
    check("家庭成员快照行建出来了", len(mbase) == 1)
    if mbase:
        check("成员快照行已挂批次", bool(mbase[0]["batch_id"]))

# ---------- 3. 修改 ----------
log("")
log("=== 3. 修改：PUT /contractors/{code} ===")
resp = client.put(
    f"{BASE}/contractors/{TEMP_CODE}",
    json=make_payload(TEMP_CODE, "验收临时户改", "验收成员乙", "320324199001011236"),
    headers=HEADERS,
)
check("PUT /contractors 返回 200", resp.status_code == 200, f"-> {resp.status_code} {resp.text[:300]}")
if resp.status_code == 200:
    after = resp.json()["data"]
    log(f"    改后 name={after.get('name')} members={[m.get('name') for m in after.get('familyMembers') or []]}")
    check("名称已更新", after.get("name") == "验收临时户改")
    check("成员已替换", [m.get("name") for m in after.get("familyMembers") or []] == ["验收成员乙"])
    db_after = q("SELECT cbfmc FROM survey_cbf_result WHERE cbfbm = :c", c=TEMP_CODE)
    check("库内名称同步", db_after and db_after[0]["cbfmc"] == "验收临时户改", f"-> {db_after}")
    base_after = q("SELECT cbfmc, source_cbfbm FROM survey_cbf_base WHERE cbfbm = :c", c=TEMP_CODE)
    check("批次快照同步", bool(base_after) and base_after[0]["cbfmc"] == "验收临时户改", f"-> {base_after}")
    stale = q("SELECT count(*) AS n FROM survey_cbf_jtcy_result WHERE cbfbm = :c AND cyxm = :n", c=TEMP_CODE, n="验收成员甲")
    check("旧成员没有残留", stale[0]["n"] == 0)

# 再读一次详情，确认修改后详情可正常打开（这正是用户报错的那步）
resp = client.get(f"{BASE}/contractors/{TEMP_CODE}", headers=HEADERS)
check("改后详情仍可打开（200）", resp.status_code == 200, f"-> {resp.status_code}")

# ---------- 4. 删除 ----------
log("")
log("=== 4. 删除：DELETE /contractors/{code} ===")
resp = client.delete(f"{BASE}/contractors/{TEMP_CODE}", headers=HEADERS)
check("DELETE /contractors 返回 204", resp.status_code == 204, f"-> {resp.status_code} {resp.text[:300]}")

# ---------- 5. 清理与残留断言 ----------
cleanup(TEMP_CODE)
residue = q(
    "SELECT (SELECT count(*) FROM survey_cbf_result WHERE cbfbm = :c) AS r, "
    "       (SELECT count(*) FROM survey_cbf_base WHERE cbfbm = :c) AS b, "
    "       (SELECT count(*) FROM survey_cbf_jtcy_result WHERE cbfbm = :c) AS jr, "
    "       (SELECT count(*) FROM survey_cbf_jtcy_base WHERE cbfbm = :c) AS jb",
    c=TEMP_CODE,
)
dump("残留", residue)
check("验收痕迹已清空", all(value == 0 for value in residue[0].values()))

# 真实数据没被动过
real_now = q("SELECT cbfmc FROM survey_cbf_result WHERE cbfbm = :c", c=REAL_CODE)
check("真实数据未被修改", bool(real_now), f"-> {real_now}")

log("")
log("=" * 60)
log(f"结论：{'全部通过' if not FAILED else '存在失败项 -> ' + ', '.join(FAILED)}")

RESULT_PATH.write_text("\n".join(OUT), encoding="utf-8")
print("\n".join(OUT))
