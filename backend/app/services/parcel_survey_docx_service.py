"""承包地块调查表 Word 导出：HTML 母版 → docx。

复用 `cadastral_survey.html` 中已按 CS 版（承包地块调查表.dot）复刻的
「承包地块调查表」版式，只渲染选中的地块页，不输出封面/发包方/承包方/
界址点坐标成果表。
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


class ParcelSurveyDocxService:
    """按地块渲染《承包地块调查表》Word 文档。"""

    def render(
        self,
        db: Session,
        *,
        cbfbm: str,
        dkbm: str,
        batch_id: int | None = None,
    ) -> tuple[bytes, str]:
        html, packet = contract_template_service.build_parcel_survey_html(
            db, cbfbm=cbfbm, dkbms=[dkbm], batch_id=batch_id
        )
        parcels = packet.get("parcels") or []
        if not parcels:
            raise ValueError(f"未找到承包地块：{cbfbm} / {dkbm}")

        contractor = packet.get("contractor") or {}
        contractor_name = (contractor.get("name") or "").strip()
        payload = html_docx.build_docx(html)
        stem = f"{(cbfbm or '').strip()}{contractor_name}{dkbm}承包地块调查表"
        return payload, f"{stem.translate(_FILENAME_UNSAFE)}.docx"


parcel_survey_docx_service = ParcelSurveyDocxService()
