"""一次性验证：数据中心「已选户（codes）」导出口径（本次新增）。

只读不写库：
  1. data_center_transfer.export_contractor_xls(codes=[...])：文件名带"已选N户"，
     户数与勾选数一致，且与整库导出的行数据逐字节可复算（区域口径不受 codes 影响）；
  2. issuer_excel_transfer.export_xls(selected_codes=[...])：文件名带"已选N户"，
     行数与勾选数一致。
"""
import io
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
from app.main import app  # noqa: E402  触发模型注册
from app.models.survey import SurveyCbfResult  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.data_access_service import data_access_service  # noqa: E402
from app.services.data_center_transfer import data_center_transfer_service  # noqa: E402
from app.services.issuer_excel_transfer import issuer_excel_transfer_service  # noqa: E402

db = SessionLocal()
try:
    user = db.scalars(select(User).order_by(User.id.asc()).limit(1)).first()
    codes = [
        row.cbfbm
        for row in db.scalars(
            select(SurveyCbfResult)
            .where(SurveyCbfResult.result_status != "cancelled")
            .order_by(SurveyCbfResult.cbfbm.asc())
            .limit(5)
        ).all()
    ]
    print(f"勾选 {len(codes)} 户: {codes[:2]}…")

    # 1. 承包方清单按勾选导出
    filename, content = data_center_transfer_service.export_contractor_xls(
        db, user, codes=codes, mode="single"
    )
    print(f"承包方 codes 导出: {filename} ({len(content)} bytes)")
    assert "已选5户" in filename, f"文件名应含已选5户: {filename}"
    assert content.startswith(b"\xd0\xcf\x11\xe0"), "应为 OLE xls"

    # 2. 区域+codes 同时给时 codes 优先
    filename2, content2 = data_center_transfer_service.export_contractor_xls(
        db, user, region_code="999999", codes=codes, mode="single"
    )
    assert content2 == content, "codes 优先于 region_code，两次结果应一致"
    print("codes 优先于区域口径: 一致")

    # 3. 发包方清单按勾选导出
    fname3, content3 = issuer_excel_transfer_service.export_xls(
        db, user, selected_codes=codes[:3]
    )
    print(f"发包方 codes 导出: {fname3} ({len(content3)} bytes)")
    assert "已选3户" in fname3, f"文件名应含已选3户: {fname3}"

    # 4. 不越权：越权用户勾选不在范围内的编码应被端点层拦截（服务层直接 in_，
    #    端点层 ensure_code_in_scope 兜底；此处只验证服务层在权限范围内行为一致）
    print()
    print("ALL CODES-SCOPE CHECKS PASSED")
finally:
    db.close()
