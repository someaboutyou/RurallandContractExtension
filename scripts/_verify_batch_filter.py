"""离线验证：发包方 / 承包方管理的批次过滤（batchId）逻辑。

只读不写库。取库里一个真实批次，分别对比：
  1. batch_issuer_codes / batch_contractor_uids 能取到成员；
  2. list_issuers / list_contractors 带 batch_id 的 total 与不带时的差异；
  3. 不存在的 batch_id 抛 404。
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

from sqlalchemy import select, func  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402  触发模型注册（UserRegionPermission 等）
from app.models.survey import SurveyBatch  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.contractor_service import contractor_service  # noqa: E402
from app.services.issuer_service import issuer_service  # noqa: E402

db = SessionLocal()
try:
    batch = db.scalars(
        select(SurveyBatch).order_by(SurveyBatch.id.desc()).limit(1)
    ).first()
    if batch is None:
        print("SKIP: 库里没有调查批次")
        sys.exit(0)

    print(f"使用批次: id={batch.id} name={batch.batch_name} tenant={batch.tenant_code}")
    user = db.scalars(select(User).order_by(User.id.asc()).limit(1)).first()
    print(f"使用用户: {user.username} (id={user.id})")
    print()

    issuer_codes = issuer_service.batch_issuer_codes(db, batch.id)
    contractor_uids = contractor_service.batch_contractor_uids(db, batch.id)
    print(f"批次发包方快照: {len(issuer_codes)} 个村组；批次承包方快照: {len(contractor_uids)} 户")
    print()

    all_issuers = issuer_service.list_issuers(db, page=1, page_size=5, current_user=user)
    batch_issuers = issuer_service.list_issuers(db, page=1, page_size=5, current_user=user, batch_id=batch.id)
    print(f"发包方: 全量 total={all_issuers['total']} → 批次 total={batch_issuers['total']}")
    assert batch_issuers["total"] <= all_issuers["total"] or not issuer_codes, "批次 total 不应大于全量"
    if issuer_codes:
        assert batch_issuers["total"] > 0, "批次内应有发包方"
        for row in batch_issuers["items"]:
            assert row["code"] in issuer_codes, f"泄漏: {row['code']} 不在批次快照内"
    print(f"  批次页首 code 示例: {[r['code'] for r in batch_issuers['items'][:3]]}")

    all_contractors = contractor_service.list_contractors(db, page=1, page_size=5, current_user=user)
    batch_contractors = contractor_service.list_contractors(db, page=1, page_size=5, current_user=user, batch_id=batch.id)
    print(f"承包方: 全量 total={all_contractors['total']} → 批次 total={batch_contractors['total']}")
    if contractor_uids:
        assert batch_contractors["total"] > 0, "批次内应有承包方"
    print(f"  批次页首 cbfbm 示例: {[r['code'] for r in batch_contractors['items'][:3]]}")

    # 404 校验
    from fastapi import HTTPException  # noqa: E402

    try:
        issuer_service.batch_issuer_codes(db, 99999999)
        print("FAIL: 不存在的批次未抛 404")
        sys.exit(1)
    except HTTPException as exc:
        assert exc.status_code == 404
        print("不存在的 batch_id → 404 ✓")

    print()
    print("ALL CHECKS PASSED")
finally:
    db.close()

# ---- 追加：承包地块 overview 的批次过滤（land_parcel_service.get_parcels_overview）----
from app.services.land_parcel_service import land_parcel_service  # noqa: E402

ov_all = land_parcel_service.get_parcels_overview(db, 1, 5, None, user)
ov_batch = land_parcel_service.get_parcels_overview(db, 1, 5, None, user, batch_id=batch.id)
print(f"承包地块: 全量 total={ov_all['total']} → 批次 total={ov_batch['total']}")
if contractor_uids:
    assert ov_batch["total"] > 0, "批次内应有承包地块"
    batch_uid_set = set(contractor_uids)
    assert ov_batch["total"] <= ov_all["total"]
print("PARCEL OVERVIEW CHECK PASSED")
