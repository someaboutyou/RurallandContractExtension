from pydantic import BaseModel, Field


class WorkflowDefinitionVersionRead(BaseModel):
    id: int
    workflowKey: str
    versionNo: int
    name: str
    processIds: list[str]
    remark: str | None = None
    isActive: bool
    publishedByName: str | None = None
    createdAt: str


class WorkflowDefinitionListItem(BaseModel):
    key: str
    name: str
    filename: str
    processIds: list[str]
    updatedAt: str
    versionCount: int = 0
    activeVersionId: int | None = None
    activeVersionNo: int | None = None
    hasDraft: bool = False
    draftUpdatedAt: str | None = None


class WorkflowDefinitionRead(WorkflowDefinitionListItem):
    content: str
    versions: list[WorkflowDefinitionVersionRead] = []


class WorkflowDefinitionSave(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1)


class WorkflowDefinitionValidate(BaseModel):
    content: str = Field(min_length=1)


class WorkflowDefinitionPublish(BaseModel):
    remark: str | None = Field(default=None, max_length=1000)
    activate: bool = True


class WorkflowDefinitionActivate(BaseModel):
    versionId: int


class WorkflowDefinitionValidationResult(BaseModel):
    valid: bool
    processIds: list[str]
    name: str | None = None
    message: str
