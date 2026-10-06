# -*- coding: utf-8 -*-
"""验收：地块列表操作列上「保存」这一行 —— 把一条待保存的新增地块单独落库。

用户诉求（2026-09-28）：
    「新增的地块一定要点击保存调查结果后才能开始编辑界址点界址线吗？这样不合理，
      在地块列表中不是有操作按钮吗，可以让新增的在操作列加个保存按钮」

背景：界址点 / 界址线由库里的地块图形（`survey_dk_result.geom`）推导，地块不落库就没有宿体。
所以「能不能编辑界址点」== 「这块地在库里存没存过」。本脚本验的是新增的那条行级入口：

    POST /api/v1/surveys/batches/{batch_id}/results/{contractor_uid}/parcels/persist

⚠️ 与 `_verify_add_parcel_boundary.py` 的分工（别互相替代）：
    那个脚本验「闸门顺序与文案」——为什么以前报错、报错指向对不对；
    本脚本验「新入口本身」——能落库、幂等、越权拦得住、且**只动地块不动承包方主体**。

验收项：
    A. 行级落库成功：返回 {dkbm, alreadyPersisted:False}，库里确实多了地块行 + 关联行
    B. 落库后**立刻**可维护界址点：GET boundary → 200，点数 == 图形顶点数
       （这一条就是用户诉求的正面回答：点一次「保存」就能编辑界址点，不必整份提交）
    C. 幂等：同一条重复提交 → alreadyPersisted:True，且库中该 dkbm 仍只有 1 行
       （否则整体保存时会撞 add_parcel 的重复校验，把整次保存打回）
    D. 编码被占：拿**别人家已落库**的 dkbm 提交 → 400，文案点名「已被其他承包方占用」
    E. 类型闸门：type=split_parcel → 400，文案指向「保存调查结果」
       （「保存一行」对切割/互换不是准确语义，它们仍应整份提交）
    F. 边界（**最关键**）：调用前后承包方主体的每一个字段逐字不变、survey_status 不推进
       —— 证明它没有变成"偷偷的整份保存"
    G. 回滚后零留痕

数据策略：A/B/C/F 全部在**一个事务里**跑（`commit=False` + 结尾 rollback），
D/E 走 HTTP 但都是会被拒的请求、不写库。所以整脚本跑完库应与运行前逐字一致。

用法：
    runtime/windows/python/python.exe scripts/_verify_persist_parcel_boundary.py
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
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.db.session import SessionLocal, set_current_user  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.services.auth_service import auth_service  # noqa: E402
from app.services.survey import survey_service  # noqa: E402

UNSAVED_MARK = "尚未保存"
NOT_OWNED_MARK = "该地块不属于当前承包方"
PERSIST_ROUTE = "/api/v1/surveys/batches/{batch_id}/results/{contractor_uid}/parcels/persist"
BOUNDARY_ROUTE = "/api/v1/surveys/batches/{batch_id}/results/{contractor_uid}/parcels/{dkbm}/boundary"

# 会被 add_parcel 合法触碰的字段：调查时间戳 + 任务态（`survey_cbf_base` 是任务表）。
# 除这些之外，承包方主体字段必须逐字不变 —— 这就是 F 项的判据。
SUBJECT_FIELDS_IGNORED = {"investigated_at", "updated_at"}

RESULTS: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))


def subject_snapshot(db, result_id: int) -> dict:
    """取承包方主体行的全部字段（排除合法会被触碰的时间戳）。"""
    row = db.execute(
        text("SELECT * FROM survey_cbf_result WHERE id = :i"), {"i": result_id}
    ).mappings().first()
    if row is None:
        return {}
    return {k: v for k, v in dict(row).items() if k not in SUBJECT_FIELDS_IGNORED}


def pick_fixture(db) -> dict:
    """挑一个「active 批次 + 能过 _get_result + 有带图形地块 + 未确认」的承包户。"""
    rows = db.execute(text(
        """
        SELECT t.batch_id, t.contractor_uid, t.cbfbm
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
            "result_id": result.id,
            "survey_status": result.survey_status,
            "own_dkbm": parcel.dkbm,
            "other_dkbm": other.dkbm if other else None,
            "other_cbfbm": other.cbfbm if other else None,
        }
    raise SystemExit("找不到可用夹具：active 批次里没有「可读 + 有带图形地块」的承包户")


def find_free_dkbm(db, prefix: str) -> str:
    used = set(db.scalars(text("SELECT dkbm FROM survey_dk_result WHERE dkbm LIKE :p"), {"p": f"{prefix}%"}).all())
    for serial in range(97000, 99999):
        candidate = f"{prefix}{serial:05d}"
        if candidate not in used:
            return candidate
    raise SystemExit("拿不到空闲地块编码")


def main() -> None:
    db = SessionLocal()
    admin = auth_service.get_current_user(db, 1)
    set_current_user(db, admin)
    print(f"操作账号: id={admin.id} 名称={admin.real_name} 数据范围={admin.role.data_scope}")

    fixture = pick_fixture(db)
    print("夹具:", {k: v for k, v in fixture.items() if k != "result_id"})

    batch_id = fixture["batch_id"]
    contractor_uid = fixture["contractor_uid"]
    prefix = str(fixture["own_dkbm"])[:14]
    new_dkbm = find_free_dkbm(db, prefix)

    # 图形放在远离本县的经纬度上：既不与其他地块重叠（重叠会被 add_parcel 拒），
    # 也不受"地块必须在行政区内"之外的限制影响。
    lon, lat, side = 90.0, 30.0, 0.001
    geometry = {
        "type": "Polygon",
        "coordinates": [[
            [lon, lat], [lon + side, lat], [lon + side, lat + side],
            [lon, lat + side], [lon, lat],
        ]],
    }
    operation = {
        "type": "add_parcel",
        "payload": {
            "dkbm": new_dkbm,
            "dkmc": "行级落库验收临时地块",
            "dklb": "20",
            "dldj": "1",
            "tdyt": "1",
            "scmj": 16.0,
            "reason": "verify-persist-parcel",
            "geometry": geometry,
            "geometrySourceSrid": 4326,
        },
    }

    before = subject_snapshot(db, fixture["result_id"])

    # ── A/B/C：事务内落库（commit=False），跑完回滚 ──────────────────────────
    try:
        response = survey_service.persist_pending_operation(
            db, batch_id, contractor_uid, operation, admin, commit=False
        )
        parcel_rows = db.scalar(
            text("SELECT count(*) FROM survey_dk_result WHERE dkbm = :d"), {"d": new_dkbm}
        )
        relation_rows = db.scalar(
            text("SELECT count(*) FROM survey_cbdkxx_result WHERE dkbm = :d"), {"d": new_dkbm}
        )
        record(
            "A 行级落库成功（地块行 + 关联行都建了）",
            response.get("alreadyPersisted") is False and parcel_rows == 1 and relation_rows == 1,
            f"返回={response} 地块行={parcel_rows} 关联行={relation_rows} dkbm={new_dkbm}",
        )

        # B. 落库后立刻读界址点（用户的真实诉求：点完「保存」就能编辑界址点）
        try:
            boundary = survey_service.get_parcel_boundary(db, batch_id, contractor_uid, new_dkbm, admin)
            point_count = len(boundary.get("points") or [])
            record(
                "B 落库后立刻可维护界址点",
                point_count == 4,
                f"dkbm={new_dkbm} 状态=200 界址点={point_count} 环={boundary.get('ringCount')}（正方形应 4 点）",
            )
        except HTTPException as exc:
            record("B 落库后立刻可维护界址点", False, f"读界址点被拒: {exc.status_code} {exc.detail}")

        # C. 幂等：同一条再来一次
        again = survey_service.persist_pending_operation(
            db, batch_id, contractor_uid, operation, admin, commit=False
        )
        parcel_rows_after = db.scalar(
            text("SELECT count(*) FROM survey_dk_result WHERE dkbm = :d"), {"d": new_dkbm}
        )
        record(
            "C 重复提交幂等（不重复插入）",
            again.get("alreadyPersisted") is True and parcel_rows_after == 1,
            f"第二次返回={again} 地块行={parcel_rows_after}（应仍为 1）",
        )

        # F. 边界：承包方主体字段与调查状态逐字不变
        after = subject_snapshot(db, fixture["result_id"])
        changed = {
            k: (before.get(k), after.get(k))
            for k in set(before) | set(after)
            if before.get(k) != after.get(k)
        }
        record(
            "F 只落地块、不碰承包方主体与调查状态",
            not changed,
            f"对比 {len(before)} 个字段，变化 {len(changed)} 个：{changed or '无'}"
            f"（survey_status 保持 {after.get('survey_status')!r}）",
        )
    finally:
        db.rollback()

    # ── G. 回滚后零留痕 ────────────────────────────────────────────────────
    left = db.scalar(text("SELECT count(*) FROM survey_dk_result WHERE dkbm = :d"), {"d": new_dkbm})
    rel_left = db.scalar(text("SELECT count(*) FROM survey_cbdkxx_result WHERE dkbm = :d"), {"d": new_dkbm})
    record("G 回滚后库未留痕", left == 0 and rel_left == 0, f"地块行={left} 关联行={rel_left} dkbm={new_dkbm}")

    # ── D/E：走 HTTP 端点（都会被拒，因此不写库）────────────────────────────
    client = TestClient(fastapi_app)  # 不用 with：避免触发 lifespan 里的 bootstrap/seed
    headers = {"Authorization": f"Bearer {create_access_token('1')}"}
    url = PERSIST_ROUTE.format(batch_id=batch_id, contractor_uid=contractor_uid)

    if fixture["other_dkbm"]:
        resp = client.post(url, json={
            "type": "add_parcel",
            "payload": {
                "dkbm": fixture["other_dkbm"], "dkmc": "占位", "dklb": "20",
                "dldj": "1", "tdyt": "1", "scmj": 1.0,
            },
        }, headers=headers)
        detail = str((resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}).get("detail") or resp.text)
        record(
            "D 占用别人家编码被拒（HTTP 400）",
            resp.status_code == 400 and "已被其他承包方占用" in detail,
            f"dkbm={fixture['other_dkbm']}（归属 {fixture['other_cbfbm']}）状态={resp.status_code} 文案=「{detail}」",
        )
    else:
        record("D 占用别人家编码被拒（HTTP 400）", False, "库里找不到第二户的地块，无法验证")

    resp = client.post(url, json={"type": "split_parcel", "payload": {"dkbm": fixture["own_dkbm"]}}, headers=headers)
    detail = str((resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}).get("detail") or resp.text)
    record(
        "E 非新增操作被拒（HTTP 400，指向整份保存）",
        resp.status_code == 400 and "保存调查结果" in detail,
        f"type=split_parcel 状态={resp.status_code} 文案=「{detail}」",
    )

    # D/E 万一真的写进了库，这里再核一次（它们本该什么都没动）
    dkbm_touched = db.scalar(
        text("SELECT count(*) FROM survey_cbdkxx_result WHERE dkbm = :d"), {"d": fixture["other_dkbm"] or ""}
    )
    print(f"[info] D 项目标编码现行数（应保持原状，未被新增）: {dkbm_touched}")

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
