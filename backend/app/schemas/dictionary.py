from datetime import datetime

from pydantic import BaseModel, Field


class DictionaryOption(BaseModel):
    value: str
    label: str


class DictionaryItemCreate(BaseModel):
    dictType: str = Field(min_length=1, max_length=100)
    dictName: str = Field(min_length=1, max_length=200)
    itemValue: str = Field(min_length=1, max_length=100)
    itemName: str = Field(min_length=1, max_length=200)
    sortOrder: int = 0
    enabled: bool = True
    remark: str | None = None


class DictionaryItemUpdate(BaseModel):
    dictType: str = Field(min_length=1, max_length=100)
    dictName: str = Field(min_length=1, max_length=200)
    itemValue: str = Field(min_length=1, max_length=100)
    itemName: str = Field(min_length=1, max_length=200)
    sortOrder: int = 0
    enabled: bool = True
    remark: str | None = None


class DictionaryItemRead(BaseModel):
    id: int
    dictType: str
    dictName: str
    itemValue: str
    itemName: str
    sortOrder: int
    enabled: bool
    remark: str | None
    createdAt: datetime
    updatedAt: datetime
