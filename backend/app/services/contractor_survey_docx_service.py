"""承包方调查表 Word 导出：HTML 母版 → docx。

复用 `cadastral_survey.html` 中已复刻的《承包方调查表》版式，只渲染
承包方那一页（封面/发包方/地块页不输出）。
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


class ContractorSurveyDocxService:
    """按承包方渲染《承包方调查表》Word 文档。"""

    def render(
        self,
        db: Session,
        *,
        cbfbm: str,
        batch_id: int | None = None,
    ) -> tuple[bytes, str]:
        html, contractor = contract_template_service.build_contractor_survey_html(
            db, cbfbm=cbfbm, batch_id=batch_id
        )
        payload = html_docx.build_docx(html)
        stem = (
            f"{(contractor.get('code') or cbfbm).strip()}"
            f"{(contractor.get('name') or '').strip()}承包方调查表"
        )
        return payload, f"{stem.translate(_FILENAME_UNSAFE)}.docx"


contractor_survey_docx_service = ContractorSurveyDocxService()
