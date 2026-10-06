# -*- coding: utf-8 -*-
"""给「撤回互换」端到端取证准备上下文（**只读，不写库**）。

输出 runtime/.state/_e2e_swap_rollback_ctx.json：
  · 管理员 token（离线铸，sub=1）
  · 批次 41「二组调查批次」里**已保存过互换、且还能编辑**的那一户
    （当前是对方户 321324100001020014 —— 它名下有 swap_parcels 换入的地块，
     地块行上会出现「撤回互换」按钮；013 已 confirmed，弹窗只读，不适合点击）

跑法：runtime/windows/python/python.exe scripts/_e2e_swap_rollback_ctx.py
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
OUT_PATH = ROOT / "runtime" / ".state" / "_e2e_swap_rollback_ctx.json"


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


def main() -> int:
    token = create_access_token("1")
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        batches = client.get("/api/v1/surveys/batches", headers=headers).json()["data"]
        items = batches.get("items") or batches
        batch = next((b for b in items if b["id"] == 41), None)
        if batch is None:
            print("批次 41 不存在")
            return 1

        tasks = client.get(
            "/api/v1/surveys/batches/41/tasks",
            params={"regionCode": "32132410000102", "pageSize": 100},
            headers=headers,
        ).json()["data"]["items"]
        changes = client.get(
            "/api/v1/surveys/batches/41/changes",
            params={"contractorUid": "e4c63a91-3616-54c8-8146-edd9b0f96b34", "pageSize": 50},
            headers=headers,
        ).json()["data"]["items"]
        swap = [c for c in changes if c["changeType"] == "swap_parcels" and c["changeStatus"] != "rolled_back"]
        peer = next((t for t in tasks if t["cbfbm"] == "321324100001020014"), None)

        report = {
            "userId": 1,
            "userName": "超级管理员",
            "token": token,
            "batchId": 41,
            "batchName": batch["batchName"],
            "batchStatus": batch["status"],
            "target": peer,
            "swapChange": swap[0] if swap else None,
            "taskCount": len(tasks),
        }
        OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "token"}, ensure_ascii=False, indent=2))
        print("写入", OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
