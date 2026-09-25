# -*- coding: utf-8 -*-
"""探查：为「承包方调查录入」的保存/撤回闭环测试挑一个安全、可复现的夹具。

只读脚本，不改任何数据。输出：
  1. 库规模 / 活跃连接（判断能否用 TEMPLATE 复制库）
  2. survey_* 相关表行数
  3. 候选批次（active 优先）及其户 / 地块 / 成员分布
  4. survey_change_records 的 change_type 分布（找可撤回的记录）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DATABASE_PORT", "15432")
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
    "survey_cbf_base",
    "survey_cbf_jtcy_result",
    "survey_cbf_jtcy_base",
    "survey_dk_result",
    "survey_dk_base",
    "survey_cbdkxx_result",
    "survey_cbdkxx_base",
    "survey_fbf_result",
    "survey_fbf_base",
    "survey_change_records",
    "survey_change_diffs",
    "users",
    "regions",
]


def main() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        cur = conn.cursor()
        cur.execute("SELECT current_database(), pg_size_pretty(pg_database_size(current_database()))")
        print("库:", cur.fetchone())
        cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
        print("当前库活跃连接数:", cur.fetchone()[0])
        cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname")
        print("已有数据库:", [r[0] for r in cur.fetchall()])

        print("\n--- 表行数 ---")
        for table in TABLES:
            try:
                cur.execute(f"SELECT count(*) FROM {table}")
                print(f"  {table:<28} {cur.fetchone()[0]}")
            except Exception as exc:  # noqa: BLE001
                print(f"  {table:<28} [缺失] {type(exc).__name__}")

        print("\n--- 批次（最近 8 个）---")
        cur.execute(
            """
            SELECT b.id, b.batch_no, b.status, b.survey_type, b.region_code, b.region_name,
                   (SELECT count(*) FROM survey_cbf_result r WHERE r.tenant_code = b.tenant_code
                      AND r.contractor_uid IN (SELECT contractor_uid FROM survey_cbf_base x WHERE x.batch_id = b.id)) AS households
            FROM survey_batches b
            ORDER BY b.id DESC LIMIT 8
            """
        )
        for row in cur.fetchall():
            print("  ", row)

        print("\n--- 地块最多的 5 个户（在最近批次里）---")
        cur.execute(
            """
            SELECT x.batch_id, x.contractor_uid, x.cbfbm, x.cbfmc, x.task_status, x.has_change,
                   (SELECT count(*) FROM survey_cbdkxx_result c WHERE c.cbfbm = x.cbfbm AND c.result_status NOT IN ('removed','split_source')) AS parcels,
                   (SELECT count(*) FROM survey_cbf_jtcy_result j WHERE j.contractor_uid = x.contractor_uid) AS members,
                   (SELECT count(*) FROM survey_change_diffs d WHERE d.contractor_uid = x.contractor_uid) AS diffs
            FROM survey_cbf_base x
            WHERE x.batch_id = (SELECT max(id) FROM survey_batches)
            ORDER BY parcels DESC, members DESC
            LIMIT 5
            """
        )
        for row in cur.fetchall():
            print("  ", row)

        print("\n--- survey_change_records 的 change_type / status 分布 ---")
        cur.execute(
            """
            SELECT change_type, change_status, count(*) AS n
            FROM survey_change_records
            GROUP BY change_type, change_status
            ORDER BY n DESC
            """
        )
        for row in cur.fetchall():
            print("  ", row)

        print("\n--- 全库可撤回(未 rolled_back)的操作类变更记录 ---")
        cur.execute(
            """
            SELECT batch_id, contractor_uid, change_no, change_type, change_status, created_at
            FROM survey_change_records
            WHERE change_type IN ('remove_parcel','split_parcel','swap_parcels','deregister','split_household','merge_household')
              AND change_status <> 'rolled_back'
            ORDER BY id DESC LIMIT 15
            """
        )
        rows = cur.fetchall()
        if not rows:
            print("  （无）")
        for row in rows:
            print("  ", row)


if __name__ == "__main__":
    main()
