from typing import Literal

from pydantic import BaseModel, Field


class FamilyMemberBase(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    gender: str = Field(min_length=1, max_length=1)
    idType: str = Field(min_length=1, max_length=1)
    idNo: str = Field(min_length=1, max_length=20)
    relationToHead: str = Field(min_length=1, max_length=2)
    noteCode: str | None = Field(default=None, max_length=1)
    isCoOwner: str | None = Field(default=None, max_length=1)
    note: str | None = Field(default=None, max_length=254)


class FamilyMemberCreate(FamilyMemberBase):
    pass


class FamilyMemberRead(BaseModel):
    """家庭成员读模型。

    ⛔ 不沿用 FamilyMemberBase 的 min_length 约束：库内存量数据允许
    姓名/证件号等字段为空（质检会标记，但读接口必须能返回，
    否则这类户的「编辑承包方」对话框直接 500 打不开——实测波及
    2388/7161 户）。完整性由前端 validateFamilyMembers 在保存时把关。
    """

    name: str = Field(default="", max_length=50)
    gender: str = Field(default="", max_length=1)
    idType: str = Field(default="", max_length=1)
    idNo: str = Field(default="", max_length=20)
    relationToHead: str = Field(default="", max_length=2)
    noteCode: str | None = Field(default=None, max_length=1)
    isCoOwner: str | None = Field(default=None, max_length=1)
    note: str | None = Field(default=None, max_length=254)


class ContractorBase(BaseModel):
    code: str = Field(min_length=1, max_length=18)
    typeCode: str = Field(min_length=1, max_length=1)
    name: str = Field(min_length=1, max_length=50)
    idType: str = Field(min_length=1, max_length=1)
    idNo: str = Field(min_length=1, max_length=20)
    address: str = Field(min_length=1, max_length=100)
    postcode: str = Field(min_length=1, max_length=6)
    mobile: str | None = Field(default=None, max_length=20)
    surveyDate: str | None = None
    surveyorName: str = Field(min_length=1, max_length=50)
    surveyNote: str | None = Field(default=None, max_length=254)
    publicNoticeNote: str | None = Field(default=None, max_length=254)
    publicNoticeRecorder: str | None = Field(default=None, max_length=50)
    publicNoticeReviewDate: str | None = None
    publicNoticeReviewer: str | None = Field(default=None, max_length=50)
    groupRegionCode: str | None = Field(default=None, max_length=32)
    groupRegionName: str | None = Field(default=None, max_length=120)
    familyMembers: list[FamilyMemberCreate] = []


class ContractorCreate(ContractorBase):
    pass


class ContractorUpdate(ContractorBase):
    pass


class ContractorRead(BaseModel):
    code: str
    typeCode: str
    name: str
    idType: str
    idNo: str
    address: str
    postcode: str
    mobile: str | None = None
    memberCount: int
    surveyDate: str | None = None
    surveyorName: str
    surveyNote: str | None = None
    publicNoticeNote: str | None = None
    publicNoticeRecorder: str | None = None
    publicNoticeReviewDate: str | None = None
    publicNoticeReviewer: str | None = None
    groupRegionCode: str | None = None
    groupRegionName: str | None = None
    familyMembers: list[FamilyMemberRead]
    contracts: list[dict] = []


class CadastralExportRequest(BaseModel):
    """批量导出《地籍调查表》Word 的筛选条件（与列表查询同口径）。"""

    regionCode: str | None = Field(default=None, max_length=32)
    regionLabel: str | None = Field(default=None, max_length=120)
    keyword: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, max_length=100)
    memberName: str | None = Field(default=None, max_length=100)
    idNo: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=200)
    batchId: int | None = None


class SurveySheetExportRequest(CadastralExportRequest):
    """批量导出摸底表 Word 的请求（复用地籍调查表的筛选条件 + 表类型）。

    ``sheetType``：``land-change``（包地变化摸底表）/ ``member-change``（家庭成员变化摸底表）。
    """

    sheetType: Literal["land-change", "member-change"]


class CadastralExportProgressRead(BaseModel):
    id: str
    status: str
    done: int
    total: int
    percent: int
    message: str
    error: str | None = None
    filename: str | None = None
    regionLabel: str | None = None
