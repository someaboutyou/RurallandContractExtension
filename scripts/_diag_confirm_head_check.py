# -*- coding: utf-8 -*-
"""只读诊断：`_validate_confirmable` 的户主校验对**真实户**是否必然报错？

`base.py:126` 的判据是 `member.is_household_head or member.yhzgx == "01"`，
并要求 `len(household_heads) == 1`，否则 400 "request failed"。

已知：`is_household_head=true` 全库仅 1 条；`yhzgx='01'` 全库仅 1 条；
而真实户主用 `02`（17.98 万条）。⇒ 真实户很可能 `household_heads == 0`。

本脚本按"当前判据"与"修正后判据"各算一遍，量化影响面。

跑法：runtime/windows/python/python.exe scripts/_diag_confirm_head_check.py
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
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        log("说明：old_pass = 现行判据(01) 恰好 1 个户主的户数；new_pass = 修正判据(02→01) 恰好 1 个")
        log("")
        cur.execute("""
            WITH h AS (
                SELECT r.contractor_uid, r.cbflx,
                       count(m.id) AS member_cnt,
                       count(m.id) FILTER (WHERE m.is_household_head OR m.yhzgx = '01') AS heads_old,
                       count(m.id) FILTER (WHERE m.is_household_head OR m.yhzgx IN ('02', '01')) AS heads_new,
                       count(m.id) FILTER (WHERE m.yhzgx = '02') AS heads_02
                FROM survey_cbf_result r
                LEFT JOIN survey_cbf_jtcy_result m ON m.contractor_uid = r.contractor_uid
                GROUP BY r.contractor_uid, r.cbflx
            )
            SELECT cbflx, count(*) AS households,
                   count(*) FILTER (WHERE member_cnt = 0) AS no_member,
                   count(*) FILTER (WHERE heads_old = 1) AS old_pass,
                   count(*) FILTER (WHERE heads_new = 1) AS new_pass,
                   count(*) FILTER (WHERE heads_02 = 1) AS by_02_pass,
                   count(*) FILTER (WHERE member_cnt > 0 AND heads_02 = 0) AS member_but_no_02,
                   count(*) FILTER (WHERE heads_02 > 1) AS multi_02
            FROM h GROUP BY cbflx ORDER BY cbflx
        """)
        log(f"  {'cbflx':<7}{'户数':>10}{'无成员':>9}{'现行通过':>10}{'修正通过':>10}{'恰1个02':>10}{'有成员无02':>12}{'多个02':>9}")
        for row in cur.fetchall():
            cbflx, households, no_member, old_pass, new_pass, by_02, no_02, multi = row
            log(f"  {str(cbflx):<7}{households:>10,}{no_member:>9,}{old_pass:>10,}{new_pass:>10,}{by_02:>10,}{no_02:>12,}{multi:>9,}")

        log("")
        log("=" * 78)
        log("抽样：有成员但没有 02 的户（这类户在现行判据下必然确认失败）")
        log("=" * 78)
        cur.execute("""
            WITH h AS (
                SELECT r.contractor_uid, r.cbfbm, r.cbfmc,
                       count(m.id) AS member_cnt,
                       count(m.id) FILTER (WHERE m.yhzgx = '02') AS heads_02,
                       array_agg(m.yhzgx ORDER BY m.id) AS codes
                FROM survey_cbf_result r
                LEFT JOIN survey_cbf_jtcy_result m ON m.contractor_uid = r.contractor_uid
                WHERE r.cbflx = '1'
                GROUP BY r.contractor_uid, r.cbfbm, r.cbfmc
            )
            SELECT cbfbm, cbfmc, member_cnt, codes FROM h
            WHERE member_cnt > 0 AND heads_02 = 0 LIMIT 10
        """)
        rows = cur.fetchall()
        if not rows:
            log("  （没有：全部有成员的 cbflx=1 户都恰好有一个 02）")
        for cbfbm, cbfmc, cnt, codes in rows:
            log(f"  {cbfbm}  {cbfmc}  成员{cnt}  yhzgx={codes}")

    dest = ROOT / "runtime" / ".state" / "_diag_confirm_head_check.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(OUT), encoding="utf-8")
    print(f"\n[written] {dest}")


if __name__ == "__main__":
    main()
