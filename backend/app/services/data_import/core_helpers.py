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

    # 业务数据落库后反推补齐镇/村/组区域（缺则补，幂等）。
    # 种子只提供省/市/县三级国标链路，镇/村/组以导入数据为准 —— 所有导入路径
    # （CSV / GDB / 国标包）都收敛到本函数收尾，挂这里一次即可全覆盖。
    try:
        from app.db.init_db import sync_regions_from_business_codes

        sync_regions_from_business_codes(db)
    except Exception:  # noqa: BLE001 —— 区域反推失败不阻断导入结果
        import logging

        logging.getLogger(__name__).exception(
            "导入收尾阶段反推补齐镇/村/组区域失败（batch=%s）", batch.import_no
        )

    # 图层自愈：导入可能新增几何/扩大数据范围，确保 GeoServer 图层可用并刷新缓存
    # （补发布缺失的 featuretype → 重算 bbox → 固定 gridSubset → 清空过期瓦片）。
    # 内部已做「GeoServer 未启动则整体跳过 + 逐层容错」，失败只记日志不阻断导入。
    try:
        from app.services.geoserver_service import geoserver_service

        geoserver_service.refresh_after_data_change()
    except Exception:  # noqa: BLE001 —— 图层刷新失败不阻断导入结果
        import logging

        logging.getLogger(__name__).exception(
            "导入收尾阶段刷新 GeoServer 图层失败（batch=%s）", batch.import_no
        )
