from datetime import datetime

from pydantic import BaseModel, Field


class SurveyBatchCreate(BaseModel):
    batchName: str = Field(min_length=1, max_length=120)
    regionCode: str | None = Field(default=None, max_length=32)
    regionName: str | None = Field(default=None, max_length=120)
    surveyType: str = Field(default="household_survey", max_length=32)
    remark: str | None = None


class SurveyBatchRead(BaseModel):
    id: int
    batchNo: str
    batchName: str
    regionCode: str | None = None
    regionName: str | None = None
    surveyType: str
    status: str
    taskCount: int = 0
    notStartedCount: int = 0
    surveyedCount: int = 0
    changedCount: int = 0
    confirmedCount: int = 0
    skippedCount: int = 0
    createdAt: datetime
    remark: str | None = None


class SurveyTaskRead(BaseModel):
    id: int
    batchId: int
    contractorUid: str
    cbfbm: str
    cbfmc: str
    regionCode: str | None = None
    taskStatus: str
    hasChange: bool
    changeCount: int
    investigatedAt: datetime | None = None
    remark: str | None = None


class SurveyChangeRecordRead(BaseModel):
    id: int
    changeNo: str
    batchId: int
    contractorUid: str
    cbfbm: str
    changeType: str
    changeLevel: str
    changeStatus: str
    changeReason: str | None = None
    policyBasis: str | None = None
    generatedRequestId: int | None = None
    generatedRequestNo: str | None = None
    investigatorName: str | None = None
    investigatedAt: datetime | None = None
    createdAt: datetime


class SurveyChangeDiffRead(BaseModel):
    id: int
    batchId: int
    contractorUid: str
    changeId: int | None = None
    entityType: str
    entityUid: str
    entityName: str | None = None
    fieldName: str
    fieldLabel: str
    beforeValue: str | None = None
    afterValue: str | None = None
    changeReason: str | None = None
    createdAt: datetime


class SurveyTagCreate(BaseModel):
    tagCode: str = Field(min_length=1, max_length=64)
    tagName: str = Field(min_length=1, max_length=80)
    reason: str | None = None
    policyBasis: str | None = None


class SurveyTagDisable(BaseModel):
    disabledReason: str = Field(min_length=1, max_length=500)


class SurveyRestructureMemberUpdate(BaseModel):
    memberUid: str | None = None
    memberName: str = Field(min_length=1, max_length=50)
    memberIdNo: str | None = Field(default=None, max_length=20)
    fromCbfbm: str | None = Field(default=None, max_length=18)
    toCbfbm: str | None = Field(default=None, max_length=18)
    actionType: str = Field(default="move", max_length=32)
    rightsDisposition: str | None = Field(default=None, max_length=64)
    remark: str | None = None


class SurveyRestructureCreate(BaseModel):
    restructureType: str = Field(min_length=1, max_length=32)
    sourceContractorUid: str | None = Field(default=None, max_length=36)
    sourceCbfbm: str | None = Field(default=None, max_length=18)
    sourceCbfmc: str | None = Field(default=None, max_length=50)
    targetContractorUid: str | None = Field(default=None, max_length=36)
    targetCbfbm: str | None = Field(default=None, max_length=18)
    targetCbfmc: str | None = Field(default=None, max_length=50)
    newCbfbm: str | None = Field(default=None, max_length=18)
    newCbfmc: str | None = Field(default=None, max_length=50)
    status: str = Field(default="draft", max_length=32)
    reason: str | None = None
    policyBasis: str | None = None
    rightsSummary: str | None = None
    contractDisposition: str | None = Field(default=None, max_length=64)
    certificateDisposition: str | None = Field(default=None, max_length=64)
    remark: str | None = None
    members: list[SurveyRestructureMemberUpdate] = []


class SurveyAuthorizationCreate(BaseModel):
    principalName: str = Field(min_length=1, max_length=50)
    principalIdNo: str | None = Field(default=None, max_length=32)
    agentName: str = Field(min_length=1, max_length=50)
    agentIdNo: str | None = Field(default=None, max_length=32)
    agentPhone: str | None = Field(default=None, max_length=32)
    authorizedMatters: str = Field(min_length=1)
    validFrom: str | None = None
    validTo: str | None = None
    status: str = Field(default="active", max_length=32)
    remark: str | None = None


class SurveyAuthorizationRevoke(BaseModel):
    revokeReason: str = Field(min_length=1, max_length=500)


class SurveyGenerateRequest(BaseModel):
    requestType: str | None = Field(default=None, max_length=32)
    requestTitle: str | None = Field(default=None, max_length=120)
    reason: str | None = None
    note: str | None = None


class SurveyTaskSkip(BaseModel):
    skipReason: str = Field(min_length=1, max_length=500)


class SurveyMemberUpdate(BaseModel):
    memberUid: str | None = None
    name: str = Field(min_length=1, max_length=50)
    gender: str = Field(min_length=1, max_length=1)
    idType: str = Field(min_length=1, max_length=1)
    idNo: str = Field(min_length=1, max_length=20)
    relationToHead: str = Field(min_length=1, max_length=2)
    noteCode: str | None = Field(default=None, max_length=1)
    isCoOwner: str | None = Field(default=None, max_length=1)
    note: str | None = Field(default=None, max_length=254)
    memberResultStatus: str = "normal"
    surveyStatus: str = "surveyed"
    isHouseholdHead: bool = False
    isUrbanSettled: bool = False
    urbanSettledDate: str | None = None
    urbanSettledPlace: str | None = None
    isMarriedOutWoman: bool = False
    marriedOutDate: str | None = None
    marriedOutPlace: str | None = None
    isDeceased: bool = False
    deceasedDate: str | None = None
    isFiveGuarantees: bool = False
    currentResidenceAddress: str | None = None
    householdRegisterAddress: str | None = None
    phone: str | None = None
    changeReason: str | None = None
    policyBasis: str | None = None
    rightsDisposition: str | None = None
    remark: str | None = None


class SurveyContractorUpdate(BaseModel):
    code: str = Field(min_length=1, max_length=18)
    typeCode: str = Field(min_length=1, max_length=1)
    name: str = Field(min_length=1, max_length=50)
    idType: str = Field(min_length=1, max_length=1)
    idNo: str = Field(min_length=1, max_length=20)
    address: str = Field(min_length=1, max_length=100)
    postcode: str = Field(min_length=1, max_length=6)
    mobile: str | None = None
    surveyDate: str | None = None
    surveyorName: str | None = None
    surveyNote: str | None = None
    publicNoticeNote: str | None = None
    publicNoticeRecorder: str | None = None
    publicNoticeReviewDate: str | None = None
    publicNoticeReviewer: str | None = None
    groupRegionCode: str | None = Field(default=None, max_length=32)
    groupRegionName: str | None = Field(default=None, max_length=120)
    surveyStatus: str = "surveyed"
    resultStatus: str = "normal"
    changeType: str = "none"
    changeReason: str | None = None
    policyBasis: str | None = None
    evidenceSummary: str | None = None
    remark: str | None = None
    familyMembers: list[SurveyMemberUpdate] = []


class SurveyMemberRead(SurveyMemberUpdate):
    memberUid: str
    baseId: int | None = None
    isChanged: bool = False


class SurveyBaseMemberRead(BaseModel):
    memberUid: str
    name: str
    gender: str
    idType: str
    idNo: str
    relationToHead: str
    noteCode: str | None = None
    isCoOwner: str | None = None
    note: str | None = None


class SurveyBaseContractorRead(BaseModel):
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
    surveyorName: str | None = None
    surveyNote: str | None = None
    publicNoticeNote: str | None = None
    publicNoticeRecorder: str | None = None
    publicNoticeReviewDate: str | None = None
    publicNoticeReviewer: str | None = None
    groupRegionCode: str | None = None
    groupRegionName: str | None = None
    familyMembers: list[SurveyBaseMemberRead] = []


class SurveyContractorRead(BaseModel):
    id: int
    batchId: int
    contractorUid: str
    baseId: int
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
    surveyorName: str | None = None
    surveyNote: str | None = None
    publicNoticeNote: str | None = None
    publicNoticeRecorder: str | None = None
    publicNoticeReviewDate: str | None = None
    publicNoticeReviewer: str | None = None
    groupRegionCode: str | None = None
    groupRegionName: str | None = None
    surveyStatus: str
    resultStatus: str
    isChanged: bool
    changeType: str
    changeReason: str | None = None
    policyBasis: str | None = None
    evidenceSummary: str | None = None
    remark: str | None = None
    baseContractor: SurveyBaseContractorRead | None = None
    familyMembers: list[SurveyMemberRead]
    generatedRequestId: int | None = None
    generatedRequestNo: str | None = None
