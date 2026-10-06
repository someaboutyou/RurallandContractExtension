# -*- coding: utf-8 -*-
"""数据修复（**默认 dry-run**，加 --apply 才落库）：批次 41 承包方 013 / 014。

背景（2026-09-27）：
  用户在 013 上做完「互换 → 保存 → 重进 → 撤销互换」，点到了弹窗底部的
  「确认调查结果」（该按钮当时缺 `!hasPendingOperations` 闸门，已修），造成两件事：
    ① 待保存的 rollback_swap_parcels 被静默丢弃 ⇒ 互换仍生效；
    ② 013 被锁成 confirmed ⇒ 本户不可编辑，且**系统无撤回确认接口**，界面里出不来。

  另：本身份（小奥）的取证脚本拦截正则写错，误把 014 的一次「保存调查结果」落了库
  （2026-09-27 21:41:27，新增 change record 877 + 21 行 diffs）。

本脚本做两件事，**都在一个事务里**：
  A. 解锁 013（解除误确认，回到「已录入未定案」）—— 之后用户可在界面上重做「撤销互换」；
     ⚠️ 只解除"确认"这一个动作的痕迹，**不动**互换本身（873/874 与地块归属保持原样）。
  B. 回滚 014 的误落库 —— 删掉 877 及其 21 行 diffs，并把 result/base 恢复到快照值
     （快照来源：runtime/.state/_e2e_swap_rollback_ctx.json 的 `target` 字段，
       该文件生成于污染前 21:40）。

不做的（需要用户另行拍板）：
  · 不替用户执行「撤回互换」本身（要走界面，让业务代码正确写变更记录/地块归属）；
  · 不动 `survey_change_records.change_no` 序列（序列不回退 ⇒ 877 号段留空是正常的）。

用法：
    runtime/windows/python/python.exe scripts/_fix_013_unlock_014_restore.py            # 只看
    runtime/windows/python/python.exe scripts/_fix_013_unlock_014_restore.py --apply    # 落库
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

# 污染前的快照值（来自 _e2e_swap_rollback_ctx.json，生成于 2026-09-27 21:40）
SWAP_SAVED_AT = "2026-09-27 21:09:09.511417+08:00"

TARGET_013 = {"result_id": 44, "base_id": 100542, "cbfbm": "321324100001020013"}
TARGET_014 = {"result_id": 45, "base_id": 100543, "cbfbm": "321324100001020014"}
POLLUTED_CHANGE_ID = 877

APPLY = "--apply" in sys.argv


def show(cur, sql, params=()):
    cur.execute(sql, params)
    cols = [d.name for d in cur.description]
    rows = cur.fetchall()
    print("   " + " | ".join(cols))
    for r in rows:
        print("   " + " | ".join(repr(v) for v in r))
    return rows


def main() -> None:
    print(f"模式：{'★ APPLY（会写库）' if APPLY else 'dry-run（只读）'}")
    with psycopg.connect(DSN) as conn:
        cur = conn.cursor()

        # ---------- 前置校验：库里的现状必须和预期一致，否则拒绝执行 ----------
        print("\n=== 0. 前置校验（对不上就退出，不猜） ===")
        problems: list[str] = []

        cur.execute(
            "SELECT id, cbfbm, survey_status, reviewer_name, confirmed_at "
            "FROM survey_cbf_result WHERE id = %s",
            (TARGET_013["result_id"],),
        )
        r13 = cur.fetchone()
        print(f"   013 result: {r13}")
        if not r13 or r13[2] != "confirmed" or r13[1] != TARGET_013["cbfbm"]:
            problems.append(f"013 result 期望 confirmed/{TARGET_013['cbfbm']}，实际 {r13}")

        cur.execute(
            "SELECT id, cbfbm, task_status FROM survey_cbf_base WHERE id = %s",
            (TARGET_013["base_id"],),
        )
        b13 = cur.fetchone()
        print(f"   013 base  : {b13}")
        if not b13 or b13[2] != "confirmed":
            problems.append(f"013 base 期望 task_status=confirmed，实际 {b13}")

        cur.execute(
            "SELECT id, cbfbm, survey_status, investigator_name, investigated_at "
            "FROM survey_cbf_result WHERE id = %s",
            (TARGET_014["result_id"],),
        )
        r14 = cur.fetchone()
        print(f"   014 result: {r14}")
        if not r14 or r14[2] != "surveyed" or r14[1] != TARGET_014["cbfbm"]:
            problems.append(f"014 result 期望 surveyed/{TARGET_014['cbfbm']}，实际 {r14}")

        cur.execute(
            "SELECT id, cbfbm, task_status, change_count, investigated_at "
            "FROM survey_cbf_base WHERE id = %s",
            (TARGET_014["base_id"],),
        )
        b14 = cur.fetchone()
        print(f"   014 base  : {b14}")
        if not b14 or b14[2] != "surveyed":
            problems.append(f"014 base 期望 task_status=surveyed，实际 {b14}")

        cur.execute(
            "SELECT id, change_no, cbfbm, change_type, change_status FROM survey_change_records WHERE id = %s",
            (POLLUTED_CHANGE_ID,),
        )
        c877 = cur.fetchone()
        print(f"   污染记录  : {c877}")
        if not c877 or c877[2] != TARGET_014["cbfbm"] or c877[3] != "info_change":
            problems.append(f"change record {POLLUTED_CHANGE_ID} 期望 info_change/{TARGET_014['cbfbm']}，实际 {c877}")

        cur.execute("SELECT count(*) FROM survey_change_diffs WHERE change_id = %s", (POLLUTED_CHANGE_ID,))
        diff_count = cur.fetchone()[0]
        print(f"   污染 diffs: {diff_count} 行")

        # 交换是否仍生效（013 持 …0014 / 014 持 …0015）——本次**不改**，仅确认前提
        cur.execute(
            "SELECT dkbm, cbfbm FROM survey_cbdkxx_result "
            "WHERE dkbm IN ('3213241000010200014','3213241000010200015') ORDER BY dkbm"
        )
        holdings = cur.fetchall()
        print(f"   地块归属  : {holdings}")
        if sorted(x[1] for x in holdings) != [TARGET_013["cbfbm"], TARGET_014["cbfbm"]]:
            problems.append(f"地块归属与预期不符（互换可能已被撤）：{holdings}")

        if problems:
            print("\n✗ 前置校验未通过，已中止：")
            for p in problems:
                print("   -", p)
            sys.exit(2)
        print("   ✓ 全部通过")

        # ---------- A. 解锁 013 ----------
        print("\n=== A. 解锁 013（解除误确认，不动互换本身） ===")
        cur.execute(
            """
            UPDATE survey_cbf_result
               SET survey_status = 'surveyed',
                   reviewer_id   = NULL,
                   reviewer_name = NULL,
                   reviewed_at   = NULL,
                   confirmed_at  = NULL,
                   change_reason = NULL,          -- 确认时 _ensure_change_reasons 自动补的默认值
                   updated_at    = now()
             WHERE id = %s
            """,
            (TARGET_013["result_id"],),
        )
        print(f"   result id={TARGET_013['result_id']}: confirmed → surveyed，清 reviewer_*/reviewed_at/confirmed_at/change_reason")
        cur.execute(
            """
            UPDATE survey_cbf_base
               SET task_status = 'surveyed',
                   reviewed_at = NULL,
                   updated_at  = now()
             WHERE id = %s
            """,
            (TARGET_013["base_id"],),
        )
        print(f"   base   id={TARGET_013['base_id']}: task_status confirmed → surveyed，清 reviewed_at")
        print("   （注：survey_cbf_base 没有 confirmed_at 列，`task.py:426` 那行赋值是静默无效的）")

        # ---------- B. 回滚 014 的误落库 ----------
        print("\n=== B. 回滚 014 的误落库（删 877 + 21 行 diffs，状态回快照） ===")
        cur.execute("DELETE FROM survey_change_diffs WHERE change_id = %s", (POLLUTED_CHANGE_ID,))
        print(f"   删除 survey_change_diffs WHERE change_id={POLLUTED_CHANGE_ID} → {cur.rowcount} 行")
        cur.execute("DELETE FROM survey_change_records WHERE id = %s", (POLLUTED_CHANGE_ID,))
        print(f"   删除 survey_change_records id={POLLUTED_CHANGE_ID} → {cur.rowcount} 行")

        cur.execute(
            """
            UPDATE survey_cbf_result
               SET survey_status     = 'not_surveyed',
                   investigator_id   = NULL,
                   investigator_name = NULL,
                   investigated_at   = %s,
                   updated_at        = %s
             WHERE id = %s
            """,
            (SWAP_SAVED_AT, SWAP_SAVED_AT, TARGET_014["result_id"]),
        )
        print(f"   result id={TARGET_014['result_id']}: surveyed → not_surveyed，清 investigator_*，investigated_at 回 {SWAP_SAVED_AT}")

        cur.execute(
            """
            UPDATE survey_cbf_base
               SET task_status     = 'not_started',
                   change_count    = 1,
                   investigated_at = %s,
                   updated_at      = %s
             WHERE id = %s
            """,
            (SWAP_SAVED_AT, SWAP_SAVED_AT, TARGET_014["base_id"]),
        )
        print(f"   base   id={TARGET_014['base_id']}: surveyed → not_started，change_count → 1，investigated_at 回 {SWAP_SAVED_AT}")

        # ---------- 复核（在提交前读，dry-run 也能看到"将要变成的样子"） ----------
        print("\n=== 复核（事务内视图 = 提交后的样子） ===")
        show(
            cur,
            "SELECT id, cbfbm, survey_status, change_type, change_reason, reviewer_name, "
            "investigated_at, updated_at FROM survey_cbf_result WHERE id IN (44, 45) ORDER BY id",
        )
        show(
            cur,
            "SELECT id, cbfbm, task_status, has_change, change_count, investigated_at, reviewed_at "
            "FROM survey_cbf_base WHERE id IN (100542, 100543) ORDER BY id",
        )
        show(cur, "SELECT id, change_no, cbfbm, change_type, change_status FROM survey_change_records WHERE batch_id = 41 ORDER BY id DESC LIMIT 5")

        # ---------- 收尾 ----------
        if APPLY:
            conn.commit()
            print("\n★ 已提交。")
        else:
            conn.rollback()
            print("\n（dry-run：已回滚，未写库。加 --apply 落库）")


if __name__ == "__main__":
    main()
