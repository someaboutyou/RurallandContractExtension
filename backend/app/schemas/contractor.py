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


class FamilyMemberRead(FamilyMemberBase):
    pass


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
