# -*- coding: utf-8 -*-
"""定点验收：NY/T 2539 导出包内权属单位代码表.xls 的存在性与内容。

跑真实 create_export（mdb_shp，动态挑最小区域），解包检查：
1. zip 内含 权属单位代码表.xls；
2. xlrd 读回，行数 == 区域表前缀子树行数，首行 == 县级补零码；
3. 与区域表逐行勾稽。
收尾删除本次验收生成的导出记录与产物。

用法：runtime/windows/python/python.exe scripts/_verify_qs_export_zip.py
"""

import io
import os
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
    text = line.strip()
    if not text or text.startswith("#") or "=" not in text:
        continue
    key, value = text.split("=", 1)
    os.environ.setdefault(key.strip(), value.strip())

sys.path.insert(0, str(ROOT / "backend"))

import xlrd  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

import app.main  # noqa: F401,E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.data_export import DataExport  # noqa: E402
from app.models.region import Region  # noqa: E402
from app.models.survey import SurveyCbfResult  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.data_export_service import data_export_service  # noqa: E402
from app.services.data_import.qs_code_table import build_qs_rows_from_regions  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def main() -> None:
    db = SessionLocal()
    export_id = None
    try:
        user = db.get(User, 1)
        assert user is not None

        row = db.execute(
            select(SurveyCbfResult.region_code, func.count())
            .group_by(SurveyCbfResult.region_code)
            .having(func.count() > 0)
            .order_by(func.count())
        ).first()
        assert row is not None, "库里没有任何承包方数据"
        region_code = row[0]
        county_prefix = str(region_code)[:6]
        print(f"区域={region_code}")

        payload = data_export_service.create_export(
            db,
            {"exportType": "nyt2539_mdb_shp", "regionCode": region_code, "remark": "qs-code-table 验收"},
            user,
        )
        export_id = payload.id
        export = db.get(DataExport, export_id)
        check("导出状态 success", export.status == "success", f"got={export.status}")

        zip_path = ROOT / "backend" / "storage" / export.file_path
        with ZipFile(zip_path) as zf:
            names = zf.namelist()
            xls_names = [n for n in names if n.endswith("权属单位代码表.xls")]
            check("zip 含权属单位代码表.xls", len(xls_names) == 1, f"got={xls_names}")

            # 导出口径：xls = 所选区域（本次导出的 region_code）子树的代码表
            expected_rows = build_qs_rows_from_regions(db, region_code)
            data = zf.read(xls_names[0])
        workbook = xlrd.open_workbook(file_contents=data)
        sheet = workbook.sheet_by_index(0)
        check("sheet 表头", str(sheet.cell_value(0, 0)) == "权属单位代码" and str(sheet.cell_value(0, 1)) == "权属单位名称")
        got_rows = []
        for r in range(1, sheet.nrows):
            v = sheet.cell_value(r, 0)
            code = str(int(v)) if isinstance(v, float) else str(v).strip()
            name = str(sheet.cell_value(r, 1)).strip()
            got_rows.append((code, name))
        check("行数 == 所选区域子树行数", len(got_rows) == len(expected_rows), f"zip={len(got_rows)} 库={len(expected_rows)}")
        check("逐行勾稽一致", got_rows == expected_rows)
        if got_rows:
            check("首行 = 所选区域补零码", got_rows[0][0] == (region_code + "0" * (14 - len(region_code)) if len(region_code) < 14 else region_code), f"got={got_rows[0]}")
            check("全部行在所选区域前缀内", all(c.startswith(region_code[:9]) for c, _ in got_rows), f"got={[c for c, _ in got_rows[:3]]}")
            codes = [c for c, _ in got_rows]
            check("补零码升序", codes == sorted(codes))
    finally:
        if export_id is not None:
            try:
                data_export_service.delete_export(db, export_id, user)
            except Exception:
                db.rollback()
        db.close()

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n共 {len(RESULTS)} 项，失败 {len(failed)} 项")
    if failed:
        for name, _, detail in failed:
            print(f"  FAIL: {name} {detail}")
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
