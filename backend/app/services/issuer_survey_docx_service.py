"""发包方调查表 Word 导出：HTML 母版 → docx。

复用 `cadastral_survey.html` 中已复刻的《发包方调查表》版式（含封面/发包方/
承包方/地块页面的同一套样式），只渲染发包方那一页。
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.services import html_docx
from app.services.contract_template_service import contract_template_service

logger = logging.getLogger(__name__)

_FILENAME_UNSAFE = str.maketrans({char: "_" for char in '\\/:*?"<>|'})
DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


class IssuerSurveyDocxService:
    """按发包方渲染《发包方调查表》Word 文档。"""

    def render(
        self,
        db: Session,
        *,
        fbfbm: str,
        batch_id: int | None = None,
    ) -> tuple[bytes, str]:
        html, issuer = contract_template_service.build_issuer_survey_html(
            db, fbfbm=fbfbm, batch_id=batch_id
        )
        payload = html_docx.build_docx(html)
        stem = f"{(issuer.get('code') or fbfbm).strip()}{(issuer.get('name') or '').strip()}发包方调查表"
        return payload, f"{stem.translate(_FILENAME_UNSAFE)}.docx"


issuer_survey_docx_service = IssuerSurveyDocxService()
