# -*- coding: utf-8 -*-
"""数据修复（**默认 dry-run**，加 --apply 才落库）：

把批次 41 里 0014 / 0015 两块地块关联的「变更态」还原成互换前的原值。

背景（2026-09-28）：用户重测「互换 → 保存 → 撤回互换 → 保存」后，发现被互换的两块地
仍显示为「变更」。根因是 `swap_parcels` / `rollback_swap_parcels` 会覆写地块的
is_changed / change_type，撤回时不还原（代码已修，见 parcel_ops.py）。但**已经写坏的
存量行**不会自己变回去，需要本脚本刷一次。

目标值判定依据（都是可核验的，不是猜）：
  1) 库里全部变更记录中，提到这两块地的**只有** swap_parcels / rollback_swap_parcels
     这 8 条（873/874/884/885/887/888/890/891），没有任何 add/remove/split 类记录
     ⇒ 这两块地除互换外没有别的变更动作；
  2) 本批次其余 14 块地块关联全部是 is_changed=False / change_type='none'
     ⇒ 「未变更」就是本批次的原始基线；
  3) 地块主表 survey_dk_result 里这两块地本来就是 False / none（互换只动关联表）。
  ⇒ 互换前的原值 = is_changed=False / change_type='none' / change_reason=NULL

不做的事：
  · 不动地块归属（互换已经撤回，归属本来就是对的）；
  · 不动 8 条 swap 系变更记录（那是审计留痕，且 873/874/884/885 的 change_status
    另有含义）；
  · 不动 change_count / has_change（属"次数统计"口径，另议）。

用法：
    runtime/windows/python/python.exe scripts/_fix_0120_parcel_change_state.py            # 只看
    runtime/windows/python/python.exe scripts/_fix_0120_parcel_change_state.py --apply    # 落库
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
    "SECRET_KEY": "repair-only",
})

import psycopg  # noqa: E402

DSN = (
    "host=127.0.0.1 port=15432 dbname=erlunyanbao "
    "user=RurallandContractExtension password=dK9venBRbBRewDFAWYHRGdCM"
)
BATCH = 41
# dkbm -> 互换前的原值持有者（互换已撤回，归属本来就是对的，这里只做校验）
EXPECT = {
    "3213241000010200014": "321324100001020014",
    "3213241000010200015": "321324100001020013",
}
APPLY = "--apply" in sys.argv


def show(cur, sql, params=()):
    cur.execute(sql, params)
    cols = [d.name for d in cur.description]
    print("   " + " | ".join(cols))
    for r in cur.fetchall():
        print("   " + " | ".join(repr(v) for v in r))


def main() -> None:
    print(f"模式：{'★ APPLY（会写库）' if APPLY else 'dry-run（只读）'}")
    with psycopg.connect(DSN) as conn:
        cur = conn.cursor()
        problems: list[str] = []

        print("\n=== 0. 前置校验（对不上就退出，不猜） ===")
        cur.execute(
            "SELECT id, dkbm, cbfbm, result_status, is_changed, change_type, change_reason "
            "FROM survey_cbdkxx_result WHERE dkbm = ANY(%s) ORDER BY dkbm",
            (list(EXPECT),),
        )
        rows = cur.fetchall()
        for r in rows:
            print(f"   {r}")
        if len(rows) != 2:
            problems.append(f"期望 2 行地块关联，实际 {len(rows)}")
        for rid, dkbm, cbfbm, result_status, is_changed, change_type, reason in rows:
            if cbfbm != EXPECT[dkbm]:
                problems.append(f"{dkbm} 归属 {cbfbm} 与预期 {EXPECT[dkbm]} 不符（互换可能又被做过）")
            if not is_changed or change_type != "rollback_swap_parcels":
                problems.append(f"{dkbm} 当前 {is_changed}/{change_type}，不是待修复态（可能已修过）")
            if result_status != "normal":
                problems.append(f"{dkbm} result_status={result_status}，非正常态，需人工判断")

        # 依据 1：除互换外，没有任何别的变更记录动过这两块地
        cur.execute(
            """
            SELECT id, change_no, change_type, change_status, cbfbm
              FROM survey_change_records
             WHERE (before_summary::text LIKE %s OR before_summary::text LIKE %s
                 OR after_summary::text LIKE %s OR after_summary::text LIKE %s)
               AND change_type NOT IN ('swap_parcels', 'rollback_swap_parcels')
            """,
            (
                "%3213241000010200014%", "%3213241000010200015%",
                "%3213241000010200014%", "%3213241000010200015%",
            ),
        )
        other = cur.fetchall()
        print(f"\n   除互换系以外的、动过这两块地的变更记录：{len(other)} 条")
        for r in other:
            print("   ", r)
        if other:
            problems.append("存在非互换类的变更记录动过这两块地 ⇒ 原值不是简单的 none，需人工判断")

        # 依据 2：本批次其余地块的基线
        cur.execute(
            "SELECT count(*), count(*) FILTER (WHERE is_changed = false AND change_type = 'none') "
            "FROM survey_cbdkxx_result WHERE cbfbm LIKE '32132410000102001%%'"
        )
        total, untouched = cur.fetchone()
        print(f"   本批次地块关联：共 {total} 块，其中「未变更」{untouched} 块")

        if problems:
            print("\n✗ 前置校验未通过，已中止：")
            for p in problems:
                print("   -", p)
            sys.exit(2)
        print("   ✓ 全部通过")

        print("\n=== A. 把这两块地的变更态还原为互换前的原值 ===")
        cur.execute(
            """
            UPDATE survey_cbdkxx_result
               SET is_changed = false,
                   change_type = 'none',
                   change_reason = NULL
             WHERE dkbm = ANY(%s)
               AND change_type = 'rollback_swap_parcels'
            """,
            (list(EXPECT),),
        )
        print(f"   更新行数 = {cur.rowcount}（期望 2）")
        if cur.rowcount != 2:
            problems.append(f"更新行数 {cur.rowcount} != 2，中止")
            conn.rollback()
            print("\n✗ 更新行数不符，已回滚。")
            sys.exit(2)

        print("\n=== 复核 ===")
        show(
            cur,
            "SELECT dkbm, cbfbm, result_status, is_changed, change_type, change_reason "
            "FROM survey_cbdkxx_result WHERE dkbm = ANY(%s) ORDER BY dkbm",
            (list(EXPECT),),
        )

        if APPLY:
            conn.commit()
            print("\n★ 已提交。")
        else:
            conn.rollback()
            print("\n（dry-run：已回滚，未写库。加 --apply 落库）")


if __name__ == "__main__":
    main()
