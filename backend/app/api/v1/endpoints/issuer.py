from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_permission
from app.models.fbf import Fbf
from app.models.user import User
from app.schemas.issuer import (
    IssuerContractorRead,
    IssuerCreate,
    IssuerDocxExportRequest,
    IssuerMergeRequest,
    IssuerRead,
    IssuerUpdate,
)
from app.schemas.land_parcel import LandParcelItem
from app.schemas.pagination import PageResponse
from app.schemas.response import ApiResponse
from app.services.data_access_service import data_access_service
from app.services.issuer_excel_transfer import issuer_excel_transfer_service
from app.services.issuer_service import issuer_service
from app.services.land_parcel_service import land_parcel_service

router = APIRouter()


@router.get("", response_model=ApiResponse[PageResponse[IssuerRead]])
def list_issuers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None),
    region_code: str | None = Query(default=None, alias="regionCode"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.view")),
):
    return {
        "data": issuer_service.list_issuers(
            db,
            page=page,
            page_size=page_size,
            current_user=current_user,
            keyword=keyword,
            region_code=region_code,
        )
    }


@router.post("", response_model=ApiResponse[IssuerRead], status_code=status.HTTP_201_CREATED)
def create_issuer(
    payload: IssuerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.manage")),
):
    return {"data": issuer_service.create_issuer(db, payload.model_dump(), current_user)}


@router.post("/merge", response_model=ApiResponse[dict])
def merge_issuers(
    payload: IssuerMergeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.manage")),
):
    """合并发包方：选中多条记录，指定一条保留，其余划转后删除。"""
    return {
        "data": issuer_service.merge_issuers(
            db, payload.keepCode, payload.mergeCodes, current_user
        )
    }


# ── 发包方调查表 Excel 导入 / 导出 ──────────────────────────────────────────


@router.get("/xls")
def export_issuers_xls(
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.view")),
):
    """导出发包方清单（Excel，口径与页面查询一致）。"""
    from urllib.parse import quote

    filename, content = issuer_excel_transfer_service.export_xls(
        db, current_user, keyword=keyword
    )
    return Response(
        content=content,
        media_type="application/vnd.ms-excel",
        headers={
            "Content-Disposition": f"attachment; filename=\"issuer_survey.xls\"; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.post("/xls/preview")
async def preview_issuers_xls(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.manage")),
):
    content = await file.read()
    return {
        "data": issuer_excel_transfer_service.preview_xls(db, current_user, content)
    }


@router.post("/xls/import")
async def import_issuers_xls(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.manage")),
):
    content = await file.read()
    return {
        "data": issuer_excel_transfer_service.import_xls(db, current_user, content)
    }


# ── 发包方调查表 Word 导出 ──────────────────────────────────────────────────


def _ensure_issuer_exportable(db: Session, issuer_code: str, current_user: User) -> Fbf:
    issuer = db.get(Fbf, issuer_code)
    if issuer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"发包方不存在：{issuer_code}",
        )
    data_access_service.ensure_code_in_scope(
        current_user, issuer.fbfbm, detail="发包方不在当前数据权限范围内"
    )
    return issuer


@router.post("/export-docx")
def export_issuers_survey_docx(
    payload: IssuerDocxExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.view")),
):
    """按选中的发包方批量导出《发包方调查表》Word（单个 docx / 多个 zip）。"""
    import io
    import zipfile
    from urllib.parse import quote

    from app.services.issuer_survey_docx_service import (
        DOCX_MEDIA_TYPE,
        issuer_survey_docx_service,
    )

    codes: list[str] = []
    seen: set[str] = set()
    for raw_code in payload.codes:
        code = str(raw_code or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code)

    files: list[tuple[str, bytes]] = []
    for code in codes:
        _ensure_issuer_exportable(db, code, current_user)
        content, filename = issuer_survey_docx_service.render(db, fbfbm=code)
        files.append((filename, content))

    if not files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="未找到可导出的发包方调查表"
        )

    if len(files) == 1:
        filename, content = files[0]
        return Response(
            content=content,
            media_type=DOCX_MEDIA_TYPE,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
            },
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, content in files:
            archive.writestr(filename, content)
    zip_name = "发包方调查表.zip"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(zip_name)}"
        },
    )


@router.get("/{issuer_code}/survey-docx")
def export_issuer_survey_docx(
    issuer_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.view")),
):
    """导出一个发包方的《发包方调查表》Word。"""
    from urllib.parse import quote

    from app.services.issuer_survey_docx_service import (
        DOCX_MEDIA_TYPE,
        issuer_survey_docx_service,
    )

    issuer = _ensure_issuer_exportable(db, issuer_code, current_user)
    content, filename = issuer_survey_docx_service.render(db, fbfbm=issuer.fbfbm)
    return Response(
        content=content,
        media_type=DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        },
    )


@router.put("/{issuer_code}", response_model=ApiResponse[IssuerRead])
def update_issuer(
    issuer_code: str,
    payload: IssuerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.manage")),
):
    return {"data": issuer_service.update_issuer(db, issuer_code, payload.model_dump(), current_user)}


@router.get("/{issuer_code}/contractors", response_model=ApiResponse[list[IssuerContractorRead]])
def list_issuer_contractors(
    issuer_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.view")),
):
    return {"data": issuer_service.list_contractors(db, issuer_code, current_user)}


@router.get("/{issuer_code}/parcels", response_model=ApiResponse[list[LandParcelItem]])
def list_issuer_parcels(
    issuer_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.view")),
):
    return {"data": land_parcel_service.get_parcels_for_issuer(db, issuer_code, current_user)}


@router.delete("/{issuer_code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_issuer(
    issuer_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("issuers.manage")),
):
    issuer_service.delete_issuer(db, issuer_code, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
