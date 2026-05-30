from pathlib import Path
from datetime import date

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select as sa_select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.cbht import Cbht
from app.models.survey import SurveyCbdkxxBase, SurveyCbdkxxResult
from app.models.user import User
from app.schemas.pagination import PageResponse
from app.schemas.response import ApiResponse
from app.schemas.land_parcel import LandParcelItem
from app.schemas.survey import (
    SurveyBatchCreate,
    SurveyBatchRead,
    SurveyAuthorizationCreate,
    SurveyAuthorizationRevoke,
    SurveyChangeDiffRead,
    SurveyChangeHeadRequest,
    SurveyChangeRecordRead,
    SurveyContractorCreate,
    SurveyContractorRead,
    SurveyContractorUpdate,
    SurveyContractRead,
    SurveyIssuerCreate,
    SurveyIssuerRead,
    SurveyIssuerRowRead,
    SurveyIssuerUpdate,
    SurveyMaintainMembersRequest,
    SurveyDeregisterRequest,
    SurveyAddParcelRequest,
    SurveyRemoveParcelRequest,
    SurveySplitParcelRequest,
    SurveySwapParcelsRequest,
    SurveySplitHouseholdRequest,
    SurveyMergeHouseholdRequest,
    SurveyGenerateRequest,
    SurveyPlotSketchMapRead,
    SurveyRestructureCreate,
    SurveyTagCreate,
    SurveyTagDisable,
    SurveyTaskSkip,
    SurveyTaskRead,
)
from app.services.contract_template_service import contract_template_service
from app.services.land_parcel_service import land_parcel_service
from app.services.survey_service import survey_service

router = APIRouter()


@router.get("/batches", response_model=ApiResponse[PageResponse[SurveyBatchRead]])
def list_survey_batches(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None),
    batch_status: str | None = Query(default=None, alias="status"),
    region_code: str | None = Query(default=None, alias="regionCode"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {"data": survey_service.list_batches(db, page, page_size, keyword, batch_status, region_code, current_user)}


@router.post("/batches", response_model=ApiResponse[SurveyBatchRead])
def create_survey_batch(
    payload: SurveyBatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.create_batch(db, payload.model_dump(), current_user)}


@router.get("/batches/{batch_id}/tasks", response_model=ApiResponse[PageResponse[SurveyTaskRead]])
def list_survey_tasks(
    batch_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None),
    task_status: str | None = Query(default=None, alias="taskStatus"),
    region_code: str | None = Query(default=None, alias="regionCode"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {
        "data": survey_service.list_tasks(
            db,
            batch_id=batch_id,
            page=page,
            page_size=page_size,
            keyword=keyword,
            task_status=task_status,
            region_code=region_code,
            current_user=current_user,
        )
    }


@router.post("/batches/{batch_id}/tasks", response_model=ApiResponse[SurveyTaskRead], status_code=status.HTTP_201_CREATED)
def create_survey_contractor(
    batch_id: int,
    payload: SurveyContractorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.create_contractor(db, batch_id, payload.model_dump(), current_user)}


@router.get("/batches/{batch_id}/issuers", response_model=ApiResponse[PageResponse[SurveyIssuerRowRead]])
def list_survey_issuers(
    batch_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    keyword: str | None = Query(default=None),
    region_code: str | None = Query(default=None, alias="regionCode"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {
        "data": survey_service.list_issuers(
            db,
            batch_id=batch_id,
            page=page,
            page_size=page_size,
            keyword=keyword,
            region_code=region_code,
            current_user=current_user,
        )
    }


@router.post("/batches/{batch_id}/issuers", response_model=ApiResponse[SurveyIssuerRowRead], status_code=status.HTTP_201_CREATED)
def create_survey_issuer(
    batch_id: int,
    payload: SurveyIssuerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.create_issuer(db, batch_id, payload.model_dump(), current_user)}


@router.get("/batches/{batch_id}/issuers/{issuer_uid}", response_model=ApiResponse[SurveyIssuerRead])
def get_survey_issuer(
    batch_id: int,
    issuer_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {"data": survey_service.get_issuer(db, batch_id, issuer_uid, current_user)}


@router.put("/batches/{batch_id}/issuers/{issuer_uid}", response_model=ApiResponse[SurveyIssuerRead])
def update_survey_issuer(
    batch_id: int,
    issuer_uid: str,
    payload: SurveyIssuerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.update_issuer(db, batch_id, issuer_uid, payload.model_dump(), current_user)}


@router.get("/batches/{batch_id}/results/{contractor_uid}", response_model=ApiResponse[SurveyContractorRead])
def get_survey_result(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {"data": survey_service.get_result(db, batch_id, contractor_uid, current_user)}


@router.get("/batches/{batch_id}/results/{contractor_uid}/parcels", response_model=ApiResponse[list[LandParcelItem]])
def get_survey_parcels(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    result = survey_service.get_result(db, batch_id, contractor_uid, current_user)
    cbfbm = result.get("code", "")
    return {"data": land_parcel_service.get_survey_parcels(db, result.get("batchId") or batch_id, cbfbm, current_user)}


@router.get("/batches/{batch_id}/results/{contractor_uid}/phase2", response_model=ApiResponse[dict])
def get_survey_phase2_context(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {"data": survey_service.get_phase2_context(db, batch_id, contractor_uid, current_user)}


@router.post("/batches/{batch_id}/results/{contractor_uid}/tags/refresh", response_model=ApiResponse[list])
def refresh_survey_tags(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {"data": survey_service.refresh_auto_tags(db, batch_id, contractor_uid, current_user)}


@router.post("/batches/{batch_id}/results/{contractor_uid}/tags", response_model=ApiResponse[dict], status_code=status.HTTP_201_CREATED)
def create_survey_tag(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyTagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.create_manual_tag(db, batch_id, contractor_uid, payload.model_dump(), current_user)}


@router.post("/tags/{tag_id}/disable", response_model=ApiResponse[dict])
def disable_survey_tag(
    tag_id: int,
    payload: SurveyTagDisable,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.disable_tag(db, tag_id, payload.disabledReason, current_user)}


@router.post("/batches/{batch_id}/results/{contractor_uid}/restructures", response_model=ApiResponse[dict], status_code=status.HTTP_201_CREATED)
def create_survey_restructure(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyRestructureCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.save_restructure(db, batch_id, contractor_uid, payload.model_dump(), current_user)}


@router.put("/restructures/{restructure_id}", response_model=ApiResponse[dict])
def update_survey_restructure(
    restructure_id: int,
    payload: SurveyRestructureCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.update_restructure(db, restructure_id, payload.model_dump(), current_user)}


@router.delete("/restructures/{restructure_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_survey_restructure(
    restructure_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    survey_service.delete_restructure(db, restructure_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/batches/{batch_id}/results/{contractor_uid}/authorizations", response_model=ApiResponse[dict], status_code=status.HTTP_201_CREATED)
def create_survey_authorization(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyAuthorizationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.save_authorization(db, batch_id, contractor_uid, payload.model_dump(), current_user)}


@router.put("/authorizations/{authorization_id}", response_model=ApiResponse[dict])
def update_survey_authorization(
    authorization_id: int,
    payload: SurveyAuthorizationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.update_authorization(db, authorization_id, payload.model_dump(), current_user)}


@router.post("/authorizations/{authorization_id}/file", response_model=ApiResponse[dict])
async def upload_survey_authorization_file(
    authorization_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": await survey_service.upload_authorization_file(db, authorization_id, file, current_user)}


@router.get("/authorizations/{authorization_id}/file")
def download_survey_authorization_file(
    authorization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    item = survey_service.get_authorization_file(db, authorization_id, current_user)
    return FileResponse(path=Path(item.storage_path), media_type=item.content_type or "application/octet-stream", filename=item.original_name or "authorization")


@router.get("/authorizations/{authorization_id}/template")
def download_survey_authorization_template(
    authorization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    filename, content = survey_service.build_authorization_template(db, authorization_id, current_user)
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/authorizations/{authorization_id}/revoke", response_model=ApiResponse[dict])
def revoke_survey_authorization(
    authorization_id: int,
    payload: SurveyAuthorizationRevoke,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.revoke_authorization(db, authorization_id, payload.revokeReason, current_user)}


@router.post("/batches/{batch_id}/results/{contractor_uid}/attachments", response_model=ApiResponse[dict], status_code=status.HTTP_201_CREATED)
async def upload_survey_attachment(
    batch_id: int,
    contractor_uid: str,
    category: str = Form(...),
    description: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": await survey_service.upload_attachment(db, batch_id, contractor_uid, category, description, file, current_user)}


@router.get("/attachments/{attachment_id}/download")
def download_survey_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    item = survey_service.get_attachment(db, attachment_id, current_user)
    return FileResponse(path=Path(item.storage_path), media_type=item.content_type or "application/octet-stream", filename=item.original_name)


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_survey_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    survey_service.delete_attachment(db, attachment_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/batches/{batch_id}/results/{contractor_uid}/generate-request", response_model=ApiResponse[dict])
def generate_request_from_survey_result(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.manage")),
):
    return {"data": survey_service.generate_request_from_result(db, batch_id, contractor_uid, payload.model_dump(), current_user)}


@router.get("/batches/{batch_id}/changes", response_model=ApiResponse[PageResponse[SurveyChangeRecordRead]])
def list_survey_changes(
    batch_id: int,
    contractor_uid: str | None = Query(default=None, alias="contractorUid"),
    region_code: str | None = Query(default=None, alias="regionCode"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {
        "data": survey_service.list_changes(
            db,
            batch_id=batch_id,
            contractor_uid=contractor_uid,
            region_code=region_code,
            page=page,
            page_size=page_size,
            current_user=current_user,
        )
    }


@router.get("/batches/{batch_id}/export-results.zip")
def export_survey_results(
    batch_id: int,
    region_code: str | None = Query(default=None, alias="regionCode"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    filename, content = survey_service.build_results_zip(db, batch_id, current_user, region_code)
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/batches/{batch_id}/results/{contractor_uid}/diffs", response_model=ApiResponse[PageResponse[SurveyChangeDiffRead]])
def list_survey_diffs(
    batch_id: int,
    contractor_uid: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {
        "data": survey_service.list_diffs(
            db,
            batch_id=batch_id,
            contractor_uid=contractor_uid,
            page=page,
            page_size=page_size,
            current_user=current_user,
        )
    }


@router.put("/batches/{batch_id}/results/{contractor_uid}", response_model=ApiResponse[SurveyContractorRead])
def update_survey_result(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyContractorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.update_result(db, batch_id, contractor_uid, payload.model_dump(), current_user)}


@router.post("/batches/{batch_id}/results/{contractor_uid}/confirm", response_model=ApiResponse[SurveyContractorRead])
def confirm_survey_result(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.confirm_result(db, batch_id, contractor_uid, current_user)}


@router.post("/batches/{batch_id}/tasks/{contractor_uid}/skip", response_model=ApiResponse[SurveyTaskRead])
def skip_survey_task(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyTaskSkip,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.skip_task(db, batch_id, contractor_uid, payload.skipReason, current_user)}


# 鈹€鈹€ 鍚堝悓淇℃伅 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def _get_cbhtbm_for_contractor(db: Session, cbfbm: str, batch_id: int) -> str | None:
    """Find a contract code for a contractor."""
    cbhtbm = db.scalar(
        sa_select(SurveyCbdkxxResult.cbhtbm)
        .where(SurveyCbdkxxResult.cbfbm == cbfbm)
        .limit(1)
    )
    if not cbhtbm:
        cbhtbm = db.scalar(
            sa_select(SurveyCbdkxxBase.cbhtbm)
            .where(SurveyCbdkxxBase.cbfbm == cbfbm)
            .limit(1)
        )
    return cbhtbm


def _get_survey_contract_summary(db: Session, cbfbm: str, cbhtbm: str, batch_id: int) -> dict:
    """Build contract preview summary from survey parcel relations."""
    relations = db.scalars(
        sa_select(SurveyCbdkxxResult).where(
            SurveyCbdkxxResult.cbfbm == cbfbm,
            SurveyCbdkxxResult.cbhtbm == cbhtbm,
        )
    ).all()
    if not relations:
        relations = db.scalars(
            sa_select(SurveyCbdkxxBase).where(
                SurveyCbdkxxBase.batch_id == batch_id,
                SurveyCbdkxxBase.cbfbm == cbfbm,
                SurveyCbdkxxBase.cbhtbm == cbhtbm,
            )
        ).all()
    total_area = sum(float(item.htmj or 0) for item in relations)
    return {
        "cbdkzs": len(relations),
        "htzmj": total_area if relations else None,
        "htzmjm": total_area / 666.67 if relations and total_area else None,
        "cbfs": relations[0].cbjyqqdfs if relations else None,
        "fbfbm": relations[0].fbfbm if relations else None,
    }


def _fmt_area_mu(value) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _parcel_area_mu(parcel: dict) -> float:
    for key in ("htmjm", "scmj_mu"):
        value = parcel.get(key)
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    value = parcel.get("htmj") or parcel.get("scmj")
    try:
        return float(value) / 666.67 if value not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _fmt_date_cn(value: date) -> str:
    return f"{value.year}年{value.month:02d}月{value.day:02d}日"


@router.get("/batches/{batch_id}/results/{contractor_uid}/contract", response_model=ApiResponse[SurveyContractRead | None])
def get_survey_contract(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    """Get contract data and rendered HTML for a survey contractor."""
    result = survey_service.get_result(db, batch_id, contractor_uid, current_user)
    cbfbm = result.get("code", "")
    data_batch_id = result.get("batchId") or batch_id
    cbhtbm = _get_cbhtbm_for_contractor(db, cbfbm, data_batch_id)
    if not cbhtbm:
        return {"data": None}

    contract = db.scalar(sa_select(Cbht).where(Cbht.cbhtbm == cbhtbm))
    survey_summary = _get_survey_contract_summary(db, cbfbm, cbhtbm, data_batch_id)
    rendered = contract_template_service.render_survey_contract(
        db, cbhtbm=cbhtbm, batch_id=data_batch_id, cbfbm=cbfbm,
    )
    return {
        "data": {
            "cbhtbm": cbhtbm,
            "ycbhtbm": contract.ycbhtbm if contract else None,
            "fbfbm": (contract.fbfbm if contract else None) or survey_summary["fbfbm"],
            "fbfmc": None,
            "cbfbm": contract.cbfbm if contract else cbfbm,
            "cbfs": (contract.cbfs if contract else None) or survey_summary["cbfs"],
            "cbqxq": str(contract.cbqxq) if contract and contract.cbqxq else None,
            "cbqxz": str(contract.cbqxz) if contract and contract.cbqxz else None,
            "htzmj": (float(contract.htzmj) if contract and contract.htzmj else None) or survey_summary["htzmj"],
            "htzmjm": (float(contract.htzmjm) if contract and contract.htzmjm else None) or survey_summary["htzmjm"],
            "cbdkzs": (contract.cbdkzs if contract else None) or survey_summary["cbdkzs"],
            "qdsj": str(contract.qdsj) if contract and contract.qdsj else None,
            "renderedHtml": rendered,
        }
    }


@router.get("/batches/{batch_id}/results/{contractor_uid}/registration-application")
def get_registration_application(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    """Render the registration application HTML for the survey result."""
    result = survey_service.get_result(db, batch_id, contractor_uid, current_user)
    cbfbm = result.get("code", "")
    data_batch_id = result.get("batchId") or batch_id
    rendered = contract_template_service.render_registration_application(
        db, batch_id=data_batch_id, cbfbm=cbfbm, contractor_uid=contractor_uid,
    )
    return {
        "data": {
            "renderedHtml": rendered,
        }
    }


@router.get("/batches/{batch_id}/results/{contractor_uid}/plot-sketch-map", response_model=ApiResponse[SurveyPlotSketchMapRead])
def get_survey_plot_sketch_map(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    """Render the contracted parcel sketch map for the survey result."""
    result = survey_service.get_result(db, batch_id, contractor_uid, current_user)
    cbfbm = result.get("code", "")
    data_batch_id = result.get("batchId") or batch_id
    parcels = land_parcel_service.get_survey_parcels(db, data_batch_id, cbfbm, current_user)
    nearby_parcels = land_parcel_service.get_nearby_survey_parcels(db, data_batch_id, cbfbm, current_user)
    today_text = _fmt_date_cn(date.today())

    sketch_plots = []
    for parcel in parcels:
        area_mu = _parcel_area_mu(parcel)
        sketch_plots.append({
            "code": (parcel.get("dkbm") or "")[14:] or parcel.get("dkbm") or "",
            "dkbm": parcel.get("dkbm") or "",
            "area": _fmt_area_mu(area_mu),
            "north": parcel.get("dkbz") or "",
            "south": parcel.get("dknz") or "",
            "west": parcel.get("dkxz") or "",
            "east": parcel.get("dkdz") or "",
            "geometry": parcel.get("geometry"),
        })

    total_area = sum(_parcel_area_mu(parcel) for parcel in parcels)
    rendered = contract_template_service.render_plot_sketch_map(
        contractor_name=result.get("name") or result.get("cbfmc") or "",
        contractor_code=cbfbm,
        total_plots=len(parcels),
        total_area=_fmt_area_mu(total_area),
        sketch_plots=sketch_plots,
        overview_plots=nearby_parcels,
        highlight_plots=sketch_plots,
        audit_date=today_text,
        map_date=today_text,
    )
    return {
        "data": {
            "cbfbm": cbfbm,
            "cbfmc": result.get("name") or result.get("cbfmc") or "",
            "plotCount": len(parcels),
            "totalArea": _fmt_area_mu(total_area),
            "renderedHtml": rendered,
        }
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/contract/print")
def print_survey_contract(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    # Return rendered HTML for printing.
    result = survey_service.get_result(db, batch_id, contractor_uid, current_user)
    cbfbm = result.get("code", "")
    data_batch_id = result.get("batchId") or batch_id
    cbhtbm = _get_cbhtbm_for_contractor(db, cbfbm, data_batch_id)
    if not cbhtbm:
        return Response(content="", media_type="text/html")
    rendered = contract_template_service.render_survey_contract(
        db, cbhtbm=cbhtbm, batch_id=data_batch_id, cbfbm=cbfbm,
    )
    return Response(content=rendered, media_type="text/html; charset=utf-8")


# 鈹€鈹€ 璋冩煡鎿嶄綔 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@router.post("/batches/{batch_id}/results/{contractor_uid}/change-head", response_model=ApiResponse[SurveyContractorRead])
def change_household_head(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyChangeHeadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    # Change household head.
    return {
        "data": survey_service.change_household_head(
            db, batch_id, contractor_uid,
            payload.newHeadMemberUid, payload.reason, current_user,
        )
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/maintain-members", response_model=ApiResponse[SurveyContractorRead])
def maintain_survey_members(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyMaintainMembersRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    # Maintain household members in bulk.
    return {
        "data": survey_service.maintain_members(
            db, batch_id, contractor_uid,
            [m.model_dump() for m in payload.membersToAdd],
            [m.model_dump() for m in payload.membersToUpdate],
            payload.membersToDelete, payload.reason, current_user,
        )
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/deregister", response_model=ApiResponse[dict])
def deregister_contractor(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyDeregisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    # Cancel a contractor result while keeping the base snapshot.
    return {
        "data": survey_service.deregister_contractor(
            db, batch_id, contractor_uid, payload.reason, current_user,
        )
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/add-parcel", response_model=ApiResponse[dict])
def add_parcel(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyAddParcelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    # Add a parcel result and relation.
    return {
        "data": survey_service.add_parcel(
            db, batch_id, contractor_uid, payload.model_dump(), current_user,
        )
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/split-parcel", response_model=ApiResponse[dict])
def split_survey_parcel(
    batch_id: int,
    contractor_uid: str,
    payload: SurveySplitParcelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    # Split a parcel result.
    return {
        "data": survey_service.split_parcel(
            db, batch_id, contractor_uid, payload.model_dump(), current_user,
        )
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/swap-parcels", response_model=ApiResponse[dict])
def swap_survey_parcels(
    batch_id: int,
    contractor_uid: str,
    payload: SurveySwapParcelsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    # Exchange parcel ownership between two contractors.
    return {
        "data": survey_service.swap_parcels(
            db, batch_id, contractor_uid, payload.model_dump(), current_user,
        )
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/remove-parcel", response_model=ApiResponse[dict])
def remove_survey_parcel(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyRemoveParcelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    # Remove a parcel from the contractor.
    return {
        "data": survey_service.remove_parcel(
            db, batch_id, contractor_uid, payload.model_dump(), current_user,
        )
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/split-household", response_model=ApiResponse[dict])
def split_household(
    batch_id: int,
    contractor_uid: str,
    payload: SurveySplitHouseholdRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    # Split one contractor into a new contractor.
    return {
        "data": survey_service.split_household(
            db, batch_id, contractor_uid, payload.model_dump(), current_user,
        )
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/merge-household", response_model=ApiResponse[dict])
def merge_household(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyMergeHouseholdRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    # Merge one contractor into another contractor.
    return {
        "data": survey_service.merge_household(
            db, batch_id, contractor_uid, payload.model_dump(), current_user,
        )
    }


@router.post("/batches/{batch_id}/finish", response_model=ApiResponse[SurveyBatchRead])
def finish_survey_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.finish_batch(db, batch_id, current_user)}
