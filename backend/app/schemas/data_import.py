from datetime import datetime

from pydantic import BaseModel, Field


class DataImportBatchCreate(BaseModel):
    importName: str = Field(min_length=1, max_length=120)
    importType: str = Field(default="initial_build", max_length=32)
    sourceType: str = Field(default="csv", max_length=32)
    sourceOrg: str | None = Field(default=None, max_length=120)
    regionCode: str | None = Field(default=None, max_length=32)
    regionName: str | None = Field(default=None, max_length=120)
    remark: str | None = None


class DataImportBatchRead(BaseModel):
    id: int
    importNo: str
    importName: str
    importType: str
    sourceType: str
    sourceName: str | None = None
    sourceOrg: str | None = None
    regionCode: str | None = None
    regionName: str | None = None
    status: str
    totalCount: int
    successCount: int
    failedCount: int
    warningCount: int
    linkedSurveyBatchId: int | None = None
    importedByName: str | None = None
    importedAt: datetime | None = None
    remark: str | None = None
    createdAt: datetime


class DataImportFileRead(BaseModel):
    id: int
    importBatchId: int
    fileType: str
    originalName: str
    parseStatus: str
    rowCount: int
    errorCount: int
    uploadedAt: datetime | None = None


class DataImportRowRead(BaseModel):
    id: int
    rowNo: int
    entityType: str
    entityKey: str | None = None
    operationType: str
    status: str
    targetTable: str | None = None
    targetId: str | None = None
    errorMessage: str | None = None
    warningMessage: str | None = None
    rawData: dict | None = None
    normalizedData: dict | None = None
    createdAt: datetime
