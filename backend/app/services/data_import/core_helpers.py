"""Internal helpers shared between core orchestration and GDB progress.

Separated from helpers.py to avoid circular imports with progress.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.data_import import DataImportBatch
from app.models.survey import SurveyBatch
from app.models.user import User

from .helpers import next_no


def ensure_import_survey_batch(
    db: Session,
    batch: DataImportBatch,
    current_user: User,
    now: datetime,
) -> SurveyBatch:
    """Return the linked ``SurveyBatch`` for *batch*, creating one if absent."""
    if batch.linked_survey_batch_id:
        survey_batch = db.get(SurveyBatch, batch.linked_survey_batch_id)
        if survey_batch is not None:
            return survey_batch

    survey_batch = SurveyBatch(
        batch_no=next_no(db, "SUR", SurveyBatch.id),
        batch_name=f"{batch.import_name} template import",
        region_code=batch.region_code,
        region_name=batch.region_name,
        survey_type="import_survey",
        status="active",
        started_at=now,
        created_by=current_user.id,
        remark=f"Auto-created from import batch {batch.import_no}",
    )
    db.add(survey_batch)
    db.flush()
    batch.linked_survey_batch_id = survey_batch.id
    return survey_batch


def finish_batch_import(
    db: Session,
    batch: DataImportBatch,
    *,
    stats_list: list[dict],
    source_name: str,
    file_hash: str | None,
    current_user: User,
    now: datetime,
) -> None:
    """Update *batch* totals, status, and summary after a completed import."""
    total_count = sum(item["row_count"] for item in stats_list)
    success_count = sum(item["success_count"] for item in stats_list)
    failed_count = sum(item["failed_count"] for item in stats_list)
    warning_count = sum(item["warning_count"] for item in stats_list)
    affected_contractors: set[str] = set()
    for item in stats_list:
        affected_contractors.update(item["affected_contractors"])

    batch.total_count += total_count
    batch.success_count += success_count
    batch.failed_count += failed_count
    batch.warning_count += warning_count
    batch.source_name = source_name
    batch.file_hash = file_hash
    batch.status = "success" if failed_count == 0 else ("partial_success" if success_count else "failed")
    batch.validation_summary = {
        "lastFiles": [
            {"fileType": item["file_type"], "fileName": item["original_name"], "rows": item["row_count"]}
            for item in stats_list
        ]
    }
    batch.error_summary = {"lastFailedCount": failed_count}
    batch.imported_at = now
    db.commit()
    db.refresh(batch)
