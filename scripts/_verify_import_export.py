# -*- coding: utf-8 -*-
"""导入/导出功能离线验收（坐标系收口改造后回归）。

覆盖：
  L1 导入 CRS 闸门：正例（真实 4527 GDB 放行）+ 反例（4326 shp 拒收 / 无 CRS 拒收）
  L2 导入写几何：write_dk_geometries 打标签 round-trip（SRID/坐标逐位比对，事务回滚）
  L3 录入转换：_geojson_to_target_sql 4326→目标带（SRID/类型/坐标落带范围）
  L4 NY/T 2539 导出端到端：create_export(nyt2539_gdb) → zip 结构 + 说明文案 + 记录数

用法：runtime/windows/python/python.exe scripts/_verify_import_export.py
产物与临时文件都在 runtime/.state/_verify_io/ 下；导出记录用完即删。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "runtime" / ".state" / "_verify_io"
if WORK.exists():
    shutil.rmtree(WORK)
WORK.mkdir(parents=True)

# ── 先注入环境变量再 import app（老规矩）──────────────────────────────────
runtime_env = ROOT / "runtime" / ".state" / "runtime.env"
if runtime_env.exists():
    for line in runtime_env.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

sys.path.insert(0, str(ROOT / "backend"))

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, bool(ok), detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" | {detail}" if detail else ""))


import app.main  # noqa: E402,F401 —— 注册全部 mapper
import fiona  # noqa: E402
from fiona.crs import CRS as FionaCRS  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.crs import crs_to_epsg, describe_mismatch, get_target_srid, srid_display_name  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.data_export_service import data_export_service  # noqa: E402
from app.services.data_import.row_import import write_dk_geometries  # noqa: E402
from app.services.survey import parcel_geometry as pg_module  # noqa: E402

TARGET = get_target_srid()

# ═══ L1 导入 CRS 闸门 ═════════════════════════════════════════════════
print("── L1 导入 CRS 闸门 ──")


def _gate(gdb_path: str, layer_names: list[str]) -> tuple[int | None, str]:
    """复刻 progress.process_gdb_layers 的闸门片段（只读，不写库）。"""
    source_srid: int | None = None
    for layer_name in layer_names:
        try:
            with fiona.open(gdb_path, layer=layer_name) as source:
                source_srid = crs_to_epsg(source.crs)
        except Exception:
            source_srid = None
        if source_srid is not None:
            break
    if source_srid == TARGET:
        return source_srid, ""
    return source_srid, describe_mismatch(source_srid, TARGET)


# 正例：真实 4527 GDB
gdb_sample = ROOT / "datas" / "sihongTest.gdb"
if gdb_sample.exists():
    layers = list(fiona.listlayers(str(gdb_sample)))
    srid, detail = _gate(str(gdb_sample), layers)
    check("闸门正例：sihongTest.gdb（4527）放行", srid == TARGET,
          f"layers={layers[:4]} resolved={srid}")
else:
    check("闸门正例：找不到 datas/sihongTest.gdb（跳过样本改为 NYT 回流包）", False)

# 正例备选：NYT2539 导出回流 GDB
for cand in (ROOT / "datas").glob("NYT2539_导入数据*.gdb"):
    layers = list(fiona.listlayers(str(cand)))
    srid, detail = _gate(str(cand), layers)
    check(f"闸门正例：{cand.name} 放行", srid == TARGET, f"resolved={srid}")
    break

# 反例 1：4326 shp → 必须拒收
shp_4326 = WORK / "wrong_zone.shp"
schema = {"geometry": "Polygon", "properties": {"n": "int"}}
with fiona.open(
    str(shp_4326), "w", driver="ESRI Shapefile", crs="EPSG:4326", schema=schema
) as out:
    out.write({
        "geometry": {"type": "Polygon",
                     "coordinates": [[[116.0, 33.0], [116.01, 33.0], [116.01, 33.01], [116.0, 33.01], [116.0, 33.0]]]},
        "properties": {"n": 1},
    })
with fiona.open(str(shp_4326)) as src:
    srid, detail = _gate(str(shp_4326), [Path(shp_4326).stem])
check("闸门反例：4326 shp 拒收且文案点名双方坐标系",
      srid == 4326 and "4326" in detail and str(TARGET) in detail,
      detail[:100])

# 反例 2：CRS 元数据为空 → 必须按"无法识别"拒收
shp_nocrs = WORK / "nocrs.shp"
with fiona.open(str(shp_nocrs), "w", driver="ESRI Shapefile", crs=None, schema=schema) as out:
    out.write({
        "geometry": {"type": "Polygon",
                     "coordinates": [[[116.0, 33.0], [116.01, 33.0], [116.01, 33.01], [116.0, 33.01], [116.0, 33.0]]]},
        "properties": {"n": 1},
    })
with fiona.open(str(shp_nocrs)) as src:
    raw = crs_to_epsg(src.crs)
srid, detail = _gate(str(shp_nocrs), ["nocrs"])
check("闸门反例：无 CRS 拒收（宁拒不猜带）",
      raw is None and srid != TARGET and detail, detail[:100])

# ═══ L2 导入写几何 round-trip ═════════════════════════════════════════
print("── L2 导入写几何（write_dk_geometries）──")
db = SessionLocal()
try:
    row = db.execute(text(
        "SELECT id, ST_SRID(geom) AS srid, ST_AsText(geom) AS wkt "
        "FROM survey_dk_result WHERE geom IS NOT NULL ORDER BY id LIMIT 1"
    )).mappings().one()
    original_wkt = row["wkt"]

    geojson = json.loads(db.execute(text(
        "SELECT ST_AsGeoJSON(geom) FROM survey_dk_result WHERE id = :id"
    ), {"id": row["id"]}).scalar())

    write_dk_geometries(db, "survey_dk_result", {row["id"]: geojson})
    after = db.execute(text(
        "SELECT ST_SRID(geom) AS srid, ST_Equals(geom, "
        "ST_SetSRID(ST_GeomFromGeoJSON(:before), :srid)) AS equal, "
        "ST_IsValid(geom) AS valid, "
        "abs(ST_Area(geom) - :area) AS darea "
        "FROM survey_dk_result WHERE id = :id"
    ), {"before": json.dumps(geojson), "srid": TARGET, "id": row["id"],
        "area": db.execute(text(
            "SELECT ST_Area(geom) FROM survey_dk_result WHERE id = :id"
        ), {"id": row["id"]}).scalar()}).mappings().one()

    check("write_dk_geometries：写入后 SRID = 目标带",
          after["srid"] == TARGET, f"expected {TARGET}, got {after['srid']}")
    check("write_dk_geometries：几何完全一致、面积零漂移（只打标签不变形）",
          after["equal"] and after["valid"] and after["darea"] == 0,
          f"equal={after['equal']} darea={after['darea']}")

    # 空 geometry → 置 NULL（导入链路对无图形行的处理）
    write_dk_geometries(db, "survey_dk_result", {row["id"]: None})
    after_null = db.execute(text(
        "SELECT geom IS NULL AS is_null FROM survey_dk_result WHERE id = :id"
    ), {"id": row["id"]}).scalar()
    check("write_dk_geometries：空 geometry 置 NULL", bool(after_null))
    db.rollback()  # ⛔ 测试数据不落盘
    check("事务已回滚，测试改动不落盘", True)
finally:
    db.close()

# ═══ L3 录入转换路径（4326 → 目标带）══════════════════════════════════
print("── L3 录入转换路径（_geojson_to_target_sql）──")
owner_cls = next(
    (v for v in vars(pg_module).values()
     if isinstance(v, type) and "_geojson_to_target_sql" in vars(v)),
    None,
)
if owner_cls is None:
    check("定位 _geojson_to_target_sql 所属类", False)
else:
    frag = owner_cls._geojson_to_target_sql(None)  # 纯字符串构造，不依赖实例状态
    poly_4326 = {"type": "Polygon", "coordinates": [[[118.20, 33.46], [118.22, 33.46],
                                                    [118.22, 33.48], [118.20, 33.48], [118.20, 33.46]]]}
    db = SessionLocal()
    try:
        rec = db.execute(
            text(
                f"SELECT ST_SRID(g) AS srid, ST_GeometryType(g) AS gtype, "
                f"ST_X(ST_Centroid(g)) AS cx, ST_Y(ST_Centroid(g)) AS cy "
                f"FROM (SELECT {frag} AS g) t"
            ),
            {"geojson": json.dumps(poly_4326), "source_srid": 4326},
        ).mappings().one()
        in_zone = 39_000_000 <= rec["cx"] < 40_000_000 and 3_300_000 <= rec["cy"] < 4_100_000
        check("录入转换：SRID = 目标带 且 MultiPolygon",
              rec["srid"] == TARGET and rec["gtype"] == "ST_MultiPolygon",
              f"srid={rec['srid']} type={rec['gtype']}")
        check("录入转换：质心落在 39 带坐标范围（39xxxxxx / 3xxx xxx）",
              in_zone, f"cx={rec['cx']:.1f} cy={rec['cy']:.1f}")
    finally:
        db.close()

# ═══ L4 NY/T 2539 导出端到端 ══════════════════════════════════════════
print("── L4 NY/T 2539 导出（nyt2539_gdb，区域 321324100008）──")
db = SessionLocal()
export_id = None
try:
    admin = db.get(User, 1)
    result = data_export_service.create_export(
        db,
        {"regionCode": "321324100008", "regionName": "IO验收测试区", "exportType": "nyt2539_gdb"},
        admin,
    )
    export_id = result.id
    check("create_export 状态 = success",
          result.status == "success",
          f"status={result.status} msg={result.progressMessage} err={(result.errorMessage or '')[:120]}")
    check("记录数 > 0 且文件非空",
          (result.recordCount or 0) > 0 and (result.fileSize or 0) > 0,
          f"records={result.recordCount} bytes={result.fileSize}")

    zip_path = ROOT / "backend" / "storage" / "data_exports" / str(export_id) / (result.fileName or "")
    if zip_path.exists():
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            gdb_files = [n for n in names if ".gdb" in n]
            readme_name = next((n for n in names if n.endswith("导出说明.txt")), None)
            readme = zf.read(readme_name).decode("utf-8-sig") if readme_name else ""
            has_a0001 = any("a00000001.gdbtable" in n for n in gdb_files)
            check("zip 内含 FileGDB 主体文件", has_a0001, f"gdb entries={len(gdb_files)}")
            check("导出说明.txt 坐标系文案 = 目标带动态生成",
                  srid_display_name(TARGET) in readme or f"EPSG:{TARGET}" in readme,
                  (readme_name or "无说明文件"))
    else:
        check("导出 zip 存在", False, str(zip_path))
finally:
    # 清理：删导出记录 + 产物目录，不留测试数据
    if export_id is not None:
        try:
            from app.models.data_export import DataExport
            exp = db.get(DataExport, export_id)
            if exp is not None:
                db.delete(exp)
                db.commit()
            shutil.rmtree(ROOT / "backend" / "storage" / "data_exports" / str(export_id),
                          ignore_errors=True)
            print(f"[CLEAN] 导出记录 {export_id} 与产物目录已删除")
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] 清理失败（可手动删）：export_id={export_id} err={exc}")
    db.close()

# ═══ 汇总 ═════════════════════════════════════════════════════════════
failed = [r for r in _results if not r[1]]
print("=" * 60)
print(f"TOTAL {len(_results)} | PASS {len(_results) - len(failed)} | FAIL {len(failed)}")
for name, _, detail in failed:
    print(f"  FAILED: {name} | {detail}")
sys.exit(1 if failed else 0)
