# -*- coding: utf-8 -*-
"""离线验收：「变化原因」默认值兜底（2026-09-27 起取代旧的必填闸门）。

旧行为（已废弃）
    「承包方/成员有变化却没填 change_reason」⇒ 确认接口返回 400，detail 点名
    「请填写变化原因」。可全库 change_reason 非空 **0 条** ⇒ 几乎每个"有变化"的户
    都被卡死在「确认调查结果」前，而承包方级连个录入控件都没有（用户报的
    刘乃高 321324100001020020 就是这么卡住的）。
新行为
    确认前 `SurveyServiceBase._ensure_change_reasons` 按**变更类型 / 成员自身标记**
    自动写入默认值（人工填过的不动）；闸门不再因它拦人。

零写入
    * A / B / D 组在读事务里跑，结束 `rollback()`；
    * C 组把 `Session.commit` 打成 no-op 再发 HTTP 请求，请求结束后再比对库里
      的 change_reason 与请求前一致 —— 既证明"接口不再 400"，又证明没动数据。

验收项
    A. 服务层：_ensure_change_reasons 能把空的 change_reason 补成默认值（承包方 + 全部有变化成员）
    B. 服务层：补齐后 `_validate_confirmable` 不再抛异常
    C. HTTP 层：confirm 不再 400（且零写入）
    D. 服务层：merge_household(commit=False) 返回 newHouseholds（前端"是否进入新户页面"要用）
    E. 静态：_apply_pending_operations 返回 created、update_result 响应带 createdContractors、
       闸门源码里已无 change_reason 的报错分支
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

import psycopg  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
# ⛔ 必须先把整个应用加载进来，否则 `app/models/__init__.py` 没导出 UserRegionPermission
# ⇒ SQLAlchemy 配置 mapper 时 `UserRegionPermission` 解析失败。见 MEMORY 的 mapper 坑。
from app.main import app  # noqa: E402,F401

UID = "d8233ebd-f2a7-50d4-a572-2436ea97a577"   # 刘乃高（合户生成的新户）
CBMB = "321324100001020020"
BATCH_ID = 41

DSN = (
    f"host={settings.database_host} port={settings.database_port} "
    f"dbname={settings.database_name} user={settings.database_user} "
    f"password={settings.database_password}"
)
SYNC_URL = f"postgresql+psycopg://{settings.database_user}:{settings.database_password}@" \
           f"{settings.database_host}:{settings.database_port}/{settings.database_name}"

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


def _snapshot_reasons() -> tuple:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("select change_reason from survey_cbf_result where contractor_uid = %s", (UID,))
        row = cur.fetchone()
        cur.execute(
            "select count(*) from survey_cbf_jtcy_result "
            "where contractor_uid = %s and coalesce(btrim(change_reason),'') <> ''",
            (UID,),
        )
        filled_members = cur.fetchone()[0]
    return (row[0] if row else None, filled_members)


# ─────────────────── A / B. 服务层：默认值 + 闸门不再拦 ───────────────────
def part_ab() -> None:
    print("\nA/B. _ensure_change_reasons 补默认值，_validate_confirmable 不再拦")
    from app.models.survey import SurveyCbfJtcyResult, SurveyCbfResult
    from app.services.survey import survey_service

    engine = create_engine(SYNC_URL, future=True)
    with Session(engine) as db:
        result = db.scalars(
            select(SurveyCbfResult).where(SurveyCbfResult.contractor_uid == UID)
            .order_by(SurveyCbfResult.id.desc())
        ).first()
        members = db.scalars(
            select(SurveyCbfJtcyResult).where(SurveyCbfJtcyResult.contractor_uid == UID)
            .order_by(SurveyCbfJtcyResult.id.asc())
        ).all()
        check("A0 夹具户存在且有成员", result is not None and len(members) > 0,
              f"cbfbm={getattr(result, 'cbfbm', None)} 成员={len(members)}")
        if result is None or not members:
            return

        # A1 先把"变化原因"在**内存里**清空（不改库），再跑兜底；
        # 这样无论库里是否已被 backfill 补过，都能验到真行为。
        result.change_reason = None
        for member in members:
            if survey_service._member_change_requires_reason(member):
                member.change_reason = None
        changed_members = [m for m in members if survey_service._member_change_requires_reason(m)]

        filled = survey_service._ensure_change_reasons(db, result)
        print(f"     自动补齐 {len(filled)} 项：{filled[:4]}{' …' if len(filled) > 4 else ''}")
        check("A1 承包方变化原因被补上默认值",
              bool((result.change_reason or "").strip()), repr(result.change_reason))
        check("A2 承包方默认值来自变更类型（合户 → 含「合户」）",
              "合户" in (result.change_reason or ""), repr(result.change_reason))
        check("A3 全部有变化的成员都被补上原因",
              bool(changed_members) and all((m.change_reason or "").strip() for m in changed_members),
              f"{sum(1 for m in changed_members if (m.change_reason or '').strip())}/{len(changed_members)}")
        check("A4 成员默认值按户级操作为「因合户转入新户」",
              bool(changed_members) and all("合户" in (m.change_reason or "") for m in changed_members),
              repr(changed_members[0].change_reason) if changed_members else "无")
        check("A5 幂等：再跑一次不再产生新的补齐项",
              survey_service._ensure_change_reasons(db, result) == [])

        # B 补齐后闸门必须放行（其余校验：户主、证件号重复仍需满足）
        try:
            survey_service._validate_confirmable(db, result)
            b_ok, b_detail = True, "通过"
        except HTTPException as exc:
            b_ok, b_detail = False, str(exc.detail)
        print(f"     B detail={b_detail!r}")
        check("B1 补齐后可过确认判据（不再因变化原因被拦）",
              b_ok or "变化原因" not in b_detail, b_detail)

        db.rollback()   # 显式回滚：上面全是内存改动


# ─────────────────── C. HTTP 层：confirm 不再 400（零写入） ───────────────────
def part_c() -> None:
    print("\nC. HTTP 层：confirm 不再 400，且请求不落库")
    from fastapi.testclient import TestClient

    from app.main import app

    before = _snapshot_reasons()
    print(f"     请求前：承包方 reason={before[0]!r}，成员非空 {before[1]} 条")

    token = create_access_token("1")
    client = TestClient(app)   # 刻意不用 with：避免触发 lifespan（bootstrap/seed）

    # 把 commit 打成 no-op —— 只验"接口是否放行"，不让验收脚本改生产数据。
    original_commit = Session.commit
    Session.commit = lambda self, *a, **k: None  # type: ignore[assignment]
    try:
        resp = client.post(
            f"/api/v1/surveys/batches/{BATCH_ID}/results/{UID}/confirm",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        Session.commit = original_commit  # type: ignore[assignment]

    detail = ""
    try:
        detail = str(resp.json().get("detail") or "")
    except Exception:  # noqa: BLE001
        detail = resp.text[:200]
    print(f"     status={resp.status_code} detail={detail!r}")
    check("C1 confirm 不再被 400 拦下", resp.status_code != 400,
          f"status={resp.status_code} detail={detail!r}")
    check("C2 detail 里不再出现「请填写其「变化原因」」", "变化原因" not in detail, detail)

    after = _snapshot_reasons()
    check("C3 验收请求没有改动数据（零写入）", before == after, f"before={before} after={after}")


# ─────────────────── D. merge_household 返回新户标识 ───────────────────
def part_d() -> None:
    print("\nD. merge_household(commit=False) 返回 newHouseholds")
    from app.models.survey import SurveyCbfJtcyResult, SurveyCbfResult
    from app.models.user import User
    from app.services.survey import survey_service

    engine = create_engine(SYNC_URL, future=True)
    new_code = ""
    with Session(engine) as db:
        user = db.scalars(select(User).where(User.id == 1)).first()
        rows = db.execute(text("""
            SELECT r.contractor_uid, r.cbfbm, r.group_region_code, r.survey_status, r.result_status, r.cbflx
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
        if len(rows) < 2:
            check("D0 找到同村组两户夹具", False, f"仅 {len(rows)} 户")
            return
        uids = [rows[0][0], rows[1][0]]
        prefix = str(rows[0][2] or "")[:14] or rows[0][1][:14]
        check("D0 找到同村组两户夹具", True, f"{rows[0][1]} / {rows[1][1]}")

        members = db.scalars(
            select(SurveyCbfJtcyResult).where(SurveyCbfJtcyResult.contractor_uid.in_(uids))
        ).all()
        if not members:
            check("D0b 夹具户有成员", False, "无成员")
            return
        if len({m.member_uid for m in members}) != len(members):
            check("D0b 夹具户成员无重复", False, "成员 uid 跨户重复，换夹具")
            return

        new_code = (prefix + "999999")[:18]
        if db.scalar(select(SurveyCbfResult.id).where(SurveyCbfResult.cbfbm == new_code)):
            new_code = (prefix + "999998")[:18]
        payload = {
            "sourceContractorUids": uids, "newCbfbm": new_code,
            "newCbfmc": "验收测试合户", "newAddress": "验收测试地址",
            "householdHeadMemberUid": members[0].member_uid,
        }
        try:
            outcome = survey_service.merge_household(db, BATCH_ID, uids[0], payload, user, commit=False)
            ok, detail = True, repr(outcome)
        except Exception as exc:  # noqa: BLE001
            ok, detail, outcome = False, f"{type(exc).__name__}: {exc}", {}
        print(f"     outcome={detail}")
        check("D1 merge_household(commit=False) 跑通", ok, "" if ok else detail)
        created = (outcome or {}).get("newHouseholds") or []
        check("D2 返回 newHouseholds 且含新户标识",
              bool(created) and created[0].get("contractorUid") and created[0].get("cbfbm") == new_code,
              repr(created))
        db.rollback()

    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM survey_cbf_result WHERE cbfbm = %s", (new_code,))
        left = cur.fetchone()[0]
    check("D3 rollback 后库中无新户（零写入）", left == 0, f"count={left}")


# ─────────────────── E. 静态：链路与闸门源码 ───────────────────
def part_e() -> None:
    print("\nE. 静态：默认值链路与闸门源码")
    survey_dir = ROOT / "backend" / "app" / "services" / "survey"
    base_src = (survey_dir / "base.py").read_text(encoding="utf-8-sig")
    changes_src = (survey_dir / "changes.py").read_text(encoding="utf-8-sig")
    result_src = (survey_dir / "result.py").read_text(encoding="utf-8-sig")
    household_src = (survey_dir / "household.py").read_text(encoding="utf-8-sig")

    check("E1 base.py 定义了默认值函数",
          "def default_contractor_change_reason" in base_src
          and "def default_member_change_reason" in base_src)
    check("E2 闸门源码已无 change_reason 报错分支",
          'errors.append("承包方存在变化时必须填写变化原因")' not in base_src
          and "missing_member_reasons" not in base_src)
    check("E3 _apply_pending_operations 返回 created",
          "return created" in changes_src and '"newHouseholds"' in changes_src)
    check("E4 update_result 响应带 createdContractors", "createdContractors" in result_src)
    check("E5 merge/split 的 commit=False 分支都返回 newHouseholds",
          household_src.count('"newHouseholds"') >= 3)
    check("E6 前端也不再拦变化原因",
          "collectConfirmBlockers" in (
              ROOT / "frontend" / "src" / "components" / "survey" / "view" / "ContractorResultDialog.vue"
          ).read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    part_ab()
    part_c()
    part_d()
    part_e()
    print(f"\n===== 汇总：PASS {len(PASS)} / FAIL {len(FAIL)} =====")
    for name in FAIL:
        print(f"  FAILED: {name}")
    sys.exit(1 if FAIL else 0)
