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
    # 授权区域清单。前端「调查批次」用它判断是否该用「所属区域」当默认筛选：
    # 多区域授权（例如「一个镇 + 另一个镇的某个村」）时所属区域只是其中之一，
    # 硬按它的前缀筛会挡掉其余授权区域的数据。服务层 serialize_current_user 一直在返回，
    # 此前只是被本响应模型过滤掉了。
    regionPermissions: list[dict] = Field(default_factory=list)
