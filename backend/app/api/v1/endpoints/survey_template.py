"""空白 Word 模板下载（2026-11-06 统一设计）。

原设计是从 CS 版 Template 目录原样分发 `.xlt` / `.dot` 二进制模板；统一为
HTML 母版后，本页面改为**下载由 HTML 母版渲染出的空白 Word**（空白上下文 →
`html_docx.build_docx`），版式与原 .dot 一致：

- 发包方 / 承包方 / 承包地块调查表：复用 `cadastral_survey.html` 母版，
  用 issuer_only / contractor_only / parcel_only 切出对应页；
- 声明书 / 测绘申请书：对应各自的 HTML 母版（无数据变量，渲染即空白文书）。
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import require_permission
from app.models.user import User
from app.schemas.response import ApiResponse
from app.schemas.survey_template import SurveyTemplateRead
from app.services.contract_template_admin_service import contract_template_admin_service

router = APIRouter()

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

#: key -> 空白 Word 定义。filename 与原 .dot 的文件名口径一致（扩展名 .docx）；
#: template_key 指向打印模板母版条目（调查表三张表的切页 flags 收在 registry 条目里）。
_BLANK_DEFINITIONS: list[dict] = [
    {
        "key": "issuer-survey",
        "label": "发包方调查表",
        "category": "调查表",
        "template_key": "issuer-survey",
        "filename": "农村土地承包经营权发包方调查表.docx",
        "description": "发包方基本信息、负责人信息与调查审核情况（空白表，打印后填写）。",
    },
    {
        "key": "contractor-survey",
        "label": "承包方调查表",
        "category": "调查表",
        "template_key": "contractor-survey",
        "filename": "农村土地承包经营权承包方调查表.docx",
        "description": "承包方及家庭成员信息、调查审核情况，一户一表（空白表）。",
    },
    {
        "key": "parcel-survey",
        "label": "承包地块调查表",
        "category": "调查表",
        "template_key": "parcel-survey",
        "filename": "农村土地承包经营权承包地块调查表.docx",
        "description": "地块名称、编码、面积、四至及调查审核信息，一地块一表（空白表）。",
    },
    {
        "key": "village-publicity",
        "label": "村组公示签字表",
        "category": "公示签字表",
        "template_key": "village-publicity",
        "filename": "村组公示签字表.docx",
        "description": "村组（发包方）基本情况公示表：发包方信息、调查记事与审核意见（空白表，打印后填写）。",
    },
    {
        "key": "householder-declaration",
        "label": "户主代表声明书",
        "category": "声明与申请",
        "template_key": "householder-declaration",
        "filename": "户主代表声明书.docx",
        "description": "户主（代表）对承包经营权调查结果的声明书。",
    },
    {
        "key": "proxy-declaration",
        "label": "委托代理声明书",
        "category": "声明与申请",
        "template_key": "proxy-declaration",
        "filename": "委托代理声明书.docx",
        "description": "委托他人代理办理承包经营权相关事项的声明书。",
    },
    {
        "key": "no-objection-declaration",
        "label": "公示无异议声明书",
        "category": "声明与申请",
        "template_key": "no-objection-declaration",
        "filename": "公示无异议声明书.docx",
        "description": "公示期满无异议的声明书。",
    },
    {
        "key": "survey-application",
        "label": "测绘申请书",
        "category": "声明与申请",
        "template_key": "survey-application",
        "filename": "测绘申请书.docx",
        "description": "承包地块测绘申请文书。",
    },
]


@router.get("", response_model=ApiResponse[list[SurveyTemplateRead]])
def list_survey_templates(
    _: User = Depends(require_permission("contractors.view")),
):
    """空白 Word 模板清单。"""
    registry = contract_template_admin_service.template_registry
    items = []
    for item in _BLANK_DEFINITIONS:
        meta = registry.get(item["template_key"])
        available = bool(
            meta
            and (contract_template_admin_service.template_dir / meta["filename"]).is_file()
        )
        items.append(
            SurveyTemplateRead(
                key=item["key"],
                label=item["label"],
                category=item["category"],
                format="Word",
                filename=item["filename"],
                description=item["description"],
                size=0,
                available=available,
            )
        )
    return {"data": items}


@router.get("/{template_key}")
def download_blank_survey_template(
    template_key: str,
    _: User = Depends(require_permission("contractors.view")),
):
    """按 key 下载空白 Word 模板（HTML 母版 → 空白渲染 → .docx）。"""
    item = next(
        (entry for entry in _BLANK_DEFINITIONS if entry["key"] == template_key),
        None,
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在"
        )

    payload = contract_template_admin_service.render_blank_word(
        item["template_key"], item.get("extra")
    )
    return Response(
        content=payload,
        media_type=DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(item['filename'])}"
        },
    )
