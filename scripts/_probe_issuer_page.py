# -*- coding: utf-8 -*-
"""探针：建库中心-发包方管理页（IssuerView /issuers）综合功能与数据勾稽。

覆盖：列表/关键字/批次筛选、字段勾稽、关联承包方/地块、增删改闭环（自清理）、
删除闸门、合并负向、5 类导出文件真实内容、异步导出任务、鉴权门禁。
可重复运行：临时发包方 finally 清理。
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


def call(method, path, payload=None, token=TOKEN, timeout=120, raw=False):
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


# ── DB 独立直查（勾稽基准）────────────────────────────────────
from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402

db = SessionLocal()
sql_total = db.execute(text("SELECT COUNT(*) FROM fbf")).scalar()
first = db.execute(
    text("SELECT fbfbm, fbfmc, fbffzrxm, lxdh, fbfdz, yzbm, fbfdcy FROM fbf ORDER BY fbfbm LIMIT 1")
).first()
CODE0 = first[0]
print(f"基准: fbf 全表 {sql_total} 行, 首行 {CODE0}")

# ── 1. 列表 + 分页 + 勾稽 ────────────────────────────────────
code, payload = call("GET", "/issuers?page=1&page_size=10")
d = (payload.get("data") or {}) if isinstance(payload, dict) else {}
items = d.get("items") or []
record("发包方列表加载（分页 total 与库一致）", code == 200 and d.get("total") == sql_total,
       f"http={code}, total={d.get('total')} vs sql={sql_total}")

it0 = items[0] if items else {}
db_row = db.execute(
    text("SELECT fbfbm, fbfmc, fbffzrxm, lxdh, fbfdz FROM fbf WHERE fbfbm=:c"), {"c": it0.get("code")}
).first()
ok_fields = db_row and it0.get("name") == db_row[1] and it0.get("ownerName") == db_row[2] \
    and (it0.get("mobile") or None) == (db_row[3] or None) and it0.get("address") == db_row[4]
record("列表字段与 fbf 表逐项勾稽", bool(ok_fields),
       f"api name={it0.get('name')} / db {db_row[1] if db_row else None}")

# ── 2. 关键字搜索 ────────────────────────────────────────────
kw = (first[1] or "")[:2]
code, payload = call("GET", f"/issuers?page=1&page_size=10&keyword={urllib.parse.quote(kw)}")
d = (payload.get("data") or {}) if isinstance(payload, dict) else {}
hit = all(kw in (i.get("name") or "") + (i.get("code") or "") for i in (d.get("items") or []))
record(f"关键字搜索「{kw}」结果命中", code == 200 and d.get("total", 0) >= 1 and hit,
       f"http={code}, total={d.get('total')}, 全部命中={hit}")

# ── 3. 批次筛选（batchId=3 vs survey_fbf_base 快照）──────────
code, payload = call("GET", f"/issuers?page=1&page_size=50&batchId={BID}")
d = (payload.get("data") or {}) if isinstance(payload, dict) else {}
api_codes = sorted(i["code"] for i in (d.get("items") or []))
snap = sorted(r[0] for r in db.execute(
    text("SELECT fbfbm FROM survey_fbf_base WHERE batch_id=:b"), {"b": BID}).all())
record(f"批次筛选 batchId={BID} 与快照勾稽", code == 200 and api_codes == snap,
       f"api={api_codes} vs 快照={snap}")

# ── 4. 关联承包方 / 地块 ─────────────────────────────────────
code, payload = call("GET", f"/issuers/{CODE0}/contractors")
ctrs = (payload.get("data") or []) if isinstance(payload, dict) else []
# 服务口径：cbdkxx_result(未 removed) 的 cbfbm 去重 ∩ cbf_result
ctr_codes = [r[0] for r in db.execute(
    text("SELECT DISTINCT cbfbm FROM survey_cbdkxx_result WHERE fbfbm=:c AND cbfbm IS NOT NULL AND result_status != 'removed'"),
    {"c": CODE0}).all()]
sql_ctrs = 0
if ctr_codes:
    sql_ctrs = db.execute(text(
        "SELECT COUNT(DISTINCT cbfbm) FROM survey_cbf_result WHERE cbfbm = ANY(:codes)"),
        {"codes": ctr_codes}).scalar()
record("关联承包方清单数量勾稽", code == 200 and len(ctrs) == sql_ctrs,
       f"http={code}, api={len(ctrs)} vs sql={sql_ctrs}")

code, payload = call("GET", f"/issuers/{CODE0}/parcels")
pk = (payload.get("data") or []) if isinstance(payload, dict) else []
sql_parcels = db.execute(
    text("SELECT COUNT(*) FROM survey_cbdkxx_result WHERE fbfbm=:c"), {"c": CODE0}).scalar()
record("关联地块清单加载（数量合理）", code == 200 and isinstance(pk, list) and len(pk) <= max(sql_parcels, 1),
       f"http={code}, api={len(pk)} 行, 库 cbdkxx={sql_parcels}")

# ── 5. 增删改闭环（临时数据自清理）──────────────────────────
tmp_code = CODE0[:12] + "90"  # 同前缀保证数据权限范围内且不撞码
base_payload = {
    "code": tmp_code, "name": "PROBE临时发包方", "ownerName": "探针测试",
    "ownerIdType": "1", "ownerIdNo": "150522199001010011", "mobile": "13900000000",
    "address": "探针测试地址", "postcode": "028000", "surveyorName": "探针调查员",
}
created = False
try:
    code, payload = call("POST", "/issuers", base_payload)
    created = code == 201
    record("新增发包方（201 + 字段回读）", created and
           (payload.get("data") or {}).get("name") == "PROBE临时发包方",
           f"http={code}, resp={payload.get('data', {}).get('name') if isinstance(payload, dict) else payload}")

    code, payload = call("POST", "/issuers", base_payload)
    record("重复代码创建被拦（409）", code == 409,
           f"http={code}, detail={payload.get('detail') if isinstance(payload, dict) else payload}")

    upd = dict(base_payload); upd["name"] = "PROBE临时发包方改名"; upd["mobile"] = "13800000000"
    code, payload = call("PUT", f"/issuers/{tmp_code}", upd)
    ok_upd = code == 200 and (payload.get("data") or {}).get("name") == "PROBE临时发包方改名"
    db_chk = db.execute(text("SELECT fbfmc, lxdh FROM fbf WHERE fbfbm=:c"), {"c": tmp_code}).first()
    record("编辑发包方（接口+落库一致）", ok_upd and db_chk and db_chk[0] == "PROBE临时发包方改名"
           and db_chk[1] == "13800000000",
           f"http={code}, 库内={db_chk}")

    code, payload = call("DELETE", f"/issuers/{tmp_code}")
    gone = db.execute(text("SELECT COUNT(*) FROM fbf WHERE fbfbm=:c"), {"c": tmp_code}).scalar()
    record("删除发包方（204 + 库内移除）", code == 204 and gone == 0, f"http={code}, 库内残留={gone}")
    created = False
finally:
    if created:
        call("DELETE", f"/issuers/{tmp_code}")
        print("  [cleanup] 临时发包方已强制清理")

# ── 6. 删除闸门 / 合并负向 ───────────────────────────────────
code, payload = call("DELETE", f"/issuers/{CODE0}")
record("有承包方的发包方删除被拦（400）", code == 400,
       f"http={code}, detail={payload.get('detail') if isinstance(payload, dict) else payload}")

code, payload = call("POST", "/issuers/merge", {"keepCode": CODE0, "mergeCodes": ["NO_SUCH_1"]})
record("合并不存在的发包方被拦（404/400）", code in (400, 404),
       f"http={code}, detail={payload.get('detail') if isinstance(payload, dict) else payload}")

# ── 7. 导出文件真实内容 ──────────────────────────────────────
code, body = call("GET", f"/issuers/{CODE0}/survey-docx", raw=True, timeout=300)
magic_ok = body[:2] in (b"PK", b"\xd0\xcf")
record("单户调查表导出（文件流有效）", code == 200 and magic_ok and len(body) > 1000,
       f"http={code}, {len(body)}B, magic={body[:4]!r}")

code, body = call("GET", "/issuers/xls?page=1&page_size=5", raw=True, timeout=300)
record("发包方清单 xls 导出（OLE2/xlsx 有效）", code == 200 and body[:4] in (b"\xd0\xcf\x11\xe0", b"PK"),
       f"http={code}, {len(body)}B, magic={body[:4]!r}")

code, body = call("POST", "/issuers/export-docx", {"codes": [CODE0]}, raw=True, timeout=300)
record("export-docx 直接导出（docx 有效）", code == 200 and body[:2] == b"PK",
       f"http={code}, {len(body)}B, magic={body[:2]!r}")

# ── 8. 异步导出任务（survey zip / publicity xls）────────────
for kind, expect in (("survey", b"PK"), ("publicity", b"\xd0\xcf\x11\xe0")):
    code, payload = call("POST", "/issuers/export-jobs", {"kind": kind, "codes": [CODE0]})
    tid = (payload.get("data") or {}).get("taskId") if isinstance(payload, dict) else None
    ok_create = code == 200 and bool(tid)
    done, dl_ok, tries = False, False, 0
    if ok_create:
        while tries < 60:
            time.sleep(2); tries += 1
            c2, p2 = call("GET", f"/issuers/export-jobs/{tid}")
            st = (p2.get("data") or {}).get("status") if isinstance(p2, dict) else None
            if st in ("done", "completed", "success"):
                done = True; break
            if st in ("failed", "error"):
                break
        c3, body3 = call("GET", f"/issuers/export-jobs/{tid}/download", raw=True, timeout=300)
        dl_ok = c3 == 200 and len(body3) > 1000 and (
            (kind == "survey" and body3[:2] == b"PK") or (kind == "publicity" and body3[:4] == expect))
        if kind == "survey":
            if body3[:2] == b"PK":
                zf = zipfile.ZipFile(io.BytesIO(body3))
                names = zf.namelist()
                dl_ok = dl_ok and len(names) >= 1
                print(f"    survey zip 内含 {len(names)} 个文件: {names[:3]}")
    record(f"异步导出任务 kind={kind}（创建→轮询→下载有效）", ok_create and done and dl_ok,
           f"create={code}, tid={tid}, done={done}, download_valid={dl_ok}")

# ── 9. 门禁负向 ──────────────────────────────────────────────
code, _ = call("GET", "/issuers?page=1", token="bad-token")
record("坏 token 访问被拦（401）", code == 401, f"http={code}")
code, _ = call("GET", "/issuers?page=1", token="")
record("未登录访问被拦（401）", code == 401, f"http={code}")

db.close()
print("\n===== 汇总 =====")
fails = [r for r in results if not r[1]]
print(f"共 {len(results)} 项, 通过 {len(results) - len(fails)}, 失败 {len(fails)}")
for name, _, detail in fails:
    print(f"  FAIL: {name} — {detail}")
