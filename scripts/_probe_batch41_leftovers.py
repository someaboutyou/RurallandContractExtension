# -*- coding: utf-8 -*-
"""只读探查：找出历次验收测试在批次 41 留下的无主数据。

⚠️ 关键认知（修正了上一版探查的错误判据）：
   P1-4 修复前的 delete_contractor **既不删地块、也不删地块关联**，
   所以被删户遗弃的地块并不是「无关联的孤立地块」——它们仍被一条
   **指向已不存在承包方的残留关联行**挂着。因此不能用
   「survey_dk_result 里没有关联」来判定，必须用
   「survey_cbdkxx_result.cbfbm 在 survey_cbf_result 里找不到对应户」。

本脚本不写任何数据。
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


def main() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        cur = conn.cursor()

        print("=== 1. 残留地块关联：cbfbm 在 survey_cbf_result 里查不到对应户 ===")
        cur.execute("""
            SELECT c.id, c.cbfbm, c.dkbm, c.result_status, c.is_changed, c.initialized_at
            FROM survey_cbdkxx_result c
            WHERE NOT EXISTS (SELECT 1 FROM survey_cbf_result r WHERE r.cbfbm = c.cbfbm)
            ORDER BY c.cbfbm, c.dkbm
        """)
        orphan_rels = cur.fetchall()
        print(f"  共 {len(orphan_rels)} 行")
        for row in orphan_rels:
            print("   ", row)

        print("\n=== 2. 这些残留关联指向的地块（survey_dk_result）===")
        cur.execute("""
            SELECT d.id, d.dkbm, d.dkmc, d.region_code, d.initialized_at,
                   (SELECT count(*) FROM survey_cbdkxx_result c2
                      WHERE c2.dkbm = d.dkbm
                        AND EXISTS (SELECT 1 FROM survey_cbf_result r2 WHERE r2.cbfbm = c2.cbfbm)) AS live_rels
            FROM survey_dk_result d
            WHERE d.dkbm IN (
                SELECT c.dkbm FROM survey_cbdkxx_result c
                WHERE NOT EXISTS (SELECT 1 FROM survey_cbf_result r WHERE r.cbfbm = c.cbfbm)
            )
            ORDER BY d.dkbm
        """)
        dk_rows = cur.fetchall()
        print(f"  共 {len(dk_rows)} 行（live_rels = 还有几个活着的户在用它）")
        for row in dk_rows:
            print("   ", row)

        print("\n=== 3. 批次 41 里 cbfbm 前缀像验收夹具的户 ===")
        cur.execute("""
            SELECT cbfbm, cbfmc, contractor_uid FROM survey_cbf_result
            WHERE cbfbm LIKE '3213241000010299%' OR cbfbm LIKE '3213241000010298%'
               OR cbfbm LIKE '3213241000010291%'
            ORDER BY cbfbm
        """)
        for row in cur.fetchall():
            print("   ", row)

        print("\n=== 4. 孤儿变更记录 / 差异行（contractor_uid 已无对应 result）===")
        for table in ("survey_change_records", "survey_change_diffs"):
            cur.execute(f"""
                SELECT count(*) FROM {table} t
                WHERE NOT EXISTS (SELECT 1 FROM survey_cbf_result r WHERE r.contractor_uid = t.contractor_uid)
            """)
            print(f"  {table}: {cur.fetchone()[0]}")

        print("\n=== 5. 孤儿变更记录的 change_type 分布 ===")
        cur.execute("""
            SELECT change_type, count(*) FROM survey_change_records t
            WHERE NOT EXISTS (SELECT 1 FROM survey_cbf_result r WHERE r.contractor_uid = t.contractor_uid)
            GROUP BY change_type ORDER BY count(*) DESC
        """)
        for row in cur.fetchall():
            print("   ", row)

        print("\n=== 6. 残留的 survey_cbdkxx_base（批次快照侧）===")
        cur.execute("""
            SELECT count(*) FROM survey_cbdkxx_base b
            WHERE NOT EXISTS (SELECT 1 FROM survey_cbf_result r WHERE r.cbfbm = b.cbfbm)
        """)
        print("   cbdkxx_base 无主行:", cur.fetchone()[0])

        print("\n=== 7. 残留的 survey_cbf_base（任务快照侧）===")
        cur.execute("""
            SELECT batch_id, cbfbm, cbfmc, contractor_uid, task_status FROM survey_cbf_base b
            WHERE NOT EXISTS (SELECT 1 FROM survey_cbf_result r WHERE r.contractor_uid = b.contractor_uid)
        """)
        rows = cur.fetchall()
        print(f"   共 {len(rows)} 行")
        for row in rows:
            print("   ", row)


if __name__ == "__main__":
    main()
