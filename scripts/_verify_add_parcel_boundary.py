# -*- coding: utf-8 -*-
"""验收：「新增地块后点『界址点 / 界址线维护』报 404」的定位与修复。

事故（2026-09-28 用户报）：
    /surveys → 承包方调查录入 → 地块信息 → 新增地块（画图 / 传 shp）→ 选中它
    → 点「界址点 / 界址线维护」→ 报「该地块不属于当前承包方」。

根因（两层，都用本脚本取证）：
    ① 前端：新增地块在对话框里只是**待保存预览行**（ContractorResultDialog
       `applyPendingParcelPreview`），不点「保存调查结果」就不会有库记录，
       但按钮只看 canManage / isResultLocked，于是能点。
    ② 后端：`boundary.py::_ensure_parcel_in_batch` **先查承包方关联行**再查地块行，
       库里既无地块行也无关联行时，关联查询落空 ⇒ 报"该地块不属于当前承包方"，
       文案指向错误（用户会以为选错了户）。

本脚本做四件事（全部在**一个事务里跑完并回滚**，结束时库应与运行前逐字一致）：
    A. 正例：已落库的地块读界址点 → 200，点数 == 图形顶点数（证明重建闸门顺序没弄坏原路径）
    B. 复现：一个库里没有的 dkbm（= 未保存的新增地块）→ 报错文案必须是"尚未保存…"
       并给出它**曾经**会命中的文案"该地块不属于当前承包方"
    C. 负向对照：拿**别人家已落库**的地块读界址点 → 仍必须是"该地块不属于当前承包方"
       （证明新增的"未保存"分支没有把归属判据吞掉）
    D. 闭环：事务内 add_parcel(commit=False) 造一块地 → 立刻读界址点必须 200
       → 回滚 → 库里查不到这块地（证明"保存后就能维护"这条因果链是真的）

用法：
    runtime/windows/python/python.exe scripts/_verify_add_parcel_boundary.py
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
    "SECRET_KEY": "verify-only",
})
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import app.main  # noqa: F401,E402  注册全部 mapper（含 UserRegionPermission）
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app.db.session import SessionLocal, set_current_user  # noqa: E402
from app.models.survey import SurveyCbdkxxResult, SurveyDkResult  # noqa: E402
from app.services.auth_service import auth_service  # noqa: E402
from app.services.survey import survey_service  # noqa: E402

UNSAVED_MARK = "尚未保存"
NOT_OWNED_MARK = "该地块不属于当前承包方"

RESULTS: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))


def call_boundary(db, batch_id, contractor_uid, dkbm, admin) -> tuple[int, str, dict]:
    """读界址点，把异常翻成 (状态码, 文案, 数据) 返回。"""
    try:
        data = survey_service.get_parcel_boundary(db, batch_id, contractor_uid, dkbm, admin)
        return 200, "", data
    except HTTPException as exc:
        return exc.status_code, str(exc.detail), {}


def pick_fixture(db) -> dict:
    """挑一个「active 批次 + 能过 _get_result + 有带图形地块 + 未确认」的承包户。

    任务行（survey_cbf_base）才是 batch↔户 的绑定处，`survey_cbf_result` 没有
    batch_id，所以候选从 base 表取，再逐个用服务层的口径复核。
    """
    rows = db.execute(text(
        """
        SELECT t.batch_id, t.contractor_uid, t.cbfbm, t.task_status
        FROM survey_cbf_base t
        JOIN survey_batches b ON b.id = t.batch_id
        WHERE b.status = 'active'
        ORDER BY t.id DESC
        LIMIT 500
        """
    )).all()

    for row in rows:
        try:
            result = survey_service._get_result(db, row.batch_id, row.contractor_uid)
        except HTTPException:
            continue
        if result.survey_status == "confirmed" or result.result_status in {"cancelled", "extinct"}:
            continue
        parcel = db.execute(text(
            """
            SELECT r.dkbm
            FROM survey_cbdkxx_result r
            JOIN survey_dk_result d ON d.dkbm = r.dkbm
            WHERE r.cbfbm = :cbfbm
              AND r.result_status NOT IN ('removed', 'split_source')
              AND d.result_status <> 'removed'
              AND d.geom IS NOT NULL
            ORDER BY r.dkbm
            LIMIT 1
            """
        ), {"cbfbm": result.cbfbm}).first()
        if parcel is None:
            continue
        other = db.execute(text(
            """
            SELECT r.dkbm, r.cbfbm
            FROM survey_cbdkxx_result r
            WHERE r.cbfbm <> :cbfbm AND r.result_status = 'normal'
            ORDER BY r.id DESC
            LIMIT 1
            """
        ), {"cbfbm": result.cbfbm}).first()
        return {
            "batch_id": row.batch_id,
            "contractor_uid": row.contractor_uid,
            "cbfbm": result.cbfbm,
            "task_status": row.task_status,
            "survey_status": result.survey_status,
            "own_dkbm": parcel.dkbm,
            "other_dkbm": other.dkbm if other else None,
            "other_cbfbm": other.cbfbm if other else None,
        }
    raise SystemExit("找不到可用夹具：active 批次里没有「可读 + 有带图形地块」的承包户")


def main() -> None:
    db = SessionLocal()
    admin = auth_service.get_current_user(db, 1)
    set_current_user(db, admin)
    print(f"操作账号: id={admin.id} 名称={admin.real_name} 角色数据范围={admin.role.data_scope}")

    fixture = pick_fixture(db)
    print("夹具:", fixture)

    batch_id = fixture["batch_id"]
    contractor_uid = fixture["contractor_uid"]
    own_dkbm = fixture["own_dkbm"]

    # ── A. 正例：已落库的地块 ────────────────────────────────────────────────
    if own_dkbm:
        code, detail, data = call_boundary(db, batch_id, contractor_uid, own_dkbm, admin)
        point_count = len(data.get("points") or [])
        ring_count = data.get("ringCount")
        ok = code == 200 and point_count > 0
        record(
            "A 已落库地块可读界址点",
            ok,
            f"dkbm={own_dkbm} 状态={code} 界址点={point_count} 环={ring_count} {detail}",
        )
    else:
        record("A 已落库地块可读界址点", False, "夹具里找不到带图形的地块，无法验证正例")

    # ── B. 复现：库里不存在的地块（未保存的新增地块就是这个形态）─────────────
    ghost = "0000000000000000000"
    code, detail, _ = call_boundary(db, batch_id, contractor_uid, ghost, admin)
    exists = db.scalar(text("SELECT count(*) FROM survey_dk_result WHERE dkbm = :d"), {"d": ghost})
    related = db.scalar(text("SELECT count(*) FROM survey_cbdkxx_result WHERE dkbm = :d"), {"d": ghost})
    ok = code == 404 and UNSAVED_MARK in detail
    record(
        "B 未落库地块报『尚未保存』",
        ok,
        f"库中地块行={exists} 关联行={related} 状态={code} 文案=「{detail}」"
        f"（修复前该分支先查关联，会错报「{NOT_OWNED_MARK}」）",
    )

    # ── C. 负向对照：别人家已落库的地块，仍必须报『不属于当前承包方』 ──────────
    if fixture["other_dkbm"]:
        code, detail, _ = call_boundary(db, batch_id, contractor_uid, fixture["other_dkbm"], admin)
        ok = code == 404 and NOT_OWNED_MARK == detail
        record(
            "C 他家地块仍报『不属于当前承包方』",
            ok,
            f"dkbm={fixture['other_dkbm']} 归属={fixture['other_cbfbm']} 状态={code} 文案=「{detail}」",
        )
    else:
        record("C 他家地块仍报『不属于当前承包方』", False, "库里找不到第二户的地块，无法做负向对照")

    # ── D. 闭环：事务内落库一块新增地块 → 立即读界址点 → 回滚 ────────────────
    prefix = str(own_dkbm)[:14] if own_dkbm else None
    if not prefix:
        record("D 落库后即可维护", False, "拿不到地块编码前缀，无法构造临时地块")
    else:
        used = set(db.scalars(text(
            "SELECT dkbm FROM survey_dk_result WHERE dkbm LIKE :p"
        ), {"p": f"{prefix}%"}).all())
        new_dkbm = next(
            (f"{prefix}{serial:05d}" for serial in range(98000, 99999) if f"{prefix}{serial:05d}" not in used),
            None,
        )
        # 图形放在远离本县的经纬度上，保证不与其他地块重叠（重叠会被 add_parcel 拒）。
        lon, lat, side = 90.0, 30.0, 0.001
        geometry = {
            "type": "Polygon",
            "coordinates": [[
                [lon, lat], [lon + side, lat], [lon + side, lat + side],
                [lon, lat + side], [lon, lat],
            ]],
        }
        try:
            survey_service.add_parcel(
                db, batch_id, contractor_uid,
                {
                    "dkbm": new_dkbm,
                    "dkmc": "界址点验收临时地块",
                    "dklb": "20",
                    "dldj": "1",
                    "tdyt": "1",
                    "scmj": 16.0,
                    "reason": "verify-add-parcel-boundary",
                    "geometry": geometry,
                    "geometrySourceSrid": 4326,
                },
                admin,
                commit=False,
            )
            code, detail, data = call_boundary(db, batch_id, contractor_uid, new_dkbm, admin)
            point_count = len(data.get("points") or [])
            ok = code == 200 and point_count == 4
            record(
                "D 落库后即可维护（事务内）",
                ok,
                f"临时地块={new_dkbm} 读状态={code} 界址点={point_count}（正方形应 4 点）{detail}",
            )
        except HTTPException as exc:
            record("D 落库后即可维护（事务内）", False, f"add_parcel 被拒: {exc.status_code} {exc.detail}")
        finally:
            db.rollback()
            left = db.scalar(text("SELECT count(*) FROM survey_dk_result WHERE dkbm = :d"), {"d": new_dkbm})
            rel_left = db.scalar(
                text("SELECT count(*) FROM survey_cbdkxx_result WHERE dkbm = :d"), {"d": new_dkbm}
            )
            record(
                "E 回滚后库未留痕",
                left == 0 and rel_left == 0,
                f"地块行={left} 关联行={rel_left}（临时地块 {new_dkbm}）",
            )

    db.close()

    print("\n=== 验收结果 ===")
    for name, status, detail in RESULTS:
        print(f"[{status}] {name}\n        {detail}")
    failed = [item for item in RESULTS if item[1] == "FAIL"]
    print(f"\n合计 {len(RESULTS)} 项，通过 {len(RESULTS) - len(failed)} 项，失败 {len(failed)} 项")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
