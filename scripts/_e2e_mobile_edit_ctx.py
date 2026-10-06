"""给「移动端调查录入编辑」前端验收准备上下文（**只读，不写库**）。

挑一户：
  1. 用户 1（管理员）能写（task.canWrite is not False）；
  2. 结果未确认、未终结（编辑闸门只锁 confirmed）；
  3. 有家庭成员数据（顺带验成员卡渲染）。

输出：runtime/.state/_e2e_mobile_edit_ctx.json
跑法：runtime/windows/python/python.exe scripts/_e2e_mobile_edit_ctx.py
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
OUT_PATH = ROOT / "runtime" / ".state" / "_e2e_mobile_edit_ctx.json"


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
    report: dict = {"token": token, "picked": None}
    with TestClient(app) as client:
        batches = client.get(
            "/api/v1/surveys/batches", headers=headers, params={"page": 1, "page_size": 20}
        ).json()["data"]["items"]

        picked = None
        for batch in batches:
            tasks = client.get(
                f"/api/v1/surveys/batches/{batch['id']}/tasks",
                headers=headers,
                params={"page": 1, "page_size": 50},
            ).json()["data"]["items"]
            for task in tasks:
                if task.get("canWrite") is False:
                    continue
                if task.get("taskStatus") in {"confirmed", "skipped", "deregistered"}:
                    continue
                detail = client.get(
                    f"/api/v1/surveys/batches/{batch['id']}/results/{task['contractorUid']}",
                    headers=headers,
                )
                if detail.status_code != 200:
                    continue
                row = detail.json()["data"]
                if row.get("isTerminal") or row.get("surveyStatus") == "confirmed":
                    continue
                picked = {
                    "batchId": batch["id"],
                    "batchName": batch.get("batchName") or batch.get("batchNo"),
                    "cbfbm": row.get("code"),
                    "cbfmc": row.get("name"),
                    "address": row.get("address"),
                    "contractorUid": task["contractorUid"],
                    "memberCount": len(row.get("familyMembers") or []),
                    "surveyStatus": row.get("surveyStatus"),
                    "canWrite": task.get("canWrite"),
                }
                break
            if picked:
                break

        report["picked"] = picked

    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if picked else 1


if __name__ == "__main__":
    raise SystemExit(main())
