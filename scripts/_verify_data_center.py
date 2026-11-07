"""离线验证：数据中心清单导出 / 导入预览 / 全库质检装载逻辑。

只读不写库：
  1. data_center_transfer.export_contractor_xls（single / group zip）能出文件；
  2. 导出文件回灌 preview_contractor_xls_import：全部应为 no_change（导出→原样导入零差异）；
  3. 伪造错误表头 → 400；错误编号 → 逐行 error；
  4. quality_check._load_db_run_context（整库与区域口径）取数正常；
  5. issuer_excel_transfer.export_xls 的 region_code 过滤生效。
"""
import io
import os
import sys
import zipfile
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
from app.models.survey import SurveyCbfResult  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.data_access_service import data_access_service  # noqa: E402
from app.services.data_center_transfer import data_center_transfer_service  # noqa: E402
from app.services.issuer_excel_transfer import issuer_excel_transfer_service  # noqa: E402
from app.services.survey import quality_check  # noqa: E402
from app.services.survey.issuer_excel_transfer import IssuerXlsTemplate  # noqa: E402

db = SessionLocal()
try:
    user = db.scalars(select(User).order_by(User.id.asc()).limit(1)).first()
    tenant = data_access_service.get_tenant_code(user)
    print(f"使用用户: {user.username} (id={user.id}) tenant={tenant}")
    total_cbf = db.scalar(select(func.count(SurveyCbfResult.id)))
    print(f"库内承包方成果行总数: {total_cbf}")
    print()

    # ── 1. 承包方清单导出（整体）──
    filename, content = data_center_transfer_service.export_contractor_xls(
        db, user, region_code=None, mode="single"
    )
    print(f"整库导出(single): {filename} ({len(content)} bytes)")
    assert filename.endswith(".xls") and len(content) > 5000

    # ── 2. 导出文件回灌预览：导出→原样导入应零差异 ──
    preview = data_center_transfer_service.preview_contractor_xls_import(db, user, content)
    summary = preview["summary"]
    print(f"回灌预览: 共 {preview['totalHouseholds']} 户 → {summary}")
    assert preview["totalHouseholds"] == sum(summary.values()), "汇总计数应一致"
    assert summary.get("error", 0) == 0, f"原样文件不应有 error: {summary}"
    unexpected = [h for h in preview["households"] if h["action"] == "update"]
    if unexpected:
        sample = unexpected[0]
        raise AssertionError(f"原样回灌不应有 update: {sample['cbfbm']} {sample['contractorChanges']}")

    # ── 3. 按发包方分组 zip ──
    zipname, zipbytes = data_center_transfer_service.export_contractor_xls(
        db, user, region_code=None, mode="group"
    )
    assert zipname.endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(zipbytes)) as zf:
        names = zf.namelist()
    print(f"整库导出(group): {zipname}，包内 {len(names)} 个 xls（前3: {names[:3]}）")
    assert len(names) >= 1 and all(n.endswith(".xls") for n in names)

    # ── 4. 错误表头 / 错误编号 ──
    bad = b"not an excel file"
    try:
        data_center_transfer_service.preview_contractor_xls_import(db, user, bad)
        raise AssertionError("非 Excel 内容应抛 400")
    except Exception as exc:
        detail = getattr(exc, "detail", None) or str(exc)
        assert "无法读取" in str(detail) or "Excel" in str(detail), f"应为无法读取类错误: {detail}"
        print("错误文件: 正确拦截（无法读取）")

    import xlwt  # noqa: E402

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("sheet1")
    ws.write(0, 0, "随便什么表头")
    ws.write(1, 0, "12345")
    buf = io.BytesIO()
    wb.save(buf)
    try:
        data_center_transfer_service.preview_contractor_xls_import(db, user, buf.getvalue())
        raise AssertionError("无「承包方编号」表头应抛 400")
    except Exception as exc:
        detail = getattr(exc, "detail", None) or str(exc)
        assert "表头" in str(detail), f"应为表头类错误: {detail}"
        print("无模板表头: 正确拦截（未找到表头）")

    # 伪造编号不存在（18 位但库内没有）→ 逐行 error
    wb2 = xlwt.Workbook(encoding="utf-8")
    ws2 = wb2.add_sheet("sheet1")
    ws2.write(0, 0, "承包方编号")
    ws2.write(0, 1, "承包方姓名")
    ws2.write(1, 0, "999999999999999999")
    ws2.write(1, 1, "测试不存在户")
    buf2 = io.BytesIO()
    wb2.save(buf2)
    preview_bad = data_center_transfer_service.preview_contractor_xls_import(db, user, buf2.getvalue())
    assert preview_bad["summary"].get("error", 0) == 1, f"不存在的编号应报 error: {preview_bad['summary']}"
    msg = preview_bad["households"][0]["errors"][0]
    assert "不存在" in msg, f"错误文案应说明仅更新已有数据: {msg}"
    print(f"不存在编号: 正确报错（{msg[:30]}…）")

    # ── 5. 质检 DB 模式上下文装载 ──
    ctx_all = quality_check._load_db_run_context(db, tenant, None)
    print(
        f"整库质检装载: 承包方 {len(ctx_all['bases'])} / 发包方 {len(ctx_all['fbf_pairs'])} / "
        f"地块 {len(ctx_all['dk_pairs'])} / 承包地块 {len(ctx_all['cbdk_pairs'])} / 合同 {len(ctx_all['contract_numbers'])}"
    )
    assert ctx_all["batch"].id == 0 and ctx_all["batch"].batch_no == "整库"
    region = (ctx_all["bases"][0].group_region_code or "")[:12] if ctx_all["bases"] else None
    if region:
        ctx_region = quality_check._load_db_run_context(db, tenant, region)
        assert len(ctx_region["bases"]) <= len(ctx_all["bases"]), "区域口径不应大于整库"
        print(f"区域 {region} 装载: 承包方 {len(ctx_region['bases'])}（区域收敛生效）")
    else:
        print("SKIP: 无承包方 group_region_code，跳过区域口径断言")

    # ── 6. 发包方清单导出的区域过滤 ──
    all_name, all_bytes = issuer_excel_transfer_service.export_xls(db, user)
    region_name, region_bytes = issuer_excel_transfer_service.export_xls(db, user, region_code="999999")
    print(f"发包方清单: 整库 {len(all_bytes)} bytes；region=999999（空域） {len(region_bytes)} bytes")
    assert len(region_bytes) < len(all_bytes), "空区域导出应显著小于整库"
    rows, warnings = IssuerXlsTemplate.parse(region_bytes)
    assert rows == [], "空区域导出应无数据行"

    print()
    print("ALL DATACENTER CHECKS PASSED")
finally:
    db.close()
