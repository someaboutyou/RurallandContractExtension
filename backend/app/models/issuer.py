from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Issuer(Base, TimestampMixin):
    __tablename__ = "issuers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    owner_name: Mapped[str] = mapped_column(String(100), nullable=False)
    owner_id_no: Mapped[str] = mapped_column(String(32), nullable=False)
    mobile: Mapped[str] = mapped_column(String(32), nullable=True)
    address: Mapped[str] = mapped_column(String(255), nullable=True)
    postcode: Mapped[str] = mapped_column(String(16), nullable=True)
    surveyor_name: Mapped[str] = mapped_column(String(100), nullable=True)
    survey_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="待提交")
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False, index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    region = relationship("Region", back_populates="issuers")
    created_by = relationship("User", foreign_keys=[created_by_id])
    request_cases = relationship("RequestCase", back_populates="issuer")
