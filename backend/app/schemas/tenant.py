from pydantic import BaseModel


class TenantRead(BaseModel):
    code: str
    name: str
    regionCode: str | None
    status: str
    description: str | None
