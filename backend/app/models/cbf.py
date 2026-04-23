from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Cbf(Base):
    __tablename__ = "cbf"

    cbfbm: Mapped[str] = mapped_column(String(18), primary_key=True)
    cbflx: Mapped[str] = mapped_column(String(1), nullable=False)
    cbfmc: Mapped[str] = mapped_column(String(50), nullable=False)
    cbfzjlx: Mapped[str] = mapped_column(String(1), nullable=False)
    cbfzjhm: Mapped[str] = mapped_column(String(20), nullable=False)
    cbfdz: Mapped[str] = mapped_column(String(100), nullable=False)
    yzbm: Mapped[str] = mapped_column(String(6), nullable=False)
    lxdh: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cbfcysl: Mapped[int] = mapped_column(Integer, nullable=False)
    cbfdcrq: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    cbfdcy: Mapped[str] = mapped_column(String(50), nullable=False)
    cbfdcjs: Mapped[str | None] = mapped_column(String(254), nullable=True)
    gsjs: Mapped[str | None] = mapped_column(String(254), nullable=True)
    gsjsr: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gsshrq: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    gsshr: Mapped[str | None] = mapped_column(String(50), nullable=True)
