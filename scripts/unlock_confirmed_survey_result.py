# -*- coding: utf-8 -*-
"""把被「确认」(survey_status='confirmed')锁成只读的承包方成果解锁，回到可编辑状态。

背景（设计约束，见 backend/app/services/survey/base.py）：
  - locked_survey_statuses = {"confirmed"} —— confirmed 是「编辑闸门」，
    一旦确认，承包方调查详情进入只读（前端 ContractorResultDialog.vue::isResultLocked /
    dataReadOnly；后端 _ensure_editable_batch_and_result 在保存时直接 400 拒绝）。
  - 系统**没有**撤回确认 / unconfirm / 取消确认 / 重开 任何接口或按钮
    （全局搜索 unconfirm|cancel_confirm|reopen|revert|撤回确认 只命中本类修复脚本）。
  - skipped（跳过）虽然是定案态，但**仍允许补录**，编辑闸门只含 confirmed；
    所以如果户其实是 skipped 而不是 confirmed，不需要解锁就能改。

本脚本做的事（与已验证的 _fix_013_unlock_014_restore.py 同口径）：
  A. 把 survey_cbf_result.survey_status 由 confirmed → surveyed，
     清掉 reviewer_id / reviewer_name / reviewed_at / confirmed_at / change_reason
     （change_reason 是确认时 _ensure_change_reasons 自动补的默认值，退回时一并清掉）。
  B. 同步把 survey_cbf_base.task_status 由 confirmed → surveyed，清 reviewed_at。
     （base 表没有 confirmed_at 列，task.py 那行赋值是静默无效的，不要照抄。）

⚠️ 本脚本**只解锁状态**，不撤销确认时可能已经发生的任何业务动作
   （互换、合户、分户、变更登记等）。如果误确认还连带触发了别的业务，
   解锁后需另行在界面上用对应「撤回」功能处理。

⚠️ 解锁后仍受其他闸门约束：
   - 批次必须是 active（base.py::_ensure_batch_editable_status 拦 finished）；
   - 该户任务必须分配给你（ensure_task_write_permission 拦未分配/分给他人的户）。

用法（默认 dry-run，只读不写）：
    runtime/windows/python/python.exe scripts/unlock_confirmed_survey_result.py --cbfbm 321324100001020013
    runtime/windows/python/python.exe scripts/unlock_confirmed_survey_result.py --result-id 44
    # 加 --apply 才真正落库
    runtime/windows/python/python.exe scripts/unlock_confirmed_survey_result.py --cbfbm 321324100001020013 --apply
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
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import psycopg  # noqa: E402

from app.core.config import settings  # noqa: E402

DSN = (
    f"host={settings.database_host} port={settings.database_port} "
    f"dbname={settings.database_name} user={settings.database_user} "
    f"password={settings.database_password}"
)

APPLY = "--apply" in sys.argv


def parse_target() -> tuple[str, str]:
    """从命令行解析定位条件，返回 (sql片段, 参数)。"""
    cbfbm = None
    result_id = None
    for i, a in enumerate(sys.argv):
        if a == "--cbfbm" and i + 1 < len(sys.argv):
            cbfbm = sys.argv[i + 1]
        elif a == "--result-id" and i + 1 < len(sys.argv):
            result_id = sys.argv[i + 1]
    if cbfbm:
        return "r.cbfbm = %s", (cbfbm,)
    if result_id:
        return "r.id = %s", (int(result_id),)
    print("✗ 用法: --cbfbm <承包方编码>  或  --result-id <result表id>  [--apply]")
    sys.exit(2)


def show(cur, sql, params=()):
    cur.execute(sql, params)
    cols = [d.name for d in cur.description]
    rows = cur.fetchall()
    print("   " + " | ".join(cols))
    for r in rows:
        print("   " + " | ".join(repr(v) for v in r))
    return rows


def main() -> None:
    if not APPLY and "--apply" not in sys.argv:
        pass
    where, params = parse_target()
    print(f"模式：{'★ APPLY（会写库）' if APPLY else 'dry-run（只读）'}")

    with psycopg.connect(DSN) as conn:
        cur = conn.cursor()

        # ---------- 前置校验 ----------
        print("\n=== 0. 前置校验（对不上就退出，不猜） ===")
        cur.execute(
            f"""
            SELECT r.id, r.cbfbm, r.survey_status, r.reviewer_name, r.confirmed_at,
                   b.id AS base_id, b.task_status, b.batch_id
              FROM survey_cbf_result r
              JOIN survey_cbf_base b ON b.contractor_uid = r.contractor_uid
             WHERE {where}
            """,
            params,
        )
        row = cur.fetchone()
        if not row:
            print("   ✗ 找不到匹配的承包方成果")
            sys.exit(2)
        (rid, cbfbm, sstatus, rev_name, confirmed_at, base_id, bstatus, batch_id) = row
        print(f"   result id={rid} cbfbm={cbfbm} survey_status={sstatus} reviewer={rev_name} confirmed_at={confirmed_at}")
        print(f"   base   id={base_id} task_status={bstatus} batch_id={batch_id}")

        problems: list[str] = []
        if sstatus != "confirmed":
            problems.append(f"survey_status 期望 confirmed，实际 {sstatus}（可能本来就可编辑，或属于 skipped 允许补录，无需解锁）")
        if bstatus != "confirmed":
            problems.append(f"base.task_status 期望 confirmed，实际 {bstatus}")

        cur.execute("SELECT status FROM survey_batch WHERE id = %s", (batch_id,))
        bstat = cur.fetchone()
        print(f"   batch  id={batch_id} status={bstat[0] if bstat else None}")
        if not bstat or bstat[0] != "active":
            problems.append(f"批次 status 必须是 active 才能解锁后继续编辑，实际 {bstat[0] if bstat else None}")

        if problems:
            print("\n✗ 前置校验未通过，已中止：")
            for p in problems:
                print("   -", p)
            sys.exit(2)
        print("   ✓ 全部通过")

        # ---------- 解锁 ----------
        print("\n=== 1. 解锁 result（confirmed → surveyed，清确认痕迹） ===")
        cur.execute(
            """
            UPDATE survey_cbf_result
               SET survey_status = 'surveyed',
                   reviewer_id   = NULL,
                   reviewer_name = NULL,
                   reviewed_at   = NULL,
                   confirmed_at  = NULL,
                   change_reason = NULL,
                   updated_at    = now()
             WHERE id = %s
            """,
            (rid,),
        )
        print(f"   result id={rid}: confirmed → surveyed，清 reviewer_*/reviewed_at/confirmed_at/change_reason")

        print("\n=== 2. 同步 base（task_status confirmed → surveyed，清 reviewed_at） ===")
        cur.execute(
            """
            UPDATE survey_cbf_base
               SET task_status = 'surveyed',
                   reviewed_at = NULL,
                   updated_at  = now()
             WHERE id = %s
            """,
            (base_id,),
        )
        print(f"   base   id={base_id}: task_status confirmed → surveyed，清 reviewed_at")

        # ---------- 复核 ----------
        print("\n=== 复核（事务内视图 = 提交后的样子） ===")
        show(
            cur,
            "SELECT id, cbfbm, survey_status, change_type, change_reason, reviewer_name, confirmed_at, updated_at "
            "FROM survey_cbf_result WHERE id = %s",
            (rid,),
        )
        show(
            cur,
            "SELECT id, cbfbm, task_status, reviewed_at, updated_at FROM survey_cbf_base WHERE id = %s",
            (base_id,),
        )

        if APPLY:
            conn.commit()
            print("\n★ 已提交。该户回到「已录入未定案」，可在界面上重新编辑 / 确认。")
        else:
            conn.rollback()
            print("\n（dry-run：已回滚，未写库。加 --apply 落库）")


if __name__ == "__main__":
    main()
