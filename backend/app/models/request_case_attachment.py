from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScopedMixin, TimestampMixin


class RequestCaseAttachment(TenantScopedMixin, Base, TimestampMixin):
    __tablename__ = "request_case_attachments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("request_cases.id"), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    request_case = relationship("RequestCase", back_populates="attachments")
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_id])
