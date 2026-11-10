"""失败行人工修正后重新导入（错误行修正导入）。

与批量导入共用 ``import_row`` 同一套写入逻辑（同一判据、同一状态闸门）：
- GDB / 国标包批次（source_type=gdb/gb_package）按 ``gdb_result_only`` 口径重放；
- CSV / ZIP 归档批次按普通 CSV 口径重放。

成功后行状态翻为 success，原错误信息移入 ``warning_message`` 留痕（批次明细
里可识别"这条是人工修正后导入的"），批次统计同步：failed-1 / success+1 /
warning+1。业务实体通过 ``last_import_row_id`` 指向该行，可追溯。
修正导入产生的 insert 同样携带 ``source_import_batch_id``，批次回滚会一并删除。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.data_import import DataImportBatch, DataImportRow
from app.models.user import User

from .core_helpers import ensure_import_survey_batch
from .helpers import serialize_row
from .row_import import import_row

logger = logging.getLogger(__name__)


def reimport_failed_row(
    db: Session,
    batch_id: int,
    row_id: int,
    data_patch: dict | None,
    current_user: User,
) -> dict:
    batch = db.get(DataImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="import batch not found")
    row = db.get(DataImportRow, row_id)
    if row is None or row.import_batch_id != batch_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="import row not found")
    if row.status != "failed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅失败行可修正导入")

    base = dict(row.normalized_data or row.raw_data or {})
    # data_patch 为空 = 按原数据重试导入（后端缺陷修复后批量重放的典型场景）
    merged = {**base, **(data_patch or {})}
    original_error = row.error_message
    now = datetime.now(timezone.utc)

    context = {}
    if batch.source_type in ("gdb", "gb_package"):
        context["gdb_result_only"] = True
    context["survey_batch"] = ensure_import_survey_batch(db, batch, current_user, now)

    try:
        with db.begin_nested():
            operation, target_id = import_row(
                db, batch, None, row, row.entity_type, merged, current_user, now, None, context,
            )
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Reimport failed: batch_id=%s row_id=%s entity_type=%s", batch_id, row_id, row.entity_type)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"修正导入失败：{exc}") from exc

    row.status = "success"
    row.operation_type = operation
    row.target_id = str(target_id) if target_id is not None else None
    row.normalized_data = merged
    operator = current_user.real_name or current_user.username
    origin = f"原错误：{original_error or '未知'}"
    if data_patch:
        row.warning_message = f"人工修正后导入（{operator}，{now.astimezone().strftime('%Y-%m-%d %H:%M')}）；{origin}"
    else:
        row.warning_message = f"按原数据重试导入（{operator}，{now.astimezone().strftime('%Y-%m-%d %H:%M')}）；{origin}"
    row.error_message = None
    batch.failed_count = max(0, (batch.failed_count or 0) - 1)
    batch.success_count = (batch.success_count or 0) + 1
    batch.warning_count = (batch.warning_count or 0) + 1
    db.commit()
    db.refresh(row)
    logger.info(
        "Row reimported: batch_id=%s row_id=%s entity_type=%s entity_key=%s operation=%s target=%s",
        batch_id, row_id, row.entity_type, row.entity_key, operation, row.target_id,
    )
    return serialize_row(row)


ERROR_DETAILS_LIMIT = 50


def reimport_failed_rows_batch(
    db: Session,
    batch_id: int,
    row_ids: list[int] | None,
    current_user: User,
) -> dict:
    """批量按原数据重试导入失败行。

    ``row_ids`` 为空 = 重试批次内全部失败行；逐行独立事务，单行失败不影响其他行。
    返回 {total, success, failed, errors}，errors 最多保留 ``ERROR_DETAILS_LIMIT`` 条。
    """
    batch = db.get(DataImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="import batch not found")

    stmt = select(DataImportRow).where(DataImportRow.import_batch_id == batch_id, DataImportRow.status == "failed")
    if row_ids:
        stmt = stmt.where(DataImportRow.id.in_(row_ids))
    rows = db.scalars(stmt.order_by(DataImportRow.row_no)).all()

    success = 0
    errors: list[dict] = []
    failed_total = 0
    for row in rows:
        try:
            reimport_failed_row(db, batch_id, row.id, None, current_user)
            success += 1
        except Exception as exc:
            failed_total += 1
            detail = getattr(exc, "detail", None) or str(exc)
            if len(errors) < ERROR_DETAILS_LIMIT:
                errors.append({"rowNo": row.row_no, "entityKey": row.entity_key, "error": str(detail)})
            logger.warning(
                "Batch reimport row failed: batch_id=%s row_id=%s entity_key=%s error=%s",
                batch_id, row.id, row.entity_key, detail,
            )
    db.rollback()  # 释放失败行残留的会话状态
    return {"total": len(rows), "success": success, "failed": failed_total, "errors": errors}
