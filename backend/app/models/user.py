from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    real_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    mobile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    tenant_code: Mapped[str | None] = mapped_column(ForeignKey("tenants.code"), nullable=True, index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)
    # 平台管理员首次初始化时若尚未导入任何区域数据，允许没有归属区域（region_id 为空）；
    # 区域相关数据权限由角色 data_scope=all 兜底，后续可在「人员权限」页补配。
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True, index=True)
    # 当前进入的调查批次（「调查批次管理」里点「进入任务」写入）。
    # 相关页面（承包方调查等）默认按该批次加载；为空时回退到默认批次。
    current_survey_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    tenant = relationship("Tenant", back_populates="users")
    role = relationship("Role", back_populates="users")
    region = relationship("Region", back_populates="users")
    region_permissions = relationship(
        "UserRegionPermission",
        back_populates="user",
        cascade="all, delete-orphan",
    )
