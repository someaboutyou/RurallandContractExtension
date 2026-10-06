# -*- coding: utf-8 -*-
"""探查（只读）：地块编码 dkbm 的唯一性到底靠什么保证。

要回答三个问题：
  1) 库里到底有没有 (tenant_code, dkbm) 的唯一索引？建成了没有？
  2) 现网数据里是否已经存在重复的 dkbm？
  3) result_status='removed' 这种状态真实存在吗（add_parcel 的判重条件是否空转）？
"""
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

TABLES = ["survey_dk_result", "survey_dk_base", "survey_cbdkxx_result", "survey_cbdkxx_base"]

INDEX_SPECS = {
    "survey_dk_result": ["uq_survey_dk_result_tenant_dkbm", "ix_survey_dk_result_dkbm_id"],
    "survey_dk_base": ["uq_survey_dk_base_tenant_batch_dkbm"],
    "survey_cbdkxx_result": ["uq_survey_cbdkxx_result_tenant_relation"],
}


def section(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        cur = conn.cursor()

        section("0. 连接信息")
        print(f"db={settings.database_name} port={settings.database_port} host={settings.database_host}")

        section("1. 唯一/普通索引现状（pg_index）")
        cur.execute(
            """
            SELECT c.relname AS table_name,
                   i.relname AS index_name,
                   idx.indisunique AS is_unique,
                   pg_get_indexdef(idx.indexrelid) AS index_def
            FROM pg_index idx
            JOIN pg_class i ON i.oid = idx.indexrelid
            JOIN pg_class c ON c.oid = idx.indrelid
            WHERE c.relname = ANY(%s)
            ORDER BY c.relname, idx.indisunique DESC, i.relname
            """,
            (TABLES,),
        )
        rows = cur.fetchall()
        if not rows:
            print("  (无)")
        for table_name, index_name, is_unique, index_def in rows:
            flag = "UNIQUE" if is_unique else "index "
            print(f"  [{flag}] {table_name}.{index_name}")
            print(f"           {index_def}")

        section("2. 预期唯一索引是否真的存在")
        for table, names in INDEX_SPECS.items():
            for name in names:
                cur.execute(
                    "SELECT indisunique FROM pg_index idx JOIN pg_class i ON i.oid = idx.indexrelid "
                    "WHERE i.relname = %s",
                    (name,),
                )
                got = cur.fetchone()
                if got is None:
                    print(f"  ✗ 缺失  {table}.{name}")
                else:
                    print(f"  ✓ 存在  {table}.{name}  unique={got[0]}")

        section("3. 重复 dkbm 实况（按 tenant_code+dkbm）")
        for table in ("survey_dk_result", "survey_dk_base"):
            cur.execute(f"SELECT count(*) FROM {table}")
            total = cur.fetchone()[0]
            cur.execute(
                f"""
                SELECT tenant_code, dkbm, count(*) AS n
                FROM {table}
                GROUP BY tenant_code, dkbm
                HAVING count(*) > 1
                ORDER BY n DESC
                """
            )
            dups = cur.fetchall()
            print(f"  {table}: 总行数={total}  重复键组数={len(dups)}")
            for tenant_code, dkbm, n in dups[:20]:
                print(f"      tenant={tenant_code} dkbm={dkbm} x{n}")

        section("4. result_status 分布（验证 'removed' 是否存在）")
        for table in ("survey_dk_result", "survey_cbdkxx_result"):
            cur.execute(
                f"SELECT result_status, count(*) FROM {table} GROUP BY 1 ORDER BY 2 DESC"
            )
            print(f"  {table}:")
            for st, n in cur.fetchall():
                print(f"      {str(st):22s} {n}")

        section("5. 号段占用：前 14 位前缀下的最大流水")
        cur.execute(
            """
            SELECT left(dkbm, 14) AS prefix,
                   count(*) AS rows,
                   max(substring(dkbm from 15 for 5)) AS max_suffix,
                   count(DISTINCT substring(dkbm from 15 for 5)) AS distinct_suffix
            FROM survey_dk_result
            WHERE length(dkbm) >= 19
            GROUP BY 1
            ORDER BY rows DESC
            LIMIT 15
            """
        )
        print(f"  {'prefix':16s} {'rows':>6s} {'max_suffix':>11s} {'distinct':>9s}")
        for prefix, n, max_suffix, distinct_suffix in cur.fetchall():
            print(f"  {str(prefix):16s} {n:>6d} {str(max_suffix):>11s} {distinct_suffix:>9d}")

        section("6. 同前缀是否跨多个承包方（号段是否共享）")
        cur.execute(
            """
            SELECT left(r.dkbm, 14) AS prefix,
                   count(DISTINCT x.cbfbm) AS cbf_count,
                   count(DISTINCT r.dkbm) AS parcel_count
            FROM survey_dk_result r
            JOIN survey_cbdkxx_result x ON x.dkbm = r.dkbm
            WHERE length(r.dkbm) >= 19
            GROUP BY 1
            ORDER BY cbf_count DESC
            LIMIT 15
            """
        )
        print(f"  {'prefix':16s} {'承包方数':>8s} {'地块数':>8s}")
        for prefix, cbf_count, parcel_count in cur.fetchall():
            print(f"  {str(prefix):16s} {cbf_count:>8d} {parcel_count:>8d}")


if __name__ == "__main__":
    main()
