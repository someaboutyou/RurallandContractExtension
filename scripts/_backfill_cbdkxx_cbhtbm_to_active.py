"""存量数据回填：把已生成现行延包合同的户，地块关联表 cbhtbm 刷成现行合同码。

背景（2026-11-13 口径变更）：生成延包合同即日起会把 survey_cbdkxx_result.cbhtbm
刷成新合同编码；此前生成的户地块关联仍挂旧码，NY/T 2539 导出的 cbdkxx.CBHTBM
与 cbht（只导 active 现行合同）引用悬空。本脚本一次性收敛存量。

默认 dry-run 只统计受影响行数；加 --apply 才真正落库。
用法：runtime/windows/python/python.exe scripts/_backfill_cbdkxx_cbhtbm_to_active.py [--apply]
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

from sqlalchemy import func, select, update  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.cbht import CONTRACT_SOURCE_GENERATED, CONTRACT_STATUS_ACTIVE, Cbht  # noqa: E402
from app.models.survey import SurveyCbdkxxResult  # noqa: E402

apply = "--apply" in sys.argv
db = SessionLocal()
try:
    # 同一承包方跨批次可能有多条 active generated 合同（各批次一份），
    # 地块关联只能挂一条 —— 按 generated_at 升序遍历，最新的覆盖先前的，并列出告警。
    contracts = db.scalars(
        select(Cbht)
        .where(
            Cbht.contract_source == CONTRACT_SOURCE_GENERATED,
            Cbht.contract_status == CONTRACT_STATUS_ACTIVE,
        )
        .order_by(Cbht.generated_at.asc().nullslast())
        .execution_options(skip_tenant_scope=True)
    ).all()
    newest_by_cbfbm: dict[str, Cbht] = {}
    multi_active: list[str] = []
    for contract in contracts:
        if contract.cbfbm and contract.cbfbm in newest_by_cbfbm:
            multi_active.append(contract.cbfbm)
        if contract.cbfbm:
            newest_by_cbfbm[contract.cbfbm] = contract
    print(f"现行延包合同 {len(contracts)} 条，覆盖 {len(newest_by_cbfbm)} 个承包方")
    if multi_active:
        print(f"⚠️ {len(set(multi_active))} 个承包方存在多条 active generated 合同（跨批次），以最新一条为准：")
        for code in sorted(set(multi_active)):
            print(f"   {code}")

    total_rows = 0
    touched = 0
    for cbfbm, contract in sorted(newest_by_cbfbm.items()):
        filters = [
            SurveyCbdkxxResult.tenant_code == contract.tenant_code,
            SurveyCbdkxxResult.cbfbm == cbfbm,
            SurveyCbdkxxResult.result_status != "removed",
            SurveyCbdkxxResult.cbhtbm != contract.cbhtbm,
        ]
        count = db.scalar(
            select(func.count()).select_from(SurveyCbdkxxResult).where(*filters).execution_options(skip_tenant_scope=True)
        )
        if not count:
            continue
        touched += 1
        total_rows += count
        print(f"  {cbfbm}  {contract.cbhtbm}  待刷 {count} 块地")
        if apply:
            db.execute(
                update(SurveyCbdkxxResult)
                .where(*filters)
                .values(cbhtbm=contract.cbhtbm)
                .execution_options(synchronize_session=False)
            )
    if apply:
        db.commit()
        print(f"\n已提交：{touched} 个承包方 / {total_rows} 行地块关联刷成现行合同码")
    else:
        print(f"\n[dry-run] 将影响 {touched} 个承包方 / {total_rows} 行；确认无误加 --apply 执行")
    if total_rows == 0:
        print("存量数据已是目标状态，无需回填")
finally:
    db.close()
