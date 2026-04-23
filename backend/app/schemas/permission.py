from pydantic import BaseModel


class PermissionRead(BaseModel):
    id: int
    name: str
    code: str
    groupName: str
    category: str
    description: str | None
