from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MapLayer(Base, TimestampMixin):
    __tablename__ = "map_layers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    layer_type: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    service_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_url: Mapped[str] = mapped_column(Text, nullable=False)
    projection: Mapped[str | None] = mapped_column(String(32), nullable=True)
    default_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
