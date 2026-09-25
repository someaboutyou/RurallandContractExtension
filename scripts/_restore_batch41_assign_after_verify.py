"""复原 `_verify_batch_assign_scope.py`（旧版夹具）在批次 41 上留下的副作用。

背景：旧版夹具写死 `ORDER BY contractor_uid LIMIT 2` 取户，2026-09-24 10:17 那次
运行挑中了已被人分给「组级测试员」的 321324100001020011（刘修连），脚本收尾
「收回分配」时把它三列清成了 NULL。夹具已改为只挑「当前未分配」的户，这里把
被误清的那一行按原值写回；另两行当时就未分配、状态未变，只顺带复原 updated_at。

跑法：
  runtime/windows/python/python.exe scripts/_restore_batch41_assign_after_verify.py          # dry-run
  runtime/windows/python/python.exe scripts/_restore_batch41_assign_after_verify.py --apply  # 落库
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]

for _line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
    _t = _line.strip()
    if _t and not _t.startswith("#") and "=" in _t:
        _k, _v = _t.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())

import psycopg  # noqa: E402

APPLY = "--apply" in sys.argv
BATCH_ID = 41

# (cbfbm, assigned_to, assigned_to_name, assigned_at, updated_at) —— 均为脚本破坏前的原值
FIXES: list[tuple[str, int | None, str | None, str | None, str]] = [
    ("321324100001020011", 7, "组级测试员", "2026-09-24 10:02:35.469343+08", "2026-09-24 10:02:35.448076+08"),
    ("321324100001020012", None, None, None, "2026-09-22 21:37:36.831806+08"),
    ("321324100001020019", None, None, None, "2026-09-23 19:58:17.682458+08"),
]

conn = psycopg.connect(
    host=os.environ["DATABASE_HOST"],
    port=int(os.environ["DATABASE_PORT"]),
    dbname=os.environ["DATABASE_NAME"],
    user=os.environ["DATABASE_USER"],
    password=os.environ["DATABASE_PASSWORD"],
)
cur = conn.cursor()

print(f"批次 {BATCH_ID} 复原 {len(FIXES)} 行（模式 = {'APPLY' if APPLY else 'DRY-RUN'}）")
print()
for cbfbm, assigned_to, name, assigned_at, updated_at in FIXES:
    cur.execute(
        "SELECT assigned_to, assigned_to_name, assigned_at, updated_at FROM survey_cbf_base"
        " WHERE batch_id = %s AND cbfbm = %s",
        (BATCH_ID, cbfbm),
    )
    before = cur.fetchone()
    print(f"{cbfbm}")
    print(f"   before = {before}")
    if APPLY:
        cur.execute(
            "UPDATE survey_cbf_base SET assigned_to = %s, assigned_to_name = %s,"
            " assigned_at = %s, updated_at = %s WHERE batch_id = %s AND cbfbm = %s",
            (assigned_to, name, assigned_at, updated_at, BATCH_ID, cbfbm),
        )
        cur.execute(
            "SELECT assigned_to, assigned_to_name, assigned_at, updated_at FROM survey_cbf_base"
            " WHERE batch_id = %s AND cbfbm = %s",
            (BATCH_ID, cbfbm),
        )
        print(f"   after  = {cur.fetchone()}")
    print(f"   target = ({assigned_to}, {name!r}, {assigned_at}, {updated_at})")

if APPLY:
    conn.commit()
    print()
    cur.execute(
        "SELECT count(*) FROM survey_cbf_base WHERE batch_id = %s AND assigned_to IS NOT NULL",
        (BATCH_ID,),
    )
    print(f"批次 {BATCH_ID} 已分配户数 = {cur.fetchone()[0]}（应为 2）")
    cur.execute(
        "SELECT cbfbm, cbfmc, assigned_to, assigned_to_name FROM survey_cbf_base"
        " WHERE batch_id = %s AND assigned_to IS NOT NULL ORDER BY cbfbm",
        (BATCH_ID,),
    )
    for row in cur.fetchall():
        print(f"   {row}")
else:
    conn.rollback()
    print()
    print("（dry-run，未落库；加 --apply 执行）")

conn.close()
