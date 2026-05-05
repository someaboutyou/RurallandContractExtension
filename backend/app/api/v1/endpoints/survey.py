from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
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
    SurveyChangeRecordRead,
    SurveyContractorRead,
    SurveyContractorUpdate,
    SurveyGenerateRequest,
    SurveyRestructureCreate,
    SurveyTagCreate,
    SurveyTagDisable,
    SurveyTaskSkip,
    SurveyTaskRead,
)
from app.services.land_parcel_service import land_parcel_service
from app.services.survey_service import survey_service

router = APIRouter()


@router.get("/batches", response_model=ApiResponse[PageResponse[SurveyBatchRead]])
def list_survey_batches(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {"data": survey_service.list_batches(db, page, page_size, keyword)}


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
            current_user=current_user,
        )
    }


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
    return {"data": land_parcel_service.get_survey_parcels(db, batch_id, cbfbm, current_user)}


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
            page=page,
            page_size=page_size,
            current_user=current_user,
        )
    }


@router.get("/batches/{batch_id}/export-results.zip")
def export_survey_results(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    filename, content = survey_service.build_results_zip(db, batch_id, current_user)
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


@router.post("/batches/{batch_id}/finish", response_model=ApiResponse[SurveyBatchRead])
def finish_survey_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.finish_batch(db, batch_id, current_user)}
