# -*- coding: utf-8 -*-
"""存量回填：按统一口径重算 `survey_cbf_jtcy_result.is_household_head`（幂等）。

为什么需要
----------
`is_household_head` 历史上按 `yhzgx == "01"` 计算，而字典
`nyt2539_c20_relation_to_head` 与真实数据里**户主是 `02`**
（全库 60.2 万成员里该标记只有 1 条为 true）⇒ 这个字段实际上一直是失效的。

它被这些地方消费：
  · `change_household_head` 用它找"原户主"（失效 ⇒ 找不到 ⇒ 原户主的 `02` 不会被清掉
    ⇒ 变更户主后一个户里出现两个"户主"）；
  · `rollback_merge_household` / 成员维护回滚用它还原；
  · `MergeHouseholdDialog` 用它预选默认户主。

口径（与 `app.services.relation_codes.pick_household_head` 完全一致）
-------------------------------------------------------------------
    ① 已是 `is_household_head=true` 的成员（保留应用自己的指定）
    ② `yhzgx == '02'`（户主）
    ③ `yhzgx == '01'`（本人）
    ④ 兜底：该户 id 最小的成员

只动 `is_household_head`，**不改写 `yhzgx`**（关系码是导入的原始数据，属另一个决策）。

跑法
----
    # 默认 dry-run，只统计不写库
    runtime/windows/python/python.exe scripts/fix_household_head_flags.py
    # 真正执行
    runtime/windows/python/python.exe scripts/fix_household_head_flags.py --apply
"""
from __future__ import annotations

import argparse
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
    "SECRET_KEY": "maintenance-only",
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

# 窗口排序 = pick_household_head 的优先级：
#   已标记为户主(true 排前) → yhzgx='02'(户主) → yhzgx='01'(本人) → id 最小
# PG 里 true > false，DESC 即"标记过的优先"。
RANKED_CTE = """
WITH ranked AS (
    SELECT id,
           row_number() OVER (
               PARTITION BY contractor_uid
               ORDER BY (is_household_head IS TRUE) DESC,
                        (yhzgx = '02') DESC,
                        (yhzgx = '01') DESC,
                        id ASC
           ) AS rn
    FROM survey_cbf_jtcy_result
)
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="回填 survey_cbf_jtcy_result.is_household_head")
    parser.add_argument("--apply", action="store_true", help="真正写库；缺省为 dry-run")
    args = parser.parse_args()

    mode = "APPLY（写库）" if args.apply else "DRY-RUN（只统计，不写库）"
    print("=" * 78)
    print(f"户主标记回填　模式：{mode}")
    print("=" * 78)

    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        # ① 总览
        cur.execute("""
            SELECT count(*) AS members,
                   count(DISTINCT contractor_uid) AS households,
                   count(*) FILTER (WHERE is_household_head) AS flagged_now
            FROM survey_cbf_jtcy_result
        """)
        members, households, flagged_now = cur.fetchone()
        print(f"成员 {members:,} 名 / 户 {households:,} 个 / 当前 is_household_head=true 共 {flagged_now:,} 条")

        # ② 画像：每户「户主类码」个数（02 或 01）
        cur.execute("""
            WITH per_house AS (
                SELECT contractor_uid,
                       count(*) FILTER (WHERE yhzgx IN ('02', '01')) AS head_codes
                FROM survey_cbf_jtcy_result
                GROUP BY contractor_uid
            )
            SELECT count(*) FILTER (WHERE head_codes = 0) AS none,
                   count(*) FILTER (WHERE head_codes = 1) AS exactly_one,
                   count(*) FILTER (WHERE head_codes > 1) AS multi
            FROM per_house
        """)
        none_cnt, one_cnt, multi_cnt = cur.fetchone()
        print(f"户主类码分布：无 {none_cnt:,} 户 / 恰好 1 个 {one_cnt:,} 户 / 多个 {multi_cnt:,} 户")
        if none_cnt:
            print(f"  ⚠️ 有 {none_cnt:,} 户一个户主类码都没有 ⇒ 回填会按兜底规则取其第一条成员")

        # ③ 受影响行数
        cur.execute(RANKED_CTE + """
            SELECT count(*)
            FROM survey_cbf_jtcy_result m
            JOIN ranked r ON r.id = m.id
            WHERE m.is_household_head IS DISTINCT FROM (r.rn = 1)
        """)
        affected = cur.fetchone()[0]
        print(f"需要改写的成员行：{affected:,}")

        if not args.apply:
            print("\n（dry-run 结束；确认无误后加 --apply 执行）")
            return

        cur.execute(RANKED_CTE + """
            UPDATE survey_cbf_jtcy_result m
            SET is_household_head = (r.rn = 1)
            FROM ranked r
            WHERE m.id = r.id
              AND m.is_household_head IS DISTINCT FROM (r.rn = 1)
        """)
        updated = cur.rowcount
        conn.commit()
        print(f"已改写 {updated:,} 行")

        # ④ 复核：每户应恰好一条 true
        cur.execute("""
            WITH per_house AS (
                SELECT contractor_uid,
                       count(*) FILTER (WHERE is_household_head) AS heads
                FROM survey_cbf_jtcy_result
                GROUP BY contractor_uid
            )
            SELECT count(*) FILTER (WHERE heads = 0) AS zero,
                   count(*) FILTER (WHERE heads = 1) AS one,
                   count(*) FILTER (WHERE heads > 1) AS multi
            FROM per_house
        """)
        zero, one, multi = cur.fetchone()
        print(f"复核：每户恰好 1 个户主 {one:,} 户 / 0 个 {zero:,} 户 / 多于 1 个 {multi:,} 户")
        print("✅ 回填完成（幂等：重复执行 affected 应为 0）" if zero == 0 and multi == 0
              else "⚠️ 仍有异常户，请检查数据")


if __name__ == "__main__":
    main()
