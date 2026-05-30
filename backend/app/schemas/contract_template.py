from pydantic import BaseModel, Field


class ContractTemplateRead(BaseModel):
    key: str | None = None
    title: str | None = None
    name: str
    content: str
    updatedAt: str | None = None
    size: int = 0


class ContractTemplateUpdate(BaseModel):
    content: str = Field(min_length=1)


class ContractTemplatePreviewRequest(BaseModel):
    content: str = Field(min_length=1)


class ContractTemplatePreviewRead(BaseModel):
    renderedHtml: str
