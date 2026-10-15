# -*- coding: utf-8 -*-
"""离线验收：调查成果导出 zip（/surveys「导出」按钮的接口 build_results_zip）。

背景（2026-10-09 测试发现，三处同腐）：
  ① exports.py 曾用 `SurveyCbfResult.batch_id`（模型无此列）⇒ AttributeError 500；
  ② 任务表 SurveyCbfBase 没有 confirmed_at（task.py:426 的赋值是静默无效的临时属性）；
  ③ `_build_tasks_csv` 在历史"invalid string literal"自动修复时弄丢了表头列表，
     `_csv_bytes(headers, rows)` 只收到 1 个参数 ⇒ TypeError。
修复后口径：
  · data_batch_ids 以**本批次任务行**（SurveyCbfBase.batch_id）为准；
  · 任务 CSV 的「确认时间」由同 region 最新 result 行回填；
  · **新增承包方**（create_contractor 落 task 行 + result_status='added'）必须同时
    出现在 survey_tasks.csv 与 survey_cbf_result.csv —— 这是本脚本的硬断言。

用法：runtime/windows/python/python.exe scripts/_verify_survey_export_zip.py
只读：build_results_zip 只做 SELECT，本脚本零落库。
"""
from __future__ import annotations

import csv
import io
import os
import sys
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
    line = line.strip()
    if "=" in line:
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())
sys.path.insert(0, str(ROOT / "backend"))

import app.main  # noqa: E402,F401  注册全部 mapper（含 UserRegionPermission）
from app.db.session import SessionLocal  # noqa: E402
from app.models.survey import SurveyCbfBase  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.survey_service import survey_service  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

EXPECTED_ENTRIES = {
    "survey_tasks.csv",
    "survey_fbf_result.csv",
    "survey_cbf_result.csv",
    "survey_cbf_jtcy_result.csv",
    "survey_change_diffs.csv",
}
TASKS_HEADER = ["批次内唯一标识", "承包方编码", "承包方名称", "调查状态", "是否变化", "变化数", "调查时间", "确认时间", "跳过原因"]

passed = 0
failed = 0


def check(name: str, ok: bool, detail="") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  [PASS] {name}" + (f"  —— {detail}" if detail else ""))
    else:
        failed += 1
        print(f"  [FAIL] {name}  —— {detail}")


def read_csv(zf: zipfile.ZipFile, name: str) -> list[list[str]]:
    return list(csv.reader(io.TextIOWrapper(io.BytesIO(zf.read(name)), encoding="utf-8-sig")))


def main() -> int:
    db = SessionLocal()
    user = db.get(User, 1)
    try:
        batch_ids = [row for row in db.scalars(select(SurveyCbfBase.batch_id).distinct()).all()]
        batch_ids = sorted(batch_ids)[:2] if len(batch_ids) >= 2 else batch_ids
        check("候选批次 ≥ 1", bool(batch_ids), f"batches={batch_ids}")

        for batch_id in batch_ids:
            print(f"\n=== 批次 {batch_id} ===")
            total_tasks = db.scalar(
                select(func.count()).select_from(SurveyCbfBase).where(SurveyCbfBase.batch_id == batch_id)
            )
            filename, content = survey_service.build_results_zip(db, batch_id, user, None)
            check(f"批次 {batch_id} 导出不抛异常", True, filename)
            zf = zipfile.ZipFile(io.BytesIO(content))
            check(f"批次 {batch_id} zip 含 5 个 CSV", set(zf.namelist()) == EXPECTED_ENTRIES, zf.namelist())

            tasks_rows = read_csv(zf, "survey_tasks.csv")
            cbf_rows = read_csv(zf, "survey_cbf_result.csv")
            check(f"批次 {batch_id} 表头完整（tasks.csv 修复）", tasks_rows[0] == TASKS_HEADER, tasks_rows[0])
            check(
                f"批次 {batch_id} 任务行数 == survey_cbf_base 计数",
                len(tasks_rows) - 1 == total_tasks,
                f"{len(tasks_rows) - 1} vs {total_tasks}",
            )

            added_in_cbf = {r[1] for r in cbf_rows[1:] if len(r) > 11 and r[11] == "added"}
            tasks_codes = {r[1] for r in tasks_rows[1:]}
            check(
                f"批次 {batch_id} 新增承包方(result=added)⊆任务行",
                added_in_cbf <= tasks_codes,
                f"added={sorted(added_in_cbf)} tasks={len(tasks_codes)}行",
            )
            if added_in_cbf:
                print(f"    （本批次新增承包方：{sorted(added_in_cbf)}）")

            confirmed_rows = [r for r in tasks_rows[1:] if len(r) > 7 and r[7]]
            confirmed_in_cbf = {
                r[1] for r in cbf_rows[1:] if len(r) > 20 and r[20] and r[10] == "confirmed"
            } if len(cbf_rows[0]) > 20 else set()
            print(f"    （带确认时间的任务行 {len(confirmed_rows)} 条；result 表 confirmed 行 {len(confirmed_in_cbf)} 条）")
        return 0 if failed == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("调查成果导出 zip 验收（只读，零落库）")
    print("=" * 60)
    code = main()
    print("\n" + "=" * 60)
    print(f"结果：PASS {passed} / FAIL {failed}")
    sys.exit(code)
