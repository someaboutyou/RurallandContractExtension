"""国标包（NY/T 2539 标准数据包：权属 mdb + 矢量 shp）导入。

与 GDB 导入（progress.py）共用同一套骨架：zip 落盘 → 解压 → 后台任务 →
逐行 SAVEPOINT 导入 → DataImportRow/Operation 记录 → 进度上报 → 回滚。

差异点：

1. **权属数据**：mdb 经 pyodbc + ACE ODBC 驱动**只读**读取（requirements
   注释里的段错误警告只针对"写路径"；现网部署机因 NY/T 2539 导出在用
   ACE OLEDB，驱动必然存在）。表名大小写不敏感，字段与大写 GDB 图层同构，
   直接复用 FIELD_MAPS + normalize_row。
2. **矢量数据**：shp 文件名 = 图层前缀 + 行政区划代码（如 DK1505262019.shp），
   按**前缀**识别；dbf 可能是 GBK 或 UTF-8，统一由 ``detect_dbf_encoding``
   抽样字段字节判断后打开，避免 UTF-8 被误按 GBK 解码成乱码。
   只取 DK/JZD/JZX 三类，其余图层（CJQY/XJQY/DZDW 等）忽略。
3. **界址点/界址线不直接灌表**：本系统的约定是"地块图形是界址点位置的
   唯一来源"（见 services/survey/boundary.py 模块注释），点号是内部自编的
   ``JZD``+序号。因此 JZD/JZX shp 只作**属性补充**：导入 DK 面后按图形
   批量 get-or-create 界址点/线（共点共线不重复），再把 shp 里的界标类型、
   界址线类别/位置/说明按坐标 / 点对回填。
4. **坐标系**：不做硬闸门（与 GDB 导入的"整包拒绝"不同）。源 CRS 能解析
   且不等于目标坐标系时用 pyproj 自动投影转换；解析不出则告警并按目标
   坐标系原样入库。
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.crs import crs_to_epsg, get_target_srid, srid_display_name
from app.db.session import SessionLocal, set_current_user
from app.models.data_import import DataImportBatch, DataImportFile
from app.models.survey import SurveyJzdResult, SurveyJzxResult
from app.models.user import User
from app.paths import STORAGE_DIR
from app.services.data_access_service import data_access_service
from app.services.data_import_progress import data_import_progress
from app.services.geoserver_service import geoserver_service
from app.services.survey.boundary import (
    POINT_CODE_PREFIX,
    POINT_CODE_WIDTH,
    _load_lines_by_points,
    _load_points_by_coords,
    _order_pair,
    _to_mm,
    load_parcel_rings,
)

from .constants import (
    GB_MDB_TABLE_NAMES,
    GB_MDB_TABLE_ORDER,
    GB_SHP_LAYER_ALIASES,
    GB_SHP_LAYER_ORDER,
    JZD_ATTR_FIELD_MAP,
    JZX_ATTR_FIELD_MAP,
)
from .core_helpers import ensure_import_survey_batch, finish_batch_import
from .errors import ImportCanceled
from .helpers import (
    apply_gdb_region_defaults,
    entity_key,
    field_map_for,
    json_safe,
    normalize_row,
    record_operation,
    serialize_batch,
    snapshot_model,
)
from .progress import extract_zip_safely
from .row_import import import_row, recount_result_member_counts

logger = logging.getLogger(__name__)

_SHP_PREFIX_PATTERN = re.compile(r"^[A-Za-z]+")
_BOUNDARY_CHUNK = 500
_BOUNDARY_INSERT_CHUNK = 5000


# ===========================================================================
# Entry points（与 progress.py 的 GDB 入口同构）
# ===========================================================================

async def start_gb_import_job(
    db: Session,
    batch: DataImportBatch,
    upload_file: UploadFile,
    current_user: User,
    background_tasks,
) -> dict:
    if not batch.region_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="上传国标数据包必须先选择区域",
        )
    content = await upload_file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="uploaded file is empty")
    filename = upload_file.filename or "import_gb.zip"
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请上传包含权属数据（mdb）与矢量数据（shp）的 ZIP 压缩包")

    storage_dir = STORAGE_DIR / "data_imports" / str(batch.id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    stored_path = storage_dir / f"{datetime.now():%Y%m%d%H%M%S}_{Path(filename).name}"
    stored_path.write_bytes(content)

    job_id = f"gb:{batch.id}:{datetime.now(timezone.utc).timestamp()}"
    batch.status = "processing"
    batch.source_type = "gb_package"
    batch.source_name = filename
    batch.imported_by = current_user.id
    batch.imported_by_name = current_user.real_name
    batch.imported_at = datetime.now(timezone.utc)
    db.commit()
    data_import_progress.init(
        batch.id,
        job_id,
        {
            "status": "queued",
            "message": "国标包导入任务已提交：",
            "filename": filename,
            "fileSize": len(content),
        },
    )
    background_tasks.add_task(
        run_gb_import_job,
        batch.id,
        str(stored_path),
        filename,
        upload_file.content_type,
        current_user.id,
        job_id,
    )
    return {"batchId": batch.id, "jobId": job_id, "status": "queued"}


def run_gb_import_job(
    batch_id: int,
    stored_path: str,
    filename: str,
    content_type: str | None,
    user_id: int,
    job_id: str,
) -> None:
    db = SessionLocal()
    try:
        current_user = db.get(User, user_id)
        batch = db.get(DataImportBatch, batch_id)
        if current_user is None or batch is None:
            data_import_progress.update(batch_id, status="failed", message="import context not found")
            return
        set_current_user(db, current_user)
        data_access_service.ensure_region_in_scope(
            current_user,
            batch.region_code,
            detail="import batch is outside the current authorized scope",
        )
        data_import_progress.update(batch_id, status="running", message="background import started")
        content = Path(stored_path).read_bytes()
        process_gb_package_archive_content(db, batch, filename, content, content_type, current_user, job_id=job_id)
    except ImportCanceled:
        db.rollback()
        batch = db.get(DataImportBatch, batch_id)
        if batch is not None:
            batch.status = "canceled"
            db.commit()
        data_import_progress.update(batch_id, status="canceled", message="import canceled")
        logger.info("GB package import canceled: batch_id=%s", batch_id)
    except Exception:
        db.rollback()
        batch = db.get(DataImportBatch, batch_id)
        if batch is not None:
            batch.status = "failed"
            db.commit()
        data_import_progress.update(batch_id, status="failed", message="import failed; see backend logs")
        logger.exception("GB package import job failed: batch_id=%s filename=%s", batch_id, filename)
    finally:
        db.close()


def process_gb_package_archive_content(
    db: Session,
    batch: DataImportBatch,
    filename: str,
    content: bytes,
    content_type: str | None,
    current_user: User,
    job_id: str | None = None,
) -> dict:
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请上传包含权属数据（mdb）与矢量数据（shp）的 ZIP 压缩包")

    try:
        logger.info(
            "GB package import started: batch_id=%s import_no=%s filename=%s size=%s user_id=%s region_code=%s",
            batch.id, batch.import_no, filename, len(content), current_user.id, batch.region_code,
        )
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        logger.warning("GB package import rejected: invalid zip batch_id=%s filename=%s", batch.id, filename)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="failed to read ZIP archive") from exc

    now = datetime.now(timezone.utc)
    batch.source_type = "gb_package"
    archive_file = DataImportFile(
        tenant_code=batch.tenant_code,
        region_code=batch.region_code,
        import_batch_id=batch.id,
        file_type="gb_package_archive",
        original_name=filename,
        content_type=content_type,
        file_size=len(content),
        file_hash=hashlib.sha256(content).hexdigest(),
        parse_status="success",
        row_count=0,
        uploaded_by=current_user.id,
        uploaded_at=now,
        remark="national standard package import (mdb + shp)",
    )
    db.add(archive_file)
    db.flush()

    with tempfile.TemporaryDirectory(prefix="rural_gb_") as temp_dir:
        extract_zip_safely(archive, temp_dir)
        mdb_path = find_mdb_path(temp_dir)
        shp_map = discover_shp_layers(temp_dir)
        logger.info(
            "GB package discovered: batch_id=%s mdb=%s shp=%s",
            batch.id, mdb_path, sorted(shp_map),
        )
        if "dk" not in shp_map:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="矢量数据中未找到 DK（地块）图层，无法导入国标包",
            )
        stats_list = process_gb_package(db, batch, mdb_path, shp_map, current_user, now)

    archive_file.row_count = sum(item["row_count"] for item in stats_list)
    archive_file.error_count = sum(item["failed_count"] for item in stats_list)
    archive_file.parse_status = "success" if archive_file.error_count == 0 else ("partial_success" if archive_file.row_count else "failed")
    finish_batch_import(
        db, batch,
        stats_list=stats_list,
        source_name=filename,
        file_hash=archive_file.file_hash,
        current_user=current_user,
        now=now,
    )
    geoserver_service.recalculate_default_bounds()
    logger.info(
        "GB package import finished: batch_id=%s total=%s success=%s failed=%s",
        batch.id, batch.total_count, batch.success_count, batch.failed_count,
    )
    data_import_progress.update(batch.id, status=batch.status, message="国标包导入完成")
    return serialize_batch(batch)


# ===========================================================================
# Archive discovery
# ===========================================================================

def find_mdb_path(root_dir: str) -> str:
    """定位权属 mdb。忽略内嵌 zip（不递归解压）；多个 mdb 时拒绝并点名。"""
    candidates = [p for p in Path(root_dir).rglob("*.mdb") if p.is_file()]
    # Access 的 .accdb 同样支持，顺手兼容
    candidates += [p for p in Path(root_dir).rglob("*.accdb") if p.is_file()]
    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="压缩包中未找到权属数据（.mdb），请确认包内包含「权属数据」目录",
        )
    if len(candidates) > 1:
        names = "、".join(str(p.relative_to(root_dir)) for p in candidates[:5])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"压缩包中发现了多个权属数据库（{names}），请只保留一个后再导入",
        )
    return str(candidates[0])


def infer_shp_layer_type(shp_path: Path) -> str | None:
    """按文件名前缀识别图层类型（DK1505262019.shp → dk）。"""
    stem = shp_path.stem.lower()
    match = _SHP_PREFIX_PATTERN.match(stem)
    if not match:
        return None
    prefix = match.group(0)
    for file_type in GB_SHP_LAYER_ORDER:
        if prefix in GB_SHP_LAYER_ALIASES[file_type]:
            return file_type
    return None


def discover_shp_layers(root_dir: str) -> dict[str, str]:
    """返回 {file_type: shp 路径}。同名图层重复时取第一个并告警。"""
    layer_map: dict[str, str] = {}
    for shp_path in sorted(Path(root_dir).rglob("*.shp")):
        file_type = infer_shp_layer_type(shp_path)
        if not file_type:
            continue
        if file_type in layer_map:
            logger.warning(
                "GB package duplicate shp layer ignored: type=%s kept=%s skipped=%s",
                file_type, layer_map[file_type], shp_path,
            )
            continue
        layer_map[file_type] = str(shp_path)
    return layer_map


# ===========================================================================
# mdb reading (pyodbc + ACE ODBC, read-only)
# ===========================================================================

def read_mdb_table(mdb_path: str, table_name: str) -> list[dict]:
    """只读整表。表名用 [] 包裹避免关键字冲突；返回值已 JSON 安全化。"""
    try:
        import pyodbc
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="服务器缺少 pyodbc，无法读取权属 mdb（需安装 Microsoft Access Database Engine）",
        ) from exc
    connection_string = (
        "Driver={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={mdb_path};"
    )
    connection = pyodbc.connect(connection_string, ansi=False)
    try:
        cursor = connection.cursor()
        existing = {row.table_name.lower() for row in cursor.tables(tableType="TABLE")}
        if table_name.lower() not in existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"权属 mdb 中缺少 {table_name} 表，数据包不完整",
            )
        cursor.execute(f"select * from [{table_name}]")
        columns = [column[0] for column in cursor.description]
        return [json_safe(dict(zip(columns, row))) for row in cursor.fetchall()]
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to read mdb table: mdb=%s table=%s", mdb_path, table_name)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"读取权属 mdb 的 {table_name} 表失败：{exc}",
        ) from exc
    finally:
        connection.close()


# ===========================================================================
# CRS
# ===========================================================================

def detect_dbf_encoding(shp_path: str | Path) -> str | None:
    """推断 DBF 文本字段编码：UTF-8 优先，其次 GB18030/GBK。

    部分国标包的 DK/JZD/JZX shapefile 实际使用 UTF-8（且带 UTF-8 LDID），
    早期代码一律传 ``encoding="gbk"``，会把 UTF-8 中文解成「涓滆タ鍦」这类
    乱码。这里直接抽样 DBF 原始字段字节判断，避免依赖 GDAL 的默认猜测。
    """
    dbf_path = Path(shp_path).with_suffix(".dbf")
    if not dbf_path.exists():
        return None
    data = dbf_path.read_bytes()
    if len(data) < 32:
        return None
    record_count = int.from_bytes(data[4:8], "little")
    header_length = int.from_bytes(data[8:10], "little")
    record_length = int.from_bytes(data[10:12], "little")
    fields: list[tuple[str, int]] = []
    pos = 32
    while pos + 32 <= len(data) and data[pos] != 0x0D:
        field_type = chr(data[pos + 11])
        field_length = data[pos + 16]
        fields.append((field_type, field_length))
        pos += 32
    if not fields or header_length <= 0 or record_length <= 0:
        return None

    samples: list[bytes] = []
    for index in range(min(record_count, 30)):
        start = header_length + index * record_length
        record = data[start : start + record_length]
        if len(record) < record_length or record[:1] == b"*":
            continue
        offset = 1
        for field_type, field_length in fields:
            raw = record[offset : offset + field_length].rstrip(b" \x00")
            offset += field_length
            if field_type == "C" and raw:
                samples.append(raw)
    if not samples:
        return None
    if not any(byte >= 0x80 for raw in samples for byte in raw):
        return None
    try:
        for raw in samples:
            raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        for raw in samples:
            raw.decode("gb18030")
        return "gb18030"
    except UnicodeDecodeError:
        return "gbk"


def _open_shp(shp_path: str | Path):
    import fiona

    return fiona.open(shp_path, encoding=detect_dbf_encoding(shp_path))


def make_geometry_transformer(source_crs):
    """源 CRS 能解析且 != 目标坐标系时返回 pyproj Transformer，否则 None。"""
    target_srid = get_target_srid()
    source_srid = crs_to_epsg(source_crs)
    if source_srid is None:
        logger.warning(
            "GB package CRS unrecognized; importing coordinates as target SRID %s",
            target_srid,
        )
        return None
    if source_srid == target_srid:
        return None
    from pyproj import Transformer

    logger.info(
        "GB package CRS transform: source=%s target=%s",
        srid_display_name(source_srid), srid_display_name(target_srid),
    )
    return Transformer.from_crs(source_srid, target_srid, always_xy=True)


def transform_geometry(geometry, transformer):
    """递归把 GeoJSON 几何坐标经 Transformer 投影（无 transformer 时原样返回）。"""
    if geometry is None or transformer is None:
        return geometry

    def convert(node):
        if isinstance(node[0], (int, float)):
            x, y = transformer.transform(node[0], node[1])
            return [x, y]
        return [convert(child) for child in node]

    result = dict(geometry)
    if result.get("coordinates"):
        result["coordinates"] = convert(result["coordinates"])
    return result


# ===========================================================================
# Layer processing（与 progress.process_gdb_layer 同构，来源换成 list / shp）
# ===========================================================================

class _ProgressState:
    """跨图层累计的进度计数器（与 GDB 管线同一份语义）。"""

    def __init__(self, batch_id: int):
        self.batch_id = batch_id
        progress = data_import_progress.get(batch_id) or {}
        self.processed = int(progress.get("processedRows") or 0)
        self.success = int(progress.get("successRows") or 0)
        self.failed = int(progress.get("failedRows") or 0)
        self.total = int(progress.get("totalRows") or 0)

    def flush(self, current_layer: str | None = None, **total_overrides) -> None:
        payload = {
            "processedRows": self.processed,
            "successRows": self.success,
            "failedRows": self.failed,
        }
        if current_layer:
            payload["currentLayer"] = current_layer
            payload["message"] = f"Processing {current_layer}"
        if total_overrides:
            payload.update(total_overrides)
        data_import_progress.update(self.batch_id, **payload)


def _new_import_file(db: Session, batch: DataImportBatch, current_user: User, now, *, file_type: str, original_name: str, content_type: str, remark: str) -> DataImportFile:
    import_file = DataImportFile(
        tenant_code=batch.tenant_code,
        region_code=batch.region_code,
        import_batch_id=batch.id,
        file_type=file_type,
        original_name=original_name,
        content_type=content_type,
        file_size=0,
        parse_status="success",
        row_count=0,
        uploaded_by=current_user.id,
        uploaded_at=now,
        remark=remark,
    )
    db.add(import_file)
    db.flush()
    return import_file


def _process_row_stream(
    db: Session,
    batch: DataImportBatch,
    current_user: User,
    now,
    *,
    file_type: str,
    import_file: DataImportFile,
    survey_batch,
    stream,
    progress: _ProgressState,
    layer_label: str,
) -> dict:
    """逐行导入一个图层/表。stream 产出 (raw_dict, geometry_or_None)。"""
    fm = field_map_for(file_type)
    success_count = 0
    failed_count = 0
    seen_keys: set[str] = set()
    affected_contractors: set[str] = set()
    row_no = 0

    def process_items(items: list[dict]) -> None:
        nonlocal success_count, failed_count
        if not items:
            return
        context = {"survey_batch": survey_batch, "gdb_result_only": True}
        for item in items:
            from app.models.data_import import DataImportRow

            row_record = DataImportRow(
                tenant_code=batch.tenant_code,
                region_code=batch.region_code,
                import_batch_id=batch.id,
                import_file_id=import_file.id,
                row_no=item["row_no"],
                entity_type=file_type,
                entity_key=item["entity_key"],
                operation_type="insert",
                status="pending",
                target_table=f"survey_{file_type}_result",
                raw_data=item["raw"],
                normalized_data=item["normalized"],
            )
            row_status = "pending"
            try:
                with db.begin_nested():
                    # 缺键行（如成员缺 cbfbm/cyzjhm）照常落库做整理，仅用行号合成
                    # 临时键防同批重复计签；真实 entity_key 仍原样记录。
                    dedup_key = item["entity_key"] or f"__unkeyed__:{item['row_no']}"
                    if dedup_key in seen_keys:
                        raise ValueError(f"Duplicate entity key: {dedup_key}")
                    operation, target_id = import_row(
                        db, batch, import_file, row_record, file_type, item["normalized"],
                        current_user, now, item.get("geometry"), context,
                    )
                seen_keys.add(dedup_key)
                row_record.operation_type = operation
                row_status = "success"
                row_record.target_id = target_id
                if item["normalized"].get("cbfbm"):
                    affected_contractors.add(item["normalized"]["cbfbm"])
                success_count += 1
            except Exception as exc:
                row_status = "failed"
                row_record.status = "failed"
                row_record.operation_type = "error"
                row_record.error_message = str(exc)
                db.add(row_record)
                failed_count += 1
                logger.exception(
                    "GB row import failed: batch_id=%s file_type=%s row_no=%s entity_key=%s",
                    batch.id, file_type, item["row_no"], item["entity_key"],
                )
            finally:
                progress.processed += 1
                progress.success += 1 if row_status == "success" else 0
                progress.failed += 1 if row_status == "failed" else 0
                if progress.processed % 100 == 0:
                    progress.flush(layer_label)
        db.commit()
        progress.flush(layer_label)

    pending_items: list[dict] = []
    for raw, geometry in stream:
        row_no += 1
        if row_no % 200 == 0 and data_import_progress.is_cancel_requested(batch.id):
            raise ImportCanceled()
        normalized = normalize_row(raw, fm)
        apply_gdb_region_defaults(batch, normalized)
        pending_items.append(
            {
                "row_no": row_no,
                "raw": raw,
                "normalized": normalized,
                "entity_key": entity_key(file_type, normalized),
                "geometry": geometry,
            }
        )
        if len(pending_items) >= 5000:
            process_items(pending_items)
            pending_items = []
    process_items(pending_items)
    progress.flush(layer_label)

    import_file.row_count = row_no
    import_file.error_count = failed_count
    import_file.parse_status = "success" if failed_count == 0 else ("partial_success" if success_count else "failed")
    return {
        "file_type": file_type,
        "import_file_id": import_file.id,
        "original_name": import_file.original_name,
        "file_hash": None,
        "row_count": row_no,
        "success_count": success_count,
        "failed_count": failed_count,
        "warning_count": 0,
        "affected_contractors": affected_contractors,
    }


def process_gb_package(
    db: Session,
    batch: DataImportBatch,
    mdb_path: str,
    shp_map: dict[str, str],
    current_user: User,
    now,
) -> list[dict]:
    try:
        import fiona  # noqa: F401
    except ImportError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Fiona/GDAL not installed") from exc

    survey_batch = ensure_import_survey_batch(db, batch, current_user, now)
    progress = _ProgressState(batch.id)
    stats_list: list[dict] = []

    # ── 1. 权属 mdb 五张表 ────────────────────────────────────────────────
    for file_type in GB_MDB_TABLE_ORDER:
        table_name = GB_MDB_TABLE_NAMES[file_type]
        rows = read_mdb_table(mdb_path, table_name)
        import_file = _new_import_file(
            db, batch, current_user, now,
            file_type=file_type,
            original_name=table_name,
            content_type="application/x-msaccess",
            remark=f"from national package mdb table: {table_name}",
        )
        progress.total += len(rows)
        progress.flush(totalRows=progress.total)
        logger.info(
            "GB mdb table import started: batch_id=%s table=%s rows=%s",
            batch.id, table_name, len(rows),
        )
        stats_list.append(
            _process_row_stream(
                db, batch, current_user, now,
                file_type=file_type,
                import_file=import_file,
                survey_batch=survey_batch,
                stream=iter((row, None) for row in rows),
                progress=progress,
                layer_label=table_name,
            )
        )
        if file_type == "cbf_jtcy":
            recount_result_member_counts(
                db,
                stats_list[-1]["affected_contractors"],
                survey_batch.id,
            )

    # ── 2. DK 地块面（shp）───────────────────────────────────────────────
    stats_list.append(
        _process_shp_layer(
            db, batch, current_user, now,
            shp_path=shp_map["dk"],
            file_type="dk",
            survey_batch=survey_batch,
            progress=progress,
        )
    )

    # ── 3. 界址点 / 界址线：由 DK 图形推导 + shp 属性回填 ─────────────────
    stats_list.extend(
        derive_and_enrich_boundaries(
            db, batch, current_user, now,
            shp_map=shp_map,
            survey_batch=survey_batch,
            progress=progress,
        )
    )
    return stats_list


def _process_shp_layer(
    db: Session,
    batch: DataImportBatch,
    current_user: User,
    now,
    *,
    shp_path: str,
    file_type: str,
    survey_batch,
    progress: _ProgressState,
) -> dict:
    import fiona

    import_file = _new_import_file(
        db, batch, current_user, now,
        file_type=file_type,
        original_name=Path(shp_path).name,
        content_type="application/x-esri-shapefile",
        remark=f"from national package shapefile: {Path(shp_path).name}",
    )
    with _open_shp(shp_path) as source:
        transformer = make_geometry_transformer(source.crs)
        row_count = len(source)
        progress.total += row_count
        progress.flush(totalRows=progress.total)
        logger.info(
            "GB shp layer import started: batch_id=%s file_type=%s shp=%s rows=%s",
            batch.id, file_type, shp_path, row_count,
        )

        def stream():
            for feature in source:
                geometry = transform_geometry(json_safe(feature.get("geometry")), transformer)
                yield json_safe(dict(feature.get("properties") or {})), geometry

        return _process_row_stream(
            db, batch, current_user, now,
            file_type=file_type,
            import_file=import_file,
            survey_batch=survey_batch,
            stream=stream(),
            progress=progress,
            layer_label=Path(shp_path).stem,
        )


# ===========================================================================
# 界址点 / 界址线推导 + 属性回填
# ===========================================================================

def _region_dkbms(db: Session, batch: DataImportBatch, tenant_code: str | None) -> list[str]:
    """本批次区域内的全部地块编码。

    ⛔ 两处必须与导入行同口径：
    - ``tenant_code``：dk 行的租户是导入人所在租户（``_gdb_dk`` 用
      ``get_tenant_code(current_user)``），不是 batch.tenant_code（批次无
      业务码，before_flush 按区域码推导，两者在授权区域外会分叉）；
    - 走原生 SQL：``geom`` 是迁移加的 PostGIS 列（
      ``_upgrade_survey_dk_postgis_geometry``），ORM 模型上没有声明，
      ``SurveyDkResult.geom`` 会 AttributeError。
    """
    rows = db.execute(
        text(
            "SELECT dkbm FROM survey_dk_result "
            "WHERE tenant_code = :tenant "
            "  AND region_code LIKE :prefix "
            "  AND result_status <> 'removed' "
            "  AND geom IS NOT NULL"
        ),
        {"tenant": tenant_code, "prefix": f"{batch.region_code}%"},
    )
    return [row[0] for row in rows]


def _load_shp_crs_transformer(shp_path: str):
    import fiona

    with _open_shp(shp_path) as source:
        return make_geometry_transformer(source.crs)


def _load_shp_point_attributes(shp_path: str, transformer) -> tuple[dict, dict]:
    """读 JZD shp：返回 (坐标→属性, 外部点号→坐标)。

    坐标键与界址推导一致：``(毫米化北坐标, 毫米化东坐标)``（见
    ``load_parcel_rings``：X=北坐标，Y=东坐标）。
    """
    import fiona

    attr_by_coord: dict[tuple, dict] = {}
    coord_by_jzdh: dict[str, tuple] = {}
    with _open_shp(shp_path) as source:
        for feature in source:
            geometry = feature.get("geometry") or {}
            coords = geometry.get("coordinates")
            if not coords:
                continue
            easting, northing = coords[0], coords[1]
            if transformer is not None:
                easting, northing = transformer.transform(easting, northing)
            key = (_to_mm(northing), _to_mm(easting))
            raw = json_safe(dict(feature.get("properties") or {}))
            normalized = normalize_row(raw, JZD_ATTR_FIELD_MAP)
            if normalized.get("jzdh"):
                coord_by_jzdh.setdefault(str(normalized["jzdh"]).strip(), key)
            if normalized.get("jblx"):
                attr_by_coord.setdefault(key, {"jblx": normalized["jblx"]})
    return attr_by_coord, coord_by_jzdh


def _load_shp_line_attributes(shp_path: str, coord_by_jzdh: dict[str, tuple], coord_to_code: dict[tuple, str]) -> dict[tuple[str, str], dict]:
    """读 JZX shp：按两端外部点号 → 坐标 → 内部界址点号，返回 (有序点对→属性)。"""
    import fiona

    attr_by_pair: dict[tuple[str, str], dict] = {}
    if not coord_by_jzdh:
        return attr_by_pair
    with _open_shp(shp_path) as source:
        for feature in source:
            raw = json_safe(dict(feature.get("properties") or {}))
            normalized = normalize_row(raw, JZX_ATTR_FIELD_MAP)
            qd = str(normalized.get("qjzdh") or "").strip()
            zd = str(normalized.get("zdjzdh") or "").strip()
            if not qd or not zd:
                continue
            coord_qd = coord_by_jzdh.get(qd)
            coord_zd = coord_by_jzdh.get(zd)
            if coord_qd is None or coord_zd is None:
                continue
            code_qd = coord_to_code.get(coord_qd)
            code_zd = coord_to_code.get(coord_zd)
            if not code_qd or not code_zd:
                continue
            attrs = {}
            for field in ("jzxlb", "jzxwz", "jzxsm"):
                if normalized.get(field):
                    attrs[field] = normalized[field]
            if attrs:
                attr_by_pair.setdefault(_order_pair(code_qd, code_zd), attrs)
    return attr_by_pair


def derive_and_enrich_boundaries(
    db: Session,
    batch: DataImportBatch,
    current_user: User,
    now,
    *,
    shp_map: dict[str, str],
    survey_batch,
    progress: _ProgressState,
) -> list[dict]:
    """从 DK 图形批量推导界址点/线（共点共线不重复），再用 shp 属性回填。

    追踪口径：本批**新建**的界址点/线写 ``source_import_batch_id``（回滚
    Part 1 直接删）；**复用**已有实体只补属性，属 update，走
    ``data_import_operations.before_snapshot`` 还原。
    """
    from app.models.data_import import DataImportRow

    # 与 dk 行同口径的租户（dk 行由 _gdb_dk 写入导入人所在租户）
    tenant_code = (
        data_access_service.get_tenant_code(current_user) or batch.tenant_code
    )
    dkbms = _region_dkbms(db, batch, tenant_code)
    if not dkbms:
        logger.warning(
            "GB boundary derivation skipped: no dk rows region=%s batch=%s",
            batch.region_code, batch.id,
        )
        return []

    # ── Phase A：收集全区域唯一坐标（毫米键）────────────────────────────
    coords: set[tuple] = set()
    for chunk_index, start in enumerate(range(0, len(dkbms), _BOUNDARY_CHUNK)):
        if data_import_progress.is_cancel_requested(batch.id):
            raise ImportCanceled()
        chunk = dkbms[start : start + _BOUNDARY_CHUNK]
        rings_by_dkbm = load_parcel_rings(db, chunk)
        for rings in rings_by_dkbm.values():
            for ring in rings:
                coords.update(ring)
        progress.flush(f"boundary-scan {chunk_index + 1}")

    # 界址点总量此时已可确定：先并入 total，Phase B 计数才不会超过 total
    progress.total += len(coords)
    progress.flush(totalRows=progress.total)

    # ── Phase B：界址点 get-or-create（批量）────────────────────────────
    # 判重键是 (tenant_code, x, y)：首查不带租户过滤（共点允许跨村复用），
    # 这里显式丢弃别的租户的点，防止把外租户的点号映射进本租户的界址线。
    existing_points = {
        coord: row
        for coord, row in _load_points_by_coords(db, tenant_code, list(coords)).items()
        if row.tenant_code == tenant_code
    }
    # ⛔ coord_to_code 必须在 commit 前建好：expire_on_commit=True，commit 后
    # 再逐个访问 row.jzdh 会触发十几万次单行 SELECT。
    coord_to_code: dict[tuple, str] = {
        coord: row.jzdh for coord, row in existing_points.items() if row.jzdh
    }
    missing_coords = [coord for coord in coords if coord not in existing_points]
    created_points = 0
    if missing_coords:
        next_id = (
            db.scalar(select(func.max(SurveyJzdResult.id)).execution_options(skip_tenant_scope=True))
            or 0
        ) + 1
        allocated = set(coord_to_code.values())
        for start in range(0, len(missing_coords), _BOUNDARY_INSERT_CHUNK):
            if data_import_progress.is_cancel_requested(batch.id):
                raise ImportCanceled()
            coord_chunk = missing_coords[start : start + _BOUNDARY_INSERT_CHUNK]
            with db.begin_nested():
                for coord in coord_chunk:
                    code = f"{POINT_CODE_PREFIX}{next_id:0{POINT_CODE_WIDTH}d}"
                    while code in allocated:  # 防御性：与库内已有编号撞号时顺延
                        next_id += 1
                        code = f"{POINT_CODE_PREFIX}{next_id:0{POINT_CODE_WIDTH}d}"
                    allocated.add(code)
                    next_id += 1
                    db.add(
                        SurveyJzdResult(
                            jzdh=code,
                            x=coord[0],
                            y=coord[1],
                            tenant_code=tenant_code,
                            region_code=batch.region_code,
                            source_dkbm=None,
                            source_import_batch_id=batch.id,
                        )
                    )
                    db.add(
                        DataImportRow(
                            tenant_code=batch.tenant_code,
                            region_code=batch.region_code,
                            import_batch_id=batch.id,
                            row_no=created_points + 1,
                            entity_type="jzd",
                            entity_key=code,
                            operation_type="insert",
                            status="success",
                            target_table="survey_jzd_result",
                            raw_data={"x": str(coord[0]), "y": str(coord[1])},
                            normalized_data={"jzdh": code, "x": str(coord[0]), "y": str(coord[1])},
                        )
                    )
                    coord_to_code[coord] = code
                    created_points += 1
            db.commit()
            progress.processed += len(coord_chunk)
            progress.success += len(coord_chunk)
            progress.flush(f"boundary-points {start // _BOUNDARY_INSERT_CHUNK + 1}")

    # 复用的已有界址点（get-or-create 命中）同样计入处理量
    reused_now = len(coords) - created_points
    if reused_now > 0:
        progress.processed += reused_now
        progress.success += reused_now
    progress.flush("boundary-points done")

    # ── Phase C：收集界址线点对 ─────────────────────────────────────────
    edges: set[tuple[str, str]] = set()
    for chunk_index, start in enumerate(range(0, len(dkbms), _BOUNDARY_CHUNK)):
        if data_import_progress.is_cancel_requested(batch.id):
            raise ImportCanceled()
        chunk = dkbms[start : start + _BOUNDARY_CHUNK]
        rings_by_dkbm = load_parcel_rings(db, chunk)
        for rings in rings_by_dkbm.values():
            for ring in rings:
                for index in range(len(ring)):
                    code_a = coord_to_code.get(ring[index])
                    code_b = coord_to_code.get(ring[(index + 1) % len(ring)])
                    if code_a and code_b and code_a != code_b:
                        edges.add(_order_pair(code_a, code_b))
        progress.flush(f"boundary-edges {chunk_index + 1}")

    # 界址线总量并入 total，Phase D 计数才不会超过 total
    progress.total += len(edges)
    progress.flush(totalRows=progress.total)

    # ── Phase D：界址线 get-or-create（批量）────────────────────────────
    endpoint_codes = list({code for pair in edges for code in pair})
    existing_lines = {
        pair: row
        for pair, row in _load_lines_by_points(db, tenant_code, endpoint_codes).items()
        if row.tenant_code == tenant_code
    }
    missing_pairs = [pair for pair in edges if pair not in existing_lines]
    created_lines = 0
    if missing_pairs:
        for start in range(0, len(missing_pairs), _BOUNDARY_INSERT_CHUNK):
            if data_import_progress.is_cancel_requested(batch.id):
                raise ImportCanceled()
            pair_chunk = missing_pairs[start : start + _BOUNDARY_INSERT_CHUNK]
            with db.begin_nested():
                for offset, pair in enumerate(pair_chunk):
                    row = SurveyJzxResult(
                        qdjzdh=pair[0],
                        zdjzdh=pair[1],
                        tenant_code=tenant_code,
                        region_code=batch.region_code,
                        source_dkbm=None,
                        source_import_batch_id=batch.id,
                    )
                    db.add(row)
                    existing_lines[pair] = row
                    db.add(
                        DataImportRow(
                            tenant_code=batch.tenant_code,
                            region_code=batch.region_code,
                            import_batch_id=batch.id,
                            row_no=start + offset + 1,
                            entity_type="jzx",
                            entity_key=f"{pair[0]}:{pair[1]}",
                            operation_type="insert",
                            status="success",
                            target_table="survey_jzx_result",
                            raw_data={"qdjzdh": pair[0], "zdjzdh": pair[1]},
                            normalized_data={"qdjzdh": pair[0], "zdjzdh": pair[1]},
                        )
                    )
                    created_lines += 1
            db.commit()
            progress.processed += len(pair_chunk)
            progress.success += len(pair_chunk)
            progress.flush(f"boundary-lines {start // _BOUNDARY_INSERT_CHUNK + 1}")

    # 复用的已有界址线（get-or-create 命中）同样计入处理量
    reused_lines_now = len(edges) - created_lines
    if reused_lines_now > 0:
        progress.processed += reused_lines_now
        progress.success += reused_lines_now
    progress.flush("boundary-lines done")

    # ── Phase E：shp 属性回填 ───────────────────────────────────────────
    # 界址点/线的 processed 已在 Phase B/D 实时计入，回填为属性 update、
    # 不占 total 份额，不重复计数。
    jzd_import_file = _new_import_file(
        db, batch, current_user, now,
        file_type="jzd",
        original_name=Path(shp_map["jzd"]).name if "jzd" in shp_map else "(derived from DK geometry)",
        content_type="application/x-esri-shapefile",
        remark="derived from DK geometry; attributes enriched from national package JZD shp",
    )
    jzx_import_file = _new_import_file(
        db, batch, current_user, now,
        file_type="jzx",
        original_name=Path(shp_map["jzx"]).name if "jzx" in shp_map else "(derived from DK geometry)",
        content_type="application/x-esri-shapefile",
        remark="derived from DK geometry; attributes enriched from national package JZX shp",
    )

    attr_miss_points = 0
    attr_miss_lines = 0

    if "jzd" in shp_map:
        attr_by_coord, _ = _load_shp_point_attributes(shp_map["jzd"], _load_shp_crs_transformer(shp_map["jzd"]))
        # commit 过，旧 ORM 对象已过期：按坐标重新批量装载（分块 SELECT）
        fresh_points = {
            coord: row
            for coord, row in _load_points_by_coords(db, tenant_code, list(attr_by_coord)).items()
            if row.tenant_code == tenant_code
        }
        for coord, attrs in attr_by_coord.items():
            point = fresh_points.get(coord)
            if point is None:
                attr_miss_points += 1
                continue
            if point.jblx == attrs.get("jblx"):
                continue
            is_new = point.source_import_batch_id == batch.id and point.id is not None and point.jblx is None
            before = None if is_new else snapshot_model(point)
            point.jblx = attrs["jblx"]
            if before is not None:
                record_operation(
                    db, batch,
                    DataImportRow(import_batch_id=batch.id, import_file_id=jzd_import_file.id),
                    point, "update", before, 1,
                )
        db.flush()

    if "jzx" in shp_map and "jzd" in shp_map:
        _, coord_by_jzdh = _load_shp_point_attributes(shp_map["jzd"], _load_shp_crs_transformer(shp_map["jzd"]))
        attr_by_pair = _load_shp_line_attributes(shp_map["jzx"], coord_by_jzdh, coord_to_code)
        fresh_lines = {
            pair: row
            for pair, row in _load_lines_by_points(
                db, tenant_code, list({code for pair in attr_by_pair for code in pair})
            ).items()
            if row.tenant_code == tenant_code
        }
        for pair, attrs in attr_by_pair.items():
            line = fresh_lines.get(pair)
            if line is None:
                attr_miss_lines += 1
                continue
            changed = False
            is_new = line.source_import_batch_id == batch.id and line.jzxlb is None and line.jzxwz is None and line.jzxsm is None
            before = None if is_new else snapshot_model(line)
            for field, value in attrs.items():
                if getattr(line, field) != value:
                    setattr(line, field, value)
                    changed = True
            if changed and before is not None:
                record_operation(
                    db, batch,
                    DataImportRow(import_batch_id=batch.id, import_file_id=jzx_import_file.id),
                    line, "update", before, 1,
                )
        db.flush()

    db.commit()

    jzd_import_file.row_count = len(coords)
    jzd_import_file.error_count = 0
    jzd_import_file.parse_status = "success"
    jzx_import_file.row_count = len(edges)
    jzx_import_file.error_count = 0
    jzx_import_file.parse_status = "success"

    reused_points = len(coords) - created_points
    reused_lines = len(edges) - created_lines
    logger.info(
        "GB boundary derivation finished: batch_id=%s points=%s (created=%s reused=%s) lines=%s (created=%s reused=%s) attr_miss=(%s,%s)",
        batch.id, len(coords), created_points, reused_points, len(edges), created_lines, reused_lines, attr_miss_points, attr_miss_lines,
    )
    return [
        {
            "file_type": "jzd",
            "import_file_id": jzd_import_file.id,
            "original_name": jzd_import_file.original_name,
            "file_hash": None,
            "row_count": len(coords),
            "success_count": len(coords),
            "failed_count": 0,
            "warning_count": attr_miss_points,
            "affected_contractors": set(),
        },
        {
            "file_type": "jzx",
            "import_file_id": jzx_import_file.id,
            "original_name": jzx_import_file.original_name,
            "file_hash": None,
            "row_count": len(edges),
            "success_count": len(edges),
            "failed_count": 0,
            "warning_count": attr_miss_lines,
            "affected_contractors": set(),
        },
    ]
