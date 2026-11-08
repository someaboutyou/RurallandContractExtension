"""承包地块矢量数据导出：承包地块 / 界址点 / 界址线。

支持 ESRI Shapefile 与 File Geodatabase（.gdb）两种交付格式，均打包为 zip
下载（Shapefile 必须多文件；GDB 是目录）。

范围与口径：
- 地块：仅导出勾选承包方 + 地块编码对应的当前有效成果（``survey_dk_result``）；
- 界址点：由勾选地块的边界几何空间匹配 ``survey_jzd_result``（共点只出一次）；
- 界址线：两端界址点都落在勾选地块边界上的 ``survey_jzx_result``；
- 坐标系：``app/core/crs.py`` 选定的目标投影（默认 CGCS2000 3° 高斯-克吕格）。
"""

from __future__ import annotations

import io
import json
import logging
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import fiona
from fiona.crs import CRS
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.core.crs import get_target_srid
from app.models.user import User
from app.services.data_access_service import data_access_service
from app.services.nyt2539_export_service import (
    _close_quietly,
    _ensure_proj_data,
    _fiona_props,
)

logger = logging.getLogger(__name__)

_EPSG = get_target_srid()
_INVALID_STATUSES = ("cancelled", "extinct", "removed", "split_source")
_SNAP_TOLERANCE = 0.002  # 2 毫米（米制投影坐标系）

LAYER_LABELS = {
    "dk": "承包地块",
    "jzd": "界址点",
    "jzx": "界址线",
}
SUPPORTED_FORMATS = {"shp", "gdb"}

DK_FIELDS = [
    ("DKBM", "s", 19),
    ("DKMC", "s", 50),
    ("CBFBM", "s", 18),
    ("FBFBM", "s", 14),
    ("SCMJ", "f", 0),
    ("SYQXZ", "s", 2),
    ("DKLB", "s", 2),
    ("TDLYLX", "s", 3),
    ("DLDJ", "s", 2),
    ("TDYT", "s", 1),
    ("SFJBNT", "s", 1),
    ("ZJRXM", "s", 100),
    ("DKBZXX", "s", 254),
]
JZD_FIELDS = [("JZDH", "s", 32), ("JBLX", "s", 2), ("BZ", "s", 200)]
JZX_FIELDS = [
    ("QDJZDH", "s", 32),
    ("ZDJZDH", "s", 32),
    ("JZXLB", "s", 2),
    ("JZXWZ", "s", 2),
    ("JZXSM", "s", 200),
]

_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|]')


def _safe_name(value: str) -> str:
    return _UNSAFE_FILENAME.sub("_", value or "矢量数据")


def _json_geom(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def _property_value(kind: str, value):
    if value is None:
        return None
    if kind == "f":
        return float(value)
    if kind == "i":
        return int(value)
    return str(value)


class ParcelVectorExportService:
    def _selected_parcels(
        self, db: Session, items: list[dict], current_user: User
    ) -> tuple[list[dict], list[str]]:
        rows: list[dict] = []
        dkbms: list[str] = []
        seen: set[tuple[str, str]] = set()
        seen_dkbm: set[str] = set()
        for item in items or []:
            cbfbm = str(item.get("cbfbm") or "").strip()
            dkbm = str(item.get("dkbm") or "").strip()
            if not cbfbm or not dkbm or (cbfbm, dkbm) in seen or dkbm in seen_dkbm:
                continue
            seen.add((cbfbm, dkbm))
            seen_dkbm.add(dkbm)
            data_access_service.ensure_code_in_scope(
                current_user, cbfbm, detail="承包方不在当前数据权限范围内"
            )
            row = db.execute(
                text(
                    "SELECT r.cbfbm, r.fbfbm, d.dkbm, d.dkmc, d.scmj, d.syqxz, d.dklb, "
                    "d.tdlylx, d.dldj, d.tdyt, d.sfjbnt, d.zjrxm, d.dkbzxx, "
                    "ST_AsGeoJSON(ST_Multi(d.geom)) AS geom "
                    "FROM survey_cbdkxx_result r "
                    "JOIN survey_dk_result d ON d.dkbm = r.dkbm AND d.tenant_code = r.tenant_code "
                    "WHERE r.tenant_code = :tenant AND r.cbfbm = :cbfbm AND r.dkbm = :dkbm "
                    "AND r.result_status NOT IN :invalid AND d.result_status NOT IN :invalid "
                    "AND d.geom IS NOT NULL "
                    "ORDER BY r.id DESC, d.id DESC LIMIT 1"
                ).bindparams(bindparam("invalid", expanding=True)),
                {
                    "tenant": current_user.tenant_code,
                    "cbfbm": cbfbm,
                    "dkbm": dkbm,
                    "invalid": list(_INVALID_STATUSES),
                },
            ).mappings().first()
            if row is None:
                continue
            rows.append(dict(row))
            dkbms.append(dkbm)
        return rows, list(dict.fromkeys(dkbms))

    def _jzd_rows(self, db: Session, tenant: str, dkbms: list[str]) -> list[dict]:
        if not dkbms:
            return []
        stmt = text(
            "SELECT j.jzdh, j.jblx, j.bz, "
            "ST_AsGeoJSON(ST_SetSRID(ST_MakePoint(j.y, j.x), :srid)) AS geom "
            "FROM survey_jzd_result j "
            "WHERE j.tenant_code = :tenant AND EXISTS ("
            "  SELECT 1 FROM survey_dk_result d "
            "  WHERE d.tenant_code = j.tenant_code "
            "    AND d.dkbm IN :dkbms "
            "    AND d.result_status NOT IN :invalid "
            "    AND ST_DWithin(d.geom, ST_SetSRID(ST_MakePoint(j.y, j.x), :srid), :tol)"
            ")"
        ).bindparams(
            bindparam("dkbms", expanding=True),
            bindparam("invalid", expanding=True),
        )
        return [
            dict(row)
            for row in db.execute(
                stmt,
                {
                    "tenant": tenant,
                    "dkbms": dkbms,
                    "invalid": list(_INVALID_STATUSES),
                    "srid": _EPSG,
                    "tol": _SNAP_TOLERANCE,
                },
            ).mappings()
        ]

    def _jzx_rows(self, db: Session, tenant: str, jzdhs: list[str]) -> list[dict]:
        if not jzdhs:
            return []
        stmt = text(
            "SELECT z.qdjzdh, z.zdjzdh, z.jzxlb, z.jzxwz, z.jzxsm, "
            "ST_AsGeoJSON(ST_MakeLine("
            "  ST_SetSRID(ST_MakePoint(a.y, a.x), :srid), "
            "  ST_SetSRID(ST_MakePoint(b.y, b.x), :srid)"
            ")) AS geom "
            "FROM survey_jzx_result z "
            "JOIN survey_jzd_result a ON a.jzdh = z.qdjzdh AND a.tenant_code = z.tenant_code "
            "JOIN survey_jzd_result b ON b.jzdh = z.zdjzdh AND b.tenant_code = z.tenant_code "
            "WHERE z.tenant_code = :tenant "
            "AND z.qdjzdh IN :jzdhs AND z.zdjzdh IN :jzdhs"
        ).bindparams(bindparam("jzdhs", expanding=True))
        return [
            dict(row)
            for row in db.execute(
                stmt, {"tenant": tenant, "jzdhs": jzdhs, "srid": _EPSG}
            ).mappings()
        ]

    def _write_shp(self, folder: Path, layer: str, rows: list[dict], fields) -> None:
        schema = {"geometry": self._geometry_kind(layer), "properties": _fiona_props(fields)}
        path = folder / f"{LAYER_LABELS[layer]}.shp"
        with fiona.open(
            path,
            "w",
            driver="ESRI Shapefile",
            schema=schema,
            crs=CRS.from_epsg(_EPSG),
            encoding="UTF-8",
        ) as collection:
            for row in rows:
                collection.write(
                    {
                        "geometry": _json_geom(row.get("geom")),
                        "properties": {
                            name: _property_value(kind, row.get(name.lower()))
                            for name, kind, *_ in fields
                        },
                    }
                )

    def _write_gdb(self, gdb_path: Path, layers: list[tuple[str, list[dict], list]]) -> None:
        _ensure_proj_data()
        for layer, rows, fields in layers:
            schema = {
                "geometry": self._geometry_kind(layer),
                "properties": _fiona_props(fields),
            }
            collection = fiona.open(
                gdb_path,
                "w",
                driver="OpenFileGDB",
                layer=LAYER_LABELS[layer],
                schema=schema,
                crs=CRS.from_epsg(_EPSG),
            )
            try:
                for row in rows:
                    collection.write(
                        {
                            "geometry": _json_geom(row.get("geom")),
                            "properties": {
                                name: _property_value(kind, row.get(name.lower()))
                                for name, kind, *_ in fields
                            },
                        }
                    )
            finally:
                _close_quietly(collection)

    @staticmethod
    def _geometry_kind(layer: str) -> str:
        return {"dk": "MultiPolygon", "jzd": "Point", "jzx": "LineString"}[layer]

    def export(
        self,
        db: Session,
        items: list[dict],
        layers: list[str],
        export_format: str,
        current_user: User,
    ) -> tuple[str, bytes]:
        selected_layers = [layer for layer in ("dk", "jzd", "jzx") if layer in set(layers)]
        if not selected_layers:
            raise ValueError("请至少选择一种矢量数据类型")
        if export_format not in SUPPORTED_FORMATS:
            raise ValueError("不支持的矢量数据格式")

        dk_rows, dkbms = self._selected_parcels(db, items, current_user)
        if not dkbms:
            raise ValueError("未找到可导出的地块")
        jzd_rows = self._jzd_rows(db, current_user.tenant_code, dkbms) if (
            "jzd" in selected_layers or "jzx" in selected_layers
        ) else []
        jzdhs = [row["jzdh"] for row in jzd_rows if row.get("jzdh")]
        jzx_rows = self._jzx_rows(db, current_user.tenant_code, jzdhs) if "jzx" in selected_layers else []

        layer_rows = {
            "dk": dk_rows,
            "jzd": jzd_rows,
            "jzx": jzx_rows,
        }
        fields_map = {"dk": DK_FIELDS, "jzd": JZD_FIELDS, "jzx": JZX_FIELDS}

        work_dir = Path(tempfile.mkdtemp(prefix="parcel_vector_"))
        try:
            if export_format == "shp":
                for layer in selected_layers:
                    self._write_shp(work_dir, layer, layer_rows[layer], fields_map[layer])
                archive_root = work_dir
            else:
                gdb_path = work_dir / "承包地块矢量数据.gdb"
                self._write_gdb(
                    gdb_path,
                    [(layer, layer_rows[layer], fields_map[layer]) for layer in selected_layers],
                )
                archive_root = work_dir

            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(archive_root.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(archive_root).as_posix())
            suffix = "shapefile" if export_format == "shp" else "gdb"
            labels = "、".join(LAYER_LABELS[layer] for layer in selected_layers)
            filename = _safe_name(f"{labels}矢量数据_{suffix}.zip")
            return filename, buffer.getvalue()
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)


parcel_vector_export_service = ParcelVectorExportService()
