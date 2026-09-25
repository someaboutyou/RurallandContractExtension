"""最小 docx 模板填充器：定位单元格写值、勾选串替换、区块克隆。

为什么不用 python-docx：项目运行时（``runtime/windows/python``）不带该库，
而甲方模板的版式（列宽、单元格合并、横竖分节）**必须原样保留**。因此这里
不重建版式，只做三件事：

1. 把值写进已有单元格（保留原字体、段落与单元格属性）；
2. 按字典选项重写"☑/□"勾选串；
3. 克隆一段 body 元素（多地块时复用"承包地块调查表 + 界址点坐标成果表"）。

依赖只有标准库 ``zipfile`` 与 ``lxml``（运行时已具备）。
"""

from __future__ import annotations

import copy
import io
import re
import zipfile
from pathlib import Path

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
DOCUMENT_PART = "word/document.xml"

#: 模板里表示"未勾选"的字符。甲方原件混用了「口」（汉字）、「□」（U+25A1）、
#: 「£」（Wingdings 2 的空框）、「ロ」（日文片假名）以及「☑」，回写时一律归一化。
UNCHECKED_CHARS = "口□£ロ○"
CHECKED_CHARS = "☑☒√"

#: 勾选态用的字符。**不能用 U+2611「☑」**：宋体（SimSun）没有这个字形，
#: Word 会回退到别的字体渲染，与宋体的「□」大小/粗细都不一样 —— 这正是
#: 打印件"框有大有小"的原因（实测 SimSun/SimHei/KaiTi/FangSong 的 cmap 均无 U+2611，
#: 全机只有 Segoe UI Symbol 有）。改用宋体自带的几何图形区字符，两者同字体同字号，
#: 大小完全一致。
#:
#: ⚠️ 2026-09-20 起**出件主线已换成「☑」，本模块不是那套**：主线走 HTML 模板
#: （`templates/cadastral_survey.html`）→ `html_docx.build_docx`，那里用
#: ``<span class="box">`` 把 ☑ 与 □ **一起**指定为 MS Gothic，两者同字体，一样不会
#: "框有大有小"（甲方原件里的 ☑ 本来就是 MS Gothic）。本模块是直改甲方 docx 的
#: 备用路径、当前无人调用，为避免两处口径混淆，**这里保持 ■ 不动**；
#: 若将来要复活它，请照主线那样给勾选字符单独设 MS Gothic 字体，别只换字符。
CHECKED_CHAR = "■"      # U+25A0 实心方块（宋体有）
UNCHECKED_CHAR = "□"    # U+25A1 空心方块（宋体有）

#: 正文统一字体与字号：宋体 五号（10.5pt = 21 半磅）
BODY_FONT = "宋体"
BODY_HALF_POINTS = 21

#: 水平居中时允许的"短内容"上限；超过则保持左对齐（长句居中很难读）。
_CENTER_MAX_CN = 16
_CENTER_MAX_TOTAL = 30


def q(tag: str) -> str:
    """补上 w: 命名空间。"""
    return f"{{{W_NS}}}{tag}"


def cell_text(tc: etree._Element) -> str:
    """取单元格纯文本（跨多个 run / 段落）。"""
    return "".join(node.text or "" for node in tc.iter(q("t")))


def cell_paragraphs(tc: etree._Element) -> list[etree._Element]:
    return tc.findall(q("p"))


def set_cell_text(tc: etree._Element, text: str) -> None:
    """把单元格内容替换为 ``text``，保留原有的段落属性与字体。

    换行写成 ``<w:br/>``（段内软换行），与 HTML 模板里的 ``<br>`` 同义；
    若拆成多个段落，模板里的段前段后间距会把单元格撑高，破坏行高。
    """
    paragraphs = cell_paragraphs(tc)
    prototype = paragraphs[0] if paragraphs else None
    ppr = prototype.find(q("pPr")) if prototype is not None else None
    rpr = None
    if prototype is not None:
        for run in prototype.findall(q("r")):
            candidate = run.find(q("rPr"))
            if candidate is not None:
                rpr = candidate
                break

    for paragraph in paragraphs:
        tc.remove(paragraph)

    paragraph = etree.SubElement(tc, q("p"))
    if ppr is not None:
        paragraph.append(copy.deepcopy(ppr))
    run = etree.SubElement(paragraph, q("r"))
    if rpr is not None:
        run.append(copy.deepcopy(rpr))
    for index, line in enumerate((text or "").split("\n")):
        if index:
            etree.SubElement(run, q("br"))
        node = etree.SubElement(run, q("t"))
        node.text = line
        node.set(XML_SPACE, "preserve")


def replace_run_text(text_node_runs: list[etree._Element], text: str) -> None:
    """把一组 ``w:r`` 的文本合并改写：首个 run 承担全部文本，其余清空。"""
    if not text_node_runs:
        return
    first = True
    for run in text_node_runs:
        for node in run.findall(q("t")):
            if first:
                node.text = text
                node.set(XML_SPACE, "preserve")
                first = False
            else:
                run.remove(node)


def _find_option(raw: str, name: str, start: int) -> tuple[int, int] | None:
    """在 ``raw`` 里定位选项名，返回 ``(起, 止)``。

    模板为了排版会把词语拆开（如「种 植 业」「林 业」），直接 ``find`` 会失配、
    整格勾选就不被改写（表现为框仍是旧字体、勾选状态不跟着数据走）。
    因此先精确匹配，失败再按「字符间允许空白」的宽松模式重试。
    """
    direct = raw.find(name, start)
    if direct >= 0:
        return direct, direct + len(name)
    if len(name) < 2:
        return None
    pattern = r"[\s\u3000]*".join(re.escape(char) for char in name)
    match = re.compile(pattern).search(raw, start)
    if match is None:
        return None
    return match.start(), match.end()


def set_choice_text(
    tc: etree._Element, options: list[tuple[str, bool]], *, fallback: str | None = None
) -> None:
    """按 ``options``（选项名 + 是否勾选）重写勾选串，保留原串中的其余字符。

    只替换选项名前原有的勾选符号，不新增/移动字符，以免破坏模板排版。
    选项名在原文中找不到时跳过；一个都没匹配上且给了 ``fallback`` 时，
    整格换成 ``fallback``。
    """
    raw = cell_text(tc)
    chars = list(raw)
    cursor = 0
    matched = 0
    for name, checked in options:
        hit = _find_option(raw, name, cursor)
        if hit is None:
            continue
        found, end = hit
        matched += 1
        cursor = end
        mark = found - 1
        while mark >= 0 and raw[mark] in " \u3000":
            mark -= 1
        if mark >= 0 and (raw[mark] in UNCHECKED_CHARS or raw[mark] in CHECKED_CHARS):
            chars[mark] = CHECKED_CHAR if checked else UNCHECKED_CHAR

    if matched == 0:
        set_cell_text(tc, fallback if fallback is not None else raw)
        return
    set_cell_text(tc, "".join(chars))


def build_choice_text(options: list[tuple[str, bool]]) -> str:
    """无原串可依时，按 ``□/☑`` 直接拼一个勾选串。"""
    return "".join(f"{CHECKED_CHAR if on else UNCHECKED_CHAR}{name}" for name, on in options)


# ── 行级工具：整份表单的行高、合并、跨页表头 ────────────────────────────────


def strip_row_spacing(tr: etree._Element) -> None:
    """把一行内所有段落的段前/段后间距归零，让行高回到 ``w:trHeight`` 设定值。

    模板数据行的段落写的是 ``before=157`` / ``after=157`` **再加上**
    ``beforeLines=50`` / ``afterLines=50``。后者是「按行数」表达的段间距
    （50 = 0.5 行），且按 ECMA-376 **优先级高于** ``before``/``after`` ——
    只把 before/after 归零是无效的，每行会白白多出整整一行的高度，
    28 行就放不进一页（实测行高 26.6pt，其中约 11pt 是这个间距）。
    因此必须把 ``beforeLines``/``afterLines`` **删掉**，只留归零后的
    ``before``/``after``。
    """
    for tc in tr.findall(q("tc")):
        for paragraph in tc.findall(q("p")):
            ppr = paragraph.find(q("pPr"))
            if ppr is None:
                continue
            spacing = ppr.find(q("spacing"))
            if spacing is None:
                continue
            for attr in ("before", "after"):
                if spacing.get(q(attr)) is not None:
                    spacing.set(q(attr), "0")
            for attr in ("beforeLines", "afterLines"):
                if spacing.get(q(attr)) is not None:
                    del spacing.attrib[q(attr)]


def strip_vertical_merge(tr: etree._Element) -> None:
    """去掉一行里的纵向合并，使其成为独立的数据行。

    模板把成果表的数据区写成「相邻两行合并成一格」，即一行数据跨两个物理行。
    要让「一行 = 一个界址点」成立，就必须拆掉 vMerge；
    顺带也让 Word COM 能按 ``Table.Cell(r, c)`` 逐格访问（合并行会抛异常）。
    实测：拆与不拆**不影响分页**（200 点场景都是 18 页）。
    """
    for tc in tr.findall(q("tc")):
        tcpr = tc.find(q("tcPr"))
        if tcpr is None:
            continue
        merge = tcpr.find(q("vMerge"))
        if merge is not None:
            tcpr.remove(merge)


def mark_row_as_repeating_header(tr: etree._Element) -> None:
    """标记为跨页重复的表头行（``w:tblHeader``）。

    必须按 ``CT_TrPr`` 的元素顺序插入：``tblHeader`` 排在 ``trHeight`` 之后、
    ``tblCellSpacing`` / ``jc`` 之前。若只是 ``SubElement`` 追加到末尾，
    元素顺序违反 schema，Word 会**静默忽略**该标记（表头不会跨页重复）。
    """
    trpr = tr.find(q("trPr"))
    if trpr is None:
        trpr = etree.Element(q("trPr"))
        tr.insert(0, trpr)
    if trpr.find(q("tblHeader")) is not None:
        return
    #: 这些元素必须排在 ``tblHeader`` 之后
    after = {"tblCellSpacing", "jc", "hidden", "ins", "del", "trPrChange"}
    index = len(trpr)
    for position, child in enumerate(trpr):
        if etree.QName(child).localname in after:
            index = position
            break
    trpr.insert(index, etree.Element(q("tblHeader")))


# ── 版式规范化：统一字体字号、单元格居中、行高、分节 ────────────────────────

#: OOXML 对属性元素的**顺序**有硬性约束，顺序不对 Word 会静默忽略整段属性。
#: 下面三张表照 schema 的 sequence 排列，插入新元素时按它定位。
_RPR_ORDER = (
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike",
    "dstrike", "outline", "shadow", "emboss", "imprint", "noProof", "snapToGrid",
    "vanish", "webHidden", "color", "spacing", "w", "kern", "position", "sz",
    "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign",
    "rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath",
)
_PPR_ORDER = (
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr",
    "widowControl", "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs",
    "suppressAutoHyphens", "kinsoku", "wordWrap", "overflowPunct", "topLinePunct",
    "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd", "snapToGrid", "spacing",
    "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc",
    "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl", "divId",
    "cnfStyle", "rPr", "sectPr", "pPrChange",
)
_TCPR_ORDER = (
    "cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
    "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark",
)
_TRPR_ORDER = (
    "cnfStyle", "divId", "gridBefore", "gridAfter", "wBefore", "wAfter",
    "cantSplit", "trHeight", "tblHeader", "tblCellSpacing", "jc", "hidden",
    "ins", "del", "trPrChange",
)


def _rank(order: tuple[str, ...], element: etree._Element) -> int:
    name = etree.QName(element).localname
    return order.index(name) if name in order else len(order)


def set_ordered(parent: etree._Element, child: etree._Element, order: tuple[str, ...]) -> None:
    """把 ``child`` 按 ``order`` 规定的顺序插进 ``parent``（已存在同名的先移除）。"""
    name = etree.QName(child).localname
    for existing in parent.findall(q(name)):
        parent.remove(existing)
    rank = _rank(order, child)
    index = len(parent)
    for position, existing in enumerate(parent):
        if _rank(order, existing) > rank:
            index = position
            break
    parent.insert(index, child)


def normalize_run_font(
    run: etree._Element, *, font: str = BODY_FONT, half_points: int | None = BODY_HALF_POINTS
) -> None:
    """把 run 的字体强制为 ``font``（``half_points=None`` 时保留原字号）。"""
    rpr = run.find(q("rPr"))
    if rpr is None:
        rpr = etree.Element(q("rPr"))
        run.insert(0, rpr)

    fonts = rpr.find(q("rFonts"))
    if fonts is None:
        fonts = etree.Element(q("rFonts"))
        set_ordered(rpr, fonts, _RPR_ORDER)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(q(attr), font)
    # 原件的 ``w:hint="eastAsia"`` 会把西文也拉去用中文字形，统一字体后已无意义
    if fonts.get(q("hint")) is not None:
        del fonts.attrib[q("hint")]

    if half_points is None:
        return
    for name in ("sz", "szCs"):
        node = rpr.find(q(name))
        if node is None:
            node = etree.Element(q(name))
            set_ordered(rpr, node, _RPR_ORDER)
        node.set(q("val"), str(half_points))


def _is_long_text(text: str) -> bool:
    """长句/含中文的长串判定：这类内容水平居中反而难读，保持左对齐。"""
    compact = (text or "").strip()
    if not compact:
        return False
    cn = sum(1 for char in compact if ord(char) > 0x2E80)
    return cn > _CENTER_MAX_CN or len(compact) > _CENTER_MAX_TOTAL


def normalize_cell_layout(
    tc: etree._Element, *, font: str = BODY_FONT, half_points: int = BODY_HALF_POINTS
) -> None:
    """单元格：垂直居中 + 短内容水平居中 + 全部文字统一为宋体五号。"""
    text = cell_text(tc)
    long_text = _is_long_text(text)

    tcpr = tc.find(q("tcPr"))
    if tcpr is None:
        tcpr = etree.Element(q("tcPr"))
        tc.insert(0, tcpr)
    valign = etree.Element(q("vAlign"))
    valign.set(q("val"), "center")
    set_ordered(tcpr, valign, _TCPR_ORDER)

    for paragraph in tc.findall(q("p")):
        ppr = paragraph.find(q("pPr"))
        if ppr is None:
            ppr = etree.Element(q("pPr"))
            paragraph.insert(0, ppr)
        jc = etree.Element(q("jc"))
        jc.set(q("val"), "left" if long_text else "center")
        set_ordered(ppr, jc, _PPR_ORDER)
        for run in paragraph.findall(q("r")):
            normalize_run_font(run, font=font, half_points=half_points)


def normalize_table_layout(
    table: etree._Element, *, font: str = BODY_FONT, half_points: int = BODY_HALF_POINTS
) -> None:
    """整表套用「宋体五号 + 垂直居中 + 短内容水平居中」。"""
    for tc in table.iter(q("tc")):
        normalize_cell_layout(tc, font=font, half_points=half_points)


def set_row_height(tr: etree._Element, twips: int, *, rule: str = "atLeast") -> None:
    """设定行高（``w:trHeight``）。``rule="atLeast"`` 时内容更高则以内容为准。"""
    trpr = tr.find(q("trPr"))
    if trpr is None:
        trpr = etree.Element(q("trPr"))
        tr.insert(0, trpr)
    height = etree.Element(q("trHeight"))
    height.set(q("val"), str(int(twips)))
    height.set(q("hRule"), rule)
    set_ordered(trpr, height, _TRPR_ORDER)


def attach_section_to_paragraph(paragraph: etree._Element, sectpr: etree._Element) -> None:
    """把一份 ``w:sectPr`` 挂到段落上，使该段落成为所属节的结束标记。

    用途：模板的最后一节属性在 body 末尾（文档级 ``w:sectPr``），克隆中间区块时
    复制不到它，导致"上一张表"和"下一个区块"被并进同一节、进而不分页。
    先把文档级节属性**复制一份挂到区块末段落**，区块才自带完整的节边界。
    """
    ppr = paragraph.find(q("pPr"))
    if ppr is None:
        ppr = etree.Element(q("pPr"))
        paragraph.insert(0, ppr)
    copy_sect = copy.deepcopy(sectpr)
    type_node = copy_sect.find(q("type"))
    if type_node is None:
        type_node = etree.Element(q("type"))
        copy_sect.insert(0, type_node)
    type_node.set(q("val"), "nextPage")
    set_ordered(ppr, copy_sect, _PPR_ORDER)


def collapse_paragraph(paragraph: etree._Element) -> None:
    """把段落压成零高度（固定行距 1 磅 + 字号 1 磅）。

    用途：区块末尾那个空段落只负责承载 ``w:sectPr``（节边界），本身不该占位。
    若按正文行高占一行，前面那张撑满整页的表格会把它的位置挤到下一页 ——
    表现出来就是**每块后面多一张空白页**。
    """
    ppr = paragraph.find(q("pPr"))
    if ppr is None:
        ppr = etree.Element(q("pPr"))
        paragraph.insert(0, ppr)
    spacing = ppr.find(q("spacing"))
    if spacing is None:
        spacing = etree.Element(q("spacing"))
        set_ordered(ppr, spacing, _PPR_ORDER)
    spacing.set(q("before"), "0")
    spacing.set(q("after"), "0")
    spacing.set(q("line"), "20")
    spacing.set(q("lineRule"), "exact")

    for run in paragraph.findall(q("r")):
        rpr = run.find(q("rPr"))
        if rpr is None:
            rpr = etree.Element(q("rPr"))
            run.insert(0, rpr)
        for name in ("sz", "szCs"):
            node = rpr.find(q(name))
            if node is None:
                node = etree.Element(q(name))
                set_ordered(rpr, node, _RPR_ORDER)
            node.set(q("val"), "2")


def detach_section_from_paragraph(paragraph: etree._Element) -> None:
    """摘掉段落上的 ``w:sectPr``（该段落不再结束一个节）。"""
    ppr = paragraph.find(q("pPr"))
    if ppr is None:
        return
    for node in ppr.findall(q("sectPr")):
        ppr.remove(node)


def clear_row_text(tr: etree._Element) -> None:
    for tc in tr.findall(q("tc")):
        set_cell_text(tc, "")


def make_page_break_paragraph() -> etree._Element:
    """构造一个只含分页符的段落。"""
    paragraph = etree.Element(q("p"))
    run = etree.SubElement(paragraph, q("r"))
    br = etree.SubElement(run, q("br"))
    br.set(q("type"), "page")
    return paragraph


def prepend_page_break(paragraph: etree._Element) -> None:
    """在段落首个 run 的文本前插入分页符（不新增段落，避免多出空行）。"""
    run = paragraph.find(q("r"))
    if run is None:
        run = etree.SubElement(paragraph, q("r"))
    br = etree.Element(q("br"))
    br.set(q("type"), "page")
    run.insert(0, br)


class DocxTemplate:
    """把一个 .docx 当模板读写。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        with zipfile.ZipFile(self.path) as archive:
            self._infos = [info for info in archive.infolist() if not info.is_dir()]
            self._parts = {info.filename: archive.read(info.filename) for info in self._infos}
        if DOCUMENT_PART not in self._parts:
            raise ValueError(f"不是有效的 docx：缺少 {DOCUMENT_PART}")
        self.document = etree.fromstring(self._parts[DOCUMENT_PART])
        self.body = self.document.find(q("body"))
        if self.body is None:
            raise ValueError("document.xml 缺少 w:body")

    # ── 结构访问 ────────────────────────────────────────────────────────────
    def children(self) -> list[etree._Element]:
        return list(self.body)

    def section_properties(self) -> etree._Element:
        """body 末尾的文档级节属性（``w:sectPr``），即最后一节的页面设置。"""
        sectpr = self.body.find(q("sectPr"))
        if sectpr is None:
            raise ValueError("document.xml 缺少 body 级 w:sectPr")
        return sectpr

    def content_height_twips(self) -> int:
        """最后一节的正文区高度（页高 - 上下页边距），单位缇。"""
        sectpr = self.section_properties()
        size = sectpr.find(q("pgSz"))
        margin = sectpr.find(q("pgMar"))
        height = int(size.get(q("h")) or 0)
        top = int(margin.get(q("top")) or 0)
        bottom = int(margin.get(q("bottom")) or 0)
        return max(0, height - top - bottom)

    def element_index(self, element: etree._Element) -> int:
        return self.children().index(element)

    def tables(self) -> list[etree._Element]:
        """body 直属的表格（模板为平铺结构，无嵌套表）。"""
        return self.body.findall(q("tbl"))

    def table(self, index: int) -> etree._Element:
        return self.tables()[index]

    def rows(self, table_index: int) -> list[etree._Element]:
        return self.table(table_index).findall(q("tr"))

    def row_cells(self, table_index: int, row_index: int) -> list[etree._Element]:
        return self.rows(table_index)[row_index].findall(q("tc"))

    # ── 写值 ────────────────────────────────────────────────────────────────
    def set_cell(self, table_index: int, row_index: int, cell_index: int, text: str) -> None:
        cells = self.row_cells(table_index, row_index)
        if cell_index >= len(cells):
            raise IndexError(
                f"表格 {table_index} 第 {row_index} 行只有 {len(cells)} 个单元格，"
                f"取不到第 {cell_index} 个"
            )
        set_cell_text(cells[cell_index], text)

    def get_cell(self, table_index: int, row_index: int, cell_index: int) -> str:
        return cell_text(self.row_cells(table_index, row_index)[cell_index])

    def set_choice(
        self,
        table_index: int,
        row_index: int,
        cell_index: int,
        options: list[tuple[str, bool]],
    ) -> None:
        cells = self.row_cells(table_index, row_index)
        if cell_index >= len(cells):
            raise IndexError(
                f"表格 {table_index} 第 {row_index} 行只有 {len(cells)} 个单元格，"
                f"取不到第 {cell_index} 个"
            )
        set_choice_text(cells[cell_index], options, fallback=build_choice_text(options))

    # ── 段落文本（封面等） ───────────────────────────────────────────────────
    def set_paragraph_text(self, index: int, text: str) -> None:
        element = self.children()[index]
        runs = element.findall(q("r"))
        if runs:
            replace_run_text(runs, text)
            return
        run = etree.SubElement(element, q("r"))
        node = etree.SubElement(run, q("t"))
        node.text = text
        node.set(XML_SPACE, "preserve")

    def paragraph_text(self, index: int) -> str:
        element = self.children()[index]
        return "".join(node.text or "" for node in element.iter(q("t")))

    # ── 区块克隆 ────────────────────────────────────────────────────────────
    def clone_append(self, start: int, end: int) -> list[etree._Element]:
        """把 body[start:end+1]（含两端）整体复制并追加到文档末尾。

        正文末尾的 ``w:sectPr``（body 级节属性）必须留在最后，因此克隆块
        插到它之前。
        """
        nodes = self.children()[start : end + 1]
        if not nodes:
            raise ValueError(f"区间 [{start}, {end}] 为空，无法克隆")
        clones = [copy.deepcopy(node) for node in nodes]
        trailing_sect = self.body.find(q("sectPr"))
        for clone in clones:
            if trailing_sect is not None:
                trailing_sect.addprevious(clone)
            else:
                self.body.append(clone)
        return clones

    def remove_range(self, start: int, end: int) -> None:
        for node in self.children()[start : end + 1]:
            self.body.remove(node)

    # ── 输出 ────────────────────────────────────────────────────────────────
    def to_bytes(self) -> bytes:
        payload = etree.tostring(
            self.document, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for info in self._infos:
                data = payload if info.filename == DOCUMENT_PART else self._parts[info.filename]
                archive.writestr(info, data)
        return buffer.getvalue()
