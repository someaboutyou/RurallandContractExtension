from pydantic import BaseModel, Field


class RequestCaseBase(BaseModel):
    requestType: str = Field(min_length=1, max_length=32)
    requestTitle: str | None = Field(default=None, max_length=120)
    issuerCode: str = Field(min_length=1, max_length=14)
    issuerName: str | None = Field(default=None, max_length=50)
    contractorCode: str | None = Field(default=None, max_length=18)
    contractorName: str | None = Field(default=None, max_length=100)
    contractorIdType: str | None = Field(default=None, max_length=32)
    contractorIdNo: str | None = Field(default=None, max_length=32)
    contractCode: str | None = Field(default=None, max_length=19)
    mobile: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=255)
    reason: str | None = None
    note: str | None = None
    workflowCode: str | None = Field(default=None, max_length=64)
    workflowVersionId: int | None = None


class RequestCaseCreate(RequestCaseBase):
    pass


class RequestCaseUpdate(RequestCaseBase):
    pass


class RequestCaseAuditAction(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)


class RequestCaseWorkflowStepRead(BaseModel):
    code: str
    name: str
    status: str
    label: str


class RequestCaseWorkflowViewRead(BaseModel):
    workflowCode: str
    workflowName: str
    workflowVersionId: int | None = None
    workflowVersionNo: str | None = None
    workflowVersionLabel: str | None = None
    currentTaskCode: str | None = None
    currentTaskName: str | None = None
    content: str
    workflowSteps: list[RequestCaseWorkflowStepRead] = []


class RequestCaseCandidateRead(BaseModel):
    userId: int
    username: str
    userName: str
    roleName: str | None = None
    tenantCode: str | None = None
    regionCode: str | None = None
    regionName: str | None = None


class RequestCaseTaskConfigRead(BaseModel):
    code: str
    name: str
    permissionCode: str | None = None
    dataScope: str | None = None
    requireComment: bool = False
    requireAttachment: bool = False
    attachmentTypes: list[str] = []
    candidateRoleCodes: list[str] = []
    candidateUserMode: str | None = None
    isApplicantTask: bool = False


class RequestCaseParticipantRead(BaseModel):
    id: int
    userId: int
    username: str
    userName: str
    roleName: str | None = None
    action: str
    actionLabel: str
    stepName: str | None = None
    comment: str | None = None
    createdAt: str


class RequestCaseAttachmentRead(BaseModel):
    id: int
    category: str | None = None
    stageCode: str | None = None
    originalName: str
    contentType: str | None = None
    fileSize: int
    uploadedByName: str | None = None
    createdAt: str


class RequestCaseAttachmentTemplateRead(BaseModel):
    key: str
    parentId: int | None = None
    category: str
    name: str
    required: bool = True
    stageCode: str | None = None
    stageName: str | None = None
    description: str | None = None
    exampleFileName: str | None = None
    uploadedCount: int = 0
    satisfied: bool = False


class RequestCaseRead(BaseModel):
    id: int
    serialNo: str
    requestTitle: str | None = None
    requestType: str
    tenantCode: str | None = None
    regionCode: str | None = None
    issuerCode: str | None = None
    issuerName: str | None = None
    contractorCode: str | None = None
    contractorName: str
    contractorIdType: str
    contractorIdNo: str
    contractCode: str | None = None
    mobile: str | None = None
    address: str | None = None
    reason: str | None = None
    note: str | None = None
    workflowCode: str | None = None
    workflowVersionId: int | None = None
    workflowVersionNo: str | None = None
    workflowVersionLabel: str | None = None
    currentTaskCode: str | None = None
    currentTaskName: str | None = None
    currentStep: str
    status: str
    createdByName: str | None = None
    requiredPermission: str | None = None
    taskConfig: RequestCaseTaskConfigRead | None = None
    availableActions: list[str] = []
    workflowSteps: list[RequestCaseWorkflowStepRead] = []
    candidateHandlers: list[RequestCaseCandidateRead] = []
    participants: list[RequestCaseParticipantRead] = []
    attachments: list[RequestCaseAttachmentRead] = []
    attachmentTemplates: list[RequestCaseAttachmentTemplateRead] = []
    submittedAt: str | None = None
    completedAt: str | None = None
    createdAt: str
    updatedAt: str
