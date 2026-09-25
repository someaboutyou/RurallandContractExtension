"""Single-row import logic for each entity type, plus geometry and recount utilities."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.data_import import DataImportBatch, DataImportFile, DataImportRow
from app.models.fbf import Fbf
from app.models.survey import (
    SurveyBatch,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyCbdkxxResult,
    SurveyDkResult,
    SurveyFbfResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service

from .helpers import (
    chunks,
    ensure_required,
    parse_decimal,
    parse_int,
    parse_datetime,
    record_operation,
    resolve_group_region,
    resolve_effective_import_region,
    resolve_import_region,
    snapshot_model,
)

logger = logging.getLogger(__name__)


def import_row(db, batch, import_file, row_record, file_type, data, current_user, now, geometry=None, context=None):
    """Dispatch to the correct entity importer and return (operation, target_id)."""
    from .core_helpers import ensure_import_survey_batch
    survey_batch = context["survey_batch"] if context and context.get("survey_batch") else ensure_import_survey_batch(db, batch, current_user, now)
    if context and context.get("gdb_result_only"):
        return import_gdb_result_row(db, batch, survey_batch, row_record, file_type, data, current_user, now, geometry, context)
    if file_type == "cbf":
        return _import_cbf_row(db, batch, survey_batch, row_record, data, current_user, now, context)
    if file_type == "fbf":
        return _import_fbf_row(db, batch, survey_batch, row_record, data, current_user, now, context)
    if file_type == "cbdkxx":
        return _import_cbdkxx_row(db, batch, survey_batch, row_record, data, current_user, now, context)
    if file_type == "dk":
        return _import_dk_row(db, batch, survey_batch, row_record, data, current_user, now, geometry, context)
    if file_type == "cbf_jtcy":
        return _import_member_row(db, batch, survey_batch, row_record, data, current_user, now, context)
    raise ValueError(f"unsupported data type: {file_type}")


def _import_cbf_row(db, batch, survey_batch, row_record, data, current_user, now, context=None):
    chunk_no = max(1, (row_record.row_no - 1) // 5000 + 1)
    required = ["cbfbm", "region_code", "cbflx", "cbfmc", "cbfzjlx", "cbfzjhm", "cbfdz", "yzbm", "cbfdcy"]
    ensure_required(data, required)
    data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="out of scope")
    declared_region_code, _region_name = resolve_import_region(db, data, current_user)
    group_region_code, group_region_name = resolve_group_region(db, data, current_user)
    region_code = resolve_effective_import_region(batch, current_user, group_region_code, data["cbfbm"], declared_region_code)
    tenant_code = data_access_service.derive_tenant_code(region_code)
    contractor_uid = str(uuid5(NAMESPACE_URL, f"survey:cbf:{data['cbfbm']}"))
    if context and "cbf_result_by_cbfbm" in context:
        result = context["cbf_result_by_cbfbm"].get(data["cbfbm"])
    else:
        result = db.scalar(select(SurveyCbfResult).where(SurveyCbfResult.cbfbm == data["cbfbm"]).order_by(SurveyCbfResult.id.desc()))
    operation = "update" if result else "insert"
    result_before = snapshot_model(result) if result else None
    if result is None:
        result = SurveyCbfResult(tenant_code=tenant_code, region_code=group_region_code or region_code, contractor_uid=contractor_uid, initialized_at=now)
        db.add(result)
    result.tenant_code = tenant_code
    result.region_code = group_region_code or region_code
    result.contractor_uid = contractor_uid
    result.cbfbm = data["cbfbm"]
    result.cbflx = data["cbflx"]
    result.cbfmc = data["cbfmc"]
    result.cbfzjlx = data["cbfzjlx"]
    result.cbfzjhm = data["cbfzjhm"]
    result.cbfdz = data["cbfdz"]
    result.yzbm = data["yzbm"]
    result.lxdh = data.get("lxdh")
    result.cbfcysl = parse_int(data.get("cbfcysl"), default=0)
    result.cbfdcrq = parse_datetime(data.get("cbfdcrq")) or datetime.now()
    result.cbfdcy = data.get("cbfdcy") or current_user.real_name
    result.cbfdcjs = data.get("cbfdcjs")
    result.gsjs = data.get("gsjs")
    result.gsjsr = data.get("gsjsr")
    result.gsshrq = parse_datetime(data.get("gsshrq"))
    result.gsshr = data.get("gsshr")
    result.group_region_code = group_region_code
    result.group_region_name = group_region_name
    result.source_import_batch_id = result.source_import_batch_id or batch.id
    result.source_import_row_id = result.source_import_row_id or row_record.id
    result.last_import_batch_id = batch.id
    result.last_import_row_id = row_record.id
    db.flush()
    record_operation(db, batch, row_record, result, operation, result_before, chunk_no)
    return operation, result.cbfbm


def _import_member_row(db, batch, survey_batch, row_record, data, current_user, now, context=None):
    chunk_no = max(1, (row_record.row_no - 1) // 5000 + 1)
    required = ["cbfbm", "cyxm", "cyzjlx", "cyzjhm", "cyxb", "yhzgx"]
    ensure_required(data, required)
    data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="out of scope")
    if context and "contractor_result_by_cbfbm" in context:
        contractor_result = context["contractor_result_by_cbfbm"].get(data["cbfbm"])
    else:
        contractor_result = db.scalar(select(SurveyCbfResult).where(SurveyCbfResult.cbfbm == data["cbfbm"]).order_by(SurveyCbfResult.id.desc()))
    if contractor_result is None:
        raise ValueError(f"contractor not found: {data['cbfbm']}")
    member_uid = str(uuid5(NAMESPACE_URL, f"survey:member:{data['cbfbm']}:{data['cyzjhm']}"))
    if context and "member_result_by_cbfbm_member" in context:
        result = context["member_result_by_cbfbm_member"].get((data["cbfbm"], data["cyzjhm"]))
    else:
        result = db.scalar(select(SurveyCbfJtcyResult).where(SurveyCbfJtcyResult.cbfbm == data["cbfbm"], SurveyCbfJtcyResult.cyzjhm == data["cyzjhm"]).order_by(SurveyCbfJtcyResult.id.desc()))
    operation = "update" if result else "insert"
    result_before = snapshot_model(result) if result else None
    if result is None:
        result = SurveyCbfJtcyResult(tenant_code=contractor_result.tenant_code, region_code=contractor_result.region_code, contractor_uid=contractor_result.contractor_uid, member_uid=member_uid, initialized_at=now)
        db.add(result)
    result.tenant_code = contractor_result.tenant_code
    result.region_code = contractor_result.region_code
    result.contractor_uid = contractor_result.contractor_uid
    result.member_uid = member_uid
    result.cbfbm = data["cbfbm"]
    result.cyxm = data["cyxm"]
    result.cyzjlx = data["cyzjlx"]
    result.cyzjhm = data["cyzjhm"]
    result.cyxb = data["cyxb"]
    result.yhzgx = data["yhzgx"]
    result.cybz = data.get("cybz")
    result.sfgyr = data.get("sfgyr")
    result.cybzsm = data.get("cybzsm")
    result.source_import_batch_id = result.source_import_batch_id or batch.id
    result.source_import_row_id = result.source_import_row_id or row_record.id
    result.last_import_batch_id = batch.id
    result.last_import_row_id = row_record.id
    db.flush()
    record_operation(db, batch, row_record, result, operation, result_before, chunk_no)
    return operation, result.cbfbm


def _import_fbf_row(db, batch, survey_batch, row_record, data, current_user, now, context=None):
    chunk_no = max(1, (row_record.row_no - 1) // 5000 + 1)
    required = ["fbfbm", "fbfmc", "fbffzrxm", "fzrzjlx", "fzrzjhm", "fbfdz", "yzbm", "fbfdcy", "fbfdcrq"]
    ensure_required(data, required)
    data_access_service.ensure_code_in_scope(current_user, data["fbfbm"], detail="out of scope")
    region_code = resolve_effective_import_region(batch, current_user, data["fbfbm"], data.get("region_code"), batch.region_code)
    tenant_code = data_access_service.derive_tenant_code(region_code)
    issuer_uid = str(uuid5(NAMESPACE_URL, f"survey:fbf:{data['fbfbm']}"))
    survey_date = parse_datetime(data.get("fbfdcrq")) or datetime.now()
    if context and "fbf_result_by_fbfbm" in context:
        result = context["fbf_result_by_fbfbm"].get(data["fbfbm"])
    else:
        result = db.scalar(select(SurveyFbfResult).where(SurveyFbfResult.fbfbm == data["fbfbm"]).order_by(SurveyFbfResult.id.desc()))
    operation = "update" if result else "insert"
    result_before = snapshot_model(result) if result else None
    if result is None:
        result = SurveyFbfResult(tenant_code=tenant_code, region_code=region_code, issuer_uid=issuer_uid, initialized_at=now)
        db.add(result)
    result.tenant_code = tenant_code
    result.region_code = region_code
    result.issuer_uid = issuer_uid
    result.fbfbm = data["fbfbm"]
    result.fbfmc = data["fbfmc"]
    result.fbffzrxm = data["fbffzrxm"]
    result.fzrzjlx = data["fzrzjlx"]
    result.fzrzjhm = data["fzrzjhm"]
    result.lxdh = data.get("lxdh")
    result.fbfdz = data["fbfdz"]
    result.yzbm = data["yzbm"]
    result.fbfdcy = data["fbfdcy"]
    result.fbfdcrq = survey_date
    result.fbfdcjs = data.get("fbfdcjs")
    result.source_import_batch_id = result.source_import_batch_id or batch.id
    result.source_import_row_id = result.source_import_row_id or row_record.id
    result.last_import_batch_id = batch.id
    result.last_import_row_id = row_record.id
    db.flush()
    record_operation(db, batch, row_record, result, operation, result_before, chunk_no)
    return operation, result.fbfbm


def _import_cbdkxx_row(db, batch, survey_batch, row_record, data, current_user, now, context=None):
    chunk_no = max(1, (row_record.row_no - 1) // 5000 + 1)
    required = ["dkbm", "fbfbm", "cbfbm", "cbjyqqdfs", "htmj", "cbhtbm", "cbjyqzbm"]
    ensure_required(data, required)
    data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="out of scope")
    region_code = resolve_effective_import_region(batch, current_user, data["cbfbm"], data.get("region_code"), batch.region_code)
    tenant_code = data_access_service.derive_tenant_code(region_code)
    parcel_info_uid = str(uuid5(NAMESPACE_URL, f"survey:cbdkxx:{data['dkbm']}:{data['cbfbm']}"))
    if context and "cbdkxx_result_by_key" in context:
        result = context["cbdkxx_result_by_key"].get((data["dkbm"], data["cbfbm"]))
    else:
        result = db.scalar(select(SurveyCbdkxxResult).where(SurveyCbdkxxResult.dkbm == data["dkbm"], SurveyCbdkxxResult.cbfbm == data["cbfbm"]).order_by(SurveyCbdkxxResult.id.desc()))
    operation = "update" if result else "insert"
    result_before = snapshot_model(result) if result else None
    if result is None:
        result = SurveyCbdkxxResult(tenant_code=tenant_code, region_code=region_code, parcel_info_uid=parcel_info_uid, initialized_at=now)
        db.add(result)
    result.tenant_code = tenant_code
    result.region_code = region_code
    result.parcel_info_uid = parcel_info_uid
    result.dkbm = data["dkbm"]
    result.fbfbm = data["fbfbm"]
    result.cbfbm = data["cbfbm"]
    result.cbjyqqdfs = data["cbjyqqdfs"]
    result.htmj = parse_decimal(data.get("htmj"), required=True)
    result.cbhtbm = data["cbhtbm"]
    result.lzhtbm = data.get("lzhtbm")
    result.cbjyqzbm = data["cbjyqzbm"]
    result.yhtmj = parse_decimal(data.get("yhtmj"))
    result.htmjm = parse_decimal(data.get("htmjm"))
    result.yhtmjm = parse_decimal(data.get("yhtmjm"))
    result.sfqqqg = data.get("sfqqqg")
    result.source_import_batch_id = result.source_import_batch_id or batch.id
    result.source_import_row_id = result.source_import_row_id or row_record.id
    result.last_import_batch_id = batch.id
    result.last_import_row_id = row_record.id
    db.flush()
    record_operation(db, batch, row_record, result, operation, result_before, chunk_no)
    return operation, f"{result.dkbm}:{result.cbfbm}"


def _import_dk_row(db, batch, survey_batch, row_record, data, current_user, now, geometry=None, context=None):
    chunk_no = max(1, (row_record.row_no - 1) // 5000 + 1)
    required = ["ysdm", "dkbm", "dkmc", "dklb", "dldj", "tdyt", "sfjbnt", "scmj"]
    ensure_required(data, required)
    data_access_service.ensure_code_in_scope(current_user, data["dkbm"], detail="out of scope")
    region_code = resolve_effective_import_region(batch, current_user, data["dkbm"], data.get("region_code"), batch.region_code)
    tenant_code = data_access_service.derive_tenant_code(region_code)
    parcel_uid = str(uuid5(NAMESPACE_URL, f"survey:dk:{data['dkbm']}"))
    if context and "dk_result_by_dkbm" in context:
        result = context["dk_result_by_dkbm"].get(data["dkbm"])
    else:
        result = db.scalar(select(SurveyDkResult).where(SurveyDkResult.dkbm == data["dkbm"]).order_by(SurveyDkResult.id.desc()))
    operation = "update" if result else "insert"
    result_before = snapshot_model(result) if result else None
    if result is None:
        result = SurveyDkResult(tenant_code=tenant_code, region_code=region_code, parcel_uid=parcel_uid, initialized_at=now)
        db.add(result)
    result.tenant_code = tenant_code
    result.region_code = region_code
    result.parcel_uid = parcel_uid
    result.bsm = parse_int(data.get("bsm"), default=0) if data.get("bsm") else None
    result.ysdm = data["ysdm"]
    result.dkbm = data["dkbm"]
    result.dkmc = data["dkmc"]
    result.syqxz = data.get("syqxz")
    result.dklb = data["dklb"]
    result.tdlylx = data.get("tdlylx")
    result.dldj = data["dldj"]
    result.tdyt = data["tdyt"]
    result.sfjbnt = data["sfjbnt"]
    result.scmj = parse_decimal(data.get("scmj"), required=True)
    result.dkdz = data.get("dkdz")
    result.dkxz = data.get("dkxz")
    result.dknz = data.get("dknz")
    result.dkbz = data.get("dkbz")
    result.dkbzxx = data.get("dkbzxx")
    result.zjrxm = data.get("zjrxm")
    result.source_import_batch_id = result.source_import_batch_id or batch.id
    result.source_import_row_id = result.source_import_row_id or row_record.id
    result.last_import_batch_id = batch.id
    result.last_import_row_id = row_record.id
    db.flush()
    if geometry and result.id:
        write_dk_geometries(db, "survey_dk_result", {result.id: geometry})
    record_operation(db, batch, row_record, result, operation, result_before, chunk_no)
    return operation, result.dkbm


def import_gdb_result_row(db, batch, survey_batch, row_record, file_type, data, current_user, now, geometry, context=None):
    chunk_no = max(1, (row_record.row_no - 1) // 5000 + 1)
    if file_type == "cbf":
        return _gdb_cbf(db, batch, row_record, data, current_user, now, chunk_no)
    if file_type == "cbf_jtcy":
        return _gdb_member(db, batch, row_record, data, current_user, now, chunk_no)
    if file_type == "fbf":
        return _gdb_fbf(db, batch, row_record, data, current_user, now, chunk_no)
    if file_type == "cbdkxx":
        return _gdb_cbdkxx(db, batch, row_record, data, current_user, now, chunk_no)
    if file_type == "dk":
        return _gdb_dk(db, batch, row_record, data, current_user, now, geometry, chunk_no)
    raise ValueError(f"unsupported data type: {file_type}")


def _gdb_cbf(db, batch, row_record, data, current_user, now, chunk_no):
    required = ["cbfbm", "region_code", "cbflx", "cbfmc", "cbfzjlx", "cbfzjhm", "cbfdz", "yzbm", "cbfdcy"]
    ensure_required(data, required)
    data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="out of scope")
    declared_region_code, _region_name = resolve_import_region(db, data, current_user)
    group_region_code, group_region_name = resolve_group_region(db, data, current_user)
    region_code = resolve_effective_import_region(batch, current_user, group_region_code, data["cbfbm"], declared_region_code)
    tenant_code = data_access_service.get_tenant_code(current_user) or data_access_service.derive_tenant_code(region_code)
    contractor_uid = str(uuid5(NAMESPACE_URL, f"survey:cbf:{data['cbfbm']}"))
    result = db.scalar(select(SurveyCbfResult).where(SurveyCbfResult.tenant_code == tenant_code, SurveyCbfResult.cbfbm == data["cbfbm"]).order_by(SurveyCbfResult.id.desc()))
    operation = "update" if result else "insert"
    before = snapshot_model(result) if result else None
    if result is None:
        result = SurveyCbfResult(tenant_code=tenant_code, region_code=group_region_code or region_code, contractor_uid=contractor_uid, initialized_at=now)
        db.add(result)
    result.tenant_code = tenant_code
    result.region_code = group_region_code or region_code
    result.contractor_uid = contractor_uid
    result.cbfbm = data["cbfbm"]
    result.cbflx = data["cbflx"]
    result.cbfmc = data["cbfmc"]
    result.cbfzjlx = data["cbfzjlx"]
    result.cbfzjhm = data["cbfzjhm"]
    result.cbfdz = data["cbfdz"]
    result.yzbm = data["yzbm"]
    result.lxdh = data.get("lxdh")
    result.cbfcysl = parse_int(data.get("cbfcysl"), default=0)
    result.cbfdcrq = parse_datetime(data.get("cbfdcrq")) or datetime.now()
    result.cbfdcy = data.get("cbfdcy") or current_user.real_name
    result.cbfdcjs = data.get("cbfdcjs")
    result.gsjs = data.get("gsjs")
    result.gsjsr = data.get("gsjsr")
    result.gsshrq = parse_datetime(data.get("gsshrq"))
    result.gsshr = data.get("gsshr")
    result.group_region_code = group_region_code
    result.group_region_name = group_region_name
    result.source_import_batch_id = result.source_import_batch_id or batch.id
    result.source_import_row_id = result.source_import_row_id or row_record.id
    result.last_import_batch_id = batch.id
    result.last_import_row_id = row_record.id
    db.flush()
    record_operation(db, batch, row_record, result, operation, before, chunk_no)
    return operation, result.cbfbm


def _gdb_member(db, batch, row_record, data, current_user, now, chunk_no):
    required = ["cbfbm", "cyxm", "cyzjlx", "cyzjhm", "cyxb", "yhzgx"]
    ensure_required(data, required)
    data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="out of scope")
    contractor = db.scalar(select(SurveyCbfResult).where(SurveyCbfResult.cbfbm == data["cbfbm"]).order_by(SurveyCbfResult.id.desc()))
    if contractor is None:
        raise ValueError(f"contractor not found: {data['cbfbm']}")
    member_uid = str(uuid5(NAMESPACE_URL, f"survey:member:{data['cbfbm']}:{data['cyzjhm']}"))
    result = db.scalar(select(SurveyCbfJtcyResult).where(SurveyCbfJtcyResult.tenant_code == contractor.tenant_code, SurveyCbfJtcyResult.cbfbm == data["cbfbm"], SurveyCbfJtcyResult.cyzjhm == data["cyzjhm"]))
    operation = "update" if result else "insert"
    before = snapshot_model(result) if result else None
    if result is None:
        result = SurveyCbfJtcyResult(tenant_code=contractor.tenant_code, region_code=contractor.region_code, contractor_uid=contractor.contractor_uid, member_uid=member_uid, initialized_at=now)
        db.add(result)
    result.tenant_code = contractor.tenant_code
    result.region_code = contractor.region_code
    result.contractor_uid = contractor.contractor_uid
    result.member_uid = member_uid
    result.cbfbm = data["cbfbm"]
    result.cyxm = data["cyxm"]
    result.cyzjlx = data["cyzjlx"]
    result.cyzjhm = data["cyzjhm"]
    result.cyxb = data["cyxb"]
    result.yhzgx = data["yhzgx"]
    result.cybz = data.get("cybz")
    result.sfgyr = data.get("sfgyr")
    result.cybzsm = data.get("cybzsm")
    result.source_import_batch_id = result.source_import_batch_id or batch.id
    result.source_import_row_id = result.source_import_row_id or row_record.id
    result.last_import_batch_id = batch.id
    result.last_import_row_id = row_record.id
    db.flush()
    record_operation(db, batch, row_record, result, operation, before, chunk_no)
    return operation, f"{result.cbfbm}:{result.cyzjhm}"


def _gdb_fbf(db, batch, row_record, data, current_user, now, chunk_no):
    required = ["fbfbm", "fbfmc", "fbffzrxm", "fzrzjlx", "fzrzjhm", "fbfdz", "yzbm", "fbfdcy", "fbfdcrq"]
    ensure_required(data, required)
    data_access_service.ensure_code_in_scope(current_user, data["fbfbm"], detail="out of scope")
    region_code = resolve_effective_import_region(batch, current_user, data["fbfbm"], data.get("region_code"), batch.region_code)
    tenant_code = data_access_service.get_tenant_code(current_user) or data_access_service.derive_tenant_code(region_code)
    issuer_uid = str(uuid5(NAMESPACE_URL, f"survey:fbf:{data['fbfbm']}"))
    result = db.scalar(select(SurveyFbfResult).where(SurveyFbfResult.tenant_code == tenant_code, SurveyFbfResult.fbfbm == data["fbfbm"]).order_by(SurveyFbfResult.id.desc()))
    operation = "update" if result else "insert"
    before = snapshot_model(result) if result else None
    if result is None:
        result = SurveyFbfResult(tenant_code=tenant_code, region_code=region_code, issuer_uid=issuer_uid, initialized_at=now)
        db.add(result)
    result.tenant_code = tenant_code
    result.region_code = region_code
    result.issuer_uid = issuer_uid
    result.fbfbm = data["fbfbm"]
    result.fbfmc = data["fbfmc"]
    result.fbffzrxm = data["fbffzrxm"]
    result.fzrzjlx = data["fzrzjlx"]
    result.fzrzjhm = data["fzrzjhm"]
    result.lxdh = data.get("lxdh")
    result.fbfdz = data["fbfdz"]
    result.yzbm = data["yzbm"]
    result.fbfdcy = data["fbfdcy"]
    result.fbfdcrq = parse_datetime(data.get("fbfdcrq")) or datetime.now()
    result.fbfdcjs = data.get("fbfdcjs")
    result.source_import_batch_id = result.source_import_batch_id or batch.id
    result.source_import_row_id = result.source_import_row_id or row_record.id
    result.last_import_batch_id = batch.id
    result.last_import_row_id = row_record.id
    db.flush()
    record_operation(db, batch, row_record, result, operation, before, chunk_no)
    legacy = db.get(Fbf, data["fbfbm"])
    legacy_before = snapshot_model(legacy) if legacy else None
    if legacy is None:
        legacy = Fbf(fbfbm=data["fbfbm"])
        db.add(legacy)
    legacy.tenant_code = tenant_code
    legacy.region_code = region_code
    legacy.fbfmc = data["fbfmc"]
    legacy.fbffzrxm = data["fbffzrxm"]
    legacy.fzrzjlx = data["fzrzjlx"]
    legacy.fzrzjhm = data["fzrzjhm"]
    legacy.lxdh = data.get("lxdh")
    legacy.fbfdz = data["fbfdz"]
    legacy.yzbm = data["yzbm"]
    legacy.fbfdcy = data["fbfdcy"]
    legacy.fbfdcrq = result.fbfdcrq
    legacy.fbfdcjs = data.get("fbfdcjs")
    db.flush()
    record_operation(db, batch, row_record, legacy, "update" if legacy_before else "insert", legacy_before, chunk_no)
    return operation, result.fbfbm


def _gdb_cbdkxx(db, batch, row_record, data, current_user, now, chunk_no):
    required = ["dkbm", "fbfbm", "cbfbm", "cbjyqqdfs", "htmj", "cbhtbm", "cbjyqzbm"]
    ensure_required(data, required)
    data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="out of scope")
    region_code = resolve_effective_import_region(batch, current_user, data["cbfbm"], data.get("region_code"), batch.region_code)
    tenant_code = data_access_service.get_tenant_code(current_user) or data_access_service.derive_tenant_code(region_code)
    parcel_info_uid = str(uuid5(NAMESPACE_URL, f"survey:cbdkxx:{data['dkbm']}:{data['cbfbm']}"))
    result = db.scalar(select(SurveyCbdkxxResult).where(SurveyCbdkxxResult.tenant_code == tenant_code, SurveyCbdkxxResult.dkbm == data["dkbm"], SurveyCbdkxxResult.cbfbm == data["cbfbm"]).order_by(SurveyCbdkxxResult.id.desc()))
    operation = "update" if result else "insert"
    before = snapshot_model(result) if result else None
    if result is None:
        result = SurveyCbdkxxResult(tenant_code=tenant_code, region_code=region_code, parcel_info_uid=parcel_info_uid, initialized_at=now)
        db.add(result)
    result.tenant_code = tenant_code
    result.region_code = region_code
    result.parcel_info_uid = parcel_info_uid
    result.dkbm = data["dkbm"]
    result.fbfbm = data["fbfbm"]
    result.cbfbm = data["cbfbm"]
    result.cbjyqqdfs = data["cbjyqqdfs"]
    result.htmj = parse_decimal(data.get("htmj"), required=True)
    result.cbhtbm = data["cbhtbm"]
    result.lzhtbm = data.get("lzhtbm")
    result.cbjyqzbm = data["cbjyqzbm"]
    result.yhtmj = parse_decimal(data.get("yhtmj"))
    result.htmjm = parse_decimal(data.get("htmjm"))
    result.yhtmjm = parse_decimal(data.get("yhtmjm"))
    result.sfqqqg = data.get("sfqqqg")
    result.source_import_batch_id = result.source_import_batch_id or batch.id
    result.source_import_row_id = result.source_import_row_id or row_record.id
    result.last_import_batch_id = batch.id
    result.last_import_row_id = row_record.id
    db.flush()
    record_operation(db, batch, row_record, result, operation, before, chunk_no)
    return operation, f"{result.dkbm}:{result.cbfbm}"


def _gdb_dk(db, batch, row_record, data, current_user, now, geometry, chunk_no):
    required = ["ysdm", "dkbm", "dkmc", "dklb", "dldj", "tdyt", "sfjbnt", "scmj"]
    ensure_required(data, required)
    data_access_service.ensure_code_in_scope(current_user, data["dkbm"], detail="out of scope")
    region_code = resolve_effective_import_region(batch, current_user, data["dkbm"], data.get("region_code"), batch.region_code)
    tenant_code = data_access_service.get_tenant_code(current_user) or data_access_service.derive_tenant_code(region_code)
    parcel_uid = str(uuid5(NAMESPACE_URL, f"survey:dk:{data['dkbm']}"))
    result = db.scalar(select(SurveyDkResult).where(SurveyDkResult.tenant_code == tenant_code, SurveyDkResult.dkbm == data["dkbm"]).order_by(SurveyDkResult.id.desc()))
    operation = "update" if result else "insert"
    before = snapshot_model(result) if result else None
    if result is None:
        result = SurveyDkResult(tenant_code=tenant_code, region_code=region_code, parcel_uid=parcel_uid, initialized_at=now)
        db.add(result)
    result.tenant_code = tenant_code
    result.region_code = region_code
    result.parcel_uid = parcel_uid
    result.bsm = parse_int(data.get("bsm"), default=0) if data.get("bsm") else None
    result.ysdm = data["ysdm"]
    result.dkbm = data["dkbm"]
    result.dkmc = data["dkmc"]
    result.syqxz = data.get("syqxz")
    result.dklb = data["dklb"]
    result.tdlylx = data.get("tdlylx")
    result.dldj = data["dldj"]
    result.tdyt = data["tdyt"]
    result.sfjbnt = data["sfjbnt"]
    result.scmj = parse_decimal(data.get("scmj"), required=True)
    result.dkdz = data.get("dkdz")
    result.dkxz = data.get("dkxz")
    result.dknz = data.get("dknz")
    result.dkbz = data.get("dkbz")
    result.dkbzxx = data.get("dkbzxx")
    result.zjrxm = data.get("zjrxm")
    result.source_import_batch_id = result.source_import_batch_id or batch.id
    result.source_import_row_id = result.source_import_row_id or row_record.id
    result.last_import_batch_id = batch.id
    result.last_import_row_id = row_record.id
    db.flush()
    write_dk_geometries(db, "survey_dk_result", {result.id: geometry})
    record_operation(db, batch, row_record, result, operation, before, chunk_no)
    return operation, result.dkbm


def write_dk_geometries(db, table_name, geometries_by_id):
    if not geometries_by_id:
        return
    stmt = text(f"""
        UPDATE {table_name}
        SET geom = CASE
            WHEN CAST(:geojson AS text) IS NULL THEN NULL
            ELSE ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4527))
        END
        WHERE id = :row_id
    """)
    for row_id, geometry in geometries_by_id.items():
        db.execute(stmt, {"row_id": row_id, "geojson": json.dumps(geometry, ensure_ascii=False) if geometry else None})


def recount_member_counts(db, contractor_codes, survey_batch_id=None):
    if not contractor_codes:
        return
    for code_chunk in chunks(list(contractor_codes), 500):
        counts = dict(db.execute(select(SurveyCbfJtcyResult.cbfbm, func.count(SurveyCbfJtcyResult.id)).where(SurveyCbfJtcyResult.cbfbm.in_(code_chunk)).group_by(SurveyCbfJtcyResult.cbfbm).execution_options(skip_tenant_scope=True)).all())
        results = db.scalars(select(SurveyCbfResult).where(SurveyCbfResult.cbfbm.in_(code_chunk)).execution_options(skip_tenant_scope=True)).all()
        for result in results:
            count = counts.get(result.cbfbm, 0)
            if result.cbfcysl != count:
                result.cbfcysl = count
    db.flush()


def recount_result_member_counts(db, contractor_codes, survey_batch_id):
    if not contractor_codes:
        return
    for code_chunk in chunks(list(contractor_codes), 5000):
        counts = dict(db.execute(select(SurveyCbfJtcyResult.cbfbm, func.count(SurveyCbfJtcyResult.id)).where(SurveyCbfJtcyResult.cbfbm.in_(code_chunk)).group_by(SurveyCbfJtcyResult.cbfbm)).all())
        contractors = db.scalars(select(SurveyCbfResult).where(SurveyCbfResult.cbfbm.in_(code_chunk)).order_by(SurveyCbfResult.cbfbm.asc(), SurveyCbfResult.id.desc())).all()
        for contractor in contractors:
            if not contractor.is_changed and contractor.survey_status == "not_surveyed":
                contractor.cbfcysl = counts.get(contractor.cbfbm, 0)
