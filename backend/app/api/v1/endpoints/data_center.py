# -*- coding: utf-8 -*-
"""数据中心端点：清单导入导出（无批次、按区域/整库）+ 全库数据质检。

与建库中心的分工：建库中心一切按批次（/surveys、/survey-contractors、
/issuers?batchId=…）；数据中心直接面对库内全量数据，作用域用区域码表达
（空 = 整库，数据权限始终生效）。
"""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.schemas.response import ApiResponse

router = APIRouter()


def _region_or_empty(region_code: str | None) -> str:
    code = (region_code or "").strip()
    return code


@router.get("/quality-checks/runs", response_model=ApiResponse[dict])
def list_data_center_quality_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    """数据中心质检历史（batch_id=0 哨兵 = 无批次整库/区域运行）。"""
    from app.services.survey import quality_check

    return {"data": quality_check.list_runs(db, 0, page, page_size)}


@router.post("/quality-checks", response_model=ApiResponse[dict])
def start_data_center_quality_check(
    payload: dict,
    current_user: User = Depends(require_permission("contractors.view")),
):
    """启动数据中心质检：regionCode 空=整库；items 为质检项开关（缺省全开）。"""
    from app.services.survey import quality_check

    region_code = _region_or_empty((payload or {}).get("regionCode"))
    if region_code:
        from app.services.data_access_service import data_access_service

        data_access_service.ensure_region_filter_in_scope(
            current_user, region_code, detail="所选区域不在当前数据权限范围内"
        )
    items = (payload or {}).get("items") or {}
    job = quality_check.start_db_quality_check_job(current_user.id, region_code, items)
    return {"data": quality_check.job_public_view(job)}


@router.get("/quality-checks/jobs/{job_id}", response_model=ApiResponse[dict])
def get_data_center_quality_check_job(
    job_id: str,
    current_user: User = Depends(require_permission("contractors.view")),
):
    from app.services.survey import quality_check

    job = quality_check.get_job(job_id)
    if job is None or job.get("userId") != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="质检任务不存在")
    return {"data": quality_check.job_public_view(job)}


@router.get("/quality-checks/runs/{run_id}/records", response_model=ApiResponse[dict])
def list_data_center_quality_records(
    run_id: str,
    severity: str | None = Query(default=None),
    check_item: str | None = Query(default=None, alias="checkItem"),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    from app.services.survey import quality_check

    return {
        "data": quality_check.list_records(
            db, 0, run_id, severity=severity, check_item=check_item,
            keyword=keyword, page=page, page_size=page_size,
        )
    }


@router.get("/quality-checks/runs/{run_id}/records/export")
def export_data_center_quality_records(
    run_id: str,
    severity: str | None = Query(default=None),
    check_item: str | None = Query(default=None, alias="checkItem"),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    """导出一次数据中心质检运行的问题明细为 Excel。"""
    from urllib.parse import quote

    from app.services.survey import quality_check

    filename, content = quality_check.build_records_export(
        db, 0, run_id, severity=severity, check_item=check_item, keyword=keyword
    )
    return _xls_response(filename, content)


# ── 承包方清单导出 / 导入 ──────────────────────────────────────────────────


@router.post("/contractor-list/export-jobs", response_model=ApiResponse[dict])
def start_contractor_list_export_job(
    payload: dict,
    current_user: User = Depends(require_permission("contractors.view")),
):
    """启动数据中心承包方清单导出任务（regionCode 空=整库；mode=single|group）。"""
    from app.services import data_center_jobs
    from app.services.data_center_transfer import data_center_transfer_service

    region_code = _region_or_empty((payload or {}).get("regionCode"))
    mode = str((payload or {}).get("mode") or "single")
    if mode not in ("single", "group"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mode 仅支持 single / group")
    job = data_center_jobs.create_job("export", current_user.id, region_code)

    def target():
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            filename, content = data_center_transfer_service.export_contractor_xls(
                db, current_user, region_code=region_code or None, mode=mode,
                progress_cb=data_center_jobs._progress_cb(job["id"]),
            )
            data_center_jobs.update_job(job["id"], status="done", phase="导出完成",
                                        done=1, total=1, filename=filename, content=content)
        finally:
            db.close()

    data_center_jobs._run_worker(job["id"], target)
    return {"data": data_center_jobs.job_public_view(job)}


@router.get("/contractor-list/export-jobs/{job_id}", response_model=ApiResponse[dict])
def get_contractor_list_export_job(
    job_id: str,
    current_user: User = Depends(require_permission("contractors.view")),
):
    from app.services import data_center_jobs

    job = data_center_jobs.get_job(job_id)
    if job is None or job["userId"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导出任务不存在")
    return {"data": data_center_jobs.job_public_view(job)}


@router.get("/contractor-list/export-jobs/{job_id}/download")
def download_contractor_list_export_job(
    job_id: str,
    current_user: User = Depends(require_permission("contractors.view")),
):
    from app.services import data_center_jobs

    job = data_center_jobs.get_job(job_id)
    if job is None or job["userId"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导出任务不存在")
    if job["status"] != "done":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务尚未完成")
    return _blob_response(job["filename"], job["content"])


@router.post("/contractor-list/preview", response_model=ApiResponse[dict])
async def preview_contractor_list_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    """校验数据中心承包方清单 Excel（只读预览，不落库）。"""
    from app.services.data_center_transfer import data_center_transfer_service

    content = await file.read()
    return {"data": data_center_transfer_service.preview_contractor_xls_import(db, current_user, content)}


@router.post("/contractor-list/import-jobs", response_model=ApiResponse[dict])
async def start_contractor_list_import_job(
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    """启动数据中心承包方清单导入任务（按承包方编号更新主表，不建新户）。"""
    from app.services import data_center_jobs
    from app.services.data_center_transfer import data_center_transfer_service

    content = await file.read()
    job = data_center_jobs.create_job("import", current_user.id, "")

    def target():
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            result = data_center_transfer_service.import_contractors_xls(
                db, current_user, content, progress_cb=data_center_jobs._progress_cb(job["id"])
            )
            data_center_jobs.update_job(job["id"], status="done", phase="导入完成",
                                        done=1, total=1,
                                        summary=result.get("summary"),
                                        results=result.get("households"),
                                        warnings=result.get("warnings"))
        finally:
            db.close()

    data_center_jobs._run_worker(job["id"], target)
    return {"data": data_center_jobs.job_public_view(job)}


@router.get("/contractor-list/import-jobs/{job_id}", response_model=ApiResponse[dict])
def get_contractor_list_import_job(
    job_id: str,
    current_user: User = Depends(require_permission("contractors.manage")),
):
    from app.services import data_center_jobs

    job = data_center_jobs.get_job(job_id)
    if job is None or job["userId"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入任务不存在")
    return {"data": data_center_jobs.job_public_view(job)}


# ── 发包方清单导出（复用 /issuers/xls 的服务层，数据中心入口）───────────────
# 导入直接复用 POST /issuers/xls/preview 与 /issuers/xls/import（本就无批次绑定）。


def _xls_response(filename: str, content: bytes):
    from urllib.parse import quote

    return _blob_response(filename, content, media_type="application/vnd.ms-excel",
                          ascii_fallback="data_center.xls", quote=quote)


def _blob_response(
    filename: str,
    content: bytes,
    *,
    media_type: str | None = None,
    ascii_fallback: str = "download.bin",
    quote=None,
):
    from fastapi import Response

    if quote is None:
        from urllib.parse import quote
    media_type = media_type or "application/octet-stream"
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"
            ),
        },
    )
