# -*- coding: utf-8 -*-
"""只读诊断（第二批）：确认侧字段 + 批次 41 任务全貌。

用法：
    runtime/windows/python/python.exe scripts/_probe_swap_rollback2.py
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
    "SECRET_KEY": "probe-only",
})
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import psycopg  # noqa: E402

from app.core.config import settings  # noqa: E402

DSN = (
    f"host={settings.database_host} port={settings.database_port} "
    f"dbname={settings.database_name} user={settings.database_user} "
    f"password={settings.database_password}"
)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def dump(cur, sql, params=()):
    cur.execute(sql, params)
    cols = [d.name for d in cur.description]
    rows = cur.fetchall()
    if not rows:
        print("   (空)")
        return []
    print("   " + " | ".join(cols))
    for row in rows:
        print("   " + " | ".join(repr(v) for v in row))
    return rows


def main() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        cur = conn.cursor()

        section("1. result 行 CONFIRMED/复核字段（013 / 014）")
        dump(
            cur,
            """
            SELECT id, cbfbm, cbfmc, survey_status, result_status, change_type,
                   investigator_name, investigated_at,
                   reviewer_id, reviewer_name, reviewed_at, confirmed_at,
                   is_changed
            FROM survey_cbf_result
            WHERE cbfbm IN ('321324100001020013','321324100001020014')
            ORDER BY id
            """,
        )

        section("2. base 行（013 / 014）")
        dump(
            cur,
            """
            SELECT id, batch_id, cbfbm, cbfmc, task_status, has_change, change_count,
                   assigned_to, assigned_to_name, investigated_at
            FROM survey_cbf_base
            WHERE cbfbm IN ('321324100001020013','321324100001020014')
            ORDER BY id
            """,
        )

        section("3. 批次 41 全部任务行")
        dump(
            cur,
            """
            SELECT id, cbfbm, cbfmc, task_status, has_change, change_count,
                   assigned_to_name, investigated_at
            FROM survey_cbf_base WHERE batch_id = 41 ORDER BY cbfbm
            """,
        )

        section("4. survey_change_records 全批次 41（按 id 倒序 20 条）")
        dump(
            cur,
            """
            SELECT id, change_no, cbfbm, change_type, change_status, change_reason,
                   investigated_at, reviewer_name, reviewed_at
            FROM survey_change_records WHERE batch_id = 41
            ORDER BY id DESC LIMIT 20
            """,
        )

        section("5. 013 的成员/发承包方相关行计数（确认时是否被一并写）")
        dump(
            cur,
            """
            SELECT 'members' AS t, count(*) FROM survey_cyxx_result
            WHERE cbfbm = '321324100001020013'
            """,
        )


if __name__ == "__main__":
    main()
