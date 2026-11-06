"""调查表模板下载。

模板取自 CS 版《二轮延包数据建库系统》Template 目录，保留原始
``.xlt``（Excel 模板）/ ``.dot``（Word 模板）格式，下载后用 Office
打开会直接新建空白表格/文档。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import require_permission
from app.models.user import User
from app.schemas.response import ApiResponse
from app.schemas.survey_template import SurveyTemplateRead

router = APIRouter()

TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "templates" / "survey_forms"

# key -> 模板元数据。filename 必须是 survey_forms 目录下的真实文件名，
# 下载时按 key 精确查表，避免路径穿越。
_TEMPLATE_DEFINITIONS: list[dict[str, str]] = [
    {
        "key": "issuer-excel",
        "label": "发包方调查表",
        "format": "Excel",
        "filename": "农村土地承包经营权发包方调查表.xlt",
        "description": "发包方基本信息、负责人信息与调查审核情况，Excel 模板。",
    },
    {
        "key": "issuer-word",
        "label": "发包方调查表",
        "format": "Word",
        "filename": "农村土地承包经营权发包方调查表.dot",
        "description": "发包方调查表 Word 模板，与 CS 版打印版式一致。",
    },
    {
        "key": "contractor-excel",
        "label": "承包方调查表",
        "format": "Excel",
        "filename": "农村土地承包经营权承包方调查表.xlt",
        "description": "承包方及家庭成员信息、调查审核情况，Excel 模板。",
    },
    {
        "key": "contractor-word",
        "label": "承包方调查表",
        "format": "Word",
        "filename": "农村土地承包经营权承包方调查表.dot",
        "description": "承包方调查表 Word 模板，一户一表。",
    },
    {
        "key": "parcel-excel",
        "label": "承包地块调查表",
        "format": "Excel",
        "filename": "农村土地承包经营权承包地块调查表.xlt",
        "description": "承包地块名称、编码、面积、四至及调查审核信息，Excel 模板。",
    },
    {
        "key": "parcel-word",
        "label": "承包地块调查表",
        "format": "Word",
        "filename": "农村土地承包经营权承包地块调查表.dot",
        "description": "承包地块调查表 Word 模板，一地块一表。",
    },
    {
        "key": "householder-declaration",
        "label": "户主声明书",
        "format": "Word",
        "filename": "户主代表声明书.dot",
        "description": "户主（代表）对承包经营权调查结果的声明书。",
    },
    {
        "key": "authorization-declaration",
        "label": "委托声明书",
        "format": "Word",
        "filename": "委托代理声明书.dot",
        "description": "委托他人代理办理承包经营权相关事项的声明书。",
    },
    {
        "key": "no-objection-declaration",
        "label": "无异议声明书",
        "format": "Word",
        "filename": "公示无异议声明书.dot",
        "description": "公示期满无异议的声明书。",
    },
    {
        "key": "survey-application",
        "label": "测绘申请书",
        "format": "Word",
        "filename": "测绘申请书.dot",
        "description": "承包地块测绘申请文书。",
    },
]

_MEDIA_TYPES = {
    ".xlt": "application/vnd.ms-excel",
    ".xls": "application/vnd.ms-excel",
    ".dot": "application/msword",
    ".doc": "application/msword",
}

# 模板管理页的分组标题。
_CATEGORY = {
    "issuer-excel": "调查表",
    "issuer-word": "调查表",
    "contractor-excel": "调查表",
    "contractor-word": "调查表",
    "parcel-excel": "调查表",
    "parcel-word": "调查表",
    "householder-declaration": "声明与申请",
    "authorization-declaration": "声明与申请",
    "no-objection-declaration": "声明与申请",
    "survey-application": "声明与申请",
}


def _media_type(filename: str) -> str:
    return _MEDIA_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


def _to_read(item: dict[str, str]) -> SurveyTemplateRead:
    path = TEMPLATE_DIR / item["filename"]
    size = path.stat().st_size if path.is_file() else 0
    return SurveyTemplateRead(
        key=item["key"],
        label=item["label"],
        category=_CATEGORY.get(item["key"], "其他"),
        format=item["format"],
        filename=item["filename"],
        description=item["description"],
        size=size,
        available=size > 0,
    )


@router.get("", response_model=ApiResponse[list[SurveyTemplateRead]])
def list_survey_templates(
    _: User = Depends(require_permission("contractors.view")),
):
    """调查表模板清单（模板管理页）。"""
    return {"data": [_to_read(item) for item in _TEMPLATE_DEFINITIONS]}


@router.get("/{template_key}")
def download_survey_template(
    template_key: str,
    _: User = Depends(require_permission("contractors.view")),
):
    """按 key 下载模板文件。"""
    item = next(
        (entry for entry in _TEMPLATE_DEFINITIONS if entry["key"] == template_key),
        None,
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在"
        )

    path = TEMPLATE_DIR / item["filename"]
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="模板文件缺失"
        )

    return FileResponse(
        path=path,
        media_type=_media_type(item["filename"]),
        filename=item["filename"],
    )
