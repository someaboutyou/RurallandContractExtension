from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScopedMixin, TimestampMixin


class RequestCase(TenantScopedMixin, Base, TimestampMixin):
    __tablename__ = "request_cases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    serial_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    request_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    request_type: Mapped[str] = mapped_column(String(32), nullable=False)
    issuer_code: Mapped[str | None] = mapped_column(String(14), nullable=True, index=True)
    issuer_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contractor_code: Mapped[str | None] = mapped_column(String(18), nullable=True, index=True)
    contractor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    contractor_id_type: Mapped[str] = mapped_column(String(32), nullable=False)
    contractor_id_no: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    contract_code: Mapped[str | None] = mapped_column(String(19), nullable=True, index=True)
    workflow_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    workflow_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workflow_version_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_definition_versions.id"), nullable=True)
    workflow_version_no: Mapped[str | None] = mapped_column(String(16), nullable=True)
    current_step: Mapped[str] = mapped_column(String(64), nullable=False, default="申请")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="待提交")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    issuer_id: Mapped[int | None] = mapped_column(ForeignKey("issuers.id"), nullable=True, index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    issuer = relationship("Issuer", back_populates="request_cases")
    created_by = relationship("User", foreign_keys=[created_by_id])
    workflow_version = relationship("WorkflowDefinitionVersion", foreign_keys=[workflow_version_id])
    participants = relationship("RequestCaseParticipant", back_populates="request_case", cascade="all, delete-orphan")
    attachments = relationship("RequestCaseAttachment", back_populates="request_case", cascade="all, delete-orphan")
