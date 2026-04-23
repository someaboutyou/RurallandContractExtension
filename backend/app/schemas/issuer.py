from pydantic import BaseModel, Field


class IssuerBase(BaseModel):
    code: str = Field(min_length=1, max_length=14)
    name: str = Field(min_length=1, max_length=50)
    ownerName: str = Field(min_length=1, max_length=50)
    ownerIdType: str = Field(min_length=1, max_length=1)
    ownerIdNo: str = Field(min_length=1, max_length=30)
    mobile: str | None = Field(default=None, max_length=15)
    address: str = Field(min_length=1, max_length=100)
    postcode: str = Field(min_length=1, max_length=6)
    surveyorName: str = Field(min_length=1, max_length=254)
    surveyDate: str | None = None
    notes: str | None = None
    status: str | None = None
    regionId: int | None = None


class IssuerCreate(IssuerBase):
    pass


class IssuerUpdate(IssuerBase):
    pass


class IssuerRead(BaseModel):
    code: str
    name: str
    ownerName: str
    ownerIdType: str
    ownerIdNo: str
    mobile: str | None = None
    address: str | None = None
    postcode: str | None = None
    surveyorName: str | None = None
    surveyDate: str | None = None
    notes: str | None = None
    regionId: int | None = None
    region: str | None = None
    status: str | None = None
