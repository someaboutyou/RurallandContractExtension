"""Core DataImportService class -- orchestration, batch CRUD, CSV/ZIP upload, rollback."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.models.data_import import DataImportBatch, DataImportFile, DataImportOperation, DataImportRow
from app.models.fbf import Fbf
from app.models.survey import (
    SurveyBatch,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyCbdkxxResult,
    SurveyDkResult,
    SurveyFbfResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service

from .constants import FIELD_MAPS
from .helpers import (
    decode_csv,
    entity_key,
    field_map_for,
    get_by_primary_key,
    infer_archive_csv_type,
    next_no,
    normalize_row,
    restore_snapshot,
    serialize_batch,
)
from .core_helpers import ensure_import_survey_batch, finish_batch_import
from .row_import import (
    import_row,
    recount_member_counts,
    write_dk_geometries,
)
from . import attachments

logger = logging.getLogger(__name__)


class DataImportService:
    chunk_size = 5000
    progress_update_interval = 100

    def list_batches(self, db, *, page, page_size, keyword, current_user):
        stmt = select(DataImportBatch).order_by(DataImportBatch.id.desc()).offset((page - 1) * page_size).limit(page_size)
        total_stmt = select(func.count(DataImportBatch.id))
        if keyword:
            pattern = f"%{keyword.strip()}%"
            condition = or_(DataImportBatch.import_no.ilike(pattern), DataImportBatch.import_name.ilike(pattern))
            stmt = stmt.where(condition)
            total_stmt = total_stmt.where(condition)
        return {
            "items": [serialize_batch(item) for item in db.scalars(stmt).all()],
            "total": db.scalar(total_stmt) or 0,
            "page": page,
            "pageSize": page_size,
        }

    def create_batch(self, db, payload, current_user):
        region_code = data_access_service.normalize_region_code(payload.get("regionCode"))
        if not region_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择导入区域")
        data_access_service.ensure_region_in_scope(current_user, region_code, detail="导入区域不在当前授权范围内")
        now = datetime.now(timezone.utc)
        batch = DataImportBatch(
            import_no=next_no(db, "IMP", DataImportBatch.id),
            import_name=payload["importName"],
            import_type=payload.get("importType") or "initial_build",
            source_type=payload.get("sourceType") or "csv",
            source_org=payload.get("sourceOrg"),
            region_code=region_code,
            region_name=payload.get("regionName"),
            status="uploaded",
            imported_by=current_user.id,
            imported_by_name=current_user.real_name,
            imported_at=now,
            remark=payload.get("remark"),
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)
        return serialize_batch(batch)

    async def upload_csv(self, db, batch_id, file_type, upload_file, current_user):
        if file_type not in {"cbf", "cbf_jtcy"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only cbf or cbf_jtcy allowed")
        batch = db.get(DataImportBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="import batch not found")
        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="uploaded file is empty")
        now = datetime.now(timezone.utc)
        stats = self._process_csv_content(db, batch, file_type=file_type, original_name=upload_file.filename or "import.csv", content_type=upload_file.content_type, content=content, current_user=current_user, now=now)
        finish_batch_import(db, batch, stats_list=[stats], source_name=stats["original_name"], file_hash=stats["file_hash"], current_user=current_user, now=now)
        return serialize_batch(batch)

    async def upload_archive(self, db, batch_id, upload_file, current_user):
        batch = db.get(DataImportBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="import batch not found")
        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="uploaded file is empty")
        filename = upload_file.filename or "import.zip"
        if not filename.lower().endswith(".zip"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="please upload a ZIP archive")
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="failed to read ZIP archive") from exc
        csv_files = {}
        for item in archive.infolist():
            if item.is_dir():
                continue
            inner_name = PurePosixPath(item.filename).name
            if not inner_name.lower().endswith(".csv"):
                continue
            inferred_type = infer_archive_csv_type(inner_name)
            if inferred_type is None:
                continue
            if inferred_type in csv_files:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"duplicate {inferred_type} CSV file in archive")
            csv_files[inferred_type] = (inner_name, archive.read(item))
        missing = [label for key, label in (("cbf", "contractor"), ("cbf_jtcy", "member")) if key not in csv_files]
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"archive missing {', '.join(missing)} CSV file")
        now = datetime.now(timezone.utc)
        batch.source_type = "zip"
        archive_file = DataImportFile(tenant_code=batch.tenant_code, region_code=batch.region_code, import_batch_id=batch.id, file_type="archive", original_name=filename, content_type=upload_file.content_type, file_size=len(content), file_hash=hashlib.sha256(content).hexdigest(), parse_status="success", row_count=0, uploaded_by=current_user.id, uploaded_at=now, remark="contractor and member archive upload")
        db.add(archive_file)
        db.flush()
        stats_list = []
        for ft in ("cbf", "cbf_jtcy"):
            inner_name, inner_content = csv_files[ft]
            stats = self._process_csv_content(db, batch, file_type=ft, original_name=inner_name, content_type="text/csv", content=inner_content, current_user=current_user, now=now, remark=f"from archive {filename}")
            stats_list.append(stats)
        archive_file.row_count = sum(s["row_count"] for s in stats_list)
        archive_file.error_count = sum(s["failed_count"] for s in stats_list)
        archive_file.parse_status = "success" if archive_file.error_count == 0 else "partial_success"
        finish_batch_import(db, batch, stats_list=stats_list, source_name=filename, file_hash=archive_file.file_hash, current_user=current_user, now=now)
        return serialize_batch(batch)

    async def upload_gdb_archive(self, db, batch_id, upload_file, current_user):
        batch = db.get(DataImportBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="import batch not found")
        from .progress import upload_gdb_archive
        return await upload_gdb_archive(db, batch, upload_file, current_user)

    async def start_gdb_import_job(self, db, batch_id, upload_file, current_user, background_tasks):
        batch = db.get(DataImportBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="import batch not found")
        from .progress import start_gdb_import_job
        return await start_gdb_import_job(db, batch, upload_file, current_user, background_tasks)

    def _process_csv_content(self, db, batch, *, file_type, original_name, content_type, content, current_user, now, remark=None):
        file_hash = hashlib.sha256(content).hexdigest()
        text = decode_csv(content)
        rows = list(csv.DictReader(io.StringIO(text)))
        import_file = DataImportFile(tenant_code=batch.tenant_code, region_code=batch.region_code, import_batch_id=batch.id, file_type=file_type, original_name=original_name, content_type=content_type, file_size=len(content), file_hash=file_hash, parse_status="success", row_count=len(rows), uploaded_by=current_user.id, uploaded_at=now, remark=remark)
        db.add(import_file)
        db.flush()
        success_count = 0
        failed_count = 0
        warning_count = 0
        seen_keys = set()
        affected_contractors = set()
        survey_batch = ensure_import_survey_batch(db, batch, current_user, now)
        context = {"survey_batch": survey_batch}
        fm = field_map_for(file_type)
        for index, raw in enumerate(rows, start=2):
            normalized = normalize_row(raw, fm)
            ek = entity_key(file_type, normalized)
            row_record = DataImportRow(tenant_code=batch.tenant_code, region_code=batch.region_code, import_batch_id=batch.id, import_file_id=import_file.id, row_no=index, entity_type=file_type, entity_key=ek, operation_type="insert", status="pending", target_table=file_type, raw_data=raw, normalized_data=normalized)
            try:
                if not ek:
                    raise ValueError("missing entity key")
                if ek in seen_keys:
                    raise ValueError(f"duplicate entity key: {ek}")
                seen_keys.add(ek)
                operation, target_id = import_row(db, batch, import_file, row_record, file_type, normalized, current_user, now, context=context)
                row_record.operation_type = operation
                row_record.status = "success"
                row_record.target_id = target_id
                if normalized.get("cbfbm"):
                    affected_contractors.add(normalized["cbfbm"])
                success_count += 1
            except Exception as exc:
                row_record.status = "failed"
                row_record.operation_type = "error"
                row_record.error_message = str(exc)
                db.add(row_record)
                failed_count += 1
        if file_type == "cbf_jtcy":
            recount_member_counts(db, affected_contractors)
        import_file.error_count = failed_count
        import_file.parse_status = "success" if failed_count == 0 else ("partial_success" if success_count else "failed")
        return {"file_type": file_type, "import_file_id": import_file.id, "original_name": original_name, "file_hash": file_hash, "row_count": len(rows), "success_count": success_count, "failed_count": failed_count, "warning_count": warning_count, "affected_contractors": affected_contractors}

    def _build_import_context(self, db, survey_batch, file_type, cbfbms, dkbms=None, member_ids=None):
        context = {}
        tenant_code = survey_batch.tenant_code
        if file_type == "cbf":
            results = db.scalars(select(SurveyCbfResult).where(SurveyCbfResult.tenant_code == tenant_code, SurveyCbfResult.cbfbm.in_(cbfbms)).execution_options(skip_tenant_scope=True)).all()
            context["cbf_result_by_cbfbm"] = {item.cbfbm: item for item in results}
        if file_type == "cbf_jtcy" and member_ids:
            member_results = db.scalars(select(SurveyCbfJtcyResult).where(SurveyCbfJtcyResult.tenant_code == tenant_code, SurveyCbfJtcyResult.cbfbm.in_(cbfbms)).execution_options(skip_tenant_scope=True)).all()
            context["member_result_by_cbfbm_member"] = {(item.cbfbm, item.cyzjhm): item for item in member_results}
            contractor_results = db.scalars(select(SurveyCbfResult).where(SurveyCbfResult.tenant_code == tenant_code, SurveyCbfResult.cbfbm.in_(cbfbms)).execution_options(skip_tenant_scope=True)).all()
            context["contractor_result_by_cbfbm"] = {item.cbfbm: item for item in contractor_results}
        if file_type == "fbf":
            fbfbms = cbfbms
            results = db.scalars(select(SurveyFbfResult).where(SurveyFbfResult.tenant_code == tenant_code, SurveyFbfResult.fbfbm.in_(fbfbms)).execution_options(skip_tenant_scope=True)).all()
            context["fbf_result_by_fbfbm"] = {item.fbfbm: item for item in results}
        if file_type == "cbdkxx" and dkbms:
            results = db.scalars(select(SurveyCbdkxxResult).where(SurveyCbdkxxResult.tenant_code == tenant_code, SurveyCbdkxxResult.dkbm.in_(dkbms), SurveyCbdkxxResult.cbfbm.in_(cbfbms)).execution_options(skip_tenant_scope=True)).all()
            context["cbdkxx_result_by_key"] = {(item.dkbm, item.cbfbm): item for item in results}
        if file_type == "dk" and dkbms:
            results = db.scalars(select(SurveyDkResult).where(SurveyDkResult.tenant_code == tenant_code, SurveyDkResult.dkbm.in_(dkbms)).execution_options(skip_tenant_scope=True)).all()
            context["dk_result_by_dkbm"] = {item.dkbm: item for item in results}
        return context

    def build_template_csv(self, file_type):
        return attachments.build_template_csv(file_type)

    def build_template_notes_csv(self, file_type):
        return attachments.build_template_notes_csv(file_type)

    def build_failed_rows_csv(self, db, batch_id):
        return attachments.build_failed_rows_csv(db, batch_id)

    def list_rows(self, db, batch_id, page, page_size, status_filter):
        return attachments.list_rows(db, batch_id, page, page_size, status_filter)

    def rollback_batch(self, db, batch_id, current_user):
        batch = db.get(DataImportBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request failed")

        model_map = self._rollback_model_map()
        deleted = 0
        restored = 0
        skipped = 0

        # ── Part 1: Undo INSERTs ──────────────────────────────────────
        # Rows created by this batch are identified via source_import_batch_id.
        # No per-row operation log is needed for inserts.
        for table_name, model in model_map.items():
            if not hasattr(model, "source_import_batch_id"):
                continue
            rows = db.scalars(
                select(model).where(model.source_import_batch_id == batch_id)
                .execution_options(skip_tenant_scope=True)
            ).all()
            for row in rows:
                db.delete(row)
                deleted += 1

        # ── Part 2: Undo UPDATEs ──────────────────────────────────────
        # Update operations carry before_snapshot in data_import_operations.
        operations = db.scalars(
            select(DataImportOperation)
            .where(DataImportOperation.import_batch_id == batch_id)
            .order_by(DataImportOperation.id.desc())
        ).all()

        for operation in operations:
            if operation.operation_type != "update" or not operation.before_snapshot:
                skipped += 1
                continue
            model = model_map.get(operation.table_name)
            if model is None:
                skipped += 1
                continue
            instance = get_by_primary_key(db, model, operation.primary_key or {})
            if instance is None:
                skipped += 1
                continue
            restore_snapshot(instance, operation.before_snapshot)
            # Restore geometry if it was captured in the snapshot.
            if "geom" in operation.before_snapshot:
                geom_value = operation.before_snapshot["geom"]
                write_dk_geometries(
                    db,
                    operation.table_name,
                    {instance.id: json.loads(geom_value) if geom_value else None},
                )
            # Restore last_import_* to previous values.
            if hasattr(instance, "last_import_batch_id"):
                instance.last_import_batch_id = operation.before_snapshot.get("last_import_batch_id")
            if hasattr(instance, "last_import_row_id"):
                instance.last_import_row_id = operation.before_snapshot.get("last_import_row_id")
            restored += 1

        batch.status = "rolled_back"
        batch.error_summary = {
            **(batch.error_summary or {}),
            "rollback": {"restored": restored, "deleted": deleted, "skipped": skipped, "by": current_user.id},
        }
        db.commit()
        db.refresh(batch)
        return serialize_batch(batch)
    def _rollback_model_map(self):
        models = [Fbf, SurveyCbfResult, SurveyCbfJtcyResult, SurveyFbfResult, SurveyCbdkxxResult, SurveyDkResult]
        return {model.__tablename__: model for model in models}

    def run_gdb_import_job(self, batch_id, stored_path, filename, content_type, user_id, job_id):
        from .progress import run_gdb_import_job
        return run_gdb_import_job(batch_id, stored_path, filename, content_type, user_id, job_id)


data_import_service = DataImportService()
