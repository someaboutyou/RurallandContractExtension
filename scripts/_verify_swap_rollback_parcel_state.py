# -*- coding: utf-8 -*-
"""离线验收：互换 → 撤回互换 之后，地块的「变更态」是否还原成互换前的样子。

背景（2026-09-28）：用户重测「互换 → 保存 → 撤回互换 → 保存」后发现，被互换的两块地
在撤回后仍显示为「变更」。根因：`swap_parcels` 无条件覆写地块的
is_changed / change_type / change_reason，而 `rollback_swap_parcels` 又用
`change_type="rollback_swap_parcels"` 再覆写一次 ⇒ 净未变的地块挂着 swap 系类型，
前端 `parcelStatusLabel()` 落到 `isChanged → "变更"`。

本脚本在**一个事务里**跑 4 个场景，收尾整体 rollback，零落库。

  S1  互换 → 断言地块被标成 swap_parcels，且互换记录里存下了互换前的变更态快照
  S2  撤回互换 → 断言地块变更态**还原**为互换前（none / is_changed=False）
  S3  负向对照：互换前先给地块挂上别的变更类型 → 撤回后应还原成**那个类型**
      （证明是"还原快照"，不是"硬编码成 none"）
  S4  老数据（记录里没有快照）→ 断言走兼容分支，仍按未变更还原

用法：runtime/windows/python/python.exe scripts/_verify_swap_rollback_parcel_state.py
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
    "SECRET_KEY": "verify-only",
})
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal, set_current_user  # noqa: E402
from app.models.survey import SurveyCbfBase, SurveyCbdkxxResult, SurveyChangeRecord  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.survey import survey_service  # noqa: E402

BATCH = 41
HOST_CBFBM = "321324100001020013"          # 发起方
PEER_CBFBM = "321324100001020014"          # 对手方
HOST_DKBM = "3213241000010200015"          # 发起方持有、要被换出去的地块
PEER_DKBM = "3213241000010200014"          # 对手方持有、要被换进来的地块

RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    RESULTS.append((bool(ok), name, detail))
    print(f"   {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> None:
    db = SessionLocal()
    try:
        admin = db.scalars(select(User).where(User.id == 1)).first()
        _ = admin.role
        set_current_user(db, admin)

        def relation(dkbm: str) -> SurveyCbdkxxResult:
            return db.scalars(
                select(SurveyCbdkxxResult).where(SurveyCbdkxxResult.dkbm == dkbm)
            ).first()

        def uid_of(cbfbm: str) -> str:
            base = db.scalars(
                select(SurveyCbfBase).where(
                    SurveyCbfBase.batch_id == BATCH, SurveyCbfBase.cbfbm == cbfbm
                )
            ).first()
            return base.contractor_uid

        def latest_swap_record(uid: str) -> SurveyChangeRecord:
            return db.scalars(
                select(SurveyChangeRecord)
                .where(
                    SurveyChangeRecord.batch_id == BATCH,
                    SurveyChangeRecord.contractor_uid == uid,
                    SurveyChangeRecord.change_type == "swap_parcels",
                )
                .order_by(SurveyChangeRecord.id.desc())
                .execution_options(skip_tenant_scope=True)
            ).first()

        def state_of(dkbm: str) -> tuple[bool, str, str | None]:
            row = relation(dkbm)
            return bool(row.is_changed), row.change_type, row.change_reason

        def do_swap() -> None:
            survey_service.swap_parcels(
                db, BATCH, host_uid,
                {
                    "targetContractorUid": peer_uid,
                    "sourceDkbms": [HOST_DKBM],
                    "targetDkbms": [PEER_DKBM],
                    "reason": "验收用互换",
                },
                admin, commit=False,
            )

        host_uid, peer_uid = uid_of(HOST_CBFBM), uid_of(PEER_CBFBM)

        section("0. 起始状态（互换前）")
        print(f"   发起方 {HOST_CBFBM} 持有 {HOST_DKBM} → {state_of(HOST_DKBM)}")
        print(f"   对手方 {PEER_CBFBM} 持有 {PEER_DKBM} → {state_of(PEER_DKBM)}")
        start_host, start_peer = state_of(HOST_DKBM), state_of(PEER_DKBM)
        check(relation(HOST_DKBM).cbfbm == HOST_CBFBM, "前置：起始归属正确（发起方持 HOST_DKBM）",
              relation(HOST_DKBM).cbfbm)
        check(relation(PEER_DKBM).cbfbm == PEER_CBFBM, "前置：起始归属正确（对手方持 PEER_DKBM）",
              relation(PEER_DKBM).cbfbm)

        # ---------------------------------------------------------------- S1
        section("S1 互换：地块应被标成 swap_parcels，且记录里存下互换前的变更态快照")
        do_swap()
        db.flush()
        check(relation(HOST_DKBM).cbfbm == PEER_CBFBM, "互换后 HOST_DKBM 归对手方", relation(HOST_DKBM).cbfbm)
        check(relation(PEER_DKBM).cbfbm == HOST_CBFBM, "互换后 PEER_DKBM 归发起方", relation(PEER_DKBM).cbfbm)
        check(state_of(HOST_DKBM)[0] and state_of(HOST_DKBM)[1] == "swap_parcels",
              "互换后 HOST_DKBM 标记为变更/swap_parcels", str(state_of(HOST_DKBM)))
        check(state_of(PEER_DKBM)[0] and state_of(PEER_DKBM)[1] == "swap_parcels",
              "互换后 PEER_DKBM 标记为变更/swap_parcels", str(state_of(PEER_DKBM)))

        host_rec = latest_swap_record(host_uid)
        peer_rec = latest_swap_record(peer_uid)
        host_states = (host_rec.before_summary or {}).get("source_relation_states") or {}
        peer_states = (peer_rec.before_summary or {}).get("source_relation_states") or {}
        check(bool(host_states), "发起方互换记录里存下了互换前快照", f"{len(host_states)} 块地")
        check(bool(peer_states), "对手方互换记录里也存下了完整的互换前快照",
              f"{len(peer_states)} 块地")
        check(
            {HOST_DKBM, PEER_DKBM}.issubset(set(host_states)),
            "快照覆盖互换涉及的全部地块（两户各存一份完整快照）",
            str(sorted(host_states)),
        )
        check(
            host_states.get(HOST_DKBM, {}).get("change_type") == start_host[1]
            and bool(host_states.get(HOST_DKBM, {}).get("is_changed")) == start_host[0],
            "快照记的是「互换前」的值（不是互换后的）", str(host_states.get(HOST_DKBM)),
        )

        # ---------------------------------------------------------------- S2
        section("S2 撤回互换：地块变更态应还原成互换前的样子（这是本次修复的核心）")
        survey_service.rollback_swap_parcels(
            db, BATCH, host_uid, host_rec.id, {"reason": "验收用撤回"}, admin, commit=False,
        )
        db.flush()
        check(relation(HOST_DKBM).cbfbm == HOST_CBFBM, "撤回后 HOST_DKBM 归属复原", relation(HOST_DKBM).cbfbm)
        check(relation(PEER_DKBM).cbfbm == PEER_CBFBM, "撤回后 PEER_DKBM 归属复原", relation(PEER_DKBM).cbfbm)
        # 期望值取"互换前实测到的状态"，不写死 —— 否则夹具状态一变就误报。
        check(state_of(HOST_DKBM) == start_host,
              "撤回后 HOST_DKBM 还原为互换前的状态", f"{state_of(HOST_DKBM)} vs 互换前 {start_host}")
        check(state_of(PEER_DKBM) == start_peer,
              "撤回后 PEER_DKBM 还原为互换前的状态", f"{state_of(PEER_DKBM)} vs 互换前 {start_peer}")
        check(state_of(HOST_DKBM)[1] not in {"swap_parcels", "rollback_swap_parcels"}
              and state_of(PEER_DKBM)[1] not in {"swap_parcels", "rollback_swap_parcels"},
              "撤回后地块上不再残留 swap 系 change_type（界面不会再把它们显示成「变更」）",
              f"{state_of(HOST_DKBM)[1]} / {state_of(PEER_DKBM)[1]}")

        # --------------------------------------------------------------- S2b
        section("S2b 复刻用户场景：真正的「未变更」地块，互换后撤回必须回到「正常」")
        relation(HOST_DKBM).is_changed = False
        relation(HOST_DKBM).change_type = "none"
        relation(HOST_DKBM).change_reason = None
        relation(PEER_DKBM).is_changed = False
        relation(PEER_DKBM).change_type = "none"
        relation(PEER_DKBM).change_reason = None
        db.flush()
        do_swap()
        db.flush()
        rec2b = latest_swap_record(host_uid)
        check(state_of(HOST_DKBM) == (True, "swap_parcels", "验收用互换"),
              "互换后确实标成「变更/swap_parcels」", str(state_of(HOST_DKBM)))
        survey_service.rollback_swap_parcels(
            db, BATCH, host_uid, rec2b.id, {"reason": "验收用撤回"}, admin, commit=False,
        )
        db.flush()
        check(state_of(HOST_DKBM) == (False, "none", None),
              "撤回后 HOST_DKBM = 未变更/正常（用户报的那个「变更」应消失）", str(state_of(HOST_DKBM)))
        check(state_of(PEER_DKBM) == (False, "none", None),
              "撤回后 PEER_DKBM = 未变更/正常", str(state_of(PEER_DKBM)))

        # ---------------------------------------------------------------- S3
        section("S3 负向对照：互换前若已有别的变更类型，撤回后应还原成那个类型（而非硬编码 none）")
        relation(HOST_DKBM).is_changed = True
        relation(HOST_DKBM).change_type = "add_parcel"
        relation(HOST_DKBM).change_reason = "验收用：互换前已存在的变更"
        db.flush()
        do_swap()
        db.flush()
        rec3 = latest_swap_record(host_uid)
        check(state_of(HOST_DKBM)[1] == "swap_parcels", "互换后确实被覆写成 swap_parcels",
              str(state_of(HOST_DKBM)))
        survey_service.rollback_swap_parcels(
            db, BATCH, host_uid, rec3.id, {"reason": "验收用撤回"}, admin, commit=False,
        )
        db.flush()
        check(state_of(HOST_DKBM) == (True, "add_parcel", "验收用：互换前已存在的变更"),
              "撤回后还原成互换前的 add_parcel（证明是还原快照，不是硬编码 none）",
              str(state_of(HOST_DKBM)))

        # ---------------------------------------------------------------- S4
        section("S4 老数据兼容：记录里没有快照时，仍按「未变更」还原")
        relation(HOST_DKBM).is_changed = False
        relation(HOST_DKBM).change_type = "none"
        relation(HOST_DKBM).change_reason = None
        db.flush()
        do_swap()
        db.flush()
        rec4 = latest_swap_record(host_uid)
        stripped = dict(rec4.before_summary or {})
        stripped.pop("source_relation_states", None)
        rec4.before_summary = stripped          # 模拟修复前写入的老记录
        db.flush()
        survey_service.rollback_swap_parcels(
            db, BATCH, host_uid, rec4.id, {"reason": "验收用撤回"}, admin, commit=False,
        )
        db.flush()
        check(state_of(HOST_DKBM) == (False, "none", None),
              "无快照时：按未变更还原（兼容 873/874 一类老记录）", str(state_of(HOST_DKBM)))
        check(state_of(PEER_DKBM) == (False, "none", None),
              "无快照时：对手方地块同样还原", str(state_of(PEER_DKBM)))

    except Exception as exc:  # noqa: BLE001
        print(f"\n✘ 脚本异常：{type(exc).__name__}: {exc}")
        traceback.print_exc()
        RESULTS.append((False, "脚本执行未抛异常", f"{type(exc).__name__}: {exc}"))
    finally:
        db.rollback()
        db.close()
        print("\n[事务已回滚] 真实库未被修改。")

        passed = sum(1 for ok, _, _ in RESULTS if ok)
        print("\n" + "=" * 60)
        print(f"断言 {len(RESULTS)} 项：通过 {passed}，失败 {len(RESULTS) - passed}")
        for ok, name, detail in RESULTS:
            if not ok:
                print(f"  FAIL  {name}   [{detail}]")
        sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
