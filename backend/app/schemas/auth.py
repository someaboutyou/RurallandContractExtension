from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class TokenPayload(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class CurrentUser(BaseModel):
    id: int
    username: str
    realName: str
    tenantCode: str | None
    tenantName: str | None
    role: str
    roleCode: str
    dataScope: str
    regionCode: str
    region: str
    status: str
    permissions: list[str]
