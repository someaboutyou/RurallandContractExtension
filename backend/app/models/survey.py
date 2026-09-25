from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin, TimestampMixin


class SurveyBatch(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    batch_name: Mapped[str] = mapped_column(String(120), nullable=False)
    region_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    survey_type: Mapped[str] = mapped_column(String(32), nullable=False, default="household_survey")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

class SurveyCbfBase(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_cbf_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    contractor_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_cbfbm: Mapped[str] = mapped_column(String(18), nullable=False, index=True)
    cbfbm: Mapped[str] = mapped_column(String(18), nullable=False)
    cbflx: Mapped[str] = mapped_column(String(1), nullable=False)
    cbfmc: Mapped[str] = mapped_column(String(50), nullable=False)
    cbfzjlx: Mapped[str] = mapped_column(String(1), nullable=False)
    cbfzjhm: Mapped[str] = mapped_column(String(20), nullable=False)
    cbfdz: Mapped[str] = mapped_column(String(100), nullable=False)
    yzbm: Mapped[str] = mapped_column(String(6), nullable=False)
    lxdh: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cbfcysl: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cbfdcrq: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cbfdcy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cbfdcjs: Mapped[str | None] = mapped_column(String(254), nullable=True)
    gsjs: Mapped[str | None] = mapped_column(String(254), nullable=True)
    gsjsr: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gsshrq: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    gsshr: Mapped[str | None] = mapped_column(String(50), nullable=True)
    group_region_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    group_region_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initialized_from_table: Mapped[str] = mapped_column(String(64), nullable=False, default="cbf")
    initialized_from_key: Mapped[str] = mapped_column(String(120), nullable=False)
    initialized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    task_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    has_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    change_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assigned_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_to_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    investigated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyCbfResult(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_cbf_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    contractor_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    cbfbm: Mapped[str] = mapped_column(String(18), nullable=False, index=True)
    cbflx: Mapped[str] = mapped_column(String(1), nullable=False)
    cbfmc: Mapped[str] = mapped_column(String(50), nullable=False)
    cbfzjlx: Mapped[str] = mapped_column(String(1), nullable=False)
    cbfzjhm: Mapped[str] = mapped_column(String(20), nullable=False)
    cbfdz: Mapped[str] = mapped_column(String(100), nullable=False)
    yzbm: Mapped[str] = mapped_column(String(6), nullable=False)
    lxdh: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cbfcysl: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cbfdcrq: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cbfdcy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cbfdcjs: Mapped[str | None] = mapped_column(String(254), nullable=True)
    gsjs: Mapped[str | None] = mapped_column(String(254), nullable=True)
    gsjsr: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gsshrq: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    gsshr: Mapped[str | None] = mapped_column(String(50), nullable=True)
    group_region_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    group_region_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    survey_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_surveyed")
    result_status: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    is_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_basis_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    investigator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    investigator_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    investigated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_request_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    generated_request_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_request_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initialized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyCbfJtcyBase(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_cbf_jtcy_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    contractor_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    member_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    base_contractor_code: Mapped[str] = mapped_column(String(18), nullable=False)
    base_member_id_no: Mapped[str] = mapped_column(String(20), nullable=False)
    cbfbm: Mapped[str] = mapped_column(String(18), nullable=False)
    cyxm: Mapped[str] = mapped_column(String(50), nullable=False)
    cyzjlx: Mapped[str] = mapped_column(String(1), nullable=False)
    cyzjhm: Mapped[str] = mapped_column(String(20), nullable=False)
    cyxb: Mapped[str] = mapped_column(String(1), nullable=False)
    yhzgx: Mapped[str] = mapped_column(String(2), nullable=False)
    cybz: Mapped[str | None] = mapped_column(String(1), nullable=True)
    sfgyr: Mapped[str | None] = mapped_column(String(1), nullable=True)
    cybzsm: Mapped[str | None] = mapped_column(String(254), nullable=True)
    source_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initialized_from_table: Mapped[str] = mapped_column(String(64), nullable=False, default="cbf_jtcy")
    initialized_from_key: Mapped[str] = mapped_column(String(120), nullable=False)
    initialized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    task_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    has_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    change_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assigned_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_to_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyCbfJtcyResult(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_cbf_jtcy_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    contractor_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    member_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    cbfbm: Mapped[str] = mapped_column(String(18), nullable=False, index=True)
    cyxm: Mapped[str] = mapped_column(String(50), nullable=False)
    cyzjlx: Mapped[str] = mapped_column(String(1), nullable=False)
    cyzjhm: Mapped[str] = mapped_column(String(20), nullable=False)
    cyxb: Mapped[str] = mapped_column(String(1), nullable=False)
    yhzgx: Mapped[str] = mapped_column(String(2), nullable=False)
    cybz: Mapped[str | None] = mapped_column(String(1), nullable=True)
    sfgyr: Mapped[str | None] = mapped_column(String(1), nullable=True)
    cybzsm: Mapped[str | None] = mapped_column(String(254), nullable=True)
    member_result_status: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    survey_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_surveyed")
    is_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_household_head: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_urban_settled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    urban_settled_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    urban_settled_place: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_married_out_woman: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    married_out_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    married_out_place: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_deceased: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deceased_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_five_guarantees: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_residence_address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    household_register_address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_basis_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rights_disposition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initialized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    investigator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    investigator_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    investigated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyFbfBase(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_fbf_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    issuer_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_fbfbm: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    fbfbm: Mapped[str] = mapped_column(String(14), nullable=False)
    fbfmc: Mapped[str] = mapped_column(String(50), nullable=False)
    fbffzrxm: Mapped[str] = mapped_column(String(50), nullable=False)
    fzrzjlx: Mapped[str] = mapped_column(String(1), nullable=False)
    fzrzjhm: Mapped[str] = mapped_column(String(30), nullable=False)
    lxdh: Mapped[str | None] = mapped_column(String(15), nullable=True)
    fbfdz: Mapped[str] = mapped_column(String(100), nullable=False)
    yzbm: Mapped[str] = mapped_column(String(6), nullable=False)
    fbfdcy: Mapped[str] = mapped_column(String(254), nullable=False)
    fbfdcrq: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fbfdcjs: Mapped[str | None] = mapped_column(String(254), nullable=True)
    source_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initialized_from_table: Mapped[str] = mapped_column(String(64), nullable=False, default="fbf")
    initialized_from_key: Mapped[str] = mapped_column(String(120), nullable=False)
    initialized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    task_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    has_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    change_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assigned_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_to_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyFbfResult(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_fbf_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    issuer_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    fbfbm: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    fbfmc: Mapped[str] = mapped_column(String(50), nullable=False)
    fbffzrxm: Mapped[str] = mapped_column(String(50), nullable=False)
    fzrzjlx: Mapped[str] = mapped_column(String(1), nullable=False)
    fzrzjhm: Mapped[str] = mapped_column(String(30), nullable=False)
    lxdh: Mapped[str | None] = mapped_column(String(15), nullable=True)
    fbfdz: Mapped[str] = mapped_column(String(100), nullable=False)
    yzbm: Mapped[str] = mapped_column(String(6), nullable=False)
    fbfdcy: Mapped[str] = mapped_column(String(254), nullable=False)
    fbfdcrq: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fbfdcjs: Mapped[str | None] = mapped_column(String(254), nullable=True)
    survey_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_surveyed")
    result_status: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    is_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initialized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyCbdkxxBase(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_cbdkxx_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    parcel_info_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_dkbm: Mapped[str] = mapped_column(String(19), nullable=False, index=True)
    dkbm: Mapped[str] = mapped_column(String(19), nullable=False, index=True)
    fbfbm: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    cbfbm: Mapped[str] = mapped_column(String(18), nullable=False, index=True)
    cbjyqqdfs: Mapped[str] = mapped_column(String(3), nullable=False)
    htmj: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    cbhtbm: Mapped[str] = mapped_column(String(19), nullable=False)
    lzhtbm: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cbjyqzbm: Mapped[str] = mapped_column(String(19), nullable=False)
    yhtmj: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    htmjm: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    yhtmjm: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    sfqqqg: Mapped[str | None] = mapped_column(String(1), nullable=True)
    source_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initialized_from_table: Mapped[str] = mapped_column(String(64), nullable=False, default="cbdkxx")
    initialized_from_key: Mapped[str] = mapped_column(String(120), nullable=False)
    initialized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    task_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    has_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    change_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assigned_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_to_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyCbdkxxResult(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_cbdkxx_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    parcel_info_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    dkbm: Mapped[str] = mapped_column(String(19), nullable=False, index=True)
    fbfbm: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    cbfbm: Mapped[str] = mapped_column(String(18), nullable=False, index=True)
    cbjyqqdfs: Mapped[str] = mapped_column(String(3), nullable=False)
    htmj: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    cbhtbm: Mapped[str] = mapped_column(String(19), nullable=False)
    lzhtbm: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cbjyqzbm: Mapped[str] = mapped_column(String(19), nullable=False)
    yhtmj: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    htmjm: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    yhtmjm: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    sfqqqg: Mapped[str | None] = mapped_column(String(1), nullable=True)
    survey_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_surveyed")
    result_status: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    is_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initialized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyDkBase(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_dk_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    parcel_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_dkbm: Mapped[str] = mapped_column(String(19), nullable=False, index=True)
    bsm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ysdm: Mapped[str] = mapped_column(String(6), nullable=False)
    dkbm: Mapped[str] = mapped_column(String(19), nullable=False, index=True)
    dkmc: Mapped[str] = mapped_column(String(50), nullable=False)
    syqxz: Mapped[str | None] = mapped_column(String(2), nullable=True)
    dklb: Mapped[str] = mapped_column(String(2), nullable=False)
    tdlylx: Mapped[str | None] = mapped_column(String(3), nullable=True)
    dldj: Mapped[str] = mapped_column(String(2), nullable=False)
    tdyt: Mapped[str] = mapped_column(String(1), nullable=False)
    sfjbnt: Mapped[str] = mapped_column(String(1), nullable=False)
    scmj: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    dkdz: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dkxz: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dknz: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dkbz: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dkbzxx: Mapped[str | None] = mapped_column(String(300), nullable=True)
    zjrxm: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initialized_from_table: Mapped[str] = mapped_column(String(64), nullable=False, default="dk")
    initialized_from_key: Mapped[str] = mapped_column(String(120), nullable=False)
    initialized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    task_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    has_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    change_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assigned_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_to_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyDkResult(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_dk_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    parcel_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    bsm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ysdm: Mapped[str] = mapped_column(String(6), nullable=False)
    dkbm: Mapped[str] = mapped_column(String(19), nullable=False, index=True)
    dkmc: Mapped[str] = mapped_column(String(50), nullable=False)
    syqxz: Mapped[str | None] = mapped_column(String(2), nullable=True)
    dklb: Mapped[str] = mapped_column(String(2), nullable=False)
    tdlylx: Mapped[str | None] = mapped_column(String(3), nullable=True)
    dldj: Mapped[str] = mapped_column(String(2), nullable=False)
    tdyt: Mapped[str] = mapped_column(String(1), nullable=False)
    sfjbnt: Mapped[str] = mapped_column(String(1), nullable=False)
    scmj: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    dkdz: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dkxz: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dknz: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dkbz: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dkbzxx: Mapped[str | None] = mapped_column(String(300), nullable=True)
    zjrxm: Mapped[str | None] = mapped_column(String(100), nullable=True)
    survey_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_surveyed")
    result_status: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    is_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initialized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyChangeRecord(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_change_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    change_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    contractor_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    cbfbm: Mapped[str] = mapped_column(String(18), nullable=False, index=True)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False)
    change_level: Mapped[str] = mapped_column(String(32), nullable=False, default="household")
    change_status: Mapped[str] = mapped_column(String(32), nullable=False, default="surveyed")
    before_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_basis_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    basis_doc_no: Mapped[str | None] = mapped_column(String(120), nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    investigated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    investigator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    investigator_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_request_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    generated_request_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_request_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyChangeDiff(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_change_diffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    contractor_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    change_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    entity_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    field_label: Mapped[str] = mapped_column(String(120), nullable=False)
    before_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyHouseholdRestructure(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_household_restructures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    contractor_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    restructure_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    restructure_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_contractor_uid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source_cbfbm: Mapped[str | None] = mapped_column(String(18), nullable=True, index=True)
    source_cbfmc: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_contractor_uid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    target_cbfbm: Mapped[str | None] = mapped_column(String(18), nullable=True, index=True)
    target_cbfmc: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_cbfbm: Mapped[str | None] = mapped_column(String(18), nullable=True)
    new_cbfmc: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    rights_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_disposition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    certificate_disposition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_request_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyHouseholdRestructureMember(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_household_restructure_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    restructure_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    contractor_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    member_uid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    member_name: Mapped[str] = mapped_column(String(50), nullable=False)
    member_id_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    from_cbfbm: Mapped[str | None] = mapped_column(String(18), nullable=True)
    to_cbfbm: Mapped[str | None] = mapped_column(String(18), nullable=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False, default="move")
    rights_disposition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyHouseholdTag(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_household_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    contractor_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    cbfbm: Mapped[str] = mapped_column(String(18), nullable=False, index=True)
    tag_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tag_name: Mapped[str] = mapped_column(String(80), nullable=False)
    tag_source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    rule_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    disabled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_by_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SurveyAuthorization(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_authorizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    contractor_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    authorization_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    principal_name: Mapped[str] = mapped_column(String(50), nullable=False)
    principal_id_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_id_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    agent_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    authorized_matters: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyJzdResult(TenantScopedMixin, TimestampMixin, Base):
    """界址点成果。界址点是**独立实体**，不隶属于某个地块。

    一个界址点在库里只存一条，相邻地块共用同一个界址点时复用同一行——
    这正是"共点不重复生成"的落点。判重键是坐标 ``(x, y)``（毫米级），
    因为地块图形 ``survey_dk_result.geom`` 才是界址点位置的唯一来源。

    两个编号要分清：

    - ``jzdh``：**全库唯一**的内部编号（``JZD`` + 12 位序号），只用于库内引用
      （界址线用它指两端）与数据交换，不直接出现在调查表上。
    - 出图出表用的 ``J1``、``J2``… 是**每户内部按外环顶点顺序**临时编的序号，
      不落库——同一个界址点在相邻两户的打印件里可以是 ``J3`` 和 ``J7``。

    界址点的位置（点号、顺序号、X/Y、闭合边长）全部由图形推导，本表只存
    人工补充的属性，避免图形重算后与已维护的属性脱节。
    """

    __tablename__ = "survey_jzd_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    #: 全库唯一界址点号，如 ``JZD000000000123``
    jzdh: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    #: 北坐标（EPSG:4527 原值，米，毫米对齐）——与 y 一起构成判重键
    x: Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)
    #: 东坐标（EPSG:4527 原值，米，含 39 带前缀）
    y: Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)
    #: 界标类型码，取自字典 ``nyt2539_c12_boundary_marker_type``（C.12 界标类型
    #: 代码表）：1 钢钉 / 2 水泥桩 / 3 石灰桩 / 4 喷涂标志 / 5 木桩 / 6 塑料桩 /
    #: 7 带钢帽水泥桩 / 8 瓷标志 / 9 其他。
    #: 打印到甲方《承包地块调查表》时只映射到「木桩 / 埋石 / 无」三格，
    #: 见 ``services/survey/boundary.py`` 的 ``CADASTRAL_MARK_TYPE_COLUMNS``。
    jblx: Mapped[str | None] = mapped_column(String(2), nullable=True)
    #: 备注，打印在《界址点坐标成果表》的「备注」列
    bz: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: 首次生成该界址点的地块编码；仅用于追溯与区域归属推导，不参与判重
    source_dkbm: Mapped[str | None] = mapped_column(String(19), nullable=True, index=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyJzxResult(TenantScopedMixin, TimestampMixin, Base):
    """界址线成果。界址线是**独立实体**，由两端界址点定义，不隶属于某个地块。

    共用一条界址线的相邻地块复用同一行（"共线不重复生成"）。业务键是
    ``(tenant_code, qdjzdh, zdjzdh)``，两端界址点号在写入时按字典序**规范化**
    排序，因此 A→B 与 B→A 落到同一行；``qdjzdh``/``zdjzdh`` 只表示两端，
    不表示地块外环的走向。

    《地籍调查表》承包地块调查表按"该行界址点参与的这条线"关联：
    即在本户外环里取第 i 点与第 i+1 点，用这两点的界址点号（无序）反查本表。
    """

    __tablename__ = "survey_jzx_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    #: 一端界址点号（规范化后的较小者）
    qdjzdh: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    #: 另一端界址点号（规范化后的较大者）
    zdjzdh: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    #: 界址线类别码：1 田埂 … 9 两点连线（见 services/survey/boundary.py）
    jzxlb: Mapped[str | None] = mapped_column(String(2), nullable=True)
    #: 界址线位置码：1 内 / 2 中 / 3 外
    jzxwz: Mapped[str | None] = mapped_column(String(2), nullable=True)
    #: 界址线说明
    jzxsm: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: 首次生成该界址线的地块编码；仅用于追溯与区域归属推导，不参与判重
    source_dkbm: Mapped[str | None] = mapped_column(String(19), nullable=True, index=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class SurveyAttachment(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "survey_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    contractor_uid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    cbfbm: Mapped[str] = mapped_column(String(18), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
