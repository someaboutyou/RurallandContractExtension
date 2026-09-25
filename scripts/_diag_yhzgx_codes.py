# -*- coding: utf-8 -*-
"""只读诊断：`yhzgx`（与户主关系）到底用哪个码表示「户主」？

背景冲突
--------
- 代码硬编码 `YHZGX_MAP`（contract_template_service.py:99）= `01 户主 / 02 配偶 / 03 子女 …`
  —— 这是 NY/T 2539 的标准码，且**出件（合同/地籍表）在用它**。
- 项目记忆记载：字典 `nyt2539_c20_relation_to_head` 为 `01 本人 / 02 户主`，且真实数据
  `yhzgx='02'` 有十几万条、`'01'` 只有个位数。

二者不可能同时对。本脚本只读三个来源，把结论钉死：
  ① `dictionary_items` 里与"与户主关系"有关的条目（字典怎么定义）
  ② `survey_cbf_jtcy_result.yhzgx` 的取值分布（真实数据怎么写）
  ③ `is_household_head` 的真值分布 + 抽样真实户，看"哪个码的人"被标成户主

跑法：runtime/windows/python/python.exe scripts/_diag_yhzgx_codes.py
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
    "SECRET_KEY": "diag-only",
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

OUT: list[str] = []


def log(*parts) -> None:
    line = " ".join(str(p) for p in parts)
    OUT.append(line)
    print(line)


def main() -> None:
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            log("=" * 78)
            log("① 字典：与「户主关系」相关的条目（dictionary_items）")
            log("=" * 78)
            cur.execute(
                """
                SELECT dict_type, item_value, item_name, sort_order, enabled
                FROM dictionary_items
                WHERE dict_type ILIKE '%relation%'
                   OR dict_type ILIKE '%yhzgx%'
                   OR dict_type ILIKE '%c20%'
                   OR item_value IN ('01', '02')
                ORDER BY dict_type, sort_order, item_value
                """
            )
            rows = cur.fetchall()
            if not rows:
                log("  （没有匹配的字典条目）")
            for dict_type, item_value, item_name, sort_order, enabled in rows:
                log(f"  {dict_type:<40} {str(item_value):<4} {item_name}  (sort={sort_order}, enabled={enabled})")

            log("")
            log("=" * 78)
            log("② 真实数据：survey_cbf_jtcy_result.yhzgx 取值分布")
            log("=" * 78)
            cur.execute(
                """
                SELECT yhzgx, count(*) AS cnt, sum(CASE WHEN is_household_head THEN 1 ELSE 0 END) AS head_cnt
                FROM survey_cbf_jtcy_result
                GROUP BY yhzgx
                ORDER BY cnt DESC
                """
            )
            for code, cnt, head_cnt in cur.fetchall():
                log(f"  yhzgx={str(code):<6} 成员 {cnt:>9,}   其中 is_household_head=true: {head_cnt:>7,}")

            log("")
            log("=" * 78)
            log("③ is_household_head 总分布")
            log("=" * 78)
            cur.execute(
                """
                SELECT is_household_head, count(*) FROM survey_cbf_jtcy_result
                GROUP BY is_household_head ORDER BY 1
                """
            )
            for flag, cnt in cur.fetchall():
                log(f"  is_household_head={str(flag):<6} {cnt:>10,}")

            log("")
            log("=" * 78)
            log("④ 抽样：真实户里「被标成户主」的那个人的 yhzgx 是什么码")
            log("=" * 78)
            cur.execute(
                """
                SELECT m.contractor_uid, m.cbfbm, m.cyxm, m.yhzgx, m.is_household_head
                FROM survey_cbf_jtcy_result m
                WHERE m.is_household_head IS TRUE
                LIMIT 10
                """
            )
            head_rows = cur.fetchall()
            if not head_rows:
                log("  （全库没有任何 is_household_head=true 的成员）")
            for uid, cbfbm, name, yhzgx, flag in head_rows:
                log(f"  {cbfbm}  {name:<8} yhzgx={yhzgx}  head={flag}")

            log("")
            log("  对照：随便取 3 个真实户，看成员的 yhzgx 组成")
            cur.execute(
                """
                SELECT cbfbm, cyxm, yhzgx, is_household_head
                FROM survey_cbf_jtcy_result
                WHERE cbfbm IN (
                    SELECT cbfbm FROM survey_cbf_jtcy_result
                    GROUP BY cbfbm HAVING count(*) >= 3 ORDER BY cbfbm LIMIT 3
                )
                ORDER BY cbfbm, id
                """
            )
            for cbfbm, name, yhzgx, flag in cur.fetchall():
                log(f"  {cbfbm}  {str(name):<8} yhzgx={yhzgx}  head={flag}")

            log("")
            log("=" * 78)
            log("⑤ survey_cbf_base 侧（任务表）同样看一遍 yhzgx 分布")
            log("=" * 78)
            cur.execute(
                """
                SELECT yhzgx, count(*) FROM survey_cbf_jtcy_base
                GROUP BY yhzgx ORDER BY 2 DESC LIMIT 10
                """
            )
            for code, cnt in cur.fetchall():
                log(f"  base yhzgx={str(code):<6} {cnt:>9,}")

    dest = ROOT / "runtime" / ".state" / "_diag_yhzgx_codes.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(OUT), encoding="utf-8")
    print(f"\n[written] {dest}")


if __name__ == "__main__":
    main()
