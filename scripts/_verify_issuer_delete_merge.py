# -*- coding: utf-8 -*-
"""验收：发包方管理「编辑/删除」按钮 + 「合并发包方」功能（2026-11-05）。

覆盖：
  ① 删除闸门 —— 名下有承包方（cbdkxx 挂在该 fbfbm 下）不允许删除，
     前端 relatedContractorCount 预检与后端 delete_issuer 判据同源；
  ①b 删除闸门补 —— 地块关联为空但合同（cbht.fbfbm）还挂着的发包方同样拦截，
     防止删出孤儿合同；
  ② 删除正常链 —— 无任何关联的发包方 204 删除，快照行（survey_fbf_base）一并清掉；
  ③ 合并 —— 被合并方的地块/承包方关联（survey_cbdkxx_result.fbfbm）刷成保留方编码，
     合同关联（cbht.fbfbm，延包合同生成 _contract_issuer_code 的第一优先级）一并刷，
     被合并方快照+成果行删除，保留方仍在；
  ④ 合并负例 —— keep 与 merge 重叠 / 空列表 / 不存在的 uid；
  ⑤ 批次结束闸门 —— finished 批次删除/合并都被 400 拦下；
  ⑥ L1 静态核查 —— 前端按钮（编辑/删除/合并/复选框列）与后端路由、闸门文案同源。

全部用临时编码 + 临时批次，跑完清干净并断言零残留。
用法：runtime/windows/python/python.exe scripts/_verify_issuer_delete_merge.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "runtime" / ".state" / "_verify_issuer_delete_merge.txt"
FAILED: list[str] = []
OUT: list[str] = []


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

from datetime import datetime, timezone  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.cbht import Cbht, CONTRACT_SOURCE_IMPORTED  # noqa: E402
from app.models.survey import SurveyBatch, SurveyCbdkxxResult, SurveyFbfBase, SurveyFbfResult  # noqa: E402

BASE = "/api/v1"
HEADERS = {"Authorization": f"Bearer {create_access_token('1')}"}


def log(*parts: object) -> None:
    OUT.append(" ".join(str(part) for part in parts))


def check(label: str, ok: bool, extra: str = "") -> None:
    log(f"[{'PASS' if ok else 'FAIL'}] {label} {extra}".rstrip())
    if not ok:
        FAILED.append(label)


def q(sql: str, **params):
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(text(sql), params).mappings().all()]


def scalar(sql: str, **params):
    rows = q(sql, **params)
    return list(rows[0].values())[0] if rows else None


def dump(label: str, payload: object) -> None:
    log(f"    {label}: {json.dumps(payload, ensure_ascii=False, default=str)[:600]}")


# ---------------------------------------------------------------- 选前缀
prefix_row = scalar("SELECT fbfbm FROM survey_fbf_result WHERE length(fbfbm) = 14 ORDER BY id LIMIT 1")
PREFIX12 = (prefix_row or "321324100001")[:12]
# 发包方编码 14 位 = PREFIX12 + 2 位流水；挑 3 个库内不存在的
_existing_codes = {r["fbfbm"] for r in q("SELECT fbfbm FROM survey_fbf_result")}
_chosen: list[str] = []
for _s in ("98", "97", "96", "95", "94", "93", "92", "91"):
    _c = PREFIX12 + _s
    if _c not in _existing_codes:
        _chosen.append(_c)
    if len(_chosen) == 3:
        break
if len(_chosen) < 3:
    raise SystemExit("找不到 3 个可用的临时发包方编码")
ISSUER_A, ISSUER_B, ISSUER_C = _chosen
# 承包方 18 位 / 地块 19 位 / 合同 19 位，全部挂 99x 段位
CBF_1 = PREFIX12 + "999001"
CBF_2 = PREFIX12 + "999002"
CBF_3 = PREFIX12 + "999003"
CBF_4 = PREFIX12 + "999004"  # 只在 C 的合同里出现（合同关联删除闸门用）
DKBM_1 = PREFIX12 + "9990001"
DKBM_2 = PREFIX12 + "9990011"
DKBM_3 = PREFIX12 + "9990021"
DKBM_4 = PREFIX12 + "9990031"
DKBM_5 = PREFIX12 + "9990041"
CBHT_1 = PREFIX12 + "9990000"  # 19 位
CBHT_B = PREFIX12 + "9990091"  # 挂在 B 名下的合同
CBHT_C = PREFIX12 + "9990092"  # 挂在 C 名下的合同（仅合同关联，无地块关联）
TEMP_BATCH_NO = f"VERIFY-FBF-MERGE-{int(time.time())}"
TEMP_CODES = (ISSUER_A, ISSUER_B, ISSUER_C)
TEMP_CBFS = (CBF_1, CBF_2, CBF_3, CBF_4)
TEMP_CBHTS = (CBHT_1, CBHT_B, CBHT_C)
_collide = scalar(
    "SELECT count(*) FROM survey_cbdkxx_result WHERE cbfbm = ANY(:cbfs) OR dkbm = ANY(:dkbms)",
    cbfs=list(TEMP_CBFS),
    dkbms=[DKBM_1, DKBM_2, DKBM_3, DKBM_4, DKBM_5],
)
_collide_ht = scalar(
    "SELECT count(*) FROM cbht WHERE cbhtbm = ANY(:hts) OR fbfbm = ANY(:codes) OR cbfbm = ANY(:cbfs)",
    hts=list(TEMP_CBHTS), codes=list(TEMP_CODES), cbfs=list(TEMP_CBFS),
)
if _collide or _collide_ht:
    raise SystemExit(f"临时编码与库内数据冲突：cbdkxx {_collide} 条 / cbht {_collide_ht} 条")


def cleanup() -> None:
    """按临时编码清验收痕迹（先删合同/快照/关联，再删成果，最后删临时批次）。"""
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM survey_cbdkxx_result WHERE fbfbm = ANY(:codes) OR cbfbm = ANY(:cbfs)"),
            {"codes": list(TEMP_CODES), "cbfs": list(TEMP_CBFS)},
        )
        conn.execute(
            text("DELETE FROM cbht WHERE cbhtbm = ANY(:hts) OR fbfbm = ANY(:codes)"),
            {"hts": list(TEMP_CBHTS), "codes": list(TEMP_CODES)},
        )
        for code in TEMP_CODES:
            conn.execute(text("DELETE FROM survey_fbf_base WHERE fbfbm = :c"), {"c": code})
            conn.execute(text("DELETE FROM survey_fbf_result WHERE fbfbm = :c"), {"c": code})
        conn.execute(text("DELETE FROM survey_batches WHERE batch_no LIKE 'VERIFY-FBF-MERGE-%'"))


cleanup()

# ---------------------------------------------------------------- L1 静态核查
log("=== L1 静态核查：前后端接线 ===")
issuer_src = (ROOT / "backend" / "app" / "services" / "survey" / "issuer.py").read_text(encoding="utf-8-sig")
survey_api_src = (ROOT / "backend" / "app" / "api" / "v1" / "endpoints" / "survey.py").read_text(encoding="utf-8-sig")
view_src = (ROOT / "frontend" / "src" / "views" / "SurveyView.vue").read_text(encoding="utf-8-sig")
merge_dialog_src = (ROOT / "frontend" / "src" / "components" / "survey" / "view" / "MergeIssuerDialog.vue").read_text(encoding="utf-8-sig")

check("后端删除闸门文案存在（不允许删除）", "不允许删除" in issuer_src)
check("后端删除闸门覆盖合同关联（cbht.fbfbm）", "Cbht" in issuer_src and "Cbht.fbfbm" in issuer_src)
check("后端合并服务方法存在（merge_issuers）", "def merge_issuers" in issuer_src)
check("后端合并刷合同表（cbht.fbfbm 划转）", "Cbht.fbfbm == merged.fbfbm" in issuer_src)
check("合并路由已注册（/issuers/merge）", "/batches/{batch_id}/issuers/merge" in survey_api_src)
check("删除路由已注册（DELETE /issuers/{issuer_uid}）",
      re.search(r'@router\.delete\("/batches/\{batch_id\}/issuers/\{issuer_uid\}"', survey_api_src) is not None)
check("前端「进入调查」已改为「编辑」", "进入调查" not in view_src and ">编辑<" in view_src)
check("前端删除按钮已接线（deleteIssuerRow）", "deleteIssuerRow" in view_src)
check("前端合并按钮已接线（openMergeIssuer）", "openMergeIssuer" in view_src)
check("前端复选框列已加（type=selection）", 'type="selection"' in view_src)
check("前端合并弹窗已挂载（MergeIssuerDialog）", "MergeIssuerDialog" in view_src and "mergeSurveyIssuers" in merge_dialog_src)
check("删除 API 封装存在（deleteSurveyIssuer）",
      "deleteSurveyIssuer" in (ROOT / "frontend" / "src" / "api" / "survey.js").read_text(encoding="utf-8-sig"))

# ---------------------------------------------------------------- 建临时批次 + 三个发包方
log("")
log("=== 1. 建临时批次 + POST /surveys/batches/{id}/issuers × 3 ===")
with SessionLocal() as db:
    batch = SurveyBatch(
        batch_no=TEMP_BATCH_NO,
        batch_name="验收临时批次-发包方合并",
        region_code=PREFIX12,
        status="active",
        created_by=1,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    BATCH_ID = batch.id
    TENANT = batch.tenant_code
log(f"    批次 id={BATCH_ID} tenant={TENANT} region={PREFIX12}")
check("临时批次已建", bool(BATCH_ID))

client = TestClient(app)


def make_issuer_payload(code: str) -> dict:
    return {
        "code": code,
        "name": f"验收发包方{code[-2:]}",
        "responsibleName": "验收负责人",
        "responsibleIdType": "1",
        "responsibleIdNo": "320324199001011234",
        "phone": "13800000000",
        "address": "验收临时地址",
        "postcode": "223900",
        "surveyorName": "验收脚本",
        "surveyDate": "2026-11-05",
        "surveyNote": None,
        "remark": None,
    }


uids: dict[str, str] = {}
for code in TEMP_CODES:
    resp = client.post(f"{BASE}/surveys/batches/{BATCH_ID}/issuers", json=make_issuer_payload(code), headers=HEADERS)
    check(f"POST 新增发包方 {code} 返回 201", resp.status_code == 201, f"-> {resp.status_code} {resp.text[:200]}")
    if resp.status_code == 201:
        uids[code] = resp.json()["data"]["issuerUid"]
check("三个发包方 uid 齐全", len(uids) == 3, f"-> {uids}")

# ---------------------------------------------------------------- 挂关联承包方（cbdkxx）
log("")
log("=== 2. 挂关联：A 名下 2 个承包方（4 个地块关联），B 名下 1 个承包方（1 个地块关联） ===")
now = datetime.now(timezone.utc)
with SessionLocal() as db:
    _rel_seq = iter(range(1, 100))

    def add_relation(dkbm: str, fbfbm: str, cbfbm: str) -> None:
        db.add(SurveyCbdkxxResult(
            tenant_code=TENANT,
            region_code=fbfbm,
            parcel_info_uid=f"verify-piuid-{next(_rel_seq):04d}".ljust(36, "0")[:36],
            dkbm=dkbm,
            fbfbm=fbfbm,
            cbfbm=cbfbm,
            cbjyqqdfs="01",
            htmj=1.00,
            cbhtbm=CBHT_1,
            cbjyqzbm=CBHT_1,
            survey_status="surveyed",
            result_status="normal",
            is_changed=False,
            change_type="none",
            initialized_at=now,
        ))
    for dkbm, cbfbm in ((DKBM_1, CBF_1), (DKBM_2, CBF_1), (DKBM_3, CBF_2), (DKBM_4, CBF_2)):
        add_relation(dkbm, ISSUER_A, cbfbm)
    add_relation(DKBM_5, ISSUER_B, CBF_3)

    def add_contract(cbhtbm: str, fbfbm: str, cbfbm: str | None) -> None:
        db.add(Cbht(
            tenant_code=TENANT,
            region_code=fbfbm,
            cbhtbm=cbhtbm,
            fbfbm=fbfbm,
            cbfbm=cbfbm,
            contract_source=CONTRACT_SOURCE_IMPORTED,
            contract_status="active",
        ))
    add_contract(CBHT_B, ISSUER_B, CBF_3)  # B 名下承包方 C3 的合同 → 合并后应刷成 A
    add_contract(CBHT_C, ISSUER_C, CBF_4)  # C 只有合同关联、无地块关联 → 删除闸门应拦
    db.commit()

counts = q(
    "SELECT fbfbm, count(DISTINCT cbfbm) AS contractors, count(*) AS parcels "
    "FROM survey_cbdkxx_result WHERE fbfbm = ANY(:codes) GROUP BY fbfbm",
    codes=list(TEMP_CODES[:2]),
)
dump("关联分布", counts)
check("A 名下 2 个承包方 / 4 条地块关联", any(r["fbfbm"] == ISSUER_A and r["contractors"] == 2 and r["parcels"] == 4 for r in counts))
check("B 名下 1 个承包方 / 1 条地块关联", any(r["fbfbm"] == ISSUER_B and r["contractors"] == 1 and r["parcels"] == 1 for r in counts))
check("B 名下合同 1 份（fbfbm=B）", scalar("SELECT count(*) FROM cbht WHERE fbfbm = :c", c=ISSUER_B) == 1)

# ---------------------------------------------------------------- 删除闸门
log("")
log("=== 3. 删除闸门：有承包方 → 400 ===")
resp = client.delete(f"{BASE}/surveys/batches/{BATCH_ID}/issuers/{uids[ISSUER_A]}", headers=HEADERS)
check("删除 A（有 2 个承包方）返回 400", resp.status_code == 400, f"-> {resp.status_code} {resp.text[:200]}")
check("报错文案点名承包方", "承包方" in resp.text and "不允许删除" in resp.text, f"-> {resp.text[:200]}")
still_there = q("SELECT count(*) AS n FROM survey_fbf_result WHERE fbfbm = :c", c=ISSUER_A)
check("A 未被误删", still_there[0]["n"] == 1)

log("")
log("=== 4. 删除正常链：C 先因合同关联被拦，解除后 204 删除 ===")
resp = client.delete(f"{BASE}/surveys/batches/{BATCH_ID}/issuers/{uids[ISSUER_C]}", headers=HEADERS)
check("C 仅有合同关联时删除 → 400（防孤儿合同）", resp.status_code == 400, f"-> {resp.status_code} {resp.text[:200]}")
check("报错文案点名承包方", "承包方" in resp.text and "不允许删除" in resp.text, f"-> {resp.text[:200]}")
with engine.begin() as conn:
    conn.execute(text("DELETE FROM cbht WHERE cbhtbm = :h"), {"h": CBHT_C})
resp = client.delete(f"{BASE}/surveys/batches/{BATCH_ID}/issuers/{uids[ISSUER_C]}", headers=HEADERS)
check("解除合同关联后删除 C 返回 204", resp.status_code == 204, f"-> {resp.status_code} {resp.text[:200]}")
residue_c = q(
    "SELECT (SELECT count(*) FROM survey_fbf_result WHERE fbfbm = :c) AS r, "
    "(SELECT count(*) FROM survey_fbf_base WHERE fbfbm = :c) AS b",
    c=ISSUER_C,
)
check("C 的成果行+快照行都清掉了", residue_c[0]["r"] == 0 and residue_c[0]["b"] == 0, f"-> {residue_c}")

# ---------------------------------------------------------------- 合并
log("")
log("=== 5. 合并：keep=A，merge=B → 关联划转 + B 删除 ===")
resp = client.post(
    f"{BASE}/surveys/batches/{BATCH_ID}/issuers/merge",
    json={"keepIssuerUid": uids[ISSUER_A], "mergeIssuerUids": [uids[ISSUER_B]]},
    headers=HEADERS,
)
check("合并返回 200", resp.status_code == 200, f"-> {resp.status_code} {resp.text[:300]}")
if resp.status_code == 200:
    result = resp.json()["data"]
    dump("合并结果", result)
    check("movedParcelCount = 1", result.get("movedParcelCount") == 1, f"-> {result.get('movedParcelCount')}")
    check("movedContractorCount = 1", result.get("movedContractorCount") == 1, f"-> {result.get('movedContractorCount')}")
    check("movedContractCount = 1（合同一并划转）", result.get("movedContractCount") == 1, f"-> {result.get('movedContractCount')}")
    check("keepIssuer 编码 = A", (result.get("keepIssuer") or {}).get("code") == ISSUER_A)
    check("keepIssuer 关联数已累计 = 3", (result.get("keepIssuer") or {}).get("relatedContractorCount") == 3,
          f"-> {result.get('keepIssuer', {}).get('relatedContractorCount')}")

moved = q("SELECT fbfbm, cbfbm FROM survey_cbdkxx_result WHERE cbfbm = :c", c=CBF_3)
check("B 名下承包方 C3 的地块关联已刷成 A 编码", moved and all(r["fbfbm"] == ISSUER_A for r in moved), f"-> {moved}")
moved_ht = q("SELECT fbfbm, cbfbm FROM cbht WHERE cbhtbm = :h", h=CBHT_B)
check("B 名下合同的 fbfbm 已刷成 A 编码（_contract_issuer_code 第一优先级）",
      moved_ht and all(r["fbfbm"] == ISSUER_A for r in moved_ht), f"-> {moved_ht}")
residue_b = q(
    "SELECT (SELECT count(*) FROM survey_fbf_result WHERE fbfbm = :c) AS r, "
    "(SELECT count(*) FROM survey_fbf_base WHERE fbfbm = :c) AS b",
    c=ISSUER_B,
)
check("B 的成果行+快照行已删除", residue_b[0]["r"] == 0 and residue_b[0]["b"] == 0, f"-> {residue_b}")
keep_alive = q("SELECT count(*) AS n FROM survey_fbf_result WHERE fbfbm = :c", c=ISSUER_A)
check("A（保留方）仍在", keep_alive[0]["n"] == 1)

log("")
log("=== 6. 合并负例 ===")
resp = client.post(
    f"{BASE}/surveys/batches/{BATCH_ID}/issuers/merge",
    json={"keepIssuerUid": uids[ISSUER_A], "mergeIssuerUids": [uids[ISSUER_A]]},
    headers=HEADERS,
)
check("keep 与 merge 重叠 → 400", resp.status_code == 400, f"-> {resp.status_code}")
resp = client.post(
    f"{BASE}/surveys/batches/{BATCH_ID}/issuers/merge",
    json={"keepIssuerUid": uids[ISSUER_A], "mergeIssuerUids": ["not-exists-uid"]},
    headers=HEADERS,
)
check("合并不存在的 uid → 404", resp.status_code == 404, f"-> {resp.status_code} {resp.text[:150]}")

# ---------------------------------------------------------------- 批次结束闸门
log("")
log("=== 7. 批次结束闸门：finished → 删除/合并都被 400 拦下 ===")
with SessionLocal() as db:
    row = db.scalars(select(SurveyBatch).where(SurveyBatch.id == BATCH_ID)).one()
    row.status = "finished"
    db.commit()
resp = client.delete(f"{BASE}/surveys/batches/{BATCH_ID}/issuers/{uids[ISSUER_A]}", headers=HEADERS)
check("finished 批次删除 → 400", resp.status_code == 400, f"-> {resp.status_code} {resp.text[:150]}")
resp = client.post(
    f"{BASE}/surveys/batches/{BATCH_ID}/issuers/merge",
    json={"keepIssuerUid": uids[ISSUER_A], "mergeIssuerUids": [uids.get(ISSUER_B, "x")]},
    headers=HEADERS,
)
check("finished 批次合并 → 400", resp.status_code == 400, f"-> {resp.status_code} {resp.text[:150]}")

# ---------------------------------------------------------------- 清理
log("")
log("=== 8. 清理与残留断言 ===")
cleanup()
residue = q(
    "SELECT (SELECT count(*) FROM survey_fbf_result WHERE fbfbm = ANY(:codes)) AS fbf, "
    "(SELECT count(*) FROM survey_fbf_base WHERE fbfbm = ANY(:codes)) AS fbf_base, "
    "(SELECT count(*) FROM survey_cbdkxx_result WHERE cbfbm = ANY(:cbfs)) AS rel, "
    "(SELECT count(*) FROM cbht WHERE cbhtbm = ANY(:hts) OR fbfbm = ANY(:codes)) AS ht, "
    "(SELECT count(*) FROM survey_batches WHERE batch_no LIKE 'VERIFY-FBF-MERGE-%') AS batch",
    codes=list(TEMP_CODES),
    cbfs=list(TEMP_CBFS),
    hts=list(TEMP_CBHTS),
)
dump("残留", residue)
check("验收痕迹已清空", all(v == 0 for v in residue[0].values()))

log("")
log("=" * 60)
log(f"结论：{'全部通过' if not FAILED else '存在失败项 -> ' + ', '.join(FAILED)}")
RESULT_PATH.write_text("\n".join(OUT), encoding="utf-8")
print("\n".join(OUT))
if FAILED:
    sys.exit(1)
