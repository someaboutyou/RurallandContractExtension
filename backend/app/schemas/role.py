from pydantic import BaseModel, Field


class RoleRead(BaseModel):
    id: int
    name: str
    code: str
    dataScope: str
    description: str | None
    userCount: int
    isSystem: bool
    permissionCodes: list[str]


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=3, max_length=100)
    dataScope: str = Field(min_length=2, max_length=32)
    description: str | None = Field(default=None, max_length=1000)
    permissionCodes: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=3, max_length=100)
    dataScope: str = Field(min_length=2, max_length=32)
    description: str | None = Field(default=None, max_length=1000)
    permissionCodes: list[str] = Field(default_factory=list)
