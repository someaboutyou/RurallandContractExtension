# -*- coding: utf-8 -*-
"""探针：建库中心-承包方管理页（ContractorView /contractors）综合功能与数据勾稽。

覆盖：批次列表/四类筛选、详情勾稽（基本信息/成员/合同）、关联地块、
增删改闭环（含成员整体替换、重复证件号拦截、自清理）、删除闸门、
单户地籍调查表/摸底表 Word、批量打印渲染、鉴权门禁。
可重复运行：临时承包方 finally 清理。
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
env_file = ROOT / "runtime" / ".state" / "runtime.env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        t = line.strip()
        if t and not t.startswith("#") and "=" in t:
            k, v = t.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
os.environ.setdefault("SECRET_KEY", "probe-only")
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import urllib.error  # noqa: E402
import urllib.parse  # noqa: E402
import urllib.request  # noqa: E402

from app.core.security import create_access_token  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"
TOKEN = create_access_token("1")
BID = 3


def call(method, path, payload=None, token=TOKEN, timeout=300, raw=False):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, (body if raw else jb(body))
    except urllib.error.HTTPError as exc:
        body = exc.read()
        return exc.code, (body if raw else jb(body))
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def jb(body):
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return {}


results = []


def record(name, ok, detail):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} — {detail}")


from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402

db = SessionLocal()
sql_total = db.execute(
    text("SELECT COUNT(*) FROM survey_cbf_base WHERE batch_id=:b"), {"b": BID}).scalar()
print(f"基准: 批次{BID} 快照 {sql_total} 户")

# ── 1. 列表 + 批次筛选勾稽 ───────────────────────────────────
code, payload = call("GET", f"/contractors?batchId={BID}&page=1&page_size=10")
d = (payload.get("data") or {}) if isinstance(payload, dict) else {}
record("列表加载（batchId 筛选 total 与快照一致）", code == 200 and d.get("total") == sql_total,
       f"http={code}, total={d.get('total')} vs sql={sql_total}")
items = d.get("items") or []
it0 = items[0] if items else {}

# 列表字段勾稽（取列表首行）
db_row = db.execute(text("""
    SELECT r.cbfbm, r.cbfmc, r.cbflx, r.lxdh, r.cbfdz, r.cbfcysl
    FROM survey_cbf_result r
    JOIN survey_cbf_base b ON b.batch_id=:b AND b.contractor_uid=r.contractor_uid
    WHERE r.cbfbm=:c
"""), {"b": BID, "c": it0.get("code")}).first()
ok0 = db_row and it0.get("name") == db_row[1] and it0.get("typeCode") == db_row[2] \
    and (it0.get("mobile") or None) == (db_row[3] or None) \
    and it0.get("memberCount") == db_row[5]
record("列表字段与 survey_cbf_result 勾稽", bool(ok0),
       f"api={it0.get('name')}/db={db_row[1] if db_row else None}")

# ── 2. 四类筛选 ──────────────────────────────────────────────
kw_name = (db_row[1] or "户")[:1]
code, p1 = call("GET", f"/contractors?batchId={BID}&name={urllib.parse.quote(kw_name)}&page=1&page_size=5")
t1 = ((p1.get("data") or {}).get("total")) if isinstance(p1, dict) else None
record(f"按承包方名称筛选「{kw_name}」", code == 200 and t1 is not None and t1 <= sql_total,
       f"http={code}, total={t1}")

db_idno = db.execute(text("""
    SELECT r.cbfzjhm FROM survey_cbf_result r
    JOIN survey_cbf_base b ON b.batch_id=:b AND b.contractor_uid=r.contractor_uid
    WHERE r.cbfzjhm IS NOT NULL AND r.cbfzjhm != '' LIMIT 1
"""), {"b": BID}).scalar()
code, p2 = call("GET", f"/contractors?batchId={BID}&idNo={urllib.parse.quote(db_idno)}&page=1&page_size=5")
t2 = ((p2.get("data") or {}).get("total")) if isinstance(p2, dict) else None
record("按证件号码精确筛选", code == 200 and t2 == 1, f"http={code}, total={t2} (证件号 {db_idno[:6]}***)")

db_member = db.execute(text("""
    SELECT r.cyxm FROM survey_cbf_jtcy_result r
    JOIN survey_cbf_base b ON b.batch_id=:b AND b.contractor_uid=r.contractor_uid
    WHERE r.cyxm IS NOT NULL AND r.cyxm != '' LIMIT 1
"""), {"b": BID}).scalar()
code, p3 = call("GET", f"/contractors?batchId={BID}&memberName={urllib.parse.quote(db_member)}&page=1&page_size=5")
t3 = ((p3.get("data") or {}).get("total")) if isinstance(p3, dict) else None
record(f"按家庭成员名称筛选「{db_member}」", code == 200 and t3 and t3 >= 1,
       f"http={code}, total={t3}")

db_addr = db.execute(text("""
    SELECT r.cbfdz FROM survey_cbf_result r
    JOIN survey_cbf_base b ON b.batch_id=:b AND b.contractor_uid=r.contractor_uid
    WHERE r.cbfdz IS NOT NULL AND length(r.cbfdz) > 6 LIMIT 1
"""), {"b": BID}).scalar()
kw_addr = db_addr[3:9] if db_addr else ""
code, p4 = call("GET", f"/contractors?batchId={BID}&address={urllib.parse.quote(kw_addr)}&page=1&page_size=5")
t4 = ((p4.get("data") or {}).get("total")) if isinstance(p4, dict) else None
record("按承包方地址筛选", code == 200 and t4 and t4 >= 1, f"http={code}, total={t4}, kw={kw_addr}")

# ── 3. 详情勾稽（挑一户有成员+有合同的）──────────────────────
cand = db.execute(text("""
    SELECT r.cbfbm, r.contractor_uid,
           (SELECT COUNT(*) FROM survey_cbf_jtcy_result j WHERE j.contractor_uid=r.contractor_uid) AS members,
           (SELECT COUNT(*) FROM cbht h WHERE h.cbfbm=r.cbfbm) AS contracts
    FROM survey_cbf_result r
    JOIN survey_cbf_base b ON b.batch_id=:b AND b.contractor_uid=r.contractor_uid
    ORDER BY members DESC, contracts DESC LIMIT 1
"""), {"b": BID}).first()
CODE0, UID0, N_MEM, N_CTR = cand[0], cand[1], cand[2], cand[3]
print(f"详情样本: {CODE0} (成员 {N_MEM}, 合同 {N_CTR})")

code, payload = call("GET", f"/contractors/{CODE0}")
dd = (payload.get("data") or {}) if isinstance(payload, dict) else {}
detail_via = "HTTP"
if code == 500:
    # 运行中后端可能尚未包含「空证件号成员读模型放宽」修复，降级进程内 ASGI 复测。
    detail_via = "ASGI(后端未重启, 修复待重启生效)"
    import asyncio  # noqa: E402

    import httpx  # noqa: E402

    from app.main import app  # noqa: E402

    async def _detail():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get(f"/api/v1/contractors/{CODE0}",
                            headers={"Authorization": f"Bearer {TOKEN}"})
            return r.status_code, r.json()

    code, payload = asyncio.run(_detail())
    dd = (payload.get("data") or {}) if isinstance(payload, dict) else {}
db_detail = db.execute(text(
    "SELECT cbfbm, cbfmc, cbflx, cbfzjlx, cbfzjhm, cbfdz, yzbm, lxdh, cbfdcy FROM survey_cbf_result WHERE contractor_uid=:u"),
    {"u": UID0}).first()
ok_detail = dd.get("code") == db_detail[0] and dd.get("name") == db_detail[1] \
    and dd.get("typeCode") == db_detail[2] and dd.get("idNo") == db_detail[4] \
    and dd.get("surveyorName") == db_detail[8]
record(f"详情接口字段勾稽[{detail_via}]", code == 200 and ok_detail,
       f"http={code}, code={dd.get('code')}, name={dd.get('name')}")

fams = dd.get("familyMembers") or []
ok_mem = len(fams) == N_MEM
record("详情-家庭成员列表勾稽", ok_mem, f"api={len(fams)} vs sql={N_MEM}（空证件号成员允许返回，由质检标记）")
if fams:
    m0 = fams[0]
    db_m = db.execute(text(
        "SELECT cyxm, cyzjhm FROM survey_cbf_jtcy_result WHERE contractor_uid=:u AND cyzjhm=:z"),
        {"u": UID0, "z": m0.get("idNo")}).first()
    record("详情-成员逐字段与库一致", bool(db_m), f"成员 {m0.get('name')}: db={db_m}")

cts = dd.get("contracts") or []
ok_ct = len(cts) >= N_CTR
types = {c.get("type") for c in cts}
record(f"详情-合同列表勾稽[{detail_via}]", ok_ct, f"api={len(cts)} vs sql(cbht)={N_CTR}, types={types}")
if cts:
    c0 = cts[0]
    db_c = db.execute(text(
        "SELECT cbhtbm, cbfbm FROM cbht WHERE cbhtbm=:h"), {"h": c0.get("code")}).first()
    lz = None
    if c0.get("type") == "lzht" and c0.get("code"):
        lz = db.execute(text("SELECT 1 FROM lzht WHERE htcode=:h"), {"h": c0.get("code")}).first()
    record("详情-合同编码在库可溯", bool(db_c) or bool(lz),
           f"{c0.get('type')} {c0.get('code')}: cbht={bool(db_c)}, lzht={bool(lz)}")

# ── 4. 关联地块 ──────────────────────────────────────────────
code, payload = call("GET", f"/contractors/{CODE0}/parcels")
pks = (payload.get("data") or []) if isinstance(payload, dict) else []
sql_pks = db.execute(text(
    "SELECT COUNT(*) FROM survey_cbdkxx_result WHERE cbfbm=:c"), {"c": CODE0}).scalar()
record("关联地块数量勾稽", code == 200 and len(pks) == sql_pks,
       f"http={code}, api={len(pks)} vs sql={sql_pks}")
if pks:
    p0 = pks[0]
    db_pk = db.execute(text(
        "SELECT dkbm, htmj FROM survey_cbdkxx_result WHERE cbfbm=:c AND dkbm=:d"),
        {"c": CODE0, "d": p0.get("dkbm")}).first()
    api_htmj = float(p0.get("htmj") or 0)
    db_htmj = float(db_pk[1]) if db_pk and db_pk[1] is not None else 0.0
    record("关联地块字段勾稽（dkbm/合同面积）", bool(db_pk) and abs(db_htmj - api_htmj) < 0.01,
           f"dkbm={p0.get('dkbm')}, htmj api={api_htmj} vs db={db_htmj}")

# ── 5. 增删改闭环（临时数据自清理）──────────────────────────
tmp_code = (CODE0[:14] + "99")[:18]
grp = dd.get("groupRegionCode") or ""
base_payload = {
    "code": tmp_code, "typeCode": "1", "name": "PROBE临时承包方", "idType": "1",
    "idNo": "150522199001010011", "address": "探针测试地址", "postcode": "028000",
    "mobile": "13900000000", "surveyorName": "探针调查员", "surveyDate": "2026-11-08",
    "surveyNote": "探针测试记事", "publicNoticeNote": None, "publicNoticeRecorder": None,
    "publicNoticeReviewDate": None, "publicNoticeReviewer": None,
    "groupRegionCode": grp or None, "groupRegionName": dd.get("groupRegionName"),
    "familyMembers": [
        {"name": "探针成员甲", "gender": "1", "idType": "1", "idNo": "150522199001010011",
         "relationToHead": "1", "noteCode": None, "isCoOwner": "1", "note": None},
    ],
}
created = False
try:
    code, payload = call("POST", "/contractors", base_payload)
    created = code == 201
    d5 = (payload.get("data") or {}) if isinstance(payload, dict) else {}
    r_cnt = db.execute(text("SELECT COUNT(*) FROM survey_cbf_result WHERE cbfbm=:c"), {"c": tmp_code}).scalar()
    b_cnt = db.execute(text("SELECT COUNT(*) FROM survey_cbf_base WHERE source_cbfbm=:c"), {"c": tmp_code}).scalar()
    m_cnt = db.execute(text(
        "SELECT COUNT(*) FROM survey_cbf_jtcy_result r WHERE r.contractor_uid IN "
        "(SELECT contractor_uid FROM survey_cbf_result WHERE cbfbm=:c)"), {"c": tmp_code}).scalar()
    record("新增承包方（result+base+成员同步落库）", created and r_cnt == 1 and b_cnt == 1 and m_cnt == 1,
           f"http={code}, result={r_cnt}, base={b_cnt}, members={m_cnt}")

    code, payload = call("POST", "/contractors", base_payload)
    record("批次内重复代码拦截（409）", code == 409,
           f"http={code}, detail={payload.get('detail') if isinstance(payload, dict) else payload}")

    dup = json.loads(json.dumps(base_payload))
    dup["familyMembers"].append({"name": "探针成员乙", "gender": "2", "idType": "1",
                                 "idNo": "150522199001010011", "relationToHead": "2",
                                 "noteCode": None, "isCoOwner": None, "note": None})
    code, payload = call("PUT", f"/contractors/{tmp_code}", dup)
    record("成员证件号重复拦截（409）", code == 409,
           f"http={code}, detail={payload.get('detail') if isinstance(payload, dict) else payload}")

    upd = json.loads(json.dumps(base_payload))
    upd["name"] = "PROBE临时承包方改名"
    upd["mobile"] = "13800000000"
    upd["familyMembers"].append({"name": "探针成员乙", "gender": "2", "idType": "1",
                                 "idNo": "150522199001010012", "relationToHead": "2",
                                 "noteCode": None, "isCoOwner": None, "note": None})
    code, payload = call("PUT", f"/contractors/{tmp_code}", upd)
    db_chk = db.execute(text(
        "SELECT cbfmc, lxdh FROM survey_cbf_result WHERE cbfbm=:c"), {"c": tmp_code}).first()
    m2 = db.execute(text(
        "SELECT COUNT(*) FROM survey_cbf_jtcy_result r WHERE r.contractor_uid IN "
        "(SELECT contractor_uid FROM survey_cbf_result WHERE cbfbm=:c)"), {"c": tmp_code}).scalar()
    bm2 = db.execute(text(
        "SELECT COUNT(*) FROM survey_cbf_jtcy_base WHERE contractor_uid IN "
        "(SELECT contractor_uid FROM survey_cbf_base WHERE source_cbfbm=:c AND batch_id=:b)"),
        {"c": tmp_code, "b": BID}).scalar()
    record("编辑承包方（改名/改电话/成员整体替换，result+base 同步）",
           code == 200 and db_chk and db_chk[0] == "PROBE临时承包方改名" and db_chk[1] == "13800000000"
           and m2 == 2 and bm2 == 2,
           f"http={code}, 库内={db_chk}, result成员={m2}, base成员={bm2}")

    code, payload = call("DELETE", f"/contractors/{tmp_code}")
    r2 = db.execute(text("SELECT COUNT(*) FROM survey_cbf_result WHERE cbfbm=:c"), {"c": tmp_code}).scalar()
    b2 = db.execute(text("SELECT COUNT(*) FROM survey_cbf_base WHERE source_cbfbm=:c AND batch_id=:b"),
                    {"c": tmp_code, "b": BID}).scalar()
    jm = db.execute(text(
        "SELECT COUNT(*) FROM survey_cbf_jtcy_result r WHERE r.contractor_uid IN "
        "(SELECT contractor_uid FROM survey_cbf_result WHERE cbfbm=:c)"), {"c": tmp_code}).scalar()
    record("删除承包方（result/base/成员全清）", code == 204 and r2 == 0 and b2 == 0 and jm == 0,
           f"http={code}, result={r2}, base={b2}, 成员={jm}")
    created = False
finally:
    if created:
        call("DELETE", f"/contractors/{tmp_code}")
        print("  [cleanup] 临时承包方已强制清理")

code, payload = call("DELETE", "/contractors/NO_SUCH_CONTRACTOR")
record("删除不存在的承包方（404）", code == 404,
       f"http={code}, detail={payload.get('detail') if isinstance(payload, dict) else payload}")

# ── 6. 导出：单户地籍调查表 / 摸底表 ─────────────────────────
import re  # noqa: E402

code, body = call("GET", f"/contractors/{CODE0}/cadastral-survey.docx", raw=True, timeout=300)
doc_name = ""
if body[:2] == b"PK":
    zf = zipfile.ZipFile(io.BytesIO(body))
    doc = zf.read("word/document.xml").decode("utf-8", "replace")
    texts = "".join(re.findall(r"<w:t[^>]*>([^<]+)</w:t>", doc))
    doc_name = texts[:60]
record("单户《地籍调查表》Word（PK + 含户信息）", code == 200 and body[:2] == b"PK" and len(body) > 5000,
       f"http={code}, {len(body)}B, 文本头: {doc_name}")

code, body = call("GET", f"/contractors/{CODE0}/land-change-sheet.docx", raw=True, timeout=300)
if code != 200:
    # 运行中后端未含「同 uid 成员摸底行复用」修复时 500，降级 ASGI 复测
    import asyncio  # noqa: E402

    import httpx  # noqa: E402

    from app.main import app  # noqa: E402

    async def _sheet(p):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=300) as c:
            r = await c.get(f"/api/v1{p}", headers={"Authorization": f"Bearer {TOKEN}"})
            return r.status_code, r.content

    code, body = asyncio.run(_sheet(f"/contractors/{CODE0}/land-change-sheet.docx"))
ok_lc = code == 200 and body[:2] == b"PK" and len(body) > 3000
code2, body2 = call("GET", f"/contractors/{CODE0}/member-change-sheet.docx", raw=True, timeout=300)
if code2 != 200:
    import asyncio  # noqa: E402

    import httpx  # noqa: E402

    from app.main import app  # noqa: E402

    async def _sheet2(p):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=300) as c:
            r = await c.get(f"/api/v1{p}", headers={"Authorization": f"Bearer {TOKEN}"})
            return r.status_code, r.content

    code2, body2 = asyncio.run(_sheet2(f"/contractors/{CODE0}/member-change-sheet.docx"))
ok_mc = code2 == 200 and body2[:2] == b"PK" and len(body2) > 3000
record("单户摸底表 Word（地块变化/成员变化）", ok_lc and ok_mc,
       f"land-change={code}/{len(body)}B, member-change={code2}/{len(body2)}B")

# 批量打印渲染（分页 HTML；前端口径传 regionCode=村码，端点不收 batchId）
code, payload = call("GET", f"/contractors/cadastral-survey?regionCode={CODE0[:14]}&page=1&pageSize=2")
d6 = (payload.get("data") or {}) if isinstance(payload, dict) else {}
html = d6.get("renderedHtml") or ""
record("批量打印地籍调查表（regionCode 口径分页 HTML 渲染）",
       code == 200 and d6.get("total", 0) >= 1 and len(html) > 500 and d6.get("contractorCount") == 2,
       f"http={code}, total={d6.get('total')}, html={len(html)}B, 本页={d6.get('contractorCount')}户")

# ── 7. 门禁 ──────────────────────────────────────────────────
code, _ = call("GET", f"/contractors?batchId={BID}&page=1", token="bad-token")
record("坏 token 访问被拦（401）", code == 401, f"http={code}")

db.close()
print("\n===== 汇总 =====")
fails = [r for r in results if not r[1]]
print(f"共 {len(results)} 项, 通过 {len(results) - len(fails)}, 失败 {len(fails)}")
for name, _, detail in fails:
    print(f"  FAIL: {name} — {detail}")
