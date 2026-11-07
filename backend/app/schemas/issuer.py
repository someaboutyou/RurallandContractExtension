from typing import Literal

from pydantic import BaseModel, Field


class IssuerBase(BaseModel):
    code: str = Field(min_length=1, max_length=14)
    name: str = Field(min_length=1, max_length=50)
    ownerName: str = Field(min_length=1, max_length=50)
    ownerIdType: str = Field(min_length=1, max_length=1)
    ownerIdNo: str = Field(min_length=1, max_length=30)
    mobile: str | None = Field(default=None, max_length=15)
    address: str = Field(min_length=1, max_length=100)
    postcode: str = Field(min_length=1, max_length=6)
    surveyorName: str = Field(min_length=1, max_length=254)
    surveyDate: str | None = None
    notes: str | None = None
    status: str | None = None
    regionId: int | None = None


class IssuerCreate(IssuerBase):
    pass


class IssuerUpdate(IssuerBase):
    pass


class IssuerRead(BaseModel):
    code: str
    name: str
    ownerName: str
    ownerIdType: str
    ownerIdNo: str
    mobile: str | None = None
    address: str | None = None
    postcode: str | None = None
    surveyorName: str | None = None
    surveyDate: str | None = None
    notes: str | None = None
    regionId: int | None = None
    region: str | None = None
    status: str | None = None


class IssuerContractorRead(BaseModel):
    code: str
    typeCode: str | None = None
    name: str
    idType: str | None = None
    idNo: str | None = None
    mobile: str | None = None
    address: str | None = None
    memberCount: int | None = None
    surveyDate: str | None = None
    surveyorName: str | None = None
    groupRegionName: str | None = None


class IssuerMergeRequest(BaseModel):
    keepCode: str = Field(min_length=1, max_length=14)
    mergeCodes: list[str] = Field(min_length=1)


class IssuerDocxExportRequest(BaseModel):
    codes: list[str] = Field(min_length=1, max_length=500)


class IssuerExportJobRequest(BaseModel):
    """批量导出后台任务：kind=survey(发包方调查表) | publicity=村组公示签字表。

    导出范围二选一：``codes``（勾选的发包方）或 ``batchId``（导出该批次全部
    可见发包方，数据范围仍按当前用户权限收敛）。
    """

    kind: Literal["survey", "publicity"]
    codes: list[str] | None = Field(default=None, max_length=500)
    batchId: int | None = None
