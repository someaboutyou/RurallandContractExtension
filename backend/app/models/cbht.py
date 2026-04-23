from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Cbht(Base):
    __tablename__ = "cbht"

    cbhtbm: Mapped[str] = mapped_column(String(19), primary_key=True)
    ycbhtbm: Mapped[str | None] = mapped_column(String(19), nullable=True)
    fbfbm: Mapped[str | None] = mapped_column(String(14), nullable=True)
    cbfbm: Mapped[str | None] = mapped_column(String(18), nullable=True)
    cbfs: Mapped[str | None] = mapped_column(String(3), nullable=True)
    cbqxq: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cbqxz: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    htzmj: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    cbdkzs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qdsj: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    htzmjm: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    yhtzmj: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    yhtzmjm: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
