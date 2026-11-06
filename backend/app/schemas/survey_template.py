from pydantic import BaseModel


class SurveyTemplateRead(BaseModel):
    key: str
    label: str
    category: str
    format: str
    filename: str
    description: str | None = None
    size: int = 0
    available: bool = True
