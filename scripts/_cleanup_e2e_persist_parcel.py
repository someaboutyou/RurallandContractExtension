# -*- coding: utf-8 -*-
"""清理浏览器验收（`e2e_persist_parcel.mjs`）留下的临时地块。

为什么需要它：行级「保存」是**真落库**（这正是被验收的行为），所以 e2e 跑完会在库里
留下一块"行级保存验收临时地块"。本脚本把它以及它带来的一切副作用一起抹掉：

    1. survey_dk_result            该地块行
    2. survey_cbdkxx_result        该地块的承包方关联行
    3. survey_change_records       change_type='add_parcel' 且 after_summary.dkbm 命中
    4. survey_change_diffs         该户的差异行 → 删完后**按当前库内状态重建**
    5. survey_cbf_base 的任务态     has_change / change_count 按重建后的变更记录重算
       （否则该户会永远显示"有变更"，哪怕实际一条都没有）

⚠️ 只认「地块名称 = 行级保存验收临时地块」这一个标记，不做模式匹配式的批量删除；
   删之前会把要删的行逐条打印出来。

⚠️ `survey_cbdkxx_result` **没有 batch_id 列**（批次只在 `survey_cbf_base` 的任务行上），
   所以批次/uid 一律按 cbfbm 从 base 表反查。

用法：
    runtime/windows/python/python.exe scripts/_cleanup_e2e_persist_parcel.py          # 预演
    runtime/windows/python/python.exe scripts/_cleanup_e2e_persist_parcel.py --apply  # 真删
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.update({
    "DATABASE_HOST": "127.0.0.1",
    "DATABASE_PORT": "15432",
    "DATABASE_NAME": "erlunyanbao",
    "DATABASE_USER": "RurallandContractExtension",
    "DATABASE_PASSWORD": "dK9venBRbBRewDFAWYHRGdCM",
    "SECRET_KEY": "cleanup-only",
})
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import app.main  # noqa: F401,E402  注册全部 mapper
from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal, set_current_user  # noqa: E402
from app.services.auth_service import auth_service  # noqa: E402
from app.services.survey import survey_service  # noqa: E402

MARKER_NAME = "行级保存验收临时地块"
APPLY = "--apply" in sys.argv


def find_task_rows(db, codes: set[str]) -> list[dict]:
    """按 cbfbm 逐条反查任务行（避免给 ANY/IN 传数组时的类型适配问题）。"""
    rows: list[dict] = []
    for code in sorted(codes):
        rows.extend(db.execute(text(
            "SELECT contractor_uid, batch_id, cbfbm FROM survey_cbf_base WHERE cbfbm = :c"
        ), {"c": code}).mappings().all())
    return rows


def main() -> None:
    db = SessionLocal()
    admin = auth_service.get_current_user(db, 1)
    set_current_user(db, admin)

    targets = db.execute(text(
        """
        SELECT d.dkbm, d.dkmc, d.tenant_code, r.cbfbm
        FROM survey_dk_result d
        LEFT JOIN survey_cbdkxx_result r ON r.dkbm = d.dkbm
        WHERE d.dkmc = :name
        ORDER BY d.dkbm
        """
    ), {"name": MARKER_NAME}).mappings().all()

    if not targets:
        print(f"没有需要清理的临时地块（未找到「{MARKER_NAME}」）。库是干净的。")
        db.close()
        return

    codes = {row["cbfbm"] for row in targets if row["cbfbm"]}
    task_rows = find_task_rows(db, codes)
    batch_of = {row["cbfbm"]: row["batch_id"] for row in task_rows}

    print(f"找到 {len(targets)} 块验收临时地块：")
    for row in targets:
        print(f"  dkbm={row['dkbm']} 户={row['cbfbm']} 批次={batch_of.get(row['cbfbm'])} 名称={row['dkmc']}")

    if not APPLY:
        print("\n以上为**预演**。确认无误后加 --apply 执行删除。")
        db.close()
        return

    for row in targets:
        dkbm = row["dkbm"]
        # 关联行 / 地块行
        rel = db.execute(text("DELETE FROM survey_cbdkxx_result WHERE dkbm = :d"), {"d": dkbm}).rowcount
        dk = db.execute(text("DELETE FROM survey_dk_result WHERE dkbm = :d"), {"d": dkbm}).rowcount
        # 变更记录：add_parcel 且 after_summary 里点名了这块地
        rec = db.execute(text(
            """
            DELETE FROM survey_change_records
            WHERE change_type = 'add_parcel'
              AND after_summary ->> 'dkbm' = :d
            """
        ), {"d": dkbm}).rowcount
        print(f"  删除 dkbm={dkbm}: 关联行={rel} 地块行={dk} 变更记录={rec}")

    # 差异行整户重建（diff 是按户算出来的，删掉一条记录后必须重算，否则留下悬空差异）
    for task in task_rows:
        uid = task["contractor_uid"]
        batch_id = int(task["batch_id"])
        before = db.execute(text(
            "SELECT count(*) FROM survey_change_diffs WHERE batch_id = :b AND contractor_uid = :u"
        ), {"b": batch_id, "u": uid}).scalar()
        survey_service._rebuild_contractor_diffs(db, batch_id, [uid])
        db.flush()
        after = db.execute(text(
            "SELECT count(*) FROM survey_change_diffs WHERE batch_id = :b AND contractor_uid = :u"
        ), {"b": batch_id, "u": uid}).scalar()
        print(f"  重建差异 batch={batch_id} uid={uid}: {before} -> {after} 行")

    # 任务态：按重建后的变更记录重算，避免留下"永远有变更"的户
    for task in task_rows:
        batch_id = int(task["batch_id"])
        cbfbm = task["cbfbm"]
        left = db.execute(text(
            """
            SELECT count(*) FROM survey_change_records c
            JOIN survey_cbf_base t
              ON t.contractor_uid = c.contractor_uid AND t.batch_id = c.batch_id
            WHERE c.batch_id = :b AND t.cbfbm = :c
            """
        ), {"b": batch_id, "c": cbfbm}).scalar() or 0
        upd = db.execute(text(
            """
            UPDATE survey_cbf_base
            SET has_change = :has, change_count = :cnt
            WHERE batch_id = :b AND cbfbm = :c
            """
        ), {"b": batch_id, "c": cbfbm, "has": left > 0, "cnt": left}).rowcount
        print(f"  重算任务态 batch={batch_id} cbfbm={cbfbm}: 剩余变更记录={left} 更新行={upd}")

    db.commit()

    left_over = db.execute(text(
        "SELECT count(*) FROM survey_dk_result WHERE dkmc = :name"
    ), {"name": MARKER_NAME}).scalar()
    print(f"\n清理完成，剩余同名临时地块：{left_over}（应为 0）")
    db.close()


if __name__ == "__main__":
    main()
