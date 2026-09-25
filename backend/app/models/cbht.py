from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


# 合同状态 / 来源取值
CONTRACT_STATUS_ACTIVE = "active"
CONTRACT_STATUS_HISTORY = "history"
CONTRACT_SOURCE_IMPORTED = "imported"
CONTRACT_SOURCE_GENERATED = "generated"


class Cbht(TenantScopedMixin, Base):
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
    # 延包业务扩展：一条承包方可以有多个版本的合同（上次承包合同 + 延包后新合同），
    # 只有 contract_status='active' 的那条是现行合同，其余为历史合同（仍可查看/打印）。
    contract_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CONTRACT_STATUS_ACTIVE, server_default=CONTRACT_STATUS_ACTIVE
    )
    contract_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CONTRACT_SOURCE_IMPORTED, server_default=CONTRACT_SOURCE_IMPORTED
    )
    survey_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contractor_uid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
