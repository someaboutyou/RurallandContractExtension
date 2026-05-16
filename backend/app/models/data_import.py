from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin, TimestampMixin


class DataImportBatch(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "data_import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    import_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    import_name: Mapped[str] = mapped_column(String(120), nullable=False)
    import_type: Mapped[str] = mapped_column(String(32), nullable=False, default="initial_build")
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="csv")
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_org: Mapped[str | None] = mapped_column(String(120), nullable=True)
    region_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    linked_survey_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mapping_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    imported_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imported_by_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataImportFile(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "data_import_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    import_batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataImportRow(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "data_import_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    import_batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    import_file_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False, default="insert")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    target_table: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    normalized_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    warning_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataImportOperation(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "data_import_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    import_batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    import_file_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    chunk_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    table_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    primary_key: Mapped[dict] = mapped_column(JSON, nullable=False)
    operation_type: Mapped[str] = mapped_column(String(16), nullable=False)
    before_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
