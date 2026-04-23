from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Fbf(Base):
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
