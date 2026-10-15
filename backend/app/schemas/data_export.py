from datetime import datetime

from pydantic import BaseModel


class DataExportCreate(BaseModel):
    regionCode: str
    regionName: str | None = None
    regionLevel: str | None = None
    exportType: str = "contractor_roster"


class DataExportRead(BaseModel):
    id: int
    exportNo: str
    regionCode: str | None = None
    regionName: str | None = None
    regionLevel: str | None = None
    exportType: str
    status: str
    progress: int = 0
    progressMessage: str | None = None
    fileName: str | None = None
    fileSize: int = 0
    recordCount: int = 0
    operatorId: int | None = None
    operatorName: str | None = None
    errorMessage: str | None = None
    isHistorical: bool = False
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


def serialize_export(item) -> dict:
    """ORM（snake_case）→ 前端契约（camelCase），与 data_import.serialize_batch 同约定。"""
    return {
        "id": item.id,
        "exportNo": item.export_no,
        "regionCode": item.region_code,
        "regionName": item.region_name,
        "regionLevel": item.region_level,
        "exportType": item.export_type,
        "status": item.status,
        "progress": item.progress or 0,
        "progressMessage": item.progress_message,
        "fileName": item.file_name,
        "fileSize": item.file_size,
        "recordCount": item.record_count,
        "operatorId": item.operator_id,
        "operatorName": item.operator_name,
        "errorMessage": item.error_message,
        "isHistorical": bool(getattr(item, "is_historical", False)),
        "createdAt": item.created_at,
        "updatedAt": item.updated_at,
    }
