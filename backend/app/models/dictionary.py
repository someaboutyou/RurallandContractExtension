from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DictionaryItem(Base, TimestampMixin):
    __tablename__ = "dictionary_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    dict_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    dict_name: Mapped[str] = mapped_column(String(200), nullable=False)
    item_value: Mapped[str] = mapped_column(String(100), nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    tenant_code: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
