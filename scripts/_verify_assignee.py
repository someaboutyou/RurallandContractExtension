"""离线联调：验证「批次调查员聚合 / 按调查员筛批次 / 新建批次指派」三件事（服务层）。

跑法（必须用带依赖的那个解释器）：
  runtime/windows/python/python.exe scripts/_verify_assignee.py

只读部分直接打开发库；新建批次部分会真正创建一次（组级 250 户左右），
结束前把本次创建的所有行删干净，因此可重复运行。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "runtime" / ".state" / "_verify_assignee.txt"


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

from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal, set_current_user  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.survey import SurveyBatchCreate, SurveyBatchRead  # noqa: E402
from app.services.survey_service import survey_service  # noqa: E402

OUT: list[str] = []
TEMP_BATCH_IDS: list[int] = []


def log(*parts) -> None:
    OUT.append(" ".join(str(part) for part in parts))


def dump_batch(row: dict) -> str:
    return (
        f"batch#{row['id']} {row['batchName']} "
        f"assigneeNames={row['assigneeNames']} assigneeCount={row['assigneeCount']} "
        f"unassigned={row['unassignedCount']} taskCount={row['taskCount']}"
    )


db = SessionLocal()
try:
    admin = db.get(User, 1)
    set_current_user(db, admin)

    log("=== 1. list_batches（批次面板用的调查员聚合）===")
    for row in survey_service.list_batches(db, 1, 20, None, None, None, admin)["items"]:
        log("  ", dump_batch(row))

    log("=== 2. list_assignees（筛选下拉 / 新建指派用的候选名单）===")
    for item in survey_service.list_assignees(db, admin, region_code="32132410000101"):
        log("   ", item)

    log("=== 3. 找一个有承包方数据、且没有进行中批次的组区域，做新建+指派实测 ===")
    candidate = db.execute(
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
            ORDER BY count(*) DESC
            LIMIT 1
            """
        )
    ).first()
    log("   candidate =", candidate)
    if candidate is None:
        raise RuntimeError("找不到可用于验收的空闲区域")
    code, name = candidate

    options = survey_service.list_assignees(db, admin, region_code=code)
    covering = [item["id"] for item in options if item["coversRegion"]]
    log("   全部候选 =", [(item["id"], item["realName"], item["coversRegion"]) for item in options])
    log("   覆盖该区域的调查员 =", covering)
    if not covering:
        raise RuntimeError("没有覆盖该区域的调查员，换个候选区域")

    created = survey_service.create_batch(
        db,
        {
            "batchName": "__指派验收批次__",
            "regionCode": code,
            "regionName": name,
            "assigneeIds": covering[:3],
        },
        admin,
    )
    batch_id = created["id"]
    TEMP_BATCH_IDS.append(batch_id)
    log("   新建结果：", dump_batch(created))

    log("   任务归属分布（应按承包方编码顺序轮流均分）：")
    for row in db.execute(
        text(
            "SELECT assigned_to, assigned_to_name, count(*) FROM survey_cbf_base "
            "WHERE batch_id = :bid GROUP BY assigned_to, assigned_to_name ORDER BY assigned_to"
        ),
        {"bid": batch_id},
    ).all():
        log("      ", row)
    log(
        "   assigned_at 非空户数 =",
        db.execute(
            text("SELECT count(*) FROM survey_cbf_base WHERE batch_id = :bid AND assigned_at IS NOT NULL"),
            {"bid": batch_id},
        ).scalar(),
    )

    tasks = survey_service.list_tasks(db, batch_id, 1, 5, None, None, None, admin)
    log("   调查列表前 5 行的 assignedToName：", [item["assignedToName"] for item in tasks["items"]])

    log("=== 4. 新建后按调查员筛批次 ===")
    hit = survey_service.list_batches(db, 1, 20, None, None, None, admin, assignee_id=covering[0])
    log("   assigneeId=%s total=%s ids=%s" % (covering[0], hit["total"], [row["id"] for row in hit["items"]]))
    miss = survey_service.list_batches(db, 1, 20, None, None, None, admin, assignee_id=999999)
    log("   assigneeId=999999 total =", miss["total"], "（应为 0）")

    log("=== 5. 响应/请求 schema 校验（防止 response_model 把新字段滤掉）===")
    parsed = SurveyBatchRead.model_validate(next(row for row in hit["items"] if row["id"] == batch_id))
    log("   SurveyBatchRead OK ->", parsed.assigneeNames, parsed.assigneeCount, parsed.unassignedCount)
    log(
        "   SurveyBatchCreate OK ->",
        SurveyBatchCreate.model_validate({"batchName": "x", "regionCode": code, "assigneeIds": covering[:2]}).model_dump(),
    )

    log("=== 6. 指派名单非法时应直接报错 ===")
    try:
        survey_service.resolve_batch_assignees(db, [999999], region_code=code, tenant_code="321324")
        log("   未报错（不符合预期）")
    except Exception as exc:  # noqa: BLE001
        log(f"   [999999] -> {type(exc).__name__}: {getattr(exc, 'detail', exc)}")
finally:
    try:
        for _bid in TEMP_BATCH_IDS:
            for _table in (
                "survey_cbf_jtcy_base",
                "survey_cbdkxx_base",
                "survey_dk_base",
                "survey_fbf_base",
                "survey_cbf_base",
            ):
                db.execute(text(f"DELETE FROM {_table} WHERE batch_id = :bid"), {"bid": _bid})
            db.execute(text("DELETE FROM survey_batches WHERE id = :bid"), {"bid": _bid})
        db.commit()
        OUT.append("")
        OUT.append("=== cleanup ===")
        OUT.append("deleted temp batches = " + str(TEMP_BATCH_IDS))
        OUT.append(
            "残留已分配户数 = "
            + str(db.execute(text("SELECT count(*) FROM survey_cbf_base WHERE assigned_to IS NOT NULL")).scalar())
        )
        OUT.append(
            "残留验收批次 = "
            + str(db.execute(text("SELECT count(*) FROM survey_batches WHERE batch_name LIKE '%验收批次%'")).scalar())
        )
    except Exception as exc:  # noqa: BLE001
        OUT.append(f"CLEANUP FAILED: {exc}")
    db.close()

RESULT_PATH.write_text("\n".join(OUT), encoding="utf-8")
print("\n".join(OUT))
