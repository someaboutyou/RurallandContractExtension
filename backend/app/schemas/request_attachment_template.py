from pydantic import BaseModel, Field


class RequestAttachmentTemplateBase(BaseModel):
    tenantCode: str | None = Field(default=None, max_length=12)
    parentId: int | None = None
    requestType: str = Field(min_length=1, max_length=32)
    stageCode: str = Field(min_length=1, max_length=64)
    stageName: str | None = Field(default=None, max_length=100)
    category: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    required: bool = True
    description: str | None = None
    exampleFileName: str | None = Field(default=None, max_length=255)
    sortOrder: int = 0
    enabled: bool = True


class RequestAttachmentTemplateCreate(RequestAttachmentTemplateBase):
    pass


class RequestAttachmentTemplateUpdate(RequestAttachmentTemplateBase):
    pass


class RequestAttachmentTemplateRead(RequestAttachmentTemplateBase):
    id: int
    hasChildren: bool = False
