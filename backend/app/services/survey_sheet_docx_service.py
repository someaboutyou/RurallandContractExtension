"""两张摸底表的 Word 导出：与地籍调查表同链路（HTML 模板 → ``html_docx.build_docx``）。

- ``land-change``  → 《承包方承包地变化情况摸底表》（A4 横向）
- ``member-change``→ 《承包农户家庭成员变化情况摸底表》（A3 横向，35 列宽表）
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.services import html_docx
from app.services.contract_template_service import contract_template_service

logger = logging.getLogger(__name__)

_FILENAME_UNSAFE = str.maketrans({char: "_" for char in '\\/:*?"<>|'})

#: 支持的摸底表类型 → （模板渲染方法名, 文件名后缀）
SHEET_RENDERERS = {
    "land-change": ("render_land_change_sheet", "承包方承包地变化情况摸底表"),
    "member-change": ("render_member_change_sheet", "承包农户家庭成员变化情况摸底表"),
}


class SurveySheetDocxService:
    """按户渲染摸底表 Word 文档（HTML 模板 → docx）。"""

    def output_filename(self, cbfbm: str, cbfmc: str | None, sheet: str) -> str:
        label = SHEET_RENDERERS.get(sheet, (None, "摸底表"))[1]
        stem = f"{(cbfbm or '').strip()}{(cbfmc or '').strip()}{label}"
        return f"{stem.translate(_FILENAME_UNSAFE)}.docx"

    def render_contractor(
        self, db: Session, *, cbfbm: str, sheet: str, batch_id: int | None = None,
    ) -> tuple[bytes, str]:
        """渲染一户，返回 ``(docx 字节, 建议文件名)``。"""
        if sheet not in SHEET_RENDERERS:
            raise ValueError(f"未知的摸底表类型：{sheet}")
        method_name, _ = SHEET_RENDERERS[sheet]
        html = getattr(contract_template_service, method_name)(db, cbfbm=cbfbm)
        payload = html_docx.build_docx(html)
        from app.services.survey.sheet import survey_sheet_service

        contractor = survey_sheet_service.load_contractor(db, cbfbm)
        filename = self.output_filename(
            cbfbm, (contractor.cbfmc if contractor else "") or "", sheet
        )
        return payload, filename


survey_sheet_docx_service = SurveySheetDocxService()
