"""Shared utility functions for the data import package.

Organised into sections: parsing, row normalization, serialization,
snapshot/operation helpers, region resolution, and general-purpose utilities.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, inspect as sa_inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.sqltypes import (
    Date as SADate,
    DateTime as SADateTime,
    Integer as SAInteger,
    Numeric as SANumeric,
)

from app.models.data_import import DataImportBatch, DataImportOperation, DataImportRow
from app.models.region import Region
from app.services.data_access_service import data_access_service

from .constants import FIELD_MAPS

logger = logging.getLogger(__name__)


# ===========================================================================
# General-purpose helpers
# ===========================================================================

def chunks(items: list, size: int):
    """Yield successive *size*-sized slices of *items*."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


def has_any(db: Session, model, *conditions) -> bool:
    """Return True if at least one row matches *conditions* for *model*."""
    primary_key = sa_inspect(model).primary_key[0]
    stmt = select(primary_key).limit(1)
    if conditions:
        stmt = stmt.where(*conditions)
    return db.scalar(stmt) is not None


# ===========================================================================
# Parsing helpers
# ===========================================================================

def json_safe(value: Any) -> Any:
    """Recursively convert *value* to a JSON-safe Python object."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if hasattr(value, "__geo_interface__"):
        return json_safe(value.__geo_interface__)
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def decode_csv(content: bytes) -> str:
    """Decode raw CSV bytes, trying ``utf-8-sig`` → ``utf-8`` → ``gbk``."""
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="\u95e8\u724c\u7248\u7389 CSV \u7a97\u724c\u5206\u80c6",
    )


def infer_archive_csv_type(filename: str) -> str | None:
    """Best-effort mapping from an archive entry name to a file type."""
    name = filename.replace("\\", "/").lower()
    if any(token in name for token in ("cbf_jtcy", "jtcy", "member", "\u2558\u2553\u2568\u2552")):
        return "cbf_jtcy"
    if any(token in name for token in ("cbf", "contractor", "\u93f8\u2568\u2553\u00b7\u255c\u255a")):
        return "cbf"
    return None


def parse_int(value: str | None, default: int = 0) -> int:
    if value in (None, ""):
        return default
    return int(float(str(value)))


def parse_decimal(value: str | None, required: bool = False) -> Decimal | None:
    if value in (None, ""):
        if required:
            raise ValueError("missing required numeric field")
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid decimal value: {value}") from exc


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.combine(datetime.strptime(text, fmt).date(), datetime.min.time())
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return datetime.combine(date.fromisoformat(text), datetime.min.time())


# ===========================================================================
# Row normalization & validation
# ===========================================================================

def normalize_row(row: dict, field_map: dict[str, list[str]]) -> dict:
    """Map an input CSV/GDB *row* to canonical field names using *field_map*."""
    chinese_aliases = {
        "cbfbm": ["\u93f8\u2568\u2553\u00b7\u2550\u2554\u256c\u2550\u00b7\u2550\u0393"],
        "region_code": ["\u2557\u2552\u2559\u256b\u2553\u255c\u2550\u0393"],
        "region_name": ["\u2557\u2552\u2559\u256b\u2553\u2567\u2556\u2552"],
        "cbflx": ["\u93f8\u2568\u2553\u00b7\u2569\u2556\u2563\u256a"],
        "cbfmc": ["\u93f8\u2568\u2553\u00b7\u255c\u255a\u2552\u256c", "\u93f8\u2568\u2553\u00b7\u255c\u255a\uff09\u2567\u256a\u2556\u2552"],
        "cbfzjlx": ["\u255a\u00d7\u255d\u2553\u2514\u255c\u2563\u256a", "\u93f8\u2568\u2553\u00b7\u255c\u255a\uff09\u255a\u00d7\u255d\u2553\u2514\u255c\u2563\u256a"],
        "cbfzjhm": ["\u255a\u00d7\u255d\u2553\u2551\u2567\u252c", "\u93f8\u2568\u2553\u00b7\u255c\u255a\uff09\u255a\u00d7\u255d\u2553\u2551\u2567\u252c"],
        "cbfdz": ["\u93f8\u2568\u2553\u00b7\u255c\u255a\u2552\u256c\u2550\u2554\u2554\u2552"],
        "yzbm": ["\u2553\u2550\u255e\u2565\u255e\u2562\u2550\u0393"],
        "lxdh": ["\u2514\u256a\u2553\u2568\u2553\u2562\u255a\u255e"],
        "cbfcysl": ["\u93f8\u2568\u2553\u00b7\u255c\u255a\u2554\u2558\u2553\u2568\u2553\u2591\u2550\u2564", "\u2554\u2555\u252c\u2555\u2558\u2553\u2568\u2553\u2591\u2550\u2564"],
        "cbfdcrq": ["\u93f8\u2568\u2553\u00b7\u255c\u255a\u2561\u2553\u2551\u255c\u2569\u252c\u2555\u2551"],
        "cbfdcy": ["\u93f8\u2568\u2553\u00b7\u255c\u255a\u2561\u2553\u2551\u255c\u2559\u2568"],
        "cbfdcjs": ["\u93f8\u2568\u2553\u00b7\u255c\u255a\u2561\u2553\u2551\u255c\u255f\u2552\u00b7\u2553\u2568"],
        "gsjs": ["\u255c\u2555\u2553\u255e\u255f\u2552\u2551\u255c"],
        "gsjsr": ["\u255c\u2555\u2553\u255e\u255f\u2552\u2551\u255c\u2553\u2568\u2553\u2552\u00b7"],
        "gsshrq": ["\u255c\u2555\u2553\u255e\u2567\u2591\u2567\u2560\u2569\u252c\u2555\u2551"],
        "gsshr": ["\u255c\u2555\u2553\u255e\u2567\u2591\u2567\u2560\u2553\u2568\u2553\u2552\u00b7"],
        "group_region_code": ["\u93f8\u2592\u255c\u2552\u256b\u256c\u2553\u255c\u2550\u0393"],
        "group_region_name": ["\u93f8\u2592\u255c\u2552\u256b\u256c\u2553\u2567\u2556\u2552"],
        "cyxm": ["\u2558\u2553\u2568\u2552\u2557\u256b\u256b\u255c\u255a", "\u2557\u256b\u256b\u255c\u255a"],
        "cyzjlx": ["\u255a\u00d7\u255d\u2553\u2514\u255c\u2563\u256a"],
        "cyzjhm": ["\u255a\u00d7\u255d\u2553\u2551\u2567\u252c", "\u2569\u2552\u2557\u255e\u2550\u2559\u2551\u2567\u252c"],
        "cyxb": ["\u256c\u2550\u256c\u2591"],
        "yhzgx": ["\u2553\u2568\u2558\u2559\u2553\u2568\u256b\u2551\u2553\u2552"],
        "cybz": ["\u2558\u2553\u2568\u2552\u2554\u256b\u255c\u2553\u2550\u0393", "\u2554\u256b\u255c\u2553\u2550\u0393"],
        "sfgyr": ["\u2554\u2569\u2551\u2554\u2555\u255c\u256a\u2553\u2568\u2553\u2552\u00b7"],
        "cybzsm": ["\u2558\u2553\u2568\u2552\u2554\u256b\u255c\u2553\u2558\u2556\u2562\u255f\u2559", "\u2554\u256b\u255c\u2553\u2558\u2556\u2562\u255f\u2559"],
    }
    row_lookup = {str(key).strip().lower(): value for key, value in row.items()}
    normalized = {}
    for target, candidates in field_map.items():
        value = None
        for key in [*candidates, *chinese_aliases.get(target, [])]:
            if key in row and row[key] not in (None, ""):
                value = row[key]
                break
            lookup_value = row_lookup.get(str(key).strip().lower())
            if lookup_value not in (None, ""):
                value = lookup_value
                break
        normalized[target] = str(value).strip() if value is not None else None
    return normalized


def entity_key(file_type: str, data: dict) -> str | None:
    """Derive a deduplication key for the given entity *file_type* and *data*."""
    if file_type == "cbf":
        return data.get("cbfbm")
    if file_type == "cbf_jtcy" and data.get("cbfbm") and data.get("cyzjhm"):
        return f"{data['cbfbm']}:{data['cyzjhm']}"
    if file_type == "fbf":
        return data.get("fbfbm")
    if file_type == "cbdkxx" and data.get("dkbm") and data.get("cbfbm"):
        return f"{data['dkbm']}:{data['cbfbm']}"
    if file_type == "dk":
        return data.get("dkbm")
    return None


def ensure_required(data: dict, fields: list[str]) -> None:
    missing = [field for field in fields if not data.get(field)]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")


def field_map_for(file_type: str) -> dict[str, list[str]]:
    fm = FIELD_MAPS.get(file_type)
    if fm is None:
        raise ValueError(f"unsupported data type: {file_type}")
    return fm


def apply_gdb_region_defaults(batch: DataImportBatch, data: dict) -> None:
    """Apply batch-level region info to *data* when not already present."""
    if not data.get("region_code") and batch.region_code:
        data["region_code"] = batch.region_code
    if not data.get("region_name") and batch.region_name:
        data["region_name"] = batch.region_name


# ===========================================================================
# Snapshot / operation helpers
# ===========================================================================

def snapshot_model(instance) -> dict:
    mapper = sa_inspect(instance).mapper
    return {
        column.key: json_safe(getattr(instance, column.key))
        for column in mapper.column_attrs
    }


def primary_key_snapshot(instance) -> dict:
    mapper = sa_inspect(instance).mapper
    return {
        column.key: json_safe(getattr(instance, column.key))
        for column in mapper.primary_key
    }


def record_operation(
    db: Session,
    batch: DataImportBatch,
    row_record: DataImportRow,
    instance,
    operation_type: str,
    before_snapshot: dict | None,
    chunk_no: int,
) -> None:
    """Persist an ``DataImportOperation`` row for rollback tracking."""
    if operation_type != "update" or before_snapshot is None:
        return
    db.add(
        DataImportOperation(
            tenant_code=batch.tenant_code,
            region_code=batch.region_code,
            import_batch_id=batch.id,
            import_file_id=row_record.import_file_id,
            import_row_id=row_record.id,
            chunk_no=chunk_no,
            table_name=instance.__tablename__,
            primary_key=primary_key_snapshot(instance),
            operation_type=operation_type,
            before_snapshot=before_snapshot,
            after_snapshot=snapshot_model(instance),
        )
    )


def restore_value(column_attr, value):
    if value is None:
        return None
    column_type = column_attr.columns[0].type
    if isinstance(column_type, SAInteger):
        return int(value)
    if isinstance(column_type, SANumeric):
        return Decimal(str(value))
    if isinstance(column_type, SADateTime):
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if isinstance(column_type, SADate):
        return date.fromisoformat(str(value))
    return value


def restore_snapshot(instance, snapshot: dict) -> None:
    mapper = sa_inspect(instance).mapper
    columns = {column.key: column for column in mapper.column_attrs}
    for key, value in snapshot.items():
        column = columns.get(key)
        if column is None:
            continue
        setattr(instance, key, restore_value(column, value))


def get_by_primary_key(db: Session, model, primary_key: dict):
    mapper = sa_inspect(model).mapper
    values = []
    for column in mapper.primary_key:
        if column.key not in primary_key:
            return None
        values.append(restore_value(column, primary_key[column.key]))
    return db.get(model, values[0] if len(values) == 1 else tuple(values))


# ===========================================================================
# Region / numbering helpers
# ===========================================================================

def resolve_group_region(db: Session, data: dict, current_user) -> tuple[str | None, str | None]:
    code = (data.get("group_region_code") or "").strip()
    if not code:
        return None, None
    data_access_service.ensure_region_in_scope(current_user, code, detail="region out of scope")
    region = db.scalar(select(Region).where(Region.code == code).execution_options(skip_tenant_scope=True))
    name = region.full_name if region else (data.get("group_region_name") or "")
    return code, name.strip() or None


def resolve_import_region(db: Session, data: dict, current_user) -> tuple[str, str | None]:
    code = (data.get("region_code") or "").strip()
    if not code:
        raise ValueError("\u7f16\u6536\u7684\u8be5\u7248\u7389 region_code")
    normalized = data_access_service.normalize_region_code(code)
    if not normalized or len(normalized) < 6:
        raise ValueError("invalid region code")
    data_access_service.ensure_region_in_scope(current_user, normalized, detail="region out of scope")
    region = db.scalar(select(Region).where(Region.code == normalized).execution_options(skip_tenant_scope=True))
    name = region.full_name if region else (data.get("region_name") or "")
    return normalized, name.strip() or None


def resolve_code_region(value: str | None, current_user) -> str:
    return data_access_service.normalize_region_code(value, current_user)


def next_no(db: Session, prefix: str, id_column) -> str:
    next_id = (db.scalar(select(func.max(id_column))) or 0) + 1
    return f"{prefix}{datetime.now():%Y%m%d}{next_id:04d}"


# ===========================================================================
# Serialization
# ===========================================================================

def serialize_batch(item: DataImportBatch) -> dict:
    return {
        "id": item.id,
        "importNo": item.import_no,
        "importName": item.import_name,
        "importType": item.import_type,
        "sourceType": item.source_type,
        "sourceName": item.source_name,
        "sourceOrg": item.source_org,
        "regionCode": item.region_code,
        "regionName": item.region_name,
        "status": item.status,
        "totalCount": item.total_count,
        "successCount": item.success_count,
        "failedCount": item.failed_count,
        "warningCount": item.warning_count,
        "linkedSurveyBatchId": item.linked_survey_batch_id,
        "importedByName": item.imported_by_name,
        "importedAt": item.imported_at,
        "remark": item.remark,
        "createdAt": item.created_at,
    }


def serialize_row(item: DataImportRow) -> dict:
    return {
        "id": item.id,
        "rowNo": item.row_no,
        "entityType": item.entity_type,
        "entityKey": item.entity_key,
        "operationType": item.operation_type,
        "status": item.status,
        "targetTable": item.target_table,
        "targetId": item.target_id,
        "errorMessage": item.error_message,
        "warningMessage": item.warning_message,
        "rawData": item.raw_data,
        "normalizedData": item.normalized_data,
        "createdAt": item.created_at,
    }
