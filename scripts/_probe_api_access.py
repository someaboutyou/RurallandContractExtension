# -*- coding: utf-8 -*-
"""探测：能否用默认 secret 铸管理员令牌，打通运行中的 8000 后端。

只读探测（只打 GET）。成功则后续所有测试走 HTTP，完全不碰数据库。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("SECRET_KEY", "probe-only")
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from app.core.security import create_access_token  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"


def get(path: str, token: str, timeout: int = 20):
    req = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def main() -> None:
    token = create_access_token("1")
    print("JWT 前缀:", token[:32], "...")
    code, body = get("/surveys/batches?page=1&page_size=3", token)
    print(f"GET /surveys/batches -> {code}")
    print("  ", body[:600])

    if code == 200:
        try:
            payload = json.loads(body)
            items = (payload.get("data") or {}).get("items") or []
            print(f"  批次条数: {len(items)}")
            for item in items:
                print("   ", {k: item.get(k) for k in ("id", "batchNo", "status", "regionCode", "regionName") if k in item})
        except Exception as exc:  # noqa: BLE001
            print("  解析失败:", exc)


if __name__ == "__main__":
    main()
