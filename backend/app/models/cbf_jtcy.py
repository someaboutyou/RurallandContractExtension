from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CbfJtcy(Base):
    __tablename__ = "cbf_jtcy"

    cbfbm: Mapped[str] = mapped_column(String(18), primary_key=True)
    cyzjhm: Mapped[str] = mapped_column(String(20), primary_key=True)
    cyxm: Mapped[str] = mapped_column(String(50), nullable=False)
    cyzjlx: Mapped[str] = mapped_column(String(1), nullable=False)
    cyxb: Mapped[str] = mapped_column(String(1), nullable=False)
    yhzgx: Mapped[str] = mapped_column(String(2), nullable=False)
    cybz: Mapped[str | None] = mapped_column(String(1), nullable=True)
    sfgyr: Mapped[str | None] = mapped_column(String(1), nullable=True)
    cybzsm: Mapped[str | None] = mapped_column(String(254), nullable=True)
