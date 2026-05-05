from pydantic import BaseModel, Field


class UserRead(BaseModel):
    id: int
    username: str
    realName: str
    mobile: str | None
    tenantCode: str | None
    tenantName: str | None
    roleId: int
    role: str
    roleCode: str
    dataScope: str
    regionId: int
    region: str
    regionPermissions: list[dict] = Field(default_factory=list)
    status: str


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    realName: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=100)
    mobile: str | None = Field(default=None, max_length=32)
    roleId: int
    regionCodes: list[str] = Field(default_factory=list)
    status: str = Field(default="active", max_length=32)


class UserUpdate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    realName: str = Field(min_length=2, max_length=100)
    mobile: str | None = Field(default=None, max_length=32)
    roleId: int
    regionCodes: list[str] = Field(default_factory=list)
    status: str = Field(default="active", max_length=32)


class UserPasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=100)
