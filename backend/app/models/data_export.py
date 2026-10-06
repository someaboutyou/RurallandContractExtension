from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin, TimestampMixin


class DataExport(TenantScopedMixin, TimestampMixin, Base):
    """数据导出记录。

    每次在「数据中心 → 数据导出」里对某个区域（县/镇/村/组）发起导出，
    都会落一条记录：包含区域信息、导出类型、生成状态、产物文件与操作人，
    供右侧「导出记录列表」展示与下载。
    """

    __tablename__ = "data_exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    export_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    region_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    region_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    export_type: Mapped[str] = mapped_column(String(32), nullable=False, default="contractor_roster")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing")
    # 生成进度（0-100）与当前阶段文案；worker_pid 记录生成进程，供 stale 清扫判活
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_message: Mapped[str | None] = mapped_column(String(200), nullable=True)
    worker_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    operator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operator_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
