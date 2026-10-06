# -*- coding: utf-8 -*-
"""只读诊断：复现「撤回互换」这一步到底会不会失败。

三问：
  Q1 前端 `handleRollbackSavedSwap` 依赖 `props.tasks` 里能找到对方承包方
     （321324100001020014）—— 本批次任务列表里到底有没有它？
  Q2 前端保存前会跑 `ContractorMemberPanel.validateIdNos()` —— 这一户的
     承包方 / 成员证件号有没有过不了校验的（会把保存直接拦下）？
  Q3 后端 `rollback_swap_parcels` 在这份真实数据上直接调用会不会抛异常？
     （在事务内调用，收尾 rollback，零落库）

用法：runtime/windows/python/python.exe scripts/_probe_rollback_swap_repro.py
"""
from __future__ import annotations

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
from app.models.survey import SurveyCbfBase, SurveyCbfJtcyResult, SurveyCbfResult  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.survey import survey_service  # noqa: E402

TARGET = "321324100001020013"
PEER = "321324100001020014"
BATCH = 41
SWAP_CHANGE_ID = 873  # 013 的那条 swap_parcels 变更记录

WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
CHECK = "10X98765432"


def id_check(s: str) -> tuple[bool, str]:
    s = (s or "").strip().upper()
    if len(s) != 18:
        return False, f"长度 {len(s)}"
    if not s[:17].isdigit():
        return False, "前17位非数字"
    if s[17] not in "0123456789X":
        return False, "校验位非法字符"
    total = sum(int(c) * w for c, w in zip(s[:17], WEIGHTS))
    expect = CHECK[total % 11]
    if expect != s[17]:
        return False, f"校验位应为 {expect}"
    return True, "ok"


def section(t: str) -> None:
    print(f"\n=== {t} ===")


def main() -> None:
    db = SessionLocal()
    try:
        admin = db.scalars(select(User).where(User.id == 1)).first()
        _ = admin.role
        set_current_user(db, admin)
        print(f"当前操作人：id={admin.id} {admin.real_name} scope={admin.role.data_scope}")

        section("Q1 本批次 41 的任务列表里有没有对方承包方")
        rows = db.scalars(
            select(SurveyCbfBase).where(SurveyCbfBase.batch_id == BATCH).order_by(SurveyCbfBase.cbfbm)
        ).all()
        for r in rows:
            flag = "  <== 对方户" if r.cbfbm == PEER else ("  <== 目标户" if r.cbfbm == TARGET else "")
            print(f"   {r.cbfbm} {r.cbfmc} task={r.task_status} assigned={r.assigned_to_name}{flag}")
        peer_base = db.scalars(
            select(SurveyCbfBase).where(SurveyCbfBase.batch_id == BATCH, SurveyCbfBase.cbfbm == PEER)
        ).first()
        print(f"   -> 对方户存在 = {peer_base is not None}; contractor_uid = {getattr(peer_base, 'contractor_uid', None)}")
        print(f"   -> region_code = {getattr(peer_base, 'region_code', None)}")

        section("Q2 证件号校验（前端 validateIdNos 口径的校验位）")
        cbf = db.scalars(select(SurveyCbfResult).where(SurveyCbfResult.cbfbm == TARGET)).first()
        ok, why = id_check(cbf.cbfzjhm)
        print(f"   承包方 {cbf.cbfmc} {cbf.cbfzjhm} -> {ok} {why}")
        members = db.scalars(
            select(SurveyCbfJtcyResult).where(SurveyCbfJtcyResult.contractor_uid == cbf.contractor_uid)
        ).all()
        for m in members:
            ok, why = id_check(m.cyzjhm)
            print(f"   成员 {m.cyxm} {m.cyzjhm} -> {ok} {why}")

        section("Q3 直接调用 rollback_swap_parcels（事务内，收尾回滚）")
        # 该户现在已是 confirmed，闸门会先拦下；为了单独验"撤回互换"这条路径，
        # 先在事务里把它改回 surveyed（随后整体 rollback，不落库）。
        cbf.survey_status = "surveyed"
        cbf.result_status = "normal"
        db.flush()
        db.execute  # noqa: B018
        try:
            out = survey_service.rollback_swap_parcels(
                db, BATCH, cbf.contractor_uid, SWAP_CHANGE_ID,
                {"reason": "probe"}, admin, commit=False,
            )
            print(f"   ✔ 调用成功，返回 {out}")
            db.flush()
            for dkbm in ("3213241000010200014", "3213241000010200015"):
                from app.models.survey import SurveyCbdkxxResult
                rel = db.scalars(
                    select(SurveyCbdkxxResult).where(SurveyCbdkxxResult.dkbm == dkbm)
                ).first()
                print(f"   地块 {dkbm} 现在归属 = {rel.cbfbm} (change_type={rel.change_type})")
        except Exception as exc:  # noqa: BLE001
            print(f"   ✘ 抛异常：{type(exc).__name__}: {exc}")
            traceback.print_exc()
    finally:
        db.rollback()
        db.close()
        print("\n[事务已回滚] 真实库未被修改。")


if __name__ == "__main__":
    main()
