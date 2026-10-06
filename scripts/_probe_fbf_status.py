# -*- coding: utf-8 -*-
"""只读取证：发包方（survey_fbf_result / survey_fbf_base）的成果状态与存量分布。

用途：
  1. 定性「保存发包方调查后状态不推进」是不是系统性问题（全库分布，而非个案）；
  2. 圈定存量回填范围（investigated_at 非空但 survey_status 仍是 not_surveyed 的行）；
  3. 核对人工新增发包方时 region_code 该取什么（对齐既有行）。

只读，不写库。运行：runtime/windows/python/python.exe scripts/_probe_fbf_status.py
"""
import os
import sys

os.environ.update({
    "DATABASE_HOST": "127.0.0.1",
    "DATABASE_PORT": "15432",
    "DATABASE_NAME": "erlunyanbao",
    "DATABASE_USER": "RurallandContractExtension",
    "DATABASE_PASSWORD": "dK9venBRbBRewDFAWYHRGdCM",
    "SECRET_KEY": "x",
})

import psycopg  # noqa: E402

DSN = (
    "host=127.0.0.1 port=15432 dbname=erlunyanbao "
    "user=RurallandContractExtension password=dK9venBRbBRewDFAWYHRGdCM"
)


def main() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        cur = conn.cursor()

        print("=== ① survey_fbf_result.survey_status 全库分布 ===")
        cur.execute(
            "SELECT survey_status, count(*) FROM survey_fbf_result "
            "GROUP BY survey_status ORDER BY count(*) DESC"
        )
        for st, n in cur.fetchall():
            print(f"  {st:<16} {n}")

        print("\n=== ② survey_fbf_base.task_status 全库分布 ===")
        cur.execute(
            "SELECT task_status, count(*) FROM survey_fbf_base "
            "GROUP BY task_status ORDER BY count(*) DESC"
        )
        for st, n in cur.fetchall():
            print(f"  {st:<16} {n}")

        print("\n=== ③ 按 change_type 看「被人工改过」的发包方（可作回填判据） ===")
        cur.execute(
            """
            SELECT change_type, count(*), count(*) FILTER (WHERE is_changed)
            FROM survey_fbf_result
            GROUP BY change_type ORDER BY count(*) DESC
            """
        )
        for ct, n, changed in cur.fetchall():
            print(f"  {ct:<20} 共 {n} 行，其中 is_changed=true {changed} 行")

        print("\n=== ④ survey_fbf_base 全部行（发包方待办标记，只有这几行） ===")
        cur.execute(
            """
            SELECT b.id, b.batch_id, b.result_id, b.fbfbm, b.task_status,
                   b.region_code, b.initialized_from_table, r.survey_status
            FROM survey_fbf_base b
            LEFT JOIN survey_fbf_result r ON r.id = b.result_id
            ORDER BY b.id
            """
        )
        for r in cur.fetchall():
            print(f"  base#{r[0]} batch={r[1]} result_id={r[2]} {r[3]} "
                  f"task_status={r[4]} region={r[5]!r} from={r[6]} "
                  f"→ result.survey_status={r[7]}")

        print("\n=== ⑤ 参照：最近 5 行发包方成果（region_code / tenant_code 取法） ===")
        cur.execute(
            """
            SELECT id, tenant_code, region_code, fbfbm, survey_status,
                   change_type, result_status, fbfdcy
            FROM survey_fbf_result
            ORDER BY id DESC
            LIMIT 5
            """
        )
        for r in cur.fetchall():
            print(f"  r#{r[0]} tenant={r[1]} region={r[2]!r} {r[3]} "
                  f"status={r[4]} chg={r[5]}/{r[6]} 调查员={r[7]}")


if __name__ == "__main__":
    main()
