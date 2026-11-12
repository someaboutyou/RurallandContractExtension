from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Region(Base, TimestampMixin):
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    tenant_code: Mapped[str | None] = mapped_column(ForeignKey("tenants.code"), nullable=True, index=True)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 权属单位代码表的原始全名（如「内蒙古省通辽市扎鲁特旗巨日合镇」）。
    # regions.name 存相对名（「巨日合镇」）供界面展示；导出权属单位代码表时
    # 用本字段还原全名，保证导出/导入回环一致。qs_code_table 导入时写入。
    qs_full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    parent = relationship("Region", remote_side=[id])
    tenant = relationship("Tenant", back_populates="regions")
    users = relationship("User", back_populates="region")
    issuers = relationship("Issuer", back_populates="region")
