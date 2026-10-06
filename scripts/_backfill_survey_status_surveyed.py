# -*- coding: utf-8 -*-
"""存量回填：把「已录入过、但成果状态仍停在 not_surveyed」的户推进为 surveyed。

背景（2026-09-27）：
    `update_result` 原写法 `result.survey_status = payload.get("surveyStatus") or "surveyed"`
    依赖前端回传，而前端弹窗把表单整体展开提交、`surveyStatus` 又是打开时从库里回填的
    旧值 ⇒ 全库 `survey_status = 'surveyed'` 是 **0 行**，`task_status` 永远停在
    `not_surveyed` ⇒ 普通户拿不到「确认」按钮。后端已在
    `base.py::resolve_saved_survey_status` 里改为服务端裁定，本脚本负责把
    **改动之前就已经录过数据**的存量行补齐。

判据（不猜、只看已有事实）：
    · `survey_cbf_result.investigated_at IS NOT NULL` —— 这一户确实被保存过
      （该字段只在 `update_result` / 各操作动作里写入）
    · 且 `survey_status = 'not_surveyed'` —— 状态没跟上
任务态同步：只动 `task_status in ('not_started', 'not_surveyed')` 的行，
**不碰** deregistered / confirmed / skipped / surveyed 等已定案状态。

用法：
    python scripts/_backfill_survey_status_surveyed.py            # 试运行（默认，不写库）
    python scripts/_backfill_survey_status_surveyed.py --apply    # 真正落库

幂等：重复执行不会重复改（第二次匹配 0 行）。
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
    "SECRET_KEY": "backfill-only",
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

RESULT_SQL = """
UPDATE survey_cbf_result
SET survey_status = 'surveyed'
WHERE survey_status = 'not_surveyed'
  AND investigated_at IS NOT NULL
"""

BASE_SQL = """
UPDATE survey_cbf_base b
SET task_status = 'surveyed'
FROM survey_cbf_result r
WHERE r.contractor_uid = b.contractor_uid
  AND r.survey_status = 'surveyed'
  AND r.investigated_at IS NOT NULL
  AND b.task_status IN ('not_started', 'not_surveyed')
"""


def main() -> None:
    apply = "--apply" in sys.argv

    with psycopg.connect(DSN, autocommit=False) as conn:
        cur = conn.cursor()

        print("=== 回填前的候选行（result 侧）===")
        cur.execute(
            """
            SELECT r.id, r.cbfbm, r.cbfmc, r.survey_status, r.result_status,
                   r.change_type, r.investigator_name, r.investigated_at,
                   b.id, b.batch_id, b.task_status
            FROM survey_cbf_result r
            LEFT JOIN survey_cbf_base b ON b.contractor_uid = r.contractor_uid
            WHERE r.survey_status = 'not_surveyed' AND r.investigated_at IS NOT NULL
            ORDER BY r.id
            """
        )
        rows = cur.fetchall()
        print(f"  共 {len(rows)} 行")
        for r in rows:
            cur.execute(
                """
                SELECT
                  (SELECT count(*) FROM survey_cbf_jtcy_result WHERE contractor_uid = t.contractor_uid),
                  (SELECT count(*) FROM survey_cbdkxx_result WHERE cbfbm = t.cbfbm),
                  (SELECT count(*) FROM survey_change_records WHERE contractor_uid = t.contractor_uid)
                FROM survey_cbf_result t WHERE t.id = %s
                """,
                (r[0],),
            )
            members, parcels, changes = cur.fetchone()
            print(f"    result#{r[0]} {r[1]} {r[2]}  status={r[3]} result={r[4]} chg={r[5]} "
                  f"investigator={r[6]} at={r[7]}")
            print(f"      → base#{r[8]} batch={r[9]} task_status={r[10]}"
                  f"  | 成员 {members} / 地块关联 {parcels} / 变更记录 {changes}"
                  f"  | {'有证据⇒推进' if members or parcels or changes else '⚠️ 无证据，需人工确认'}")

        cur.execute(RESULT_SQL)
        result_affected = cur.rowcount
        cur.execute(BASE_SQL)
        base_affected = cur.rowcount
        print(f"\n=== 待更新：result {result_affected} 行 / base {base_affected} 行 ===")

        if not apply:
            conn.rollback()
            print("\n[试运行] 已回滚，未写库。加 --apply 才真正落库。")
            return

        conn.commit()
        print("\n[已落库] 校验：")
        cur.execute("SELECT survey_status, count(*) FROM survey_cbf_result GROUP BY 1 ORDER BY 2 DESC")
        print("   survey_cbf_result.survey_status :", cur.fetchall())
        cur.execute("SELECT task_status, count(*) FROM survey_cbf_base GROUP BY 1 ORDER BY 2 DESC")
        print("   survey_cbf_base.task_status     :", cur.fetchall())


if __name__ == "__main__":
    main()
