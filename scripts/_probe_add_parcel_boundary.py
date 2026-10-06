# -*- coding: utf-8 -*-
"""探查：新增地块（add_parcel）落库后，界址点/界址线维护报「该地块不属于当前承包方」的原因。

只读脚本，不改任何数据。核对三件事：
  1. survey_dk_result 里 add_parcel 的地块，是否都有对应的 survey_cbdkxx_result 关联行；
  2. 关联行的 cbfbm 是否等于该地块所属承包方（按 dkbm 前缀 / 变更记录反查）；
  3. 两张表的 tenant_code / region_code 是否一致（全局 with_loader_criteria 会按这两列筛）。
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


def main() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        cur = conn.cursor()

        print("=== 1. add_parcel 地块总体情况 ===")
        cur.execute(
            """
            SELECT count(*) FROM survey_dk_result
            WHERE change_type = 'add_parcel' AND result_status <> 'removed'
            """
        )
        print("add_parcel 地块数:", cur.fetchone()[0])

        print("\n=== 2. add_parcel 地块 与 关联表 的配对情况 ===")
        cur.execute(
            """
            SELECT d.dkbm, d.dkmc, d.tenant_code, d.region_code, d.result_status,
                   d.survey_status, d.change_type,
                   r.id IS NOT NULL AS has_relation,
                   r.cbfbm, r.tenant_code, r.region_code
            FROM survey_dk_result d
            LEFT JOIN survey_cbdkxx_result r ON r.dkbm = d.dkbm
            WHERE d.change_type = 'add_parcel' AND d.result_status <> 'removed'
            ORDER BY d.id DESC
            LIMIT 40
            """
        )
        rows = cur.fetchall()
        if not rows:
            print("（无）")
        for row in rows:
            (
                dkbm, dkmc, d_tenant, d_region, d_status, d_survey, d_ct,
                has_rel, r_cbfbm, r_tenant, r_region,
            ) = row
            flag = "OK " if has_rel else "!! 缺关联"
            print(
                f"{flag} dkbm={dkbm} 名称={dkmc} 地块表(tenant={d_tenant}, region={d_region}, "
                f"result={d_status}/{d_survey}/{d_ct})  关联(has={has_rel}, cbfbm={r_cbfbm}, "
                f"tenant={r_tenant}, region={r_region})"
            )

        print("\n=== 3. 缺关联的 add_parcel 地块（若有，说明保存路径漏写关联行）===")
        cur.execute(
            """
            SELECT d.dkbm, d.dkmc, d.tenant_code, d.region_code, d.ysdm
            FROM survey_dk_result d
            LEFT JOIN survey_cbdkxx_result r ON r.dkbm = d.dkbm
            WHERE d.change_type = 'add_parcel' AND d.result_status <> 'removed'
              AND r.id IS NULL
            """
        )
        missing = cur.fetchall()
        print("数量:", len(missing))
        for item in missing:
            print("  ", item)

        print("\n=== 4. 变更记录里的 add_parcel（含 after_summary 的 dkbm）===")
        cur.execute(
            """
            SELECT change_no, batch_id, contractor_uid, cbfbm, change_status, created_at,
                   after_summary -> 'dkbm' AS dkbm
            FROM survey_change_records
            WHERE change_type = 'add_parcel'
            ORDER BY id DESC
            LIMIT 20
            """
        )
        for row in cur.fetchall():
            print("  ", row)

        print("\n=== 5. 关联表与地块表的 tenant/region 口径抽样（判断是否会被全局 scope 筛掉）===")
        cur.execute(
            """
            SELECT d.tenant_code AS d_tenant, d.region_code AS d_region,
                   r.tenant_code AS r_tenant, r.region_code AS r_region,
                   count(*)
            FROM survey_dk_result d
            JOIN survey_cbdkxx_result r ON r.dkbm = d.dkbm
            WHERE d.change_type = 'add_parcel' AND d.result_status <> 'removed'
            GROUP BY 1, 2, 3, 4
            ORDER BY 5 DESC
            """
        )
        for row in cur.fetchall():
            print("  ", row)


if __name__ == "__main__":
    main()
