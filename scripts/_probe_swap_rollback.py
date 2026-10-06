# -*- coding: utf-8 -*-
"""只读诊断：承包方 321324100001020013「互换 → 撤销互换」后状态异常。

用户 2026-09-27 21:33 报：
    ① 对 321324100001020013 做地块互换（本户某地块 <-> 321324100001020014 的某地块），
       保存调查结果后重新进入；
    ② 点该户地块上的「撤回互换」按钮；
    ③ 撤销互换似乎没成功；
    ④ 该户的调查信息被直接确认了。

本脚本只读，不写任何数据。

用法：
    runtime/windows/python/python.exe scripts/_probe_swap_rollback.py [承包方编码] [对方承包方编码]
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


def dump(cur, sql, params=(), limit=None):
    cur.execute(sql, params)
    cols = [d.name for d in cur.description]
    rows = cur.fetchall()
    if limit:
        rows = rows[:limit]
    if not rows:
        print("   (空)")
        return []
    print("   " + " | ".join(cols))
    for row in rows:
        print("   " + " | ".join(repr(v) for v in row))
    return rows


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "321324100001020013"
    peer = sys.argv[2] if len(sys.argv) > 2 else "321324100001020014"

    with psycopg.connect(DSN, autocommit=True) as conn:
        cur = conn.cursor()

        section(f"1. 目标户 {target} 的 base 行（survey_cbf_base）")
        bases = dump(
            cur,
            """
            SELECT id, batch_id, region_code, contractor_uid, cbfbm, source_cbfbm, cbfmc,
                   task_status, has_change, change_count, assigned_to_name, investigated_at
            FROM survey_cbf_base WHERE cbfbm = %s OR source_cbfbm = %s
            ORDER BY batch_id, id
            """,
            (target, target),
        )

        section(f"2. 目标户 {target} 的 result 行（survey_cbf_result）")
        results = dump(
            cur,
            """
            SELECT id, contractor_uid, cbfbm, cbfmc,
                   survey_status, result_status, change_type, is_changed, change_reason,
                   investigator_name, investigated_at, updated_at
            FROM survey_cbf_result WHERE cbfbm = %s
            ORDER BY id
            """,
            (target,),
        )

        uid = results[0][1] if results else None

        section(f"3. 目标户地块关联（survey_cbdkxx_result，cbfbm={target}）")
        dump(
            cur,
            """
            SELECT id, dkbm, cbfbm, fbfbm, result_status, is_changed, change_type,
                   change_reason, survey_status
            FROM survey_cbdkxx_result WHERE cbfbm = %s ORDER BY dkbm, id
            """,
            (target,),
        )

        section(f"4. 对方户 {peer} 地块关联（survey_cbdkxx_result）")
        dump(
            cur,
            """
            SELECT id, dkbm, cbfbm, fbfbm, result_status, is_changed, change_type,
                   change_reason, survey_status
            FROM survey_cbdkxx_result WHERE cbfbm = %s ORDER BY dkbm, id
            """,
            (peer,),
        )

        section("5. 两块争议地块当前归属（含已删除的行）")
        for dkbm in ("3213241000010200015", "3213241000010200014"):
            print(f"   --- dkbm={dkbm} ---")
            dump(
                cur,
                """
                SELECT r.id, r.dkbm, r.cbfbm, r.result_status, r.is_changed, r.change_type,
                       r.change_reason, d.scmj, d.dkmc, d.result_status AS dk_status
                FROM survey_cbdkxx_result r
                LEFT JOIN survey_dk_result d ON d.dkbm = r.dkbm
                WHERE r.dkbm = %s
                ORDER BY r.id DESC
                """,
                (dkbm,),
            )

        section("6. 变更记录（survey_change_record）—— 全批次，含对方")
        params = [target, peer]
        if uid:
            params.append(uid)
        dump(
            cur,
            """
            SELECT id, change_no, batch_id, contractor_uid, cbfbm, change_type,
                   change_status, change_reason, investigated_at,
                   before_summary, after_summary
            FROM survey_change_records
            WHERE cbfbm IN (%s, %s)
            ORDER BY id DESC
            LIMIT 60
            """,
            (target, peer),
        )

        section("7. 全库 rollback_swap_parcels 记录（看该动作是否曾落库）")
        dump(
            cur,
            """
            SELECT id, change_no, batch_id, contractor_uid, cbfbm, change_type,
                   change_status, change_reason, investigated_at, after_summary
            FROM survey_change_records
            WHERE change_type LIKE '%%swap%%'
            ORDER BY id DESC
            LIMIT 40
            """,
        )

        section("8. 目标户地块列表（survey_dk_result join 关联，含 resultStatus）")
        dump(
            cur,
            """
            SELECT r.dkbm, r.cbfbm, r.result_status, r.is_changed, r.change_type,
                   d.dkmc, d.scmj, d.result_status, d.change_type
            FROM survey_cbdkxx_result r
            LEFT JOIN survey_dk_result d ON d.dkbm = r.dkbm
            WHERE r.cbfbm = %s OR r.cbfbm = %s
            ORDER BY r.cbfbm, r.dkbm
            """,
            (target, peer),
        )


if __name__ == "__main__":
    main()
