"""接口层验收：用 in-process ASGI 客户端打真实路由（不碰正在跑的 8000 服务，也不用重启它）。

跑法（必须用带依赖的那个解释器）：
  runtime/windows/python/python.exe scripts/_verify_api.py

覆盖：
- POST /surveys/batches 不带 assigneeIds / 传空 → 400（管理员必填；**按角色**的校验在服务层，
  入口 schema 不再写 min_length —— 非管理员要能"不传也建得出来"。
  角色分流的完整矩阵见 `scripts/_verify_batch_create_role.py`）
- POST /surveys/batches 带 assigneeIds → 200，且库内该批次无未分配户
- GET /surveys/batches?mineOnly=1 在真实数据上按「我创建 / 有户分给我」过滤
  （组级测试员创建了批次 41，镇级业务员名下没有户）
- GET /surveys/batches/<id>/tasks 的「调查员」列数据源
新建的验收批次在结束时删除，可重复运行。
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
RESULT_PATH = ROOT / "runtime" / ".state" / "_verify_api.txt"


def load_env() -> dict[str, str]:
    data: dict[str, str] = {}
    # 配置文件带 BOM，必须用 utf-8-sig
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
from app.db.session import SessionLocal, engine, set_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.survey_service import survey_service  # noqa: E402

BASE = "/api/v1"
OUT: list[str] = []
TEMP_BATCH_IDS: list[int] = []


def token(user_id) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


def log(*parts) -> None:
    OUT.append(" ".join(str(part) for part in parts))


def show(title: str, resp, limit: int = 1200) -> None:
    log(f"--- {title} -> {resp.status_code}")
    if resp.headers.get("content-type", "").startswith("application/json"):
        payload = json.dumps(resp.json(), ensure_ascii=False, default=str)
    else:
        payload = resp.text
    log("   ", payload[:limit])


# 不进入 with，所以不触发 lifespan（不会重跑 bootstrap / seed）。
client = TestClient(app)
try:
    log("========== A. 新建批次：管理员必须指派调查员（服务层按角色判） ==========")
    with engine.connect() as conn:
        candidate = conn.execute(
            text(
                """
                SELECT r.group_region_code AS code, r.group_region_name AS name
                FROM survey_cbf_result r
                WHERE r.group_region_code IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM survey_batches b
                    WHERE b.status = 'active' AND b.region_code LIKE r.group_region_code || '%'
                  )
                GROUP BY r.group_region_code, r.group_region_name
                ORDER BY count(*) DESC LIMIT 1
                """
            )
        ).first()
    log(f"候选区域 = {candidate}")
    if candidate is None:
        raise RuntimeError("找不到可用于验收的空闲区域")
    code, name = candidate

    show(
        "POST /surveys/batches（管理员 #1，不带 assigneeIds，应 400）",
        client.post(f"{BASE}/surveys/batches", json={"batchName": "__接口验收批次__", "regionCode": code, "regionName": name}, headers=token(1)),
    )
    show(
        "POST /surveys/batches（管理员 #1，assigneeIds=[]，应 400）",
        client.post(
            f"{BASE}/surveys/batches",
            json={"batchName": "__接口验收批次__", "regionCode": code, "regionName": name, "assigneeIds": []},
            headers=token(1),
        ),
    )

    db = SessionLocal()
    admin = db.get(User, 1)
    set_current_user(db, admin)
    covering = [(item["id"], item["realName"]) for item in survey_service.list_assignees(db, admin, region_code=code) if item["coversRegion"]]
    db.close()
    log("覆盖该区域的调查员 =", covering)
    assignee_ids = [item[0] for item in covering]

    resp = client.post(
        f"{BASE}/surveys/batches",
        json={"batchName": "__接口验收批次__", "regionCode": code, "regionName": name, "assigneeIds": assignee_ids},
        headers=token(1),
    )
    show("POST /surveys/batches（带 assigneeIds）", resp, limit=2500)
    temp_id = resp.json()["data"]["id"] if resp.status_code == 200 else None
    if temp_id:
        TEMP_BATCH_IDS.append(temp_id)
        with engine.connect() as conn:
            unassigned = conn.execute(
                text("SELECT count(*) FROM survey_cbf_base WHERE batch_id = :bid AND assigned_to IS NULL"),
                {"bid": temp_id},
            ).scalar()
        log(f"   新建批次 #{temp_id} 的未分配户数 = {unassigned}（必须为 0）")

    log("========== B. 调查员视角：只看与我相关的批次 ==========")
    with engine.connect() as conn:
        owners = conn.execute(
            text(
                """
                SELECT b.id, b.batch_name, b.created_by,
                       (SELECT count(*) FROM survey_cbf_base x WHERE x.batch_id = b.id AND x.assigned_to IS NOT NULL) AS assigned
                FROM survey_batches b WHERE b.survey_type = 'household_survey' ORDER BY b.id
                """
            )
        ).all()
    log("   现实数据里的批次 =", [tuple(row) for row in owners])

    for user_id in (7, 5):
        resp = client.get(f"{BASE}/surveys/batches", params={"page": 1, "page_size": 20, "mineOnly": 1}, headers=token(user_id))
        show(f"GET /surveys/batches?mineOnly=1（user#{user_id}）", resp, limit=2000)
    resp = client.get(f"{BASE}/surveys/batches", params={"page": 1, "page_size": 20}, headers=token(7))
    show("GET /surveys/batches（user#7 默认口径，含区域内的全部批次）", resp, limit=2000)

    if temp_id:
        log("========== C. 调查列表的「调查员」列 ==========")
        show(
            "GET /surveys/batches/<id>/tasks",
            client.get(f"{BASE}/surveys/batches/{temp_id}/tasks", params={"page": 1, "page_size": 3}, headers=token(1)),
            limit=2500,
        )
        show(
            "GET /surveys/batches?assigneeId=<该批次调查员>（按调查员筛批次）",
            client.get(
                f"{BASE}/surveys/batches",
                params={"page": 1, "page_size": 5, "assigneeId": assignee_ids[0]},
                headers=token(1),
            ),
        )
finally:
    try:
        with engine.connect() as conn:
            for row in conn.execute(
                text("SELECT id FROM survey_batches WHERE batch_name = '__接口验收批次__'")
            ).all():
                if row[0] not in TEMP_BATCH_IDS:
                    TEMP_BATCH_IDS.append(row[0])
        with engine.begin() as conn:
            for _bid in TEMP_BATCH_IDS:
                for _table in (
                    "survey_cbf_jtcy_base",
                    "survey_cbdkxx_base",
                    "survey_dk_base",
                    "survey_fbf_base",
                    "survey_change_diffs",
                    "survey_change_records",
                    "survey_cbf_base",
                ):
                    conn.execute(text(f"DELETE FROM {_table} WHERE batch_id = :bid"), {"bid": _bid})
                conn.execute(text("DELETE FROM survey_batches WHERE id = :bid"), {"bid": _bid})
        with engine.connect() as conn:
            OUT.append("")
            OUT.append(f"cleanup done, removed batches {TEMP_BATCH_IDS}")
            OUT.append(
                "残留验收批次 = "
                + str(conn.execute(text("SELECT count(*) FROM survey_batches WHERE batch_name LIKE '%验收批次%'")).scalar())
            )
            OUT.append(
                "残留已分配户数 = "
                + str(conn.execute(text("SELECT count(*) FROM survey_cbf_base WHERE assigned_to IS NOT NULL")).scalar())
            )
    except Exception as exc:  # noqa: BLE001
        OUT.append(f"CLEANUP FAILED: {exc}")

RESULT_PATH.write_text("\n".join(OUT), encoding="utf-8")
print("\n".join(OUT))
