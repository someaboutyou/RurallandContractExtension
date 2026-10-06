# -*- coding: utf-8 -*-
"""验收：NY/T 2539-2016 标准格式导出（gdb / sqlite db / mdb+shp）。

跑真实 create_export 链路（管理用户 + 动态挑最小村级区域），对产物做：
1. 三格式解包结构校验（gdb 图层 / sqlite 表 / mdb 表 + shp 图层）；
2. 有效性口径对照：导出集合 == 库内有效集合，且注销/历史数据 0 泄漏；
3. 坐标序验证：ST_MakePoint(jzd.x, jzd.y) 落在有效地块边界上；
4. 收尾：删除本次验收生成的导出记录与产物。

用法：runtime/windows/python/python.exe scripts/_verify_nyt2539_export.py
"""

import io
import json
import os
import shutil
import sqlite3
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

import fiona  # noqa: E402
from sqlalchemy import func, select, text  # noqa: E402

import app.main  # noqa: F401,E402  — 注册全部 mapper（含 UserRegionPermission）
from app.db.session import SessionLocal  # noqa: E402
from app.models.cbht import Cbht  # noqa: E402
from app.models.data_export import DataExport  # noqa: E402
from app.models.survey import (  # noqa: E402
    SurveyCbfResult,
    SurveyCbdkxxResult,
    SurveyDkResult,
    SurveyJzdResult,
)
from app.models.user import User  # noqa: E402
from app.services.data_export_service import data_export_service  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def _download_and_unzip(db, export_id: int, dest: Path) -> Path:
    export = db.get(DataExport, export_id)
    zip_path = Path(__file__).resolve().parents[1] / "backend" / "storage" / export.file_path
    dest.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path) as zf:
        zf.extractall(dest)
    return dest


def main() -> None:
    db = SessionLocal()
    created_export_ids: list[int] = []
    out_root = ROOT / "runtime" / ".state" / "_verify_nyt2539_out"
    try:
        user = db.get(User, 1)
        assert user is not None, "用户 id=1 不存在"

        # ---- 动态挑一个有数据的村级（12 位）区域：行数最小的，产物生成快
        row = db.execute(
            select(SurveyCbfResult.region_code, func.count())
            .group_by(SurveyCbfResult.region_code)
            .having(func.count() > 0)
            .order_by(func.count())
        ).first()
        assert row is not None, "库里没有任何承包方数据"
        region_code = row[0]
        print(f"区域={region_code} 承包方行数={row[1]}")

        cancelled_cbfbm = set(
            db.scalars(
                select(SurveyCbfResult.cbfbm).where(
                    SurveyCbfResult.region_code.like(f"{region_code}%"),
                    SurveyCbfResult.result_status.in_(("cancelled", "extinct")),
                )
            )
        )
        print(f"该区域注销/消亡承包方 {len(cancelled_cbfbm)} 户（应为泄漏对照）")

        expected = {}
        for export_type in ("nyt2539_gdb", "nyt2539_db", "nyt2539_mdb_shp"):
            print(f"\n== 生成 {export_type} ==")
            record = data_export_service.create_export(
                db,
                {
                    "regionCode": region_code,
                    "regionName": f"验收区域{region_code}",
                    "regionLevel": "village",
                    "exportType": export_type,
                },
                user,
            )
            created_export_ids.append(record.id)
            check(f"{export_type} 状态 success", record.status == "success", record.errorMessage or "")
            if record.status != "success":
                continue

            # ---- 库内期望集合（与 _Scope 同源过滤重算）
            valid_cbfbm = set(
                db.scalars(
                    select(SurveyCbfResult.cbfbm).where(
                        SurveyCbfResult.region_code.like(f"{region_code}%"),
                        SurveyCbfResult.result_status.notin_(("cancelled", "extinct")),
                    )
                )
            )
            valid_dkbm = set(
                db.scalars(
                    select(SurveyCbdkxxResult.dkbm).where(
                        SurveyCbdkxxResult.cbfbm.in_(
                            select(SurveyCbfResult.cbfbm).where(
                                SurveyCbfResult.region_code.like(f"{region_code}%"),
                                SurveyCbfResult.result_status.notin_(("cancelled", "extinct")),
                            )
                        ),
                        SurveyCbdkxxResult.result_status.notin_(
                            ("cancelled", "extinct", "removed", "split_source")
                        ),
                    )
                )
            )
            expected[export_type] = {
                "valid_cbfbm": valid_cbfbm,
                "valid_dkbm": valid_dkbm,
                "valid_cbhtbm": set(
                    db.scalars(
                        select(Cbht.cbhtbm).where(
                            Cbht.cbfbm.in_(
                                select(SurveyCbfResult.cbfbm).where(
                                    SurveyCbfResult.region_code.like(f"{region_code}%"),
                                    SurveyCbfResult.result_status.notin_(("cancelled", "extinct")),
                                )
                            ),
                            Cbht.contract_status == "active",
                        )
                    )
                ),
            }

            # ---- 解包产物
            unzip_dir = out_root / export_type
            _download_and_unzip(db, record.id, unzip_dir)
            verify_product(export_type, unzip_dir, expected[export_type], cancelled_cbfbm, db, region_code)

        # ---- 坐标序验证：界址点(按 y,x=东,北 序取点)落在其 source_dkbm 地块边界上
        print("\n== 界址点坐标序 ==")
        r = db.execute(
            text(
                """
                SELECT j.jzdh,
                    ST_DWithin(ST_Boundary(ST_Force2D(d.geom)),
                               ST_SetSRID(ST_MakePoint(j.y, j.x), 4527), 0.002) AS hit
                FROM survey_jzd_result j
                JOIN survey_dk_result d ON d.dkbm = j.source_dkbm
                """
            )
        ).fetchall()
        check("界址点 ST_MakePoint(jzd.y, jzd.x) 命中 source 地块边界", len(r) > 0 and all(row[1] for row in r),
              f"{sum(1 for row in r if row[1])}/{len(r)} 命中")

    finally:
        db.close()

    # ---- 收尾：删除验收导出记录与产物
    db2 = SessionLocal()
    try:
        for export_id in created_export_ids:
            try:
                data_export_service.delete_export(db2, export_id, db2.get(User, 1))
            except Exception as exc:  # noqa: BLE001
                print(f"  [WARN] 清理导出记录 {export_id} 失败: {exc}")
    finally:
        db2.close()
    if out_root.exists():
        shutil.rmtree(out_root, ignore_errors=True)

    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n===== 验收结果：{len(RESULTS) - len(failed)}/{len(RESULTS)} 通过 =====")
    if failed:
        for n in failed:
            print(f"  FAIL: {n}")
        sys.exit(1)


def verify_product(export_type, unzip_dir, expected, cancelled_cbfbm, db, region_code):
    valid_cbfbm = expected["valid_cbfbm"]
    valid_dkbm = expected["valid_dkbm"]
    valid_cbhtbm = expected["valid_cbhtbm"]

    if export_type == "nyt2539_gdb":
        gdb = next(unzip_dir.rglob("*.gdb"))
        layers = set(fiona.listlayers(gdb))
        want = {"CBF", "FBF", "CBF_JTCY", "CBHT", "CBDKXX", "DK", "JZD", "JZX"}
        check("gdb 8 个图层齐全", layers == want, str(sorted(layers)))
        with fiona.open(gdb, layer="CBF") as src:
            rows = list(src)
            got = {p["properties"]["CBFBM"] for p in rows}
            check("gdb CBF 行集合 == 库内有效集合", got == valid_cbfbm,
                  f"导出{len(got)} 库内{len(valid_cbfbm)}")
            check("gdb CBF 无注销户泄漏", not (got & cancelled_cbfbm))
        with fiona.open(gdb, layer="DK") as src:
            check("gdb DK CRS=4527", src.crs.to_epsg() == 4527, str(src.crs.to_epsg()))
            got_dk = {p["properties"]["DKBM"] for p in src}
            check("gdb DK 行集合 == 有效地块集合", got_dk == valid_dkbm,
                  f"导出{len(got_dk)} 库内{len(valid_dkbm)}")

    elif export_type == "nyt2539_db":
        dbf = next(unzip_dir.rglob("*.db"))
        conn = sqlite3.connect(str(dbf))
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        want = {"CBF", "FBF", "CBF_JTCY", "CBHT", "CBDKXX", "DK", "JZD", "JZX"}
        check("db 8 张表齐全", want <= tables, str(sorted(tables)))
        got = {r[0] for r in conn.execute('SELECT CBFBM FROM CBF')}
        check("db CBF 行集合 == 库内有效集合", got == valid_cbfbm)
        check("db CBF 无注销户泄漏", not (got & cancelled_cbfbm))
        got_ht = {r[0] for r in conn.execute('SELECT CBHTBM FROM CBHT')}
        check("db CBHT 全为现行合同", got_ht <= valid_cbhtbm, f"导出{len(got_ht)}")
        n_dk = conn.execute('SELECT COUNT(*) FROM DK').fetchone()[0]
        n_dk_valid = conn.execute(
            'SELECT COUNT(*) FROM DK WHERE GEOM IS NOT NULL AND LENGTH(GEOM) > 0'
        ).fetchone()[0]
        check("db DK 几何(WKT)非空率 100%", n_dk == n_dk_valid, f"{n_dk_valid}/{n_dk}")
        conn.close()

    else:
        shp_dk = unzip_dir / "mdb_shp" / "shp" / "DK.shp"
        with fiona.open(shp_dk, encoding="utf-8") as src:
            got_dk = {p["properties"]["DKBM"] for p in src}
            check("shp DK 行集合 == 有效地块集合", got_dk == valid_dkbm,
                  f"导出{len(got_dk)} 库内{len(valid_dkbm)}")
        mdb = unzip_dir / "mdb_shp" / "属性表.mdb"
        check("mdb 文件存在", mdb.exists())
        import win32com.client

        conn = win32com.client.Dispatch("ADODB.Connection")
        conn.Open(f"Provider=Microsoft.ACE.OLEDB.12.0;Data Source={mdb};")
        rs = win32com.client.Dispatch("ADODB.Recordset")
        rs.Open("SELECT CBFBM FROM CBF", conn)
        got = set()
        while not rs.EOF:
            got.add(rs.Fields("CBFBM").Value)
            rs.MoveNext()
        rs.Close()
        check("mdb CBF 行集合 == 库内有效集合", got == valid_cbfbm)
        check("mdb CBF 无注销户泄漏", not (got & cancelled_cbfbm))
        rs.Open("SELECT TOP 1 CBFMC FROM CBF WHERE CBFMC IS NOT NULL", conn)
        name = rs.Fields("CBFMC").Value
        rs.Close()
        conn.Close()
        check("mdb 中文无乱码", bool(name) and not name.startswith("æ"), repr(name))


if __name__ == "__main__":
    main()
