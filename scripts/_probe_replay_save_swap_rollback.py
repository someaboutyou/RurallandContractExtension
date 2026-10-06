# -*- coding: utf-8 -*-
"""离线回放：把 CDP 抓到的真实保存请求体喂给 `update_result`，看它抛什么。

背景（2026-09-27 21:43 取证）：
    · 前端「撤回互换 → 加入待保存 → 保存调查结果」提交的 payload **确实带上了**
      `rollback_swap_parcels`（changeId=874）；
    · 但库里毫无变化：地块归属没回退、没有 rollback 变更记录、873/874 的
      change_status 仍是 surveyed —— 说明这次保存**整体失败并回滚了**。
    · 而直接调 `rollback_swap_parcels(commit=False)`（_probe_rollback_swap_repro.py）
      却能跑通 —— 差异只能在 `update_result` 的上下文里。

本脚本在**事务内**重放同一份 payload（`Session.commit` 打成 no-op，收尾 rollback），
把异常原样打出来。零落库。

用法：runtime/windows/python/python.exe scripts/_probe_replay_save_swap_rollback.py
"""
from __future__ import annotations

import json
import os
import sys
import traceback
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

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal, set_current_user  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.survey import survey_service  # noqa: E402

PAYLOAD_PATH = ROOT / "runtime" / ".state" / "_e2e_swap_save_payload.json"
BATCH = 41
UID = "e4c63a91-3616-54c8-8146-edd9b0f96b34"  # 321324100001020014


def main() -> None:
    payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))
    print(f"payload 顶层字段：{sorted(payload.keys())}")
    print(f"pendingOperations：{[(o.get('type'), (o.get('payload') or {}).get('changeId')) for o in payload.get('pendingOperations') or []]}")

    db = SessionLocal()
    # 把 commit 打成 no-op：所有落库动作都留在事务里，最后整体 rollback。
    original_commit = db.commit
    db.commit = lambda *a, **kw: None  # type: ignore[assignment]
    try:
        admin = db.scalars(select(User).where(User.id == 1)).first()
        _ = admin.role
        set_current_user(db, admin)
        try:
            out = survey_service.update_result(db, BATCH, UID, payload, admin)
            print("✔ update_result 成功，返回：", str(out)[:300])
            db.flush()
            from app.models.survey import SurveyCbdkxxResult

            for dkbm in ("3213241000010200014", "3213241000010200015"):
                rel = db.scalars(select(SurveyCbdkxxResult).where(SurveyCbdkxxResult.dkbm == dkbm)).first()
                print(f"   地块 {dkbm} 归属 = {rel.cbfbm} ({rel.change_type})")
        except Exception as exc:  # noqa: BLE001
            print(f"\n✘ update_result 抛异常：{type(exc).__name__}")
            detail = getattr(exc, "detail", None)
            if detail is not None:
                print("   HTTPException.detail =", detail, " status =", getattr(exc, "status_code", None))
            traceback.print_exc()
    finally:
        db.commit = original_commit  # type: ignore[assignment]
        db.rollback()
        db.close()
        print("\n[事务已回滚] 真实库未被修改。")


if __name__ == "__main__":
    main()
