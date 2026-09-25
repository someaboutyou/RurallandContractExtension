# -*- coding: utf-8 -*-
"""只读探测：合户后新户的归属/可写状态，用于定位「合户后不能修改」。

用法：runtime/windows/python/python.exe scripts/_probe_merge_write.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for line in open(os.path.join(ROOT, "runtime", ".state", "runtime.env"), encoding="utf-8-sig"):
    line = line.strip()
    if not line or "=" not in line:
        continue
    key, value = line.split("=", 1)
    os.environ.setdefault(key.strip(), value.strip())

import psycopg

CODES = ("321324100001020010", "321324100001020011")

with psycopg.connect(
    host=os.environ.get("DATABASE_HOST", "127.0.0.1"),
    port=os.environ.get("DATABASE_PORT", "15432"),
    dbname=os.environ.get("DATABASE_NAME", "erlunyanbao"),
    user=os.environ.get("DATABASE_USER", "postgres"),
    password=os.environ.get("DATABASE_PASSWORD", "postgres"),
) as conn, conn.cursor() as cur:
    cur.execute(
        """
        SELECT id, contractor_uid, cbfbm, cbfmc, cbfcysl, survey_status,
               result_status, is_changed, change_type, change_reason,
               investigator_id, investigator_name, remark, region_code
        FROM survey_cbf_result
        WHERE cbfbm = ANY(%s) OR remark LIKE 'merge_group:%%'
        ORDER BY id
        """,
        (list(CODES),),
    )
    print("=== survey_cbf_result ===")
    for row in cur.fetchall():
        print(row)

    cur.execute(
        """
        SELECT b.id, b.batch_id, b.contractor_uid, b.cbfbm, b.cbfmc, b.task_status,
               b.assigned_to, b.assigned_to_name, b.assigned_at, b.change_count,
               b.remark, b.has_change
        FROM survey_cbf_base b
        WHERE b.cbfbm = ANY(%s) OR b.remark LIKE 'merge_group:%%'
        ORDER BY b.id
        """,
        (list(CODES),),
    )
    print("\n=== survey_cbf_base (task row) ===")
    for row in cur.fetchall():
        print(row)

    cur.execute(
        """
        SELECT id, batch_id, contractor_uid, cbfbm, cbfmc, member_uid, cyxm,
               yhzgx, is_household_head, is_changed, contractor_uid IN
               (SELECT contractor_uid FROM survey_cbf_result WHERE remark LIKE 'merge_group:%%') AS in_new
        FROM survey_cbf_jtcy_result
        WHERE cbfbm = ANY(%s) OR contractor_uid IN
              (SELECT contractor_uid FROM survey_cbf_result WHERE remark LIKE 'merge_group:%%')
        ORDER BY id
        """,
        (list(CODES),),
    )
    print("\n=== survey_cbf_jtcy_result (members) ===")
    for row in cur.fetchall():
        print(row)

    cur.execute(
        """
        SELECT id, batch_id, contractor_uid, cbfbm, change_type, change_status,
               after_summary, reason, created_at
        FROM survey_change_records
        WHERE change_type IN ('merge_household', 'rollback_merge_household')
        ORDER BY id DESC LIMIT 20
        """
    )
    print("\n=== survey_change_records (merge) ===")
    for row in cur.fetchall():
        print(row)
