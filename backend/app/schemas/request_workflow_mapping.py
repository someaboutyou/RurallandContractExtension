from pydantic import BaseModel, Field


class RequestWorkflowMappingBase(BaseModel):
    tenantCode: str | None = Field(default=None, max_length=12)
    requestType: str = Field(min_length=1, max_length=32)
    workflowKey: str = Field(min_length=1, max_length=64)
    workflowVersionId: int | None = None
    enabled: bool = True
    sortOrder: int = Field(default=0, ge=0, le=9999)
    remark: str | None = Field(default=None, max_length=1000)


class RequestWorkflowMappingCreate(RequestWorkflowMappingBase):
    pass


class RequestWorkflowMappingUpdate(RequestWorkflowMappingBase):
    pass


class RequestWorkflowMappingRead(RequestWorkflowMappingBase):
    id: int
    workflowName: str | None = None
    workflowVersionNo: int | None = None
    workflowVersionLabel: str | None = None
    tenantName: str | None = None
    source: str = "global"
    createdAt: str
    updatedAt: str


class RequestWorkflowOptionRead(BaseModel):
    requestType: str
    workflowKey: str
    workflowName: str | None = None
    workflowVersionId: int | None = None
    workflowVersionNo: int | None = None
    tenantCode: str | None = None
    source: str = "global"


class WorkflowSimpleRead(BaseModel):
    key: str
    name: str
    activeVersionId: int | None = None
    activeVersionNo: int | None = None


class RequestWorkflowOptionsPayload(BaseModel):
    mappings: list[RequestWorkflowOptionRead] = []
    workflows: list[WorkflowSimpleRead] = []
