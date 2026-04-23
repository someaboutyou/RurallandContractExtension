from pydantic import BaseModel


class RegionOption(BaseModel):
    id: int
    name: str
    code: str
    level: str
    tenantCode: str | None
    fullName: str
