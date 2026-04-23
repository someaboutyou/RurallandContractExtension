from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class RequestWorkflowMapping(Base, TimestampMixin):
    __tablename__ = "request_workflow_mappings"
    __table_args__ = (
        UniqueConstraint("tenant_code", "request_type", name="uq_request_workflow_mappings_tenant_request_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_code: Mapped[str | None] = mapped_column(ForeignKey("tenants.code"), nullable=True, index=True)
    request_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    workflow_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workflow_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_definition_versions.id"),
        nullable=True,
        index=True,
    )
    workflow_version_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant")
    workflow_version = relationship("WorkflowDefinitionVersion")
