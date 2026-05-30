from datetime import datetime

from pydantic import BaseModel, Field


class RegionOption(BaseModel):
    id: int
    name: str
    code: str
    level: str
    tenantCode: str | None
    fullName: str
    parentId: int | None = None
    status: str = "active"
    sortOrder: int = 0
    remark: str | None = None
    leaf: bool = False


class RegionTreeNode(RegionOption):
    assignedUserId: int | None = None
    children: list["RegionTreeNode"] = []


class RegionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=32)
    level: str = Field(min_length=1, max_length=32)
    parentId: int | None = None
    status: str = Field(default="active", max_length=32)
    sortOrder: int = 0
    remark: str | None = None


class RegionUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=32)
    level: str = Field(min_length=1, max_length=32)
    parentId: int | None = None
    status: str = Field(default="active", max_length=32)
    sortOrder: int = 0
    remark: str | None = None


class RegionRead(RegionOption):
    createdAt: datetime
    updatedAt: datetime
