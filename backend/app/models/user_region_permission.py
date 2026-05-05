from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class UserRegionPermission(Base, TimestampMixin):
    __tablename__ = "user_region_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "region_code", name="uq_user_region_permissions_user_region"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_code: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    region_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    user = relationship("User", back_populates="region_permissions")
