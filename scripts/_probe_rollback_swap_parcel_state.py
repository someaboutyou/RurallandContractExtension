# -*- coding: utf-8 -*-
"""只读探针：撤回互换后，地块关联上的 is_changed / change_type 到底是什么。

背景（2026-09-28）：用户重测「互换 → 保存 → 撤回互换 → 保存」后发现，
被互换的两块地在撤回后仍显示为「变更」。

用法：runtime/windows/python/python.exe scripts/_probe_rollback_swap_parcel_state.py
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

import psycopg  # noqa: E402

DSN = (
    "host=127.0.0.1 port=15432 dbname=erlunyanbao "
    "user=RurallandContractExtension password=dK9venBRbBRewDFAWYHRGdCM"
)
BATCH = 41
CBFBMS = ("321324100001020013", "321324100001020014")
DKBMS = ("3213241000010200014", "3213241000010200015")


def rows(cur, sql, params=()):
    cur.execute(sql, params)
    cols = [d.name for d in cur.description]
    return cols, cur.fetchall()


def table(title: str, cur, sql: str, params=()) -> None:
    print(f"\n=== {title} ===")
    cols, data = rows(cur, sql, params)
    if not data:
        print("   （无数据）")
        return
    print("   " + " | ".join(cols))
    for r in data:
        print("   " + " | ".join(str(v) for v in r))


def main() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        cur = conn.cursor()

        table(
            "承包方成果状态",
            cur,
            # survey_cbf_result 没有 batch_id 列（按 cbfbm 定位即可，本批次内 cbfbm 唯一）
            "SELECT id, cbfbm, survey_status, change_type, change_reason, "
            "investigator_name, investigated_at, reviewer_name, confirmed_at "
            "FROM survey_cbf_result WHERE cbfbm = ANY(%s) ORDER BY cbfbm",
            (list(CBFBMS),),
        )

        table(
            "任务行状态",
            cur,
            "SELECT id, cbfbm, task_status, has_change, change_count, investigated_at, reviewed_at "
            "FROM survey_cbf_base WHERE batch_id = %s AND cbfbm = ANY(%s) ORDER BY cbfbm",
            (BATCH, list(CBFBMS)),
        )

        table(
            "★ 地块关联（撤回互换后，用户看到「变更」的地方）",
            cur,
            "SELECT dkbm, cbfbm, is_changed, change_type, change_reason, result_status "
            "FROM survey_cbdkxx_result WHERE dkbm = ANY(%s) ORDER BY dkbm, cbfbm",
            (list(DKBMS),),
        )

        table(
            "变更记录（batch 41 最近 8 条）",
            cur,
            "SELECT id, change_no, cbfbm, change_type, change_status, change_reason "
            "FROM survey_change_records WHERE batch_id = %s ORDER BY id DESC LIMIT 8",
            (BATCH,),
        )

        print("\n=== 最近 2 条变更记录的 summary（看有没有存原值快照）===")
        cols, data = rows(
            cur,
            "SELECT id, change_type, before_summary, after_summary "
            "FROM survey_change_records WHERE batch_id = %s ORDER BY id DESC LIMIT 2",
            (BATCH,),
        )
        for rid, ctype, before, after in data:
            print(f"\n   --- id={rid} type={ctype} ---")
            print(f"   before_summary = {before}")
            print(f"   after_summary  = {after}")

        table(
            "同类对照：已被撤回的移除/切割，其地块 change_type 是什么",
            cur,
            """
            SELECT r.dkbm, r.cbfbm, r.is_changed, r.change_type, r.result_status
              FROM survey_cbdkxx_result r
             WHERE r.cbfbm IN (
                   SELECT cbfbm FROM survey_change_records
                    WHERE batch_id = %s AND change_type = 'rollback_remove_parcel'
                   UNION
                   SELECT cbfbm FROM survey_change_records
                    WHERE batch_id = %s AND change_type = 'rollback_split_parcel')
             ORDER BY r.dkbm
            """,
            (BATCH, BATCH),
        )


if __name__ == "__main__":
    main()
