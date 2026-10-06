# -*- coding: utf-8 -*-
"""探查（只读）：库规模 + 变更类型分布，确认「新增地块」是压根没落库还是落库后缺关联。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DATABASE_PORT", "15432")
os.environ.setdefault("DATABASE_PASSWORD", "dK9venBRbBRewDFAWYHRGdCM")
os.environ.setdefault("SECRET_KEY", "probe-only")
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import psycopg  # noqa: E402

from app.core.config import settings  # noqa: E402

DSN = (
    f"host={settings.database_host} port={settings.database_port} "
    f"dbname={settings.database_name} user={settings.database_user} "
    f"password={settings.database_password}"
)

TABLES = [
    "survey_batches",
    "survey_cbf_result",
    "survey_dk_result",
    "survey_cbdkxx_result",
    "survey_change_records",
]


def main() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        cur = conn.cursor()
        print("库:", settings.database_name, "端口:", settings.database_port)
        for table in TABLES:
            cur.execute(f"SELECT count(*) FROM {table}")
            print(f"  {table}: {cur.fetchone()[0]}")

        print("\n=== survey_dk_result.result_status 分布 ===")
        cur.execute(
            "SELECT result_status, count(*) FROM survey_dk_result GROUP BY 1 ORDER BY 2 DESC"
        )
        for row in cur.fetchall():
            print("  ", row)

        print("\n=== survey_dk_result.change_type 分布 ===")
        cur.execute(
            "SELECT change_type, count(*) FROM survey_dk_result GROUP BY 1 ORDER BY 2 DESC"
        )
        for row in cur.fetchall():
            print("  ", row)

        print("\n=== survey_change_records.change_type 分布 ===")
        cur.execute(
            "SELECT change_type, count(*) FROM survey_change_records GROUP BY 1 ORDER BY 2 DESC"
        )
        for row in cur.fetchall():
            print("  ", row)

        print("\n=== 最近 10 条变更记录 ===")
        cur.execute(
            """
            SELECT id, batch_id, cbfbm, change_type, change_status, created_at
            FROM survey_change_records ORDER BY id DESC LIMIT 10
            """
        )
        for row in cur.fetchall():
            print("  ", row)


if __name__ == "__main__":
    main()
