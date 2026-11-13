"""验收：生成延包合同时刷地块关联表 cbhtbm（2026-11-13 口径变更）。

改动点（backend/app/services/survey/contract.py + contract_template_service.py）：
1. generate_extension_contract 把该户有效地块（result_status != removed）的
   cbhtbm 全部刷成新合同编码；
2. 原合同解析链改为 ycbhtbm 优先（地块关联只给未生成户回落）；
3. 承包合同管理页 originalCode 从现行合同 ycbhtbm 反查；
4. 历史合同渲染按旧码在 result 表查空时回落 survey_cbdkxx_base 导入快照。

跑法（真实库，测试数据自动回滚）：
  runtime/windows/python/python.exe scripts/_verify_contract_cbhtbm_rewrite.py [batch_id]
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
    text = line.strip()
    if not text or text.startswith("#") or "=" not in text:
        continue
    key, value = text.split("=", 1)
    os.environ.setdefault(key.strip(), value.strip())

sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.cbht import CONTRACT_SOURCE_GENERATED, CONTRACT_SOURCE_IMPORTED, Cbht  # noqa: E402
from app.models.survey import (  # noqa: E402
    SurveyBatch,
    SurveyCbdkxxBase,
    SurveyCbdkxxResult,
    SurveyCbfBase,
)
from app.models.user import User  # noqa: E402
from app.services.contract_template_service import contract_template_service  # noqa: E402
from app.services.survey_service import survey_service  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(name)


db = SessionLocal()
restore_parcel_cbhtbm: list[tuple[int, str]] = []
cbht_created: list[str] = []
cbht_status_before: dict[str, str] = {}
try:
    # ── 0. 路由注册 ──────────────────────────────────
    from app.main import app as fastapi_app

    route = next(
        (r for r in fastapi_app.routes if getattr(r, "path", "").endswith("/contract/generate")),
        None,
    )
    check("路由 POST …/contract/generate 已注册", route is not None)

    # ── 1. 挑批次与测试户（未生成过合同的） ──────────
    batch_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    batch = db.get(SurveyBatch, batch_id) if batch_id else db.scalars(
        select(SurveyBatch).order_by(SurveyBatch.id.desc())
    ).first()
    check("找到调查批次", batch is not None, f"id={getattr(batch, 'id', None)} status={getattr(batch, 'status', None)}")
    if batch is None:
        sys.exit(1)
    if batch.status == "finished":
        print("⚠️ 该批次已 finished，生成会被拦截，验收仅覆盖只读断言")

    admin = db.scalars(select(User).where(User.username == "admin")).first()
    if admin is None:
        admin = db.scalars(select(User).order_by(User.id)).first()

    candidate = None
    cbf_rows = db.scalars(
        select(SurveyCbfBase).where(
            SurveyCbfBase.batch_id == batch.id,
            SurveyCbfBase.task_status != "deregistered",
        ).execution_options(skip_tenant_scope=True)
    ).all()
    seen_uid: set[str] = set()
    for row in cbf_rows:
        if row.contractor_uid in seen_uid:
            continue
        seen_uid.add(row.contractor_uid)
        parcels = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.tenant_code == row.tenant_code,
                SurveyCbdkxxResult.cbfbm == row.cbfbm,
                SurveyCbdkxxResult.result_status != "removed",
            ).execution_options(skip_tenant_scope=True)
        ).all()
        if not parcels:
            continue
        has_generated = db.scalar(
            select(Cbht.cbhtbm).where(
                Cbht.survey_batch_id == batch.id,
                Cbht.contractor_uid == row.contractor_uid,
                Cbht.contract_source == CONTRACT_SOURCE_GENERATED,
            ).execution_options(skip_tenant_scope=True)
        )
        if has_generated:
            continue
        candidate = row
        break

    check("找到未生成合同的测试户（有有效地块）", candidate is not None)
    if candidate is None:
        print("没有可用测试户，验收中止")
        sys.exit(1)

    uid = candidate.contractor_uid
    cbfbm = candidate.cbfbm
    parcels_before = db.scalars(
        select(SurveyCbdkxxResult).where(
            SurveyCbdkxxResult.tenant_code == candidate.tenant_code,
            SurveyCbdkxxResult.cbfbm == cbfbm,
            SurveyCbdkxxResult.result_status != "removed",
        ).execution_options(skip_tenant_scope=True)
    ).all()
    old_codes = {p.cbhtbm for p in parcels_before}
    original_code_before = sorted(old_codes)[0]
    print(f"\n测试户: uid={uid} cbfbm={cbfbm} 地块 {len(parcels_before)} 块，原合同码 {sorted(old_codes)}")

    # ── 2. 生成合同 ──────────────────────────────────
    payload = {"cbqxq": "2029-01-01", "years": 30}
    entry = survey_service.generate_extension_contract(db, batch.id, uid, payload, admin)
    new_code = entry["cbhtbm"]
    print(f"生成合同: {new_code}  originalCode={entry.get('originalCode')}")

    # ── 3. 断言：地块关联已刷成新码 ──────────────────
    parcels_after = db.scalars(
        select(SurveyCbdkxxResult).where(
            SurveyCbdkxxResult.tenant_code == candidate.tenant_code,
            SurveyCbdkxxResult.cbfbm == cbfbm,
            SurveyCbdkxxResult.result_status != "removed",
        ).execution_options(skip_tenant_scope=True)
    ).all()
    codes_after = {p.cbhtbm for p in parcels_after}
    check("该户全部有效地块 cbhtbm 已刷成新合同码", codes_after == {new_code}, f"实际={sorted(codes_after)}")

    contract_row = db.get(Cbht, new_code)
    check("新合同 ycbhtbm 指向原合同码", contract_row is not None and contract_row.ycbhtbm == original_code_before,
          f"ycbhtbm={getattr(contract_row, 'ycbhtbm', None)} 期望={original_code_before}")

    # ── 4. 断言：原合同解析走 ycbhtbm，不再取地块关联 ─
    resolved = survey_service._resolve_original_contract_code(db, cbfbm, batch.id)
    check("原合同解析 = ycbhtbm 反查的旧码", resolved == original_code_before,
          f"实际={resolved} 期望={original_code_before}")

    original_row = db.get(Cbht, original_code_before) if original_code_before else None
    check("原合同行存在且为 history（或新落的 imported 行）",
          original_row is not None and original_row.contract_status == "history",
          f"status={getattr(original_row, 'contract_status', None)}")

    catalog = survey_service.list_survey_contracts(db, batch.id, uid, admin)
    check("清单 currentCode = 新合同码", catalog["currentCode"] == new_code)
    check("清单 originalCode = 旧合同码", catalog["originalCode"] == original_code_before,
          f"实际={catalog['originalCode']}")
    check("清单含新合同（现行/延包合同）", any(
        item["cbhtbm"] == new_code and item["isCurrent"] for item in catalog["contracts"]
    ))
    check("清单含旧合同（历史/上次承包合同）", any(
        item["cbhtbm"] == original_code_before and not item["isCurrent"]
        for item in catalog["contracts"]
    ))

    # ── 5. 断言：管理页 overview ─────────────────────
    overview = survey_service._contract_overview_map(db, batch.id, [next(
        r for r in cbf_rows if r.contractor_uid == uid
    )], batch_status=batch.status)
    row = overview.get(uid)
    check("overview signed=True", row is not None and row["signed"] is True)
    check("overview contractCode = 新合同码", row is not None and row["contractCode"] == new_code)
    check("overview originalCode = 旧合同码（ycbhtbm 反查）",
          row is not None and row["originalCode"] == original_code_before,
          f"实际={row.get('originalCode') if row else None}")

    # ── 6. 断言：历史合同渲染回落 base 快照 ──────────
    result_by_old = db.scalars(
        select(SurveyCbdkxxResult).where(
            SurveyCbdkxxResult.cbhtbm == original_code_before,
            SurveyCbdkxxResult.result_status != "removed",
        ).execution_options(skip_tenant_scope=True)
    ).all()
    base_by_old = db.scalars(
        select(SurveyCbdkxxBase).where(
            SurveyCbdkxxBase.cbhtbm == original_code_before,
        ).execution_options(skip_tenant_scope=True)
    ).all()
    print(f"       旧码在 result 表剩 {len(result_by_old)} 行（应为 0），base 快照 {len(base_by_old)} 行")
    check("旧码在 result 表已无关联（刷码生效）", len(result_by_old) == 0)

    html = contract_template_service.render_survey_contract(
        db, cbhtbm=original_code_before, batch_id=batch.id, cbfbm=cbfbm,
        parcels_by_contractor=False,
    )
    parcels_count = html.count("dkbm")  # 粗查：模板里有地块数据
    check("历史合同渲染非空（base 回落生效）", len(html) > 1000, f"html={len(html)} 字符")

    detail = survey_service.get_survey_contract_detail(db, batch.id, uid, original_code_before, admin)
    check("历史合同详情可打开", detail is not None and detail.get("cbhtbm") == original_code_before)

    # ── 7. 回滚测试数据 ──────────────────────────────
    restore_parcel_cbhtbm = [(p.id, p.cbhtbm) for p in parcels_before]
    for pid, code in restore_parcel_cbhtbm:
        db.execute(
            __import__("sqlalchemy").update(SurveyCbdkxxResult)
            .where(SurveyCbdkxxResult.id == pid)
            .values(cbhtbm=code)
            .execution_options(synchronize_session=False)
        )
    created = db.scalars(
        select(Cbht).where(
            Cbht.survey_batch_id == batch.id,
            Cbht.contractor_uid == uid,
            Cbht.contract_source == CONTRACT_SOURCE_GENERATED,
        ).execution_options(skip_tenant_scope=True)
    ).all()
    cbht_created = [r.cbhtbm for r in created]
    for r in created:
        db.delete(r)
    imported_row = db.get(Cbht, original_code_before) if original_code_before else None
    if imported_row is not None and imported_row.contract_source == CONTRACT_SOURCE_IMPORTED:
        imported_row.contract_status = "active"
    db.commit()
    print(f"\n已回滚：地块关联恢复原值、删除生成合同 {cbht_created}、imported 行状态复原")

    print()
    if failures:
        print(f"共 {len(failures)} 项未通过：{failures}")
        sys.exit(1)
    print("全部通过")
finally:
    db.close()
