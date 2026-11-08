# -*- coding: utf-8 -*-
"""探针：调查批次管理页「新增发包方 → 编辑 → 删除」闭环（真实 HTTP，临时数据自清理）。"""
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
os.environ.setdefault("SECRET_KEY", "probe-only")
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from app.core.security import create_access_token  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"
TOKEN = create_access_token("1")
BID = 3  # 三益庄村批次（active）


def call(method, path, payload=None, token=TOKEN, timeout=60):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}".encode()


def jb(body):
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return {}


results = []


def record(name, ok, detail):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} — {detail}")


def cleanup(uid=None):
    if uid:
        call("DELETE", f"/surveys/batches/{BID}/issuers/{uid}")


def main():
    payload = {
        "code": "15052610320299",
        "name": "PROBE临时发包方",
        "responsibleName": "探针负责人",
        "responsibleIdNo": "150526199001010011",
        "phone": "13800000000",
        "address": "探针测试地址（脚本自动清理）",
    }
    # 1. 新增
    code, body = call("POST", f"/surveys/batches/{BID}/issuers", payload)
    created = jb(body).get("data") or {}
    uid = created.get("issuerUid")
    ok = code == 201 and bool(uid)
    record("新增发包方（POST issuers）", ok, f"HTTP {code}, issuerUid={uid}")
    if not ok:
        print(body[:300])
        return
    try:
        # 2. 编辑（Update schema 必填字段与前端 IssuerSurveyDialog 提交口径一致）
        payload.update({
            "issuerUid": uid,
            "responsibleIdType": "1",
            "postcode": "000000",
            "name": "PROBE临时发包方改名",
            "phone": "13900000000",
        })
        code, body = call("PUT", f"/surveys/batches/{BID}/issuers/{uid}", payload)
        updated = jb(body).get("data") or {}
        record("编辑发包方（PUT issuers/{uid}）", code == 200 and updated.get("name") == payload["name"], f"HTTP {code}, name={updated.get('name')!r}")
        # 3. 清单可见
        code, body = call("GET", f"/surveys/batches/{BID}/issuers?page=1&page_size=200&keyword=PROBE")
        items = ((jb(body).get("data") or {}).get("items")) or []
        record("发包方清单可见（keyword 命中）", code == 200 and len(items) == 1, f"HTTP {code}, 命中 {len(items)} 行")
        # 4. 删除
        code, body = call("DELETE", f"/surveys/batches/{BID}/issuers/{uid}")
        record("删除发包方（DELETE issuers/{uid}）", code in (200, 204), f"HTTP {code}")
    finally:
        cleanup(uid)
    # 5. 残留断言
    code, body = call("GET", f"/surveys/batches/{BID}/issuers?page=1&page_size=200&keyword=PROBE")
    items = ((jb(body).get("data") or {}).get("items")) or []
    record("清理后无残留", len(items) == 0, f"残留 {len(items)} 行")

    fails = [r for r in results if not r[1]]
    print(f"\n共 {len(results)} 项，通过 {len(results) - len(fails)}，失败 {len(fails)}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
