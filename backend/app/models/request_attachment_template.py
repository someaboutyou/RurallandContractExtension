from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class RequestAttachmentTemplate(Base, TimestampMixin):
    __tablename__ = "request_attachment_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_code: Mapped[str | None] = mapped_column(String(12), ForeignKey("tenants.code"), nullable=True, index=True)
    request_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stage_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stage_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tenant = relationship("Tenant")
