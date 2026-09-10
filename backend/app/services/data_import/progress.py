"""GDB archive handling, background import jobs, and layer processing."""

from __future__ import annotations

import hashlib
import io
import logging
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, set_current_user
from app.models.data_import import DataImportBatch, DataImportFile
from app.models.user import User
from app.services.data_import_progress import data_import_progress
from app.services.geoserver_service import geoserver_service

from .constants import GDB_LAYER_ALIASES, GDB_LAYER_ORDER
from .errors import ImportCanceled
from .helpers import (
    apply_gdb_region_defaults,
    chunks,
    entity_key,
    ensure_required,
    field_map_for,
    json_safe,
    normalize_row,
    parse_decimal,
    parse_int,
    resolve_code_region,
    snapshot_model,
)
from .core_helpers import ensure_import_survey_batch, finish_batch_import
from .row_import import import_row

logger = logging.getLogger(__name__)


# ===========================================================================
# Archive validation
# ===========================================================================

def extract_zip_safely(archive: zipfile.ZipFile, target_dir: str) -> None:
    for item in archive.infolist():
        if "\\" in item.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ZIP archive contains an unsafe path")
        item_path = PurePosixPath(item.filename)
        if item_path.is_absolute() or ".." in item_path.parts:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ZIP archive contains an unsafe path")
    archive.extractall(target_dir)


def find_gdb_path(root_dir: str) -> str:
    for path in Path(root_dir).rglob("*.gdb"):
        if path.is_dir():
            return str(path)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="ZIP \u2558\u2569\u256c\u2566\u255e\u2562\u255f\u2592\u2551\u256a\u2565\u2562\u2563\u255f\u256c .gdb \u255b\u255c\u255f\u2553",
    )


def normalize_layer_name(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum() or ch == "_")


def infer_gdb_layer_type(layer_name: str) -> str | None:
    normalized_name = normalize_layer_name(layer_name)
    for file_type, aliases in GDB_LAYER_ALIASES.items():
        if normalized_name in aliases:
            return file_type
    for file_type in sorted(GDB_LAYER_ORDER, key=len, reverse=True):
        if normalized_name.startswith(file_type):
            return file_type
    return None


# ===========================================================================
# Public entry points
# ===========================================================================

async def upload_gdb_archive(
    db: Session,
    batch: DataImportBatch,
    upload_file: UploadFile,
    current_user: User,
) -> dict:
    if not batch.region_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="\u2569\u2560\u255b\u2551\u2551\u256a GDB \u2553\u255e\u2559\u255c\u2568\u2592\u2557\u255e\u256c\u2564\u2555\u2569\u2560\u255b\u2551\u2551\u256a\u2568\u2568\u255c\u2552",
        )
    content = await upload_file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="uploaded file is empty")
    filename = upload_file.filename or "import_gdb.zip"
    return process_gdb_archive_content(db, batch, filename, content, upload_file.content_type, current_user)


async def start_gdb_import_job(
    db: Session,
    batch: DataImportBatch,
    upload_file: UploadFile,
    current_user: User,
    background_tasks,
) -> dict:
    if not batch.region_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="\u2569\u2560\u255b\u2551\u2551\u256a GDB \u2553\u255e\u2559\u255c\u2568\u2592\u2557\u255e\u256c\u2564\u2555\u2569\u2560\u255b\u2551\u2551\u256a\u2568\u2568\u255c\u2552",
        )
    content = await upload_file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="uploaded file is empty")
    filename = upload_file.filename or "import_gdb.zip"
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="please upload a ZIP archive containing a .gdb directory")

    storage_dir = Path(__file__).resolve().parents[2] / "storage" / "data_imports" / str(batch.id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    stored_path = storage_dir / f"{datetime.now():%Y%m%d%H%M%S}_{Path(filename).name}"
    stored_path.write_bytes(content)

    job_id = f"gdb:{batch.id}:{datetime.now(timezone.utc).timestamp()}"
    batch.status = "processing"
    batch.source_type = "gdb"
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
            "message": "\u95e8\u2559\u2554\u2553\u2568\u256b \u2553\u2561\u256b\u255c \u2569\u2560\u255b\u2551\u2551\u256a\uff1a",
            "filename": filename,
            "fileSize": len(content),
        },
    )
    background_tasks.add_task(
        run_gdb_import_job,
        batch.id,
        str(stored_path),
        filename,
        upload_file.content_type,
        current_user.id,
        job_id,
    )
    return {"batchId": batch.id, "jobId": job_id, "status": "queued"}


# ===========================================================================
# Background job runner
# ===========================================================================

def run_gdb_import_job(
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
        data_import_progress.update(batch_id, status="running", message="background import started")
        content = Path(stored_path).read_bytes()
        process_gdb_archive_content(db, batch, filename, content, content_type, current_user, job_id=job_id)
    except ImportCanceled:
        db.rollback()
        batch = db.get(DataImportBatch, batch_id)
        if batch is not None:
            batch.status = "canceled"
            db.commit()
        data_import_progress.update(batch_id, status="canceled", message="import canceled")
        logger.info("GDB import canceled: batch_id=%s", batch_id)
    except Exception:
        db.rollback()
        batch = db.get(DataImportBatch, batch_id)
        if batch is not None:
            batch.status = "failed"
            db.commit()
        data_import_progress.update(batch_id, status="failed", message="import failed; see backend logs")
        logger.exception("GDB import job failed: batch_id=%s filename=%s", batch_id, filename)
    finally:
        db.close()


# ===========================================================================
# Core GDB processing
# ===========================================================================

def process_gdb_archive_content(
    db: Session,
    batch: DataImportBatch,
    filename: str,
    content: bytes,
    content_type: str | None,
    current_user: User,
    job_id: str | None = None,
) -> dict:
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="please upload a ZIP archive containing a .gdb directory")

    try:
        logger.info(
            "GDB import started: batch_id=%s import_no=%s filename=%s size=%s user_id=%s region_code=%s",
            batch.id, batch.import_no, filename, len(content), current_user.id, batch.region_code,
        )
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        logger.warning("GDB import rejected: invalid zip batch_id=%s filename=%s", batch.id, filename)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="failed to read ZIP archive") from exc

    now = datetime.now(timezone.utc)
    batch.source_type = "gdb"
    archive_file = DataImportFile(
        import_batch_id=batch.id,
        file_type="gdb_archive",
        original_name=filename,
        content_type=content_type,
        file_size=len(content),
        file_hash=hashlib.sha256(content).hexdigest(),
        parse_status="success",
        row_count=0,
        uploaded_by=current_user.id,
        uploaded_at=now,
        remark="GDB archive import",
    )
    db.add(archive_file)
    db.flush()

    with tempfile.TemporaryDirectory(prefix="rural_gdb_") as temp_dir:
        extract_zip_safely(archive, temp_dir)
        gdb_path = find_gdb_path(temp_dir)
        logger.info("GDB extracted: batch_id=%s gdb_path=%s", batch.id, gdb_path)
        stats_list = process_gdb_layers(db, batch, gdb_path, current_user, now)

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
        "GDB import finished: batch_id=%s total=%s success=%s failed=%s",
        batch.id, batch.total_count, batch.success_count, batch.failed_count,
    )
    data_import_progress.update(batch.id, status=batch.status, message="GDB import finished")
    from .helpers import serialize_batch
    return serialize_batch(batch)


# ===========================================================================
# Layer discovery & per-layer processing
# ===========================================================================

def process_gdb_layers(
    db: Session,
    batch: DataImportBatch,
    gdb_path: str,
    current_user: User,
    now: datetime,
) -> list[dict]:
    try:
        import fiona
    except ImportError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Fiona/GDAL not installed") from exc

    try:
        available_layers = list(fiona.listlayers(gdb_path))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"failed to read GDB layer: {exc}") from exc

    logger.info("GDB layers discovered: gdb_path=%s layers=%s", gdb_path, available_layers)
    layer_map: dict[str, str] = {}
    for layer_name in available_layers:
        file_type = infer_gdb_layer_type(layer_name)
        if file_type and file_type not in layer_map:
            layer_map[file_type] = layer_name

    total_rows = 0
    for layer_name in layer_map.values():
        try:
            with fiona.open(gdb_path, layer=layer_name) as source:
                total_rows += len(source)
        except Exception:
            logger.exception("Failed to count GDB layer rows: gdb_path=%s layer=%s", gdb_path, layer_name)
    data_import_progress.update(
        batch.id,
        totalRows=total_rows,
        processedRows=0,
        successRows=0,
        failedRows=0,
        status="running",
        message="Processing GDB layers\u2026",
    )

    stats_list = []
    for file_type in GDB_LAYER_ORDER:
        layer_name = layer_map.get(file_type)
        if not layer_name:
            continue
        stats_list.append(
            process_gdb_layer(db, batch, gdb_path, layer_name, file_type, current_user, now, fiona)
        )

    if not stats_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GDB did not contain FBF/CBF/CBF_JTCY/CBDKXX or DK layers",
        )
    return stats_list


def process_gdb_layer(
    db: Session,
    batch: DataImportBatch,
    gdb_path: str,
    layer_name: str,
    file_type: str,
    current_user: User,
    now: datetime,
    fiona_module,
) -> dict:
    fm = field_map_for(file_type)
    import_file = DataImportFile(
        import_batch_id=batch.id,
        file_type=file_type,
        original_name=layer_name,
        content_type="application/x-filegdb-layer",
        file_size=0,
        parse_status="success",
        row_count=0,
        uploaded_by=current_user.id,
        uploaded_at=now,
        remark=f"from GDB layer: {layer_name}",
    )
    db.add(import_file)
    db.flush()

    success_count = 0
    failed_count = 0
    warning_count = 0
    seen_keys: set[str] = set()
    affected_contractors: set[str] = set()
    survey_batch = ensure_import_survey_batch(db, batch, current_user, now)
    progress = data_import_progress.get(batch.id) or {}
    progress_state = {
        "processedRows": int(progress.get("processedRows") or 0),
        "successRows": int(progress.get("successRows") or 0),
        "failedRows": int(progress.get("failedRows") or 0),
    }

    def update_progress(current_layer: str, *, force: bool = False) -> None:
        if not force and progress_state["processedRows"] % 100 != 0:
            return
        data_import_progress.update(
            batch.id,
            currentLayer=current_layer,
            processedRows=progress_state["processedRows"],
            successRows=progress_state["successRows"],
            failedRows=progress_state["failedRows"],
            message=f"Processing {current_layer}",
        )

    def process_items(items: list[dict]) -> None:
        nonlocal success_count, failed_count
        if not items:
            return
        context = {"survey_batch": survey_batch, "gdb_result_only": True}
        for item in items:
            from app.models.data_import import DataImportRow

            row_record = DataImportRow(
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
                    if not item["entity_key"]:
                        raise ValueError("Missing entity key")
                    if item["entity_key"] in seen_keys:
                        raise ValueError(f"Duplicate entity key: {item['entity_key']}")
                    operation, target_id = import_row(
                        db, batch, import_file, row_record, file_type, item["normalized"],
                        current_user, now, item.get("geometry"), context,
                    )
                seen_keys.add(item["entity_key"])
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
                    "GDB row import failed: batch_id=%s file_type=%s layer=%s row_no=%s entity_key=%s",
                    batch.id, file_type, layer_name, item["row_no"], item["entity_key"],
                )
            finally:
                progress_state["processedRows"] += 1
                progress_state["successRows"] += 1 if row_status == "success" else 0
                progress_state["failedRows"] += 1 if row_status == "failed" else 0
                update_progress(layer_name)
        db.commit()
        update_progress(layer_name, force=True)

    with fiona_module.open(gdb_path, layer=layer_name) as source:
        row_count = len(source)
        logger.info("GDB layer import started: batch_id=%s file_type=%s layer=%s rows=%s", batch.id, file_type, layer_name, row_count)
        pending_items: list[dict] = []
        for index, feature in enumerate(source, start=1):
            if data_import_progress.is_cancel_requested(batch.id):
                raise ImportCanceled()
            raw = json_safe(dict(feature.get("properties") or {}))
            normalized = normalize_row(raw, fm)
            apply_gdb_region_defaults(batch, normalized)
            pending_items.append(
                {
                    "row_no": index,
                    "raw": raw,
                    "normalized": normalized,
                    "entity_key": entity_key(file_type, normalized),
                    "geometry": json_safe(feature.get("geometry")),
                }
            )
            if len(pending_items) >= 5000:
                process_items(pending_items)
                pending_items = []
        process_items(pending_items)
        update_progress(layer_name, force=True)

    if file_type == "cbf_jtcy":
        from .row_import import recount_result_member_counts
        recount_result_member_counts(db, affected_contractors, survey_batch.id)
    import_file.row_count = row_count
    import_file.error_count = failed_count
    import_file.parse_status = "success" if failed_count == 0 else ("partial_success" if success_count else "failed")
    logger.info(
        "GDB layer import finished: batch_id=%s file_type=%s layer=%s rows=%s success=%s failed=%s",
        batch.id, file_type, layer_name, row_count, success_count, failed_count,
    )
    return {
        "file_type": file_type,
        "import_file_id": import_file.id,
        "original_name": layer_name,
        "file_hash": None,
        "row_count": row_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "warning_count": warning_count,
        "affected_contractors": affected_contractors,
    }
