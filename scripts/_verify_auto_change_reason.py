# -*- coding: utf-8 -*-
"""离线验收：合户/分户的「变化原因」由系统自动生成。

零写入：D 组走 merge_household(commit=False) 只 flush，验完 rollback，
并断言新编码在库中不存在。

验收项：
  A. 纯函数（文案生成规则）
     A1 空原因 → 合户新户文案带原承包方名称
     A2 空原因 → 分户新户文案带源户名
     A3 调查员填了 → 以他填的为准（不被系统覆盖）
     A4 无源户名时仍有兜底文案（不能是空串）
     A5 源户名超过 3 个时压缩为「甲、乙、丙 等 N 户」
     A6 成员 / 地块文案常量非空且语义正确
  B. 静态：household.py 不再直接 `change_reason=payload.get("reason")`
  C. 端到端（flush 后回滚）
     C1 调查员不填原因 → 新户 change_reason 自动非空且等于期望文案
     C2 同上 → 7 名成员 change_reason 全部自动写入
     C3 同上 → 地块 change_reason 全部自动写入
     C4 policy_basis 仍取调查员填的值（不被自动逻辑影响）
     C5 rollback 后库中不存在该新编码（证明零写入）
  D. 端到端（flush 后回滚）：调查员填了原因 → 以他填的为准
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DATABASE_PORT", "15432")
os.environ.setdefault("SECRET_KEY", "verify-only")

_env_file = ROOT / "runtime" / ".state" / "runtime.env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8-sig").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
import app.main  # noqa: E402,F401  加载全部端点/模型，确保 relationship 全部注册
# ⛔ app.models.__init__ 并没有导出 UserRegionPermission（User.user_region_permissions
#    指向它），只 import app.models 会在 mapper 初始化时报 InvalidRequestError。
from app.services.survey.household import (  # noqa: E402
    MERGE_MEMBER_REASON,
    MERGE_PARCEL_REASON,
    SPLIT_MEMBER_REASON,
    SPLIT_PARCEL_REASON,
    _names_brief,
    merge_new_household_reason,
    resolve_change_reason,
    split_new_household_reason,
)

BATCH_ID = 41
SYNC_URL = (
    f"postgresql+psycopg://{settings.database_user}:{settings.database_password}@"
    f"{settings.database_host}:{settings.database_port}/{settings.database_name}"
)

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


# ─────────────────────────── A. 纯函数 ───────────────────────────
def part_a() -> None:
    print("\nA. 文案生成规则")
    got = merge_new_household_reason(None, ["刘修连", "刘乃高"])
    check("A1 合户新户文案带原承包方", got == "因合户设立新户（原承包方：刘修连、刘乃高）", got)

    got = split_new_household_reason(None, "刘乃高")
    check("A2 分户新户文案带源户名", got == "因分户自 刘乃高 户析出设立新户", got)

    got = merge_new_household_reason(" 兄弟分家协商合户 ", ["甲", "乙"])
    check("A3 调查员填了以他的为准（且去空白）", got == "兄弟分家协商合户", got)

    got = merge_new_household_reason(None, [])
    check("A4 无源户名仍有兜底文案", got == "因合户设立新户", got)
    got = split_new_household_reason(None, None)
    check("A4b 分户无源户名仍有兜底文案", got == "因分户设立新户", got)

    got = _names_brief(["甲", "乙", "丙", "丁", "戊"])
    check("A5 超过 3 个源户时压缩", got == "甲、乙、丙 等 5 户", got)

    check(
        "A6 成员/地块文案常量语义正确",
        (MERGE_MEMBER_REASON, MERGE_PARCEL_REASON, SPLIT_MEMBER_REASON, SPLIT_PARCEL_REASON)
        == ("因合户转入新户", "因合户划入新户", "因分户转入新户", "因分户划入新户"),
        f"{MERGE_MEMBER_REASON}/{MERGE_PARCEL_REASON}/{SPLIT_MEMBER_REASON}/{SPLIT_PARCEL_REASON}",
    )

    # resolve_change_reason 的边界：空串 / 纯空白都算"没填"
    check("A7 纯空白视为未填", resolve_change_reason("   ", "兜底") == "兜底")
    check("A8 None 视为未填", resolve_change_reason(None, "兜底") == "兜底")


# ─────────────────────────── B. 静态 ───────────────────────────
def part_b() -> None:
    print("\nB. 静态：旧写法已清除")
    src = (ROOT / "backend" / "app" / "services" / "survey" / "household.py").read_text(encoding="utf-8")
    legacy = [
        'change_reason=payload.get("reason")',
        'member.change_reason = payload.get("reason")',
        'rel.change_reason = payload.get("reason")',
        'parcel.change_reason = payload.get("reason")',
    ]
    bad = [item for item in legacy if item in src]
    check("B1 无旧写法（原因直接取 payload）", not bad, f"残留 {bad}")
    check("B2 已改为函数兜底", "resolve_change_reason(" in src)


# ─────────────────── D. 端到端：不填原因 → 自动生成 ───────────────────
def _pick_fixture(db: Session):
    """动态挑同村组的两户（按当前状态挑，避免写死 id 命中别人改过的行）。"""
    rows = db.execute(text("""
        SELECT r.contractor_uid, r.cbfbm, coalesce(r.group_region_code, r.region_code)
        FROM survey_cbf_result r
        JOIN survey_cbf_base b ON b.contractor_uid = r.contractor_uid AND b.batch_id = :bid
        JOIN survey_batches bt ON bt.id = :bid
        WHERE r.survey_status <> 'confirmed'
          AND r.result_status IN ('normal', 'added')
          AND r.tenant_code = bt.tenant_code
          AND coalesce(r.group_region_code, r.region_code) = (
                SELECT coalesce(r2.group_region_code, r2.region_code)
                FROM survey_cbf_result r2
                JOIN survey_cbf_base b2 ON b2.contractor_uid = r2.contractor_uid AND b2.batch_id = :bid
                WHERE r2.survey_status <> 'confirmed' AND r2.result_status IN ('normal','added')
                GROUP BY 1 ORDER BY count(*) DESC LIMIT 1)
        ORDER BY r.id
    """), {"bid": BATCH_ID}).fetchall()
    return rows


def part_cd() -> None:
    from app.models.survey import SurveyCbdkxxResult, SurveyCbfBase, SurveyCbfJtcyResult, SurveyCbfResult
    from app.models.user import User
    from app.services.survey import survey_service

    print("\nC. 端到端：调查员不填原因 → 系统自动生成（flush 后回滚）")
    engine = create_engine(SYNC_URL, future=True)
    with Session(engine) as db:
        user = db.scalars(select(User).where(User.id == 1)).first()
        rows = _pick_fixture(db)
        if len(rows) < 2:
            check("C0 找到同村组两户夹具", False, f"仅 {len(rows)} 户")
            return

        uids = [rows[0][0], rows[1][0]]
        codes = [rows[0][1], rows[1][1]]
        prefix = str(rows[0][2] or "")[:14] or codes[0][:14]
        names = [db.scalar(select(SurveyCbfResult.cbfmc).where(SurveyCbfResult.contractor_uid == u))
                 for u in uids]
        check("C0 找到同村组两户夹具", len(uids) == 2, f"{codes} / {names}")

        members = db.scalars(
            select(SurveyCbfJtcyResult).where(SurveyCbfJtcyResult.contractor_uid.in_(uids))
        ).all()
        if not members or len({m.member_uid for m in members}) != len(members):
            check("C0b 夹具户成员齐备且无重复", False, f"{len(members)} 人")
            return
        check("C0b 夹具户成员齐备且无重复", True, f"{len(members)} 人")

        def run(new_code: str, reason, policy):
            payload = {
                "sourceContractorUids": uids,
                "newCbfbm": new_code,
                "newCbfmc": "验收测试合户",
                "newAddress": "验收测试地址",
                "householdHeadMemberUid": members[0].member_uid,
                "policyBasis": policy,
            }
            if reason is not None:
                payload["reason"] = reason
            try:
                survey_service.merge_household(db, BATCH_ID, uids[0], payload, user, commit=False)
                return True, ""
            except HTTPException as exc:
                return False, str(exc.detail)
            except Exception as exc:  # noqa: BLE001
                return False, f"{type(exc).__name__}: {exc}"

        # ── 不填原因 ──
        code_auto = prefix + "999999"[: 18 - len(prefix)]
        ok, err = run(code_auto, None, "验收-政策依据")
        check("C1 merge_household(不填原因) 跑通", ok, err)

        if ok:
            new_row = db.scalars(select(SurveyCbfResult).where(SurveyCbfResult.cbfbm == code_auto)).first()
            expect = "因合户设立新户（原承包方：" + "、".join([n for n in names if n][:3]) + "）"
            check("C2 新户变化原因自动生成", new_row is not None and new_row.change_reason == expect,
                  f"实际={getattr(new_row, 'change_reason', None)!r} 期望={expect!r}")

            new_members = db.scalars(
                select(SurveyCbfJtcyResult).where(SurveyCbfJtcyResult.contractor_uid == new_row.contractor_uid)
            ).all()
            check("C3 成员变化原因全部自动写入",
                  bool(new_members) and all(m.change_reason == MERGE_MEMBER_REASON for m in new_members),
                  f"{len(new_members)} 人，取值={sorted({m.change_reason for m in new_members})}")

            new_parcels = db.scalars(
                select(SurveyCbdkxxResult).where(SurveyCbdkxxResult.cbfbm == code_auto)
            ).all()
            check("C4 地块变化原因全部自动写入",
                  bool(new_parcels) and all(p.change_reason == MERGE_PARCEL_REASON for p in new_parcels),
                  f"{len(new_parcels)} 块，取值={sorted({p.change_reason for p in new_parcels})}")

            check("C5 政策依据仍取调查员填的值", new_row.policy_basis == "验收-政策依据",
                  repr(new_row.policy_basis))

        db.rollback()
        still = db.scalar(select(SurveyCbfResult.id).where(SurveyCbfResult.cbfbm == code_auto))
        check("C6 回滚后库中无该新编码（零写入）", still is None, f"id={still}")

        # ── 填了原因：以他的为准 ──
        print("\nD. 端到端：调查员填了原因 → 以他填的为准（flush 后回滚）")
        code_user = prefix + "999998"[: 18 - len(prefix)]
        ok, err = run(code_user, "兄弟分家协商合户", "验收-政策依据2")
        check("D1 merge_household(填了原因) 跑通", ok, err)
        if ok:
            new_row = db.scalars(select(SurveyCbfResult).where(SurveyCbfResult.cbfbm == code_user)).first()
            check("D2 新户用调查员填的原因", new_row is not None and new_row.change_reason == "兄弟分家协商合户",
                  repr(getattr(new_row, "change_reason", None)))
            new_members = db.scalars(
                select(SurveyCbfJtcyResult).where(SurveyCbfJtcyResult.contractor_uid == new_row.contractor_uid)
            ).all()
            check("D3 成员也用调查员填的原因",
                  bool(new_members) and all(m.change_reason == "兄弟分家协商合户" for m in new_members),
                  f"{len(new_members)} 人")
        db.rollback()
        still = db.scalar(select(SurveyCbfResult.id).where(SurveyCbfResult.cbfbm == code_user))
        check("D4 回滚后库中无该新编码（零写入）", still is None, f"id={still}")


def main() -> None:
    part_a()
    part_b()
    part_cd()
    print("\n" + "=" * 74)
    print(f"通过 {len(PASS)} / {len(PASS) + len(FAIL)}")
    if FAIL:
        print("失败项：")
        for name in FAIL:
            print(f"  - {name}")
    print("=" * 74)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
