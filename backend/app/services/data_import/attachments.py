"""CSV template generation, failed-rows export, and row listing."""

from __future__ import annotations

import csv
import io
import json
import logging

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.data_import import DataImportRow

from .constants import TEMPLATE_FIELD_NOTES, TEMPLATE_HEADERS
from .helpers import serialize_row

logger = logging.getLogger(__name__)


def build_template_csv(file_type: str) -> tuple[str, bytes]:
    if file_type not in TEMPLATE_HEADERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="\u6cf5\u70c6\u60e4\u2562 cbf \u256c cbf_jtcy \u2569\u2568\u253c\u2558\u2553",
        )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(TEMPLATE_HEADERS[file_type])
    if file_type == "cbf":
        writer.writerow(
            [
                "320623100200000001",
                "320623100200",
                "\u95e8\u67b5\u664e\u2562\u2592\u2569\u252c",
                "1",
                "field",
                "1",
                "320623199001010011",
                "field",
                "226400",
                "13900000000",
                "3",
                "2026-05-01",
                "\u2562\u2558\u2558\u2557\u2567\u255c\u2560\u2557",
                "",
                "",
                "",
                "",
                "",
                "32062310020001",
                "field",
            ]
        )
    else:
        writer.writerow(["320623100200000001", "\u5bfc\u2566\u2566\u256c", "1", "320623199001010011", "1", "01", "", "1", "\u256c\u2553\u2592\u2565\u2554\u2552"])
    return f"{file_type}_template.csv", output.getvalue().encode("utf-8-sig")


def build_template_notes_csv(file_type: str) -> tuple[str, bytes]:
    if file_type not in TEMPLATE_FIELD_NOTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="\u6cf5\u70c6\u60e4\u2562 cbf \u256c cbf_jtcy \u2569\u2558\u2557\u2559\u2562\u256c",
        )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["\u2569\u2558\u2557\u2559\u2560\u2553\u2567\u2556\u2552", "\u255f\u2559\u255c\u253c\u255f\u2592\u2562\u2553\u256c"])
    writer.writerows(TEMPLATE_FIELD_NOTES[file_type])
    return f"{file_type}_field_notes.csv", output.getvalue().encode("utf-8-sig")


def build_failed_rows_csv(db: Session, batch_id: int) -> tuple[str, bytes]:
    rows = db.scalars(
        select(DataImportRow)
        .where(DataImportRow.import_batch_id == batch_id, DataImportRow.status == "failed")
        .order_by(DataImportRow.row_no.asc(), DataImportRow.id.asc())
    ).all()
    output = io.StringIO()
    writer = csv.writer(output)
    for row in rows:
        writer.writerow(
            [row.row_no, row.entity_type, row.entity_key, row.error_message, json.dumps(row.raw_data, ensure_ascii=False)]
        )
    return f"import_{batch_id}_failed_rows.csv", output.getvalue().encode("utf-8-sig")


def list_rows(db: Session, batch_id: int, page: int, page_size: int, status_filter: str | None) -> dict:
    if status_filter and status_filter != "failed":
        return {"items": [], "total": 0, "page": page, "pageSize": page_size}
    stmt = (
        select(DataImportRow)
        .where(DataImportRow.import_batch_id == batch_id, DataImportRow.status == "failed")
        .order_by(DataImportRow.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    total_stmt = (
        select(func.count(DataImportRow.id))
        .where(DataImportRow.import_batch_id == batch_id, DataImportRow.status == "failed")
    )
    return {
        "items": [serialize_row(item) for item in db.scalars(stmt).all()],
        "total": db.scalar(total_stmt) or 0,
        "page": page,
        "pageSize": page_size,
    }
