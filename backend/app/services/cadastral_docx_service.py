"""地籍调查表 Word 导出：**由 HTML 打印模板生成**。

2026-09-20 用户定调：``app/templates/cadastral_survey.html`` 是唯一母版，所有出件
以它为准、所见即所得；甲方给的 ``cadastral_survey.docx`` 原件只作为制作 HTML 模板
时的版式依据，程序里**不再读它**（旧实现的「灌 docx 模板」代码已删除）。

链路很短：``contract_template_service.build_cadastral_html`` 渲染出一户的 HTML，
``html_docx.build_docx`` 按 CSS 把它转写成 .docx（页面尺寸 / 分节纸张方向 / 列宽 /
行高 / 合并单元格 / 字体字号全部照搬打印模板）。模板改版式，Word 自动跟着变。

工具模块 ``docx_template``（lxml 直改 ``word/document.xml`` 的那套）保留备用，
但地籍调查表这条链路已不再依赖它。
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.services import html_docx
from app.services.contract_template_service import contract_template_service

logger = logging.getLogger(__name__)

_FILENAME_UNSAFE = str.maketrans({char: "_" for char in '\\/:*?"<>|'})


class CadastralDocxService:
    """按户渲染《地籍调查表》Word 文档（HTML 模板 → docx）。"""

    def output_filename(self, cbfbm: str, cbfmc: str | None) -> str:
        """甲方要求的输出文件名：``CBFBM+CBFMC+地籍调查表``。"""
        stem = f"{(cbfbm or '').strip()}{(cbfmc or '').strip()}地籍调查表"
        return f"{stem.translate(_FILENAME_UNSAFE)}.docx"

    def render_contractor(
        self, db: Session, *, cbfbm: str, batch_id: int | None = None
    ) -> tuple[bytes, str]:
        """渲染一户，返回 ``(docx 字节, 建议文件名)``。"""
        html, packet = contract_template_service.build_cadastral_html(
            db, cbfbm=cbfbm, batch_id=batch_id
        )
        payload = html_docx.build_docx(html)
        filename = self.output_filename(cbfbm, packet["contractor"].get("name"))
        return payload, filename


cadastral_docx_service = CadastralDocxService()
