"""冒烟：承包方列表 / 地籍调查表打印链路（改完 contractor 仓储后确认无连带影响）。

跑法：runtime/windows/python/python.exe scripts/_smoke_contractors.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "runtime" / ".state" / "_smoke_contractors.txt"
REAL_CODE = "321324100001030142"


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

from app.core.security import create_access_token  # noqa: E402
from app.main import app  # noqa: E402

BASE = "/api/v1"
HEADERS = {"Authorization": f"Bearer {create_access_token('1')}"}
OUT: list[str] = []

client = TestClient(app)

resp = client.get(f"{BASE}/contractors", params={"page": 1, "pageSize": 3}, headers=HEADERS)
OUT.append(f"[{'PASS' if resp.status_code == 200 else 'FAIL'}] GET /contractors -> {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()["data"]
    OUT.append(f"    total={data.get('total')} 本页={len(data.get('items') or [])} 首条={ (data.get('items') or [{}])[0].get('name')}")

resp = client.get(f"{BASE}/contractors", params={"page": 1, "pageSize": 3, "keyword": REAL_CODE}, headers=HEADERS)
OUT.append(f"[{'PASS' if resp.status_code == 200 else 'FAIL'}] GET /contractors?keyword=<户码> -> {resp.status_code}")

# 批量打印（只取 1 户，避免整村渲染）
resp = client.get(
    f"{BASE}/contractors/cadastral-survey",
    params={"page": 1, "pageSize": 1, "keyword": REAL_CODE},
    headers=HEADERS,
)
ok = resp.status_code == 200
html = resp.json()["data"]["renderedHtml"] if ok else ""
OUT.append(f"[{'PASS' if ok and len(html) > 1000 else 'FAIL'}] GET /contractors/cadastral-survey（1 户整套表格） -> {resp.status_code} html={len(html)} 字符")

# 单户 Word 下载
resp = client.get(f"{BASE}/contractors/{REAL_CODE}/cadastral-survey.docx", headers=HEADERS)
ok = resp.status_code == 200 and resp.content[:2] == b"PK"
OUT.append(f"[{'PASS' if ok else 'FAIL'}] GET /contractors/{REAL_CODE}/cadastral-survey.docx -> {resp.status_code} {len(resp.content)} bytes zip={resp.content[:2] == b'PK'}")

RESULT_PATH.write_text("\n".join(OUT), encoding="utf-8")
print("\n".join(OUT))
