from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    code: Mapped[str] = mapped_column(String(12), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    users = relationship("User", back_populates="tenant")
    regions = relationship("Region", back_populates="tenant")
