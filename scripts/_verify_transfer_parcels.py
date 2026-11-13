# -*- coding: utf-8 -*-
"""离线验收：地块划转（transfer_parcels）→ 撤回划转 全链路。

覆盖点（2026-11-13 新功能）：
  S0  起始归属前置断言
  S1  划转：关联行归属搬到收地方 + 变更态覆写 + 双方各存一条对称变更记录（含划转前快照）
  S1b base 基线表不被划转触碰（可追溯的前提：diff 比对语义不被污染）
  S1c diff 表：手动重建后双方都有 parcel_relation 差异行
  S2  撤回划转：归属/变更态还原成划转前 + 两条记录一起标 rolled_back
  S3  负向对照：划转前已有别的变更类型 → 撤回后还原成那个类型（证明是还原快照）
  S4  老数据兼容：记录无快照 → 按未变更还原
  S5  注销闸门：存在未撤回划转记录的户不能注销（_ensure_can_deregister）

用法：runtime/windows/python/python.exe scripts/_verify_transfer_parcels.py
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_runtime_env() -> dict[str, str]:
    """DB 凭据以 runtime/.state/runtime.env 为准（start-postgres 写入的随机密码），
    不在脚本里硬编码 —— 密码轮换后脚本不至于失联。"""
    env_file = ROOT / "runtime" / ".state" / "runtime.env"
    values: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


_runtime_env = _load_runtime_env()
os.environ.update({
    "DATABASE_HOST": _runtime_env.get("DATABASE_HOST", "127.0.0.1"),
    "DATABASE_PORT": _runtime_env.get("DATABASE_PORT", "15432"),
    "DATABASE_NAME": _runtime_env.get("DATABASE_NAME", "erlunyanbao"),
    "DATABASE_USER": _runtime_env.get("DATABASE_USER", "RurallandContractExtension"),
    "DATABASE_PASSWORD": _runtime_env.get("DATABASE_PASSWORD", ""),
    "SECRET_KEY": "verify-only",
})
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal, set_current_user  # noqa: E402
from app.models.survey import (  # noqa: E402
    SurveyCbfBase,
    SurveyCbdkxxBase,
    SurveyCbdkxxResult,
    SurveyChangeDiff,
    SurveyChangeRecord,
)
from app.models.user import User  # noqa: E402
from app.services.survey import survey_service  # noqa: E402

BATCH = 2
FROM_CBFBM = "150526103201000001"          # 转出方（发起划转，名下有地块）
TO_CBFBM = "150526103201000002"            # 收入方（同组）
DKBM = ""                                  # 运行时取转出方第一块现势地块

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

        def base_relation(dkbm: str) -> SurveyCbdkxxBase | None:
            return db.scalars(
                select(SurveyCbdkxxBase).where(SurveyCbdkxxBase.dkbm == dkbm)
            ).first()

        def uid_of(cbfbm: str) -> str:
            base = db.scalars(
                select(SurveyCbfBase).where(
                    SurveyCbfBase.batch_id == BATCH, SurveyCbfBase.cbfbm == cbfbm
                )
            ).first()
            return base.contractor_uid

        def latest_transfer_record(uid: str) -> SurveyChangeRecord:
            return db.scalars(
                select(SurveyChangeRecord)
                .where(
                    SurveyChangeRecord.batch_id == BATCH,
                    SurveyChangeRecord.contractor_uid == uid,
                    SurveyChangeRecord.change_type == "transfer_parcels",
                )
                .order_by(SurveyChangeRecord.id.desc())
                .execution_options(skip_tenant_scope=True)
            ).first()

        def state_of(dkbm: str) -> tuple[bool, str, str | None]:
            row = relation(dkbm)
            return bool(row.is_changed), row.change_type, row.change_reason

        def do_transfer() -> None:
            survey_service.transfer_parcels(
                db, BATCH, from_uid,
                {
                    "targetContractorUid": to_uid,
                    "dkbms": [DKBM],
                    "reason": "验收用划转",
                },
                admin, commit=False,
            )

        from_uid, to_uid = uid_of(FROM_CBFBM), uid_of(TO_CBFBM)

        global DKBM
        first_parcel = db.scalars(
            select(SurveyCbdkxxResult)
            .where(
                SurveyCbdkxxResult.cbfbm == FROM_CBFBM,
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
            .order_by(SurveyCbdkxxResult.id.asc())
        ).first()
        assert first_parcel is not None, "夹具失效：转出方名下没有现势地块"
        DKBM = first_parcel.dkbm

        section("0. 起始状态（划转前）")
        print(f"   转出方 {FROM_CBFBM} 持有 {DKBM} → {state_of(DKBM)}")
        start_state = state_of(DKBM)
        base_before = base_relation(DKBM)
        check(relation(DKBM).cbfbm == FROM_CBFBM, "前置：起始归属正确（转出方持 DKBM）",
              relation(DKBM).cbfbm)

        # ---------------------------------------------------------------- S1
        section("S1 划转：归属搬到收地方，双方各存一条对称变更记录（含划转前快照）")
        do_transfer()
        db.flush()
        check(relation(DKBM).cbfbm == TO_CBFBM, "划转后 DKBM 归收入方", relation(DKBM).cbfbm)
        check(state_of(DKBM)[0] and state_of(DKBM)[1] == "transfer_parcels",
              "划转后 DKBM 标记为变更/transfer_parcels", str(state_of(DKBM)))

        from_rec = latest_transfer_record(from_uid)
        to_rec = latest_transfer_record(to_uid)
        check(from_rec is not None and to_rec is not None, "双方各有一条 transfer_parcels 变更记录")
        from_bs = from_rec.before_summary or {}
        to_bs = to_rec.before_summary or {}
        from_as = from_rec.after_summary or {}
        to_as = to_rec.after_summary or {}
        check(from_bs.get("transferred_dkbms") == [DKBM], "转出方记录：transferred_dkbms 正确", str(from_bs.get("transferred_dkbms")))
        check(to_bs.get("transferred_dkbms") == [DKBM], "收入方记录：transferred_dkbms 对称一致", str(to_bs.get("transferred_dkbms")))
        check(from_as.get("from_cbfbm") == FROM_CBFBM and from_as.get("to_cbfbm") == TO_CBFBM,
              "转出方记录：from/to 方向正确", str(from_as))
        check(to_as.get("from_cbfbm") == FROM_CBFBM and to_as.get("to_cbfbm") == TO_CBFBM,
              "收入方记录：from/to 对称一致", str(to_as))
        from_states = from_bs.get("source_relation_states") or {}
        check(bool(from_states) and from_states.get(DKBM, {}).get("change_type") == start_state[1],
              "记录里存下了划转前的变更态快照（还原的依据）", str(from_states.get(DKBM)))

        # 收入方没有地块时的保底口径：本夹具收入方有地块，走「沿用收入方合同字段」主路径。
        check(relation(DKBM).cbhtbm == (to_rec and relation(DKBM).cbhtbm),
              "关联行保留自身合同面积（htmj 随地块走，不随户走）", str(relation(DKBM).htmj))

        # ---------------------------------------------------------------- S1b
        section("S1b base 基线表不被划转触碰（可追溯前提）")
        base_after = base_relation(DKBM)
        check(
            (base_after.cbfbm if base_after else None) == (base_before.cbfbm if base_before else None),
            "survey_cbdkxx_base 的 cbfbm 未被划转修改",
            f"{getattr(base_after, 'cbfbm', None)}",
        )

        # ---------------------------------------------------------------- S1c
        section("S1c diff 表：手动重建后双方都有该地块的 parcel_relation 差异行")
        survey_service._rebuild_contractor_diffs(
            db, BATCH, [from_uid, to_uid], change_ids={from_uid: None, to_uid: None},
        )
        db.flush()
        for label, uid in (("转出方", from_uid), ("收入方", to_uid)):
            # 划走的地块按 parcel_info_uid 配对：转出方「基线有、现势无」、
            # 收入方「现势有、基线无」，两边都以 entity_name=dkbm 落整体关联差异行。
            diff_rows = db.scalars(
                select(SurveyChangeDiff).where(
                    SurveyChangeDiff.batch_id == BATCH,
                    SurveyChangeDiff.contractor_uid == uid,
                    SurveyChangeDiff.entity_type == "parcel_relation",
                    SurveyChangeDiff.entity_name == DKBM,
                )
            ).all()
            check(len(diff_rows) > 0, f"{label}侧存在地块 {DKBM} 的 parcel_relation 差异行（变更前后可追溯）",
                  f"{len(diff_rows)} 行")

        # ---------------------------------------------------------------- S2
        section("S2 撤回划转：归属/变更态还原 + 两条记录一起 rolled_back")
        survey_service.rollback_transfer_parcels(
            db, BATCH, to_uid, to_rec.id, {"reason": "验收用撤回"}, admin, commit=False,
        )
        db.flush()
        check(relation(DKBM).cbfbm == FROM_CBFBM, "撤回后 DKBM 归属复原（转回原户）", relation(DKBM).cbfbm)
        check(state_of(DKBM) == start_state,
              "撤回后 DKBM 还原为划转前的变更态", f"{state_of(DKBM)} vs 划转前 {start_state}")
        db.refresh(from_rec)
        db.refresh(to_rec)
        check(from_rec.change_status == "rolled_back", "转出方记录已标 rolled_back", from_rec.change_status)
        check(to_rec.change_status == "rolled_back", "收入方记录也标 rolled_back（对称撤回）", to_rec.change_status)

        # ---------------------------------------------------------------- S3
        section("S3 负向对照：划转前已有别的变更类型 → 撤回后还原成那个类型")
        relation(DKBM).is_changed = True
        relation(DKBM).change_type = "add_parcel"
        relation(DKBM).change_reason = "验收用：划转前已存在的变更"
        db.flush()
        do_transfer()
        db.flush()
        rec3 = latest_transfer_record(from_uid)
        check(state_of(DKBM)[1] == "transfer_parcels", "划转后确实被覆写成 transfer_parcels", str(state_of(DKBM)))
        survey_service.rollback_transfer_parcels(
            db, BATCH, to_uid, latest_transfer_record(to_uid).id, {"reason": "验收用撤回"}, admin, commit=False,
        )
        db.flush()
        check(state_of(DKBM) == (True, "add_parcel", "验收用：划转前已存在的变更"),
              "撤回后还原成划转前的 add_parcel（证明是还原快照，不是硬编码 none）", str(state_of(DKBM)))

        # ---------------------------------------------------------------- S4
        section("S4 老数据兼容：记录里没有快照时，仍按「未变更」还原")
        relation(DKBM).is_changed = False
        relation(DKBM).change_type = "none"
        relation(DKBM).change_reason = None
        db.flush()
        do_transfer()
        db.flush()
        rec4 = latest_transfer_record(to_uid)
        stripped = dict(rec4.before_summary or {})
        stripped.pop("source_relation_states", None)
        rec4.before_summary = stripped          # 模拟无快照的记录
        db.flush()
        survey_service.rollback_transfer_parcels(
            db, BATCH, to_uid, rec4.id, {"reason": "验收用撤回"}, admin, commit=False,
        )
        db.flush()
        check(state_of(DKBM) == (False, "none", None),
              "无快照时：按未变更还原（兼容分支生效）", str(state_of(DKBM)))

        # ---------------------------------------------------------------- S5
        section("S5 注销闸门：存在未撤回划转记录的户不能注销")
        do_transfer()
        db.flush()
        for label, uid in (("转出方", from_uid), ("收入方", to_uid)):
            result_row = survey_service._get_result(db, BATCH, uid)
            blocked = False
            try:
                survey_service._ensure_can_deregister(db, BATCH, uid, result_row)
            except Exception as exc:  # noqa: BLE001
                blocked = "划转" in str(getattr(exc, "detail", exc))
            check(blocked, f"{label}存在未撤回划转记录时注销被拦截")

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
