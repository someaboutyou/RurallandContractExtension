from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class Fbf(TenantScopedMixin, Base):
    __tablename__ = "fbf"

    fbfbm: Mapped[str] = mapped_column(String(14), primary_key=True)
    fbffzrxm: Mapped[str] = mapped_column(String(50), nullable=False)
    fzrzjhm: Mapped[str] = mapped_column(String(30), nullable=False)
    fbfdz: Mapped[str] = mapped_column(String(100), nullable=False)
    lxdh: Mapped[str | None] = mapped_column(String(15), nullable=True)
    fbfmc: Mapped[str] = mapped_column(String(50), nullable=False)
    fzrzjlx: Mapped[str] = mapped_column(String(1), nullable=False)
    yzbm: Mapped[str] = mapped_column(String(6), nullable=False)
    fbfdcy: Mapped[str] = mapped_column(String(254), nullable=False)
    fbfdcrq: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fbfdcjs: Mapped[str | None] = mapped_column(String(254), nullable=True)
    # 以下字段与 CS 版 JCSJ_FBF 对齐：统一社会信用代码 / 审核人 / 审核日期 /
    # 审核意见 / 备注信息（调查记事 fbfdcjs 与备注 bzxx 是两个不同的字段）。
    tyshxydm: Mapped[str | None] = mapped_column(String(18), nullable=True)
    shr: Mapped[str | None] = mapped_column(String(50), nullable=True)
    shrq: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shyj: Mapped[str | None] = mapped_column(Text, nullable=True)
    bzxx: Mapped[str | None] = mapped_column(Text, nullable=True)
