from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class WorkflowDefinitionVersion(Base, TimestampMixin):
    __tablename__ = "workflow_definition_versions"
    __table_args__ = (
        UniqueConstraint("workflow_key", "version_no", name="uq_workflow_definition_versions_workflow_key_version_no"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workflow_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    process_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    published_by = relationship("User", foreign_keys=[published_by_id])
