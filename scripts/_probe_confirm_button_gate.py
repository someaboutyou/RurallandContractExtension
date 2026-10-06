# -*- coding: utf-8 -*-
"""只读诊断：「/surveys 列表里某户没有『确认』按钮」的取证脚本。

背景（2026-09-27 定位）：
    前端 SurveyView.vue 的确认按钮条件是
        canManage && row.taskStatus === 'surveyed'
    而后端 TaskService.confirm_result 允许的准入集合是
        {surveyed, changed, unchanged}
    两处口径不一致；叠加「保存调查结果不推进 survey_status」，
    普通户保存后 task_status 恒为 not_surveyed ⇒ 确认按钮永不出现。

用法：
    runtime/windows/python/python.exe scripts/_probe_confirm_button_gate.py [承包方编码]

本脚本只读，不写任何数据。
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

# 前端按钮准入集合（SurveyView.vue:142）vs 后端准入集合（task.py:381）
FRONT_ALLOWED = {"surveyed"}
BACK_ALLOWED = {"surveyed", "changed", "unchanged"}


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "321324100001020019"

    with psycopg.connect(DSN, autocommit=True) as conn:
        cur = conn.cursor()

        section(f"1. 目标户 {target} 的任务行（survey_cbf_base）")
        cur.execute(
            """
            SELECT id, batch_id, region_code, contractor_uid, cbfbm, source_cbfbm, cbfmc,
                   task_status, has_change, change_count, assigned_to_name,
                   investigated_at, reviewed_at
            FROM survey_cbf_base WHERE cbfbm = %s OR source_cbfbm = %s
            ORDER BY batch_id, id
            """,
            (target, target),
        )
        base_rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        for row in base_rows:
            print("   ---")
            for k, v in zip(cols, row):
                print(f"     {k:18} = {v!r}")

        uids = [r[3] for r in base_rows]
        section(f"2. 目标户的调查成果行（survey_cbf_result）")
        for uid in uids:
            cur.execute(
                """
                SELECT id, contractor_uid, cbfbm, cbfmc,
                       survey_status, result_status, change_type, is_changed,
                       investigator_name, investigated_at, confirmed_at
                FROM survey_cbf_result WHERE contractor_uid = %s
                """,
                (uid,),
            )
            rows = cur.fetchall()
            cols2 = [d.name for d in cur.description]
            for row in rows:
                print("   ---")
                for k, v in zip(cols2, row):
                    print(f"     {k:18} = {v!r}")

        section("3. 按钮判据判定")
        for row in base_rows:
            ts = row[7]
            print(f"   承包方 {row[4]}：task_status = {ts!r}")
            print(f"     前端（SurveyView.vue:142）能否出现『确认』 = {ts in FRONT_ALLOWED}")
            print(f"     后端（task.py:381）是否接受确认         = {ts in BACK_ALLOWED}")

        section("4. 全库状态分布（判断是个别户还是系统性问题）")
        cur.execute("SELECT task_status, count(*) FROM survey_cbf_base GROUP BY 1 ORDER BY 2 DESC")
        print("   survey_cbf_base.task_status :", cur.fetchall())
        cur.execute("SELECT survey_status, count(*) FROM survey_cbf_result GROUP BY 1 ORDER BY 2 DESC")
        print("   survey_cbf_result.survey_status :", cur.fetchall())
        cur.execute(
            "SELECT count(*) FROM survey_cbf_result "
            "WHERE survey_status = 'not_surveyed' AND investigated_at IS NOT NULL"
        )
        print("   「已录入过(investigated_at 非空)但状态仍 not_surveyed」的户数 =", cur.fetchone()[0])

        section("5. 操作人权限核对（canManage = contractors.manage）")
        cur.execute(
            """
            SELECT u.id, u.username, u.real_name, r.name AS role_name
            FROM users u LEFT JOIN roles r ON r.id = u.role_id
            ORDER BY u.id
            """
        )
        for r in cur.fetchall():
            print("   ", r)
        cur.execute(
            """
            SELECT r.id, r.name FROM role_permissions rp
            JOIN permissions p ON p.id = rp.permission_id
            JOIN roles r ON r.id = rp.role_id
            WHERE p.code = 'contractors.manage' ORDER BY r.id
            """
        )
        print("   持有 contractors.manage 的角色：", cur.fetchall())

        section("6. 同批次各户 base/result 状态对照")
        for bid in sorted({r[1] for r in base_rows}):
            cur.execute(
                """
                SELECT b.cbfbm, b.task_status, r.survey_status, r.result_status,
                       r.change_type, r.investigator_name, r.updated_at
                FROM survey_cbf_base b
                LEFT JOIN survey_cbf_result r ON r.contractor_uid = b.contractor_uid
                WHERE b.batch_id = %s ORDER BY b.id
                """,
                (bid,),
            )
            print(f"   batch_id={bid}")
            for r in cur.fetchall():
                print("     ", r)


if __name__ == "__main__":
    main()
