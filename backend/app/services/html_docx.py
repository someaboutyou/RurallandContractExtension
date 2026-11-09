"""把打印模板渲染出的 HTML 转写成 .docx。

**设计前提（2026-09-20 用户定调）**：打印模板 `app/templates/*.html` 是**唯一母版**，
Word 导出由它生成 —— 甲方 `.docx` 原件只用来做 HTML 的版式依据，不再被程序使用。
所以这里不做「灌模板」，而做**版式的忠实转写**，保证打印件与 Word 件所见即所得：

- 页面尺寸 / 留白 ← `.page` 元素的 `width` / `height` / `padding`（mm → twips）
- 表格列宽 ← `<colgroup><col class="xN">` 的 CSS `width`
- 行高 ← `<tr class="h-NNNN">` 的 CSS `height`
- 字号 / 字体 / 对齐 / 行距 / 边距 ← 单元格自身的 CSS 解析结果（含行内 `style`）
- `colspan` / `rowspan` → `w:gridSpan` / `w:vMerge`（含跨行续格）
- `<br>` 与 `white-space: pre-line` 里的换行 → `w:br`

因此模板改版式后 Word 会**自动跟着变**，不需要在两边各维护一套尺寸。
不依赖 python-docx：直接生成 OOXML 包（lxml 造 XML + zipfile 打包）。
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

from lxml import etree, html as lxml_html

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

TWIPS_PER_MM = 1440 / 25.4
#: 单元格 / 表格边框宽度：1px = 0.75pt，`w:sz` 以 1/8 磅为单位
BORDER_SZ = 6

#: 字体名归一：CSS 里的西文名 → Word 里的字体名（本机装的仍是宋体/黑体）
#:
#: ⚠️ ``_font_name`` 按**字体栈顺序**取第一个「已登记」的名字（两条分支各自扫一遍
#: ``names``）。没登记的名字会被整条跳过 —— 实测 ``"MS Gothic", "SimSun", serif``
#: 因为 MS Gothic 没登记，两轮都直接落到后面的 SimSun，栈首形同虚设。
#: 所以新字体**必须登记进本表（东亚字体还要进 ``CJK_FONTS``），并写在栈首**。
FONT_ALIASES = {
    "simsun": "SimSun",
    "宋体": "SimSun",
    "simhei": "SimHei",
    "黑体": "SimHei",
    "consolas": "Consolas",
    # 声明书 / 申请书类文书（2026-11-06 从 survey_forms/*.dot 移植）用的字体。
    # Word 侧的字体名就是中文名（仿宋_GB2312、方正小标宋简体），目标机缺字体时
    # Word 会自行回退，不会变豆腐块。
    "仿宋": "仿宋",
    "fangsong": "仿宋",
    "仿宋_gb2312": "仿宋_GB2312",
    "fangsong_gb2312": "仿宋_GB2312",
    "方正小标宋简体": "方正小标宋简体",
    "fzxiaobiaosong": "方正小标宋简体",
    # 勾选框字形专用：☑(U+2611)/☐(U+2610)/✓(U+2713) 在宋体、黑体里**都没有字形**
    # （解析 simsun.ttc / simhei.ttf 的 cmap 实测），只有 MS Gothic / Segoe UI Symbol 有。
    # 甲方原件里那个 ☑ 的 run 也正是写死 MS Gothic。
    "ms gothic": "MS Gothic",
    "segoe ui symbol": "Segoe UI Symbol",
}
#: 每种字体「一行所需的行高」倍率 = ``(ascent + |descent|) / unitsPerEm``。
#:
#: ⚠️ ``lineRule="exact"`` 的定义是「行框就这么高」，**塞不进的部分在行框顶部被裁掉**
#: （WPS、Word 的屏幕排版都会裁；Word 导出 PDF 时反而不裁 —— 所以只在导出的 PDF 上
#: 看，是看不出「□ 少了上横」这种问题的）。于是「固定行距 ≥ 段落里最大 run 的
#: 字号 × 本倍率」就是硬约束。
#: MS Gothic 实测 hhea 220 / -36、upem 256 → 正好 1.0em：字号 10.5pt 的方框塞进
#: ``line-height:1.15`` × 8pt = 9.2pt 的行框，顶上刚好被裁 1.3pt，方框的上横就没了。
#: 宋体/黑体 asc+desc 也约等于 1.0em，故兜底取 1.0。
FONT_LINE_FACTORS = {
    "MS Gothic": 1.0,
    "Segoe UI Symbol": 1.0,
}
DEFAULT_LINE_FACTOR = 1.0

#: 会被**继承**的文本级 CSS 属性。``StyleResolver.resolve()`` 只返回元素**自己命中**的
#: 规则，不做继承，于是 ``<td><span class="ck"><span class="box">☑</span>水田</span></td>``
#: 里的 ``.box`` 只拿到 ``font-family``、拿不到字号，直接回落成默认 10.5pt ——
#: 表现就是「Word 里的方框比浏览器里大 1.5 倍」（浏览器按 CSS 继承算出来是 7pt）。
#: 字号一大，上面那条行距约束就满足不了，方框的上横随即被裁掉。
INHERITED_TEXT_PROPERTIES = ("font-family", "font-size", "font-weight", "letter-spacing")

#: 判定「东亚字体」的白名单（`in` 成员测试，与先后顺序无关）。MS Gothic /
#: Segoe UI Symbol 必须在内，否则 ``_font_name(for_east_asia=True)`` 会跳过它们、
#: 退回栈里更靠后的 SimSun，于是 eastAsia 仍是宋体、☑ 又变成无字形。
CJK_FONTS = (
    "simsun",
    "宋体",
    "simhei",
    "黑体",
    "kaiti",
    "simkai",
    "fangsong",
    "仿宋",
    "simfang",
    "fangsong_gb2312",
    "仿宋_gb2312",
    "方正小标宋简体",
    "fzxiaobiaosong",
    "ms gothic",
    "segoe ui symbol",
)

#: 不需要输出的元素（屏幕上才有的控件）
SKIP_CLASSES = {"print-btn"}


def q(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _mm_to_twips(value: float) -> int:
    return int(round(value * TWIPS_PER_MM))


_LENGTH_RE = re.compile(r"^\s*(-?[\d.]+)\s*(mm|cm|pt|px|in|%)?\s*$")


def parse_length(text: str | None) -> tuple[float, str] | None:
    """把 CSS 长度解析成 ``(数值, 单位)``。

    无单位时**单位返回空串**（不能当 px）—— CSS 里无单位数值只有
    ``line-height`` 合法，含义是「字体大小的倍数」。
    """
    if not text:
        return None
    match = _LENGTH_RE.match(text)
    if match is None:
        return None
    return float(match.group(1)), (match.group(2) or "")


def to_mm(text: str | None) -> float | None:
    """CSS 长度 → 毫米（本模板的几何量都用 mm，其它单位兜底换算）。"""
    parsed = parse_length(text)
    if parsed is None:
        return None
    value, unit = parsed
    if unit == "mm":
        return value
    if unit == "cm":
        return value * 10
    if unit == "pt":
        return value * 25.4 / 72
    if unit == "in":
        return value * 25.4
    if unit == "" or unit == "px":
        return value * 25.4 / 96
    return None


def to_pt(text: str | None) -> float | None:
    parsed = parse_length(text)
    if parsed is None:
        return None
    value, unit = parsed
    if unit == "pt":
        return value
    millimetres = to_mm(text)
    return None if millimetres is None else millimetres * 72 / 25.4


def line_height_mm(decls: dict[str, str], default_pt: float) -> float:
    """行高 → 毫米。支持无单位倍数（``line-height: 1.6``）与百分比。"""
    raw = decls.get("line-height")
    parsed = parse_length(raw)
    if parsed is None:
        return default_pt * 1.2 * 25.4 / 72
    value, unit = parsed
    if unit == "":
        return default_pt * value * 25.4 / 72
    if unit == "%":
        return default_pt * value / 100 * 25.4 / 72
    return (to_pt(raw) or default_pt) * 25.4 / 72


# ── 极简 CSS ──────────────────────────────────────────────────────────────


@dataclass
class _Rule:
    parts: list[tuple[str | None, tuple[str, ...]]]
    decls: dict[str, str]
    order: int
    specificity: tuple[int, int] = field(default=(0, 0))


def _strip_css_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _top_level_blocks(css: str) -> list[tuple[str, str]]:
    """切出 ``(选择器, 声明体)``；``@`` 开头的块整块丢弃（本模板不需要）。"""
    blocks: list[tuple[str, str]] = []
    index, length = 0, len(css)
    while index < length:
        brace = css.find("{", index)
        if brace < 0:
            break
        prelude = css[index:brace].strip()
        depth, cursor = 1, brace + 1
        while cursor < length and depth:
            if css[cursor] == "{":
                depth += 1
            elif css[cursor] == "}":
                depth -= 1
            cursor += 1
        body = css[brace + 1 : cursor - 1]
        if prelude.startswith("@"):
            if prelude.startswith("@media"):
                blocks.extend(_top_level_blocks(body))
        else:
            blocks.append((prelude, body))
        index = cursor
    return blocks


def _parse_decls(text: str) -> dict[str, str]:
    """解析声明块，并把 ``padding`` / ``margin`` 简写展开成四个方向。"""
    out: dict[str, str] = {}
    for chunk in text.split(";"):
        name, sep, value = chunk.partition(":")
        if not sep:
            continue
        name = name.strip().lower()
        value = value.strip()
        if not name or not value:
            continue
        if name in ("padding", "margin"):
            parts = value.split()
            if len(parts) == 1:
                parts = parts * 4
            elif len(parts) == 2:
                parts = [parts[0], parts[1], parts[0], parts[1]]
            elif len(parts) == 3:
                parts = [parts[0], parts[1], parts[2], parts[1]]
            for side, item in zip(("top", "right", "bottom", "left"), parts):
                out[f"{name}-{side}"] = item
            continue
        out[name] = value
    return out


def _parse_selector(selector: str) -> tuple[list[tuple[str | None, tuple[str, ...]]], tuple[int, int]]:
    parts: list[tuple[str | None, tuple[str, ...]]] = []
    classes = 0
    tags = 0
    for piece in selector.split():
        piece = re.sub(r"::?[a-z-]+(\([^)]*\))?", "", piece)
        if not piece or piece[0] in ">+~":
            continue
        tag_match = re.match(r"^[a-zA-Z][\w-]*", piece)
        tag = tag_match.group(0).lower() if tag_match else None
        found = tuple(re.findall(r"\.([\w-]+)", piece))
        if tag is None and not found:
            continue
        parts.append((tag, found))
        classes += len(found)
        tags += 1 if tag else 0
    return parts, (classes, tags)


def parse_css(css: str) -> list[_Rule]:
    rules: list[_Rule] = []
    order = 0
    for selector_text, body in _top_level_blocks(_strip_css_comments(css)):
        decls = _parse_decls(body)
        if not decls:
            continue
        for selector in selector_text.split(","):
            parts, specificity = _parse_selector(selector.strip())
            if parts:
                rules.append(_Rule(parts=parts, decls=decls, order=order, specificity=specificity))
            order += 1
    return rules


def _tag_of(element) -> str:
    tag = element.tag
    return tag.lower() if isinstance(tag, str) else ""


def _classes_of(element) -> tuple[str, ...]:
    value = element.get("class")
    return tuple(value.split()) if value else ()


def _matches_part(element, part: tuple[str | None, tuple[str, ...]]) -> bool:
    tag, classes = part
    if tag and _tag_of(element) != tag:
        return False
    present = _classes_of(element)
    return all(name in present for name in classes)


def _matches(element, rule: _Rule) -> bool:
    if not _matches_part(element, rule.parts[-1]):
        return False
    if len(rule.parts) == 1:
        return True
    ancestors = list(element.iterancestors())
    cursor = 0
    for part in reversed(rule.parts[:-1]):
        while cursor < len(ancestors) and not _matches_part(ancestors[cursor], part):
            cursor += 1
        if cursor >= len(ancestors):
            return False
        cursor += 1
    return True


#: 参与「border-bottom → 下划线」等价的行内标签。表格单元（td/th）一律排除。
_INLINE_FILL_TAGS = frozenset(
    ("span", "a", "i", "b", "em", "strong", "label", "small", "u", "sub", "sup")
)

#: 图片命名空间（wp: drawing 内联、a: DrawingML、pic: 图片扩展）
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"

#: 1 mm = 36000 EMU
_EMU_PER_MM = 36000


class StyleResolver:
    """按「层叠 + 优先级 + 行内 style」解析元素上的最终声明。

    ⚠️ 缓存**必须**同时存住元素本身并做 `is` 比对：lxml 的元素是**按需创建的代理
    对象**，`id()` 会在代理被回收后被复用 —— 只按 `id` 缓存会把 A 元素的声明错给
    B 元素（实测表现为表格行高串成别的元素的 `height`，整张表被撑高、多出空白页）。
    """

    def __init__(self, rules: list[_Rule]) -> None:
        self._rules = rules
        self._cache: dict[int, tuple[object, dict[str, str]]] = {}

    def resolve(self, element) -> dict[str, str]:
        key = id(element)
        cached = self._cache.get(key)
        if cached is not None and cached[0] is element:
            return cached[1]

        matched = [
            (rule.specificity, rule.order, rule.decls)
            for rule in self._rules
            if _matches(element, rule)
        ]
        matched.sort(key=lambda item: (item[0], item[1]))
        out: dict[str, str] = {}
        for _, _, decls in matched:
            out.update(decls)

        inline = element.get("style")
        if inline:
            out.update(_parse_decls(inline))

        # 「横线填值」的另一种写法：行内元素自带 border-bottom 实线（如合同
        # 模板的 <span class="line">）→ 等价为 text-decoration: underline。
        # 只对行内标签生效 —— td/th 的边框是表格线，绝不能变成下划线。
        if _tag_of(element) in _INLINE_FILL_TAGS:
            border_bottom = (out.get("border-bottom") or "").lower()
            if "solid" in border_bottom or "double" in border_bottom:
                out.setdefault("text-decoration", "underline")

        self._cache[key] = (element, out)
        return out

    def resolve_run(self, element) -> dict[str, str]:
        """元素**自己命中**的规则 + 祖先链上可继承的文本属性（自己命中者优先）。

        遍历时把祖先按「由外到内」压栈，内层后写即覆盖外层 —— 与 CSS 继承一致。
        只有 ``INHERITED_TEXT_PROPERTIES`` 会被带下来，其余（margin/padding/text-align/
        line-height…）保持原样，避免把 ``<tr>``/``<table>`` 上的几何属性误灌进 run。

        ⚠️ 祖先链一律要取到 ``getparent()`` 为 ``None`` 为止；lxml 里父节点可能不是
        Element（注释、PI 的 tag 不是字符串），此时停住即可。
        """
        chain = []
        node = element
        while isinstance(getattr(node, "tag", None), str):
            chain.append(node)
            node = node.getparent()
        out: dict[str, str] = {}
        for node in reversed(chain):
            own = self.resolve(node)
            for key in INHERITED_TEXT_PROPERTIES:
                if key in own:
                    out[key] = own[key]
        out.update(self.resolve(element))
        return out


# ── 文本抽取 ──────────────────────────────────────────────────────────────


def _normalize_text(text: str, keep_newlines: bool) -> str:
    text = text.replace("\u00a0", " ")
    if keep_newlines:
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
    else:
        text = re.sub(r"\s+", " ", text)
    return text


def _fill_line_placeholder(element, styles: StyleResolver) -> str | None:
    """空的「横线填值」元素 → 按 min-width 宽度折算的全角空格串。

    Word 的下划线只画在有字符的地方：`<span class="line">` 里没填值时若不垫
    空格，横线就整个消失。宽度按 ``min-width + 左右 padding`` 除以全角字宽
    （字号本身）估算，宁可多一两格也不让线短一截。
    """
    decls = styles.resolve(element)
    if "underline" not in (decls.get("text-decoration") or ""):
        return None
    if "".join(element.itertext()).strip():
        return None  # 已有真实内容，不需要垫
    width_mm = to_mm(decls.get("min-width")) or 0.0
    for side in ("padding-left", "padding-right"):
        width_mm += to_mm(decls.get(side)) or 0.0
    font_mm = ((to_pt(decls.get("font-size")) or 10.5) * 25.4) / 72.0
    if width_mm <= 0:
        return "\u3000"
    return "\u3000" * max(1, round(width_mm / font_mm))


def iter_cell_text(element, styles: StyleResolver):
    """按文档顺序产出 ``(文本, 所属元素)``；``<br>`` 与保留的换行产出 ``("\\n", 元素)``。"""
    decls = styles.resolve(element)
    keep_newlines = "pre" in (decls.get("white-space") or "")

    def walk(node):
        text = node.text
        if text:
            yield _normalize_text(text, keep_newlines), node
        for child in node:
            if not isinstance(child.tag, str):
                continue
            if _tag_of(child) == "br":
                yield "\n", node
            else:
                placeholder = _fill_line_placeholder(child, styles)
                if placeholder is not None:
                    yield placeholder, child
                else:
                    yield from walk(child)
            if child.tail:
                yield _normalize_text(child.tail, keep_newlines), node

    for piece, owner in walk(element):
        if piece:
            yield piece, owner


# ── 字体与段落属性 ────────────────────────────────────────────────────────


def _font_name(families: str | None, *, for_east_asia: bool) -> str | None:
    if not families:
        return None
    names = [item.strip().strip("'\"").lower() for item in families.split(",")]
    if for_east_asia:
        for name in names:
            if name in CJK_FONTS:
                return FONT_ALIASES.get(name, name)
        return None
    for name in names:
        if name in FONT_ALIASES:
            return FONT_ALIASES[name]
    for name in names:
        if name not in ("serif", "sans-serif", "monospace"):
            return name
    return None


def _run_properties(
    decls: dict[str, str], inherited: dict[str, str], *, default_pt: float
) -> dict[str, object]:
    merged = {**inherited, **decls}
    size_pt = to_pt(merged.get("font-size")) or default_pt
    weight = merged.get("font-weight") or ""
    # `w:spacing@val` 的单位是 1/20 磅，不能直接把 mm 数值乘 20
    letter_spacing_pt = to_pt(merged.get("letter-spacing"))
    return {
        "ascii": _font_name(merged.get("font-family"), for_east_asia=False),
        "east_asia": _font_name(merged.get("font-family"), for_east_asia=True),
        "size_half_points": int(round(size_pt * 2)),
        "bold": (weight.isdigit() and int(weight) >= 600) or weight in ("bold", "bolder"),
        # 摸底表等表单的"横线填值"：text-decoration: underline → w:u
        "underline": "underline" in (merged.get("text-decoration") or ""),
        "letter_spacing_twips": (
            None if not letter_spacing_pt else int(round(letter_spacing_pt * 20))
        ),
    }


def _make_rpr(props: dict[str, object]) -> etree._Element | None:
    ascii_font = props.get("ascii")
    east_asia = props.get("east_asia")
    if not ascii_font and not east_asia:
        ascii_font = east_asia = "SimSun"
    rpr = etree.Element(q("rPr"))
    fonts = etree.SubElement(rpr, q("rFonts"))
    for attr in ("ascii", "hAnsi", "cs"):
        fonts.set(q(attr), str(ascii_font or east_asia))
    fonts.set(q("eastAsia"), str(east_asia or ascii_font))
    if props.get("bold"):
        etree.SubElement(rpr, q("b"))
    spacing = props.get("letter_spacing_twips")
    if spacing:
        node = etree.SubElement(rpr, q("spacing"))
        node.set(q("val"), str(spacing))
    size = str(props.get("size_half_points") or 21)
    for name in ("sz", "szCs"):
        node = etree.SubElement(rpr, q(name))
        node.set(q("val"), size)
    if props.get("underline"):
        # OOXML 顺序：u 位于 sz/szCs 之后
        node = etree.SubElement(rpr, q("u"))
        node.set(q("val"), "single")
    return rpr


def _alignment(value: str | None) -> str | None:
    if not value:
        return None
    mapping = {
        "left": "left",
        "start": "left",
        "center": "center",
        "right": "right",
        "end": "right",
        "justify": "both",
    }
    return mapping.get(value.strip().lower())


def _line_spacing(decls: dict[str, str], *, default_pt: float) -> tuple[str, str] | None:
    """CSS ``line-height`` → ``w:spacing@line`` 的 ``(值, lineRule)``。

    一律换算成点数写死（``lineRule="exact"``）：CSS 的 ``line-height`` 倍数是
    **相对字号**算的，而 Word 的 ``auto``（倍数行距）是拿字体**自身行高**再乘倍数
    —— 宋体 10.5pt 的实际行高约 1.3em 还带额外行距，实测比 CSS 高出约六成，
    每个单元格都被撑高，整节被挤到下一页。写死点数才能与浏览器排出来的一致。
    """
    if parse_length(decls.get("line-height")) is None:
        return None
    size_pt = to_pt(decls.get("font-size")) or default_pt
    return _exact_line_twips(line_height_mm(decls, size_pt)), "exact"


def _required_line_twips(run_props: list[dict[str, object]]) -> int:
    """段落里**最大** run 所需的行高（twips）；没有 run 时返回 0。"""
    need_pt = 0.0
    for props in run_props:
        size_pt = (props.get("size_half_points") or 0) / 2
        font = props.get("east_asia") or props.get("ascii")
        need_pt = max(need_pt, size_pt * FONT_LINE_FACTORS.get(str(font), DEFAULT_LINE_FACTOR))
    return int(round(need_pt * 20))


def _line_spacing_fitting(
    decls: dict[str, str], *, default_pt: float, run_props: list[dict[str, object]]
) -> tuple[str, str] | None:
    """CSS 行距 → Word 固定行距，并**抬高到装得下最大的 run**。

    固定行距（``lineRule="exact"``）会在行框顶部裁掉放不下的字形，所以行距不能只看
    CSS：CSS 的 ``line-height`` 是按**单元格自己的字号**算的，单元格里若嵌了更大的
    run（典型：7pt 的格子里放 10.5pt 的勾选框），按 CSS 算出来的行距就装不下那个字，
    方框的上横会被裁掉。这里取 ``max(CSS 行距, 最大 run 所需行高)``。
    没有写死行距（CSS 没给 ``line-height``）时返回 ``None`` —— Word 用自动行距会自己
    撑高，不存在裁字问题，不要多此一举去改动它。
    """
    line = _line_spacing(decls, default_pt=default_pt)
    if line is None:
        return None
    twips, rule = line
    return str(max(int(twips), _required_line_twips(run_props))), rule


def _paragraph(
    *,
    jc: str | None = None,
    spacing: dict[str, str] | None = None,
    runs: list[etree._Element] | None = None,
    ind_first_line: str | None = None,
    ind_left: str | None = None,
    sect_pr: etree._Element | None = None,
) -> etree._Element:
    para = etree.Element(q("p"))
    ppr = etree.SubElement(para, q("pPr"))
    if spacing:
        node = etree.SubElement(ppr, q("spacing"))
        for key, value in spacing.items():
            node.set(q(key), value)
    # CT_PPr 是有序序列：spacing → ind → jc → rPr → sectPr，顺序错了 Word 会忽略
    if ind_first_line is not None or ind_left is not None:
        node = etree.SubElement(ppr, q("ind"))
        if ind_left is not None:
            node.set(q("left"), ind_left)
        if ind_first_line is not None:
            node.set(q("firstLine"), ind_first_line)
    if jc:
        node = etree.SubElement(ppr, q("jc"))
        node.set(q("val"), jc)
    if runs is None:
        etree.SubElement(ppr, q("rPr"))
    else:
        for run in runs:
            para.append(run)
    if sect_pr is not None:
        ppr.append(sect_pr)
    return para


def _exact_line_twips(height_mm: float) -> str:
    """固定行距：1 twip == 1/20 磅，正好就是 ``w:spacing@line`` 的单位。"""
    return str(max(20, _mm_to_twips(height_mm)))


def _title_paragraph(
    element,
    styles: StyleResolver,
    *,
    default_pt: float,
    extra_spacing: dict[str, str] | None = None,
    default_align: str | None = "center",
) -> tuple[etree._Element, float]:
    """居中标题类元素（封面标题 / 副题 / 表标题 / 正文块）→ 段落，并回传它占的高度（mm）。"""
    decls = styles.resolve(element)
    size_pt = to_pt(decls.get("font-size")) or default_pt
    height_mm = line_height_mm(decls, size_pt)
    top_mm = to_mm(decls.get("margin-top")) or 0.0
    bottom_mm = to_mm(decls.get("margin-bottom")) or 0.0

    spacing = {
        "before": str(_mm_to_twips(top_mm)),
        "after": str(_mm_to_twips(bottom_mm)),
        "line": _exact_line_twips(height_mm),
        "lineRule": "exact",
    }
    if extra_spacing:
        spacing.update(extra_spacing)

    props = _run_properties(decls, {}, default_pt=default_pt)
    indent_mm = to_mm(decls.get("text-indent"))
    para = _paragraph(
        jc=_alignment(decls.get("text-align")) or default_align,
        spacing=spacing,
        ind_first_line=str(_mm_to_twips(indent_mm)) if indent_mm else None,
        runs=[_simple_run("".join(element.itertext()).strip(), props)],
    )
    return para, top_mm + height_mm + bottom_mm


def _block_paragraph(element, styles: StyleResolver, *, default_pt: float) -> etree._Element:
    """把 ``<p>`` 之类**行内内容**的块级元素转成段落（保留 CSS 的对齐 / 字号 / 上下边距）。

    只按 ``ElementTree`` 直接子节点判"是不是容器"，所以 ``<p>a<b>b</b></p>``
    不会被误当容器拆开。段落里需要保留的换行（``<br>``）走和单元格同一套处理。
    """
    decls = styles.resolve(element)
    spacing: dict[str, str] = {
        "before": str(_mm_to_twips(to_mm(decls.get("margin-top")) or 0.0)),
        "after": str(_mm_to_twips(to_mm(decls.get("margin-bottom")) or 0.0)),
    }

    runs: list[etree._Element] = []
    run_props: list[dict[str, object]] = []
    for piece, owner in iter_cell_text(element, styles):
        if piece == "\n":
            runs.append(_break_run())
            continue
        props = _run_properties(
            styles.resolve_run(owner), {}, default_pt=default_pt
        )
        run_props.append(props)
        runs.append(_simple_run(piece, props))
    while runs and runs[0].find(q("br")) is not None:
        runs.pop(0)
    while runs and runs[-1].find(q("br")) is not None:
        runs.pop()

    line = _line_spacing_fitting(decls, default_pt=default_pt, run_props=run_props)
    if line:
        spacing["line"], spacing["lineRule"] = line

    # 首行缩进（声明书类文书的"首行空两格"）：CSS text-indent → w:ind@firstLine
    indent_mm = to_mm(decls.get("text-indent"))

    return _paragraph(
        jc=_alignment(decls.get("text-align")),
        spacing=spacing,
        ind_first_line=str(_mm_to_twips(indent_mm)) if indent_mm else None,
        runs=runs or None,
    )


def _simple_run(text: str, props: dict[str, object]) -> etree._Element:
    run = etree.Element(q("r"))
    rpr = _make_rpr(props)
    if rpr is not None:
        run.append(rpr)
    node = etree.SubElement(run, q("t"))
    node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    node.text = text
    return run


def _break_run(props: dict[str, object] | None = None) -> etree._Element:
    run = etree.Element(q("r"))
    if props:
        rpr = _make_rpr(props)
        if rpr is not None:
            run.append(rpr)
    etree.SubElement(run, q("br"))
    return run


def _image_paragraph(
    src: str | None,
    decls: dict[str, str],
    images: list[tuple[str, str, bytes]],
) -> etree._Element | None:
    """``<img src="data:image/...;base64,...">`` → 居中图片段落。

    ``images`` 收集 ``(relationshipId, 扩展名, 图片字节)``，由 ``_package`` 落成
    media part + relationship。尺寸读 CSS ``width``/``height``（mm）——导出用的
    整页示意图由调用方显式写死尺寸；缺失时用 Pillow 读像素按 96dpi 估算。
    返回 ``None`` 表示无法识别的 src（非 data URI），由调用方决定丢弃或兜底。
    """
    if not src or not src.startswith("data:image/"):
        return None
    try:
        header, payload = src.split(",", 1)
    except ValueError:
        return None
    import base64

    try:
        data = base64.b64decode(payload)
    except Exception:
        return None
    ext = "png" if "png" in header else ("jpeg" if "jpeg" in header or "jpg" in header else "png")

    width_mm = to_mm(decls.get("width"))
    height_mm = to_mm(decls.get("height"))
    if width_mm is None or height_mm is None:
        try:
            from PIL import Image as PILImage

            with PILImage.open(io.BytesIO(data)) as img:
                pixel_w, pixel_h = img.size
            if width_mm is None and height_mm is None:
                width_mm, height_mm = pixel_w / 96.0 * 25.4, pixel_h / 96.0 * 25.4
            elif width_mm is None:
                width_mm = height_mm * pixel_w / pixel_h
            elif height_mm is None:
                height_mm = width_mm * pixel_h / pixel_w
        except Exception:
            width_mm = width_mm or 150.0
            height_mm = height_mm or 100.0

    rid = f"rIdImg{len(images) + 1}"
    images.append((rid, ext, data))

    cx = int(width_mm * _EMU_PER_MM)
    cy = int(height_mm * _EMU_PER_MM)
    drawing = etree.Element(q("drawing"))
    inline = etree.SubElement(drawing, f"{{{WP_NS}}}inline")
    for name in ("distT", "distB", "distL", "distR"):
        inline.set(name, "0")
    extent = etree.SubElement(inline, f"{{{WP_NS}}}extent")
    extent.set("cx", str(cx))
    extent.set("cy", str(cy))
    doc_pr = etree.SubElement(inline, f"{{{WP_NS}}}docPr")
    doc_pr.set("id", str(len(images)))
    doc_pr.set("name", f"Picture {len(images)}")
    # ⚠️ 这里是 a:graphic（DrawingML 命名空间），不是 wp:graphic —— 写错
    # 命名空间 Word 会整份文档拒绝打开（2026-11-09 示意图导出踩过）。
    graphic = etree.SubElement(inline, f"{{{A_NS}}}graphic")
    graphic_data = etree.SubElement(graphic, f"{{{A_NS}}}graphicData")
    graphic_data.set("uri", PIC_NS)
    pic = etree.SubElement(graphic_data, f"{{{PIC_NS}}}pic")
    nv_pic_pr = etree.SubElement(pic, f"{{{PIC_NS}}}nvPicPr")
    cnv_pr = etree.SubElement(nv_pic_pr, f"{{{PIC_NS}}}cNvPr")
    cnv_pr.set("id", str(len(images)))
    cnv_pr.set("name", f"image{len(images)}.{ext}")
    etree.SubElement(nv_pic_pr, f"{{{PIC_NS}}}cNvPicPr")
    blip_fill = etree.SubElement(pic, f"{{{PIC_NS}}}blipFill")
    blip = etree.SubElement(blip_fill, f"{{{A_NS}}}blip")
    # r:embed —— 关系引用必须用 Office 关系命名空间（r:），不是 w:
    blip.set(f"{{{R_NS}}}embed", rid)
    stretch = etree.SubElement(blip_fill, f"{{{A_NS}}}stretch")
    etree.SubElement(stretch, f"{{{A_NS}}}fillRect")
    sp_pr = etree.SubElement(pic, f"{{{PIC_NS}}}spPr")
    xfrm = etree.SubElement(sp_pr, f"{{{A_NS}}}xfrm")
    off = etree.SubElement(xfrm, f"{{{A_NS}}}off")
    off.set("x", "0")
    off.set("y", "0")
    ext_node = etree.SubElement(xfrm, f"{{{A_NS}}}ext")
    ext_node.set("cx", str(cx))
    ext_node.set("cy", str(cy))
    prst = etree.SubElement(sp_pr, f"{{{A_NS}}}prstGeom")
    prst.set("prst", "rect")
    etree.SubElement(prst, f"{{{A_NS}}}avLst")

    run = etree.Element(q("r"))
    run.append(drawing)
    return _image_paragraph_element(run)


def _image_paragraph_element(run: etree._Element) -> etree._Element:
    """整页图片的段落：行距自动 + 1pt 字号。

    Word 把行内图片摆在**基线**上：若行距 exact = 图片高，基线在行框内偏上，
    图片会顶出页外（实测顶出约 41mm）。行距改自动后行框恰好被图片撑满，
    剩下的基线下伸部由 1pt 字号压到亚毫米级，整页图刚好占满一页。
    """
    para = etree.Element(q("p"))
    ppr = etree.SubElement(para, q("pPr"))
    spacing = etree.SubElement(ppr, q("spacing"))
    spacing.set(q("before"), "0")
    spacing.set(q("after"), "0")
    jc = etree.SubElement(ppr, q("jc"))
    jc.set(q("val"), "center")
    rpr = etree.SubElement(run, q("rPr"))
    for name in ("sz", "szCs"):
        node = etree.SubElement(rpr, q(name))
        node.set(q("val"), "2")
    para.append(run)
    return para


# ── 表格 ──────────────────────────────────────────────────────────────────


@dataclass
class _Cell:
    col: int
    span: int
    vmerge: str | None
    element: object | None


def _build_grid(table) -> list[list[_Cell]]:
    """按 colspan/rowspan 还原成网格（跨行续格也显式列出来）。

    ⚠️ ``pending`` 的键是跨行格的**起始列**，值是 ``(剩余行数, 跨列数)`` ——
    续格必须记住原始 ``colspan``。若按"每个被覆盖的列各补一个 span=1 的续格"
    来补（曾经就是这么写的），Word 里的合并格会在下一行被**切断**：合并格上半
    截横跨 2 列、下半截只占 1 列，凭空多出一条竖线。实测症状有三：
      * 承包地块调查表「墙壁」「其他界线」（跨行 2 + 跨列 2）下半截内部多一条竖线；
      * 同表「指界签章」格在**首个数据行**是 ``span=2``（不断），第 2 行起续格被拆成
        ``span=1``（断），看起来就是"竖线断开了"；
      * 界址点坐标成果表「点号」格下半截多一条竖线。
    三处都是同一个根因，也都是"首行看不出、续行才露出来"。
    """
    rows: list[list[_Cell]] = []
    pending: dict[int, tuple[int, int]] = {}

    def fill(row: list[_Cell], col: int, *, to_end: bool) -> int:
        """把挂在 ``col`` 上的跨行续格补进本行，返回推进后的列号。

        ``to_end=False``（行内 td 之间）只吃掉紧挨着的续格，遇到空档就停 ——
        后面还有真实单元格要放；``to_end=True``（行尾）要把剩余续格都补齐，
        中间允许隔着别的跨行块（不能只顺着 ``col`` 排）。
        """
        limit = max(pending) + 1 if (to_end and pending) else None
        while True:
            entry = pending.get(col)
            if entry is None:
                if limit is None or col >= limit:
                    break
                col += 1
                continue
            remaining, span = entry
            row.append(_Cell(col=col, span=span, vmerge="continue", element=None))
            if remaining > 1:
                pending[col] = (remaining - 1, span)
            else:
                del pending[col]
            col += span
        return col

    row_groups = [child for child in table if _tag_of(child) in ("thead", "tbody", "tfoot")]
    if row_groups:
        # 行组包裹（contract.html 等模板的行都在 thead/tbody 里）：按文档顺序
        # 遍历行组里的 tr。⚠️ 只认 table 的直接子级行组，别用 table.iter("tr") ——
        # 那会把单元格里嵌套表格的行也收进来。
        trs = [tr for group in row_groups for tr in group if _tag_of(tr) == "tr"]
    else:
        trs = [tr for tr in table if _tag_of(tr) == "tr"]
    for tr in trs:
        if _tag_of(tr) != "tr":
            continue
        row: list[_Cell] = []
        col = 0
        for td in tr:
            if _tag_of(td) not in ("td", "th"):
                continue
            col = fill(row, col, to_end=False)
            span = int(td.get("colspan") or 1)
            rowspan = int(td.get("rowspan") or 1)
            row.append(
                _Cell(col=col, span=span, vmerge="restart" if rowspan > 1 else None, element=td)
            )
            if rowspan > 1:
                pending[col] = (rowspan - 1, span)
            col += span
        fill(row, col, to_end=True)
        rows.append(row)
    return rows


def _column_widths(table, styles: StyleResolver, grid_columns: int) -> list[int]:
    colgroup = None
    for child in table:
        if _tag_of(child) == "colgroup":
            colgroup = child
            break
    widths: list[int] = []
    if colgroup is not None:
        for col in colgroup:
            if _tag_of(col) != "col":
                continue
            millimetres = to_mm(styles.resolve(col).get("width"))
            if millimetres is None:
                return []
            widths.append(_mm_to_twips(millimetres))
    if len(widths) != grid_columns:
        return []
    return widths


def _fit_columns(columns: list[int], limit: int | None) -> list[int]:
    """HTML 的"表宽 = 正文宽"在 mm→twips 取整后可能多出几 twip，按比例收回。"""
    total = sum(columns)
    if not limit or total <= limit:
        return columns
    scaled = [max(1, int(col * limit / total)) for col in columns]
    drift = sum(scaled) - limit
    index = 0
    while drift > 0 and index < len(scaled):
        if scaled[index] > 1:
            scaled[index] -= 1
            drift -= 1
        index += 1
    return scaled


def _cell_margins(decls: dict[str, str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for side in ("top", "right", "bottom", "left"):
        millimetres = to_mm(decls.get(f"padding-{side}"))
        out[side] = _mm_to_twips(millimetres) if millimetres is not None else 0
    return out


def _table_borders() -> etree._Element:
    borders = etree.Element(q("tblBorders"))
    for name in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = etree.SubElement(borders, q(name))
        node.set(q("val"), "single")
        node.set(q("sz"), str(BORDER_SZ))
        node.set(q("space"), "0")
        node.set(q("color"), "000000")
    return borders


def _build_table(
    table,
    styles: StyleResolver,
    *,
    default_pt: float,
    content_width: int | None,
) -> etree._Element | None:
    grid = _build_grid(table)
    if not grid:
        return None
    grid_columns = max(cell.col + cell.span for row in grid for cell in row)
    columns = _column_widths(table, styles, grid_columns)
    if not columns:
        millimetres = to_mm(styles.resolve(table).get("width"))
        total = _mm_to_twips(millimetres) if millimetres else (content_width or 9000)
        each = max(1, total // grid_columns)
        columns = [each] * grid_columns
        columns[-1] = max(1, total - each * (grid_columns - 1))
    columns = _fit_columns(columns, content_width)

    tbl = etree.Element(q("tbl"))
    tbl_pr = etree.SubElement(tbl, q("tblPr"))
    width = etree.SubElement(tbl_pr, q("tblW"))
    width.set(q("w"), str(sum(columns)))
    width.set(q("type"), "dxa")
    jc = etree.SubElement(tbl_pr, q("jc"))
    jc.set(q("val"), "center")
    tbl_pr.append(_table_borders())
    layout = etree.SubElement(tbl_pr, q("tblLayout"))
    layout.set(q("type"), "fixed")
    margins = etree.SubElement(tbl_pr, q("tblCellMar"))
    for side in ("top", "left", "bottom", "right"):
        node = etree.SubElement(margins, q(side))
        node.set(q("w"), "0")
        node.set(q("type"), "dxa")
    look = etree.SubElement(tbl_pr, q("tblLook"))
    look.set(q("val"), "0000")
    look.set(q("firstRow"), "0")
    look.set(q("lastRow"), "0")
    look.set(q("firstColumn"), "0")
    look.set(q("lastColumn"), "0")
    look.set(q("noHBand"), "0")
    look.set(q("noVBand"), "0")

    grid_el = etree.SubElement(tbl, q("tblGrid"))
    for column in columns:
        node = etree.SubElement(grid_el, q("gridCol"))
        node.set(q("w"), str(column))

    table_decls = styles.resolve(table)
    for row in grid:
        tr = etree.Element(q("tr"))
        tr_pr = etree.SubElement(tr, q("trPr"))
        etree.SubElement(tr_pr, q("cantSplit"))

        row_element = None
        for cell in row:
            if cell.element is not None:
                row_element = cell.element
                break
        if row_element is not None and row_element.getparent() is not None:
            height_mm = to_mm(styles.resolve(row_element.getparent()).get("height"))
            if height_mm:
                height = etree.SubElement(tr_pr, q("trHeight"))
                height.set(q("val"), str(_mm_to_twips(height_mm)))
                height.set(q("hRule"), "atLeast")

        for cell in row:
            tr.append(
                _build_cell(
                    cell,
                    columns,
                    styles,
                    table_decls=table_decls,
                    default_pt=default_pt,
                )
            )

        # 补齐行尾缺口必须按"已覆盖的**列数**"算，不能按"单元格个数"：
        # 用了 colspan 的行（几乎每行）格子数天然少于列数，按格子数补会凭空多出
        # 一格（实测多出 1..4 列），Word 只好把整表列宽等比压到 0.6 倍 —— 每个
        # 单元格都被挤成两行，整节被顶到下一页。
        covered = max((cell.col + cell.span for cell in row), default=0)
        if covered < grid_columns:
            filler = _Cell(col=covered, span=grid_columns - covered, vmerge=None, element=None)
            tr.append(_build_cell(filler, columns, styles, table_decls=table_decls, default_pt=default_pt))
        tbl.append(tr)
    return tbl


def _build_cell(
    cell: _Cell,
    columns: list[int],
    styles: StyleResolver,
    *,
    table_decls: dict[str, str],
    default_pt: float,
) -> etree._Element:
    tc = etree.Element(q("tc"))
    tc_pr = etree.SubElement(tc, q("tcPr"))

    span = max(1, min(cell.span, len(columns) - cell.col))
    width = sum(columns[cell.col : cell.col + span])
    node = etree.SubElement(tc_pr, q("tcW"))
    node.set(q("w"), str(width))
    node.set(q("type"), "dxa")
    if span > 1:
        node = etree.SubElement(tc_pr, q("gridSpan"))
        node.set(q("val"), str(span))
    if cell.vmerge:
        node = etree.SubElement(tc_pr, q("vMerge"))
        if cell.vmerge == "restart":
            node.set(q("val"), "restart")

    if cell.element is None:
        v_align = etree.SubElement(tc_pr, q("vAlign"))
        v_align.set(q("val"), "center")
        etree.SubElement(tc, q("p"))
        return tc

    decls = styles.resolve(cell.element)
    # 单元格级消线：相邻两张表上下拼接成一整张表时，接缝的两个格显式写
    # border-top/border-bottom: none → tcBorders nil（覆盖整表 tblBorders 的 insideH）。
    # 注意 tcPr 子元素顺序：tcBorders 必须在 tcMar / vAlign 之前。
    none_sides = [
        side
        for side in ("top", "left", "bottom", "right")
        if "none" in (decls.get(f"border-{side}") or "").lower()
    ]
    if none_sides:
        tc_borders = etree.SubElement(tc_pr, q("tcBorders"))
        for side in none_sides:
            node = etree.SubElement(tc_borders, q(side))
            node.set(q("val"), "nil")
    margins = _cell_margins(decls)
    if any(margins.values()):
        mar = etree.SubElement(tc_pr, q("tcMar"))
        for side in ("top", "left", "bottom", "right"):
            node = etree.SubElement(mar, q(side))
            node.set(q("w"), str(margins[side]))
            node.set(q("type"), "dxa")
    vertical = (decls.get("vertical-align") or "middle").strip().lower()
    v_align = etree.SubElement(tc_pr, q("vAlign"))
    v_align.set(q("val"), {"top": "top", "bottom": "bottom"}.get(vertical, "center"))

    jc = _alignment(decls.get("text-align"))
    spacing: dict[str, str] = {"before": "0", "after": "0"}

    runs: list[etree._Element] = []
    run_props: list[dict[str, object]] = []
    for piece, owner in iter_cell_text(cell.element, styles):
        if piece == "\n":
            runs.append(_break_run())
            continue
        owner_decls = decls if owner is cell.element else styles.resolve_run(owner)
        props = _run_properties(owner_decls, {}, default_pt=default_pt)
        run_props.append(props)
        runs.append(_simple_run(piece, props))
    while runs and runs[0].find(q("br")) is not None:
        runs.pop(0)
    while runs and runs[-1].find(q("br")) is not None:
        runs.pop()

    line = _line_spacing_fitting(
        {**table_decls, **decls}, default_pt=default_pt, run_props=run_props
    )
    if line:
        spacing["line"], spacing["lineRule"] = line
    elif runs:
        # ⚠️ _exact_line_twips 返回 str、_required_line_twips 返回 int，
        # 直接 max(str, int) 会 TypeError（表格 CSS 没写 line-height 时才走到
        # 这条分支，此前被静默丢表掩盖，2026-11-09 合同表格修复时首次触发）。
        spacing["line"] = str(
            max(
                int(
                    _exact_line_twips(
                        line_height_mm({}, to_pt(decls.get("font-size")) or default_pt)
                    )
                ),
                _required_line_twips(run_props),
            )
        )
        spacing["lineRule"] = "exact"
    tc.append(_paragraph(jc=jc, spacing=spacing, runs=runs or None))
    return tc


# ── 页面 / 分节 ───────────────────────────────────────────────────────────


def _section_properties(decls: dict[str, str]) -> tuple[etree._Element, float]:
    width_mm = to_mm(decls.get("width")) or 210.0
    height_mm = to_mm(decls.get("height")) or 297.0
    pad_top = to_mm(decls.get("padding-top")) or 0.0
    pad_right = to_mm(decls.get("padding-right")) or 0.0
    pad_bottom = to_mm(decls.get("padding-bottom")) or 0.0
    pad_left = to_mm(decls.get("padding-left")) or 0.0

    sect = etree.Element(q("sectPr"))
    size = etree.SubElement(sect, q("pgSz"))
    size.set(q("w"), str(_mm_to_twips(width_mm)))
    size.set(q("h"), str(_mm_to_twips(height_mm)))
    if width_mm > height_mm:
        size.set(q("orient"), "landscape")
    margins = etree.SubElement(sect, q("pgMar"))
    margins.set(q("top"), str(_mm_to_twips(pad_top)))
    margins.set(q("right"), str(_mm_to_twips(pad_right)))
    margins.set(q("bottom"), str(_mm_to_twips(pad_bottom)))
    margins.set(q("left"), str(_mm_to_twips(pad_left)))
    for name in ("header", "footer", "gutter"):
        margins.set(q(name), "0")
    columns = etree.SubElement(sect, q("cols"))
    columns.set(q("space"), "0")
    return sect, height_mm - pad_top - pad_bottom


def _zero_height_paragraph() -> etree._Element:
    """1 磅高的空段。

    用途有二：承载分节属性；以及在**表格收尾**时占位 —— OOXML 不允许表格
    是节的最后一块内容，Word 打开时会自动补一个默认行高（10.5pt）的空段落，
    表格恰好占满一页时这个补段会被挤到下一页，凭空多出一页（2026-11-06
    承包方调查表空白件踩过）。主动放一个零高段落，Word 就不再自己插。
    """
    para = etree.Element(q("p"))
    ppr = etree.SubElement(para, q("pPr"))
    spacing = etree.SubElement(ppr, q("spacing"))
    spacing.set(q("before"), "0")
    spacing.set(q("after"), "0")
    spacing.set(q("line"), "20")
    spacing.set(q("lineRule"), "exact")
    rpr = etree.SubElement(ppr, q("rPr"))
    for name in ("sz", "szCs"):
        node = etree.SubElement(rpr, q(name))
        node.set(q("val"), "2")
    return para


def _zero_height_section_paragraph(sect_pr: etree._Element) -> etree._Element:
    """承载分节属性的收尾段落：压到 1 磅，别把内容挤到下一页。"""
    para = _zero_height_paragraph()
    para.find(q("pPr")).append(sect_pr)
    return para


def _spacer_paragraph(height_mm: float) -> etree._Element:
    """精确行高的空段，用来撑出与 CSS `height` 等高的空白。"""
    return _paragraph(spacing={"line": _exact_line_twips(height_mm), "lineRule": "exact"})


def _emit_cover(
    page,
    styles: StyleResolver,
    content_height_mm: float,
    body: list,
    *,
    pad_bottom_mm: float = 0.0,
) -> None:
    """封面：`.cover-head` 撑高 + 标题 + 副题 + 落款贴底（对应 CSS 的 `margin-top: auto`）。

    另支持合同封面的两类元素：
    * ``.cover-codes`` —— 右上角编号块（``margin-left`` 整块右移，逐行成段）；
    * ``.cover-org`` —— ``position: absolute; bottom: N`` 贴底落款（用撑高空段近似）。
    """
    above_mm = 0.0
    foot_nodes: list = []
    foot_decls: dict[str, str] = {}
    org_node = None
    org_decls: dict[str, str] = {}

    for child in page:
        if not isinstance(child.tag, str):
            continue
        classes = _classes_of(child)
        decls = styles.resolve(child)
        if "cover-head" in classes:
            height = to_mm(decls.get("height")) or 0.0
            above_mm += height
            body.append(_spacer_paragraph(height))
        elif "cover-title" in classes or "cover-sub" in classes:
            para, used_mm = _title_paragraph(child, styles, default_pt=21.0)
            body.append(para)
            above_mm += used_mm
        elif "cover-codes" in classes:
            top_gap = to_mm(decls.get("margin-top")) or 0.0
            if top_gap > 0.5:
                body.append(_spacer_paragraph(top_gap))
                above_mm += top_gap
            left_twips = _mm_to_twips(to_mm(decls.get("margin-left")) or 0.0)
            line_mm = line_height_mm(decls, to_pt(decls.get("font-size")) or 10.0)
            for row in child:
                if not isinstance(row.tag, str):
                    continue
                runs: list[etree._Element] = []
                for piece, owner in iter_cell_text(row, styles):
                    if piece == "\n":
                        runs.append(_break_run())
                        continue
                    runs.append(
                        _simple_run(
                            piece,
                            _run_properties(styles.resolve_run(owner), {}, default_pt=10.0),
                        )
                    )
                body.append(
                    _paragraph(
                        spacing={
                            "before": "0",
                            "after": "0",
                            "line": _exact_line_twips(line_mm),
                            "lineRule": "exact",
                        },
                        runs=runs or None,
                        ind_left=str(left_twips) if left_twips else None,
                    )
                )
                above_mm += line_mm
        elif "cover-org" in classes:
            org_node = child
            org_decls = decls
        elif "cover-foot" in classes:
            foot_decls = decls
            foot_nodes = list(child)

    if foot_nodes:
        props = _run_properties(foot_decls, {}, default_pt=14.0)
        line_mm = line_height_mm(foot_decls, to_pt(foot_decls.get("font-size")) or 14.0)
        pad_bottom = to_mm(foot_decls.get("padding-bottom")) or 0.0
        spacer = content_height_mm - above_mm - line_mm * len(foot_nodes) - pad_bottom
        if spacer > 1:
            body.append(_spacer_paragraph(spacer))
        for node in foot_nodes:
            text = "".join(node.itertext()).strip()
            body.append(
                _paragraph(
                    jc="center",
                    spacing={"before": "0", "after": "0", "line": _exact_line_twips(line_mm), "lineRule": "exact"},
                    runs=[_simple_run(text, props)],
                )
            )
    elif org_node is not None:
        line_mm = line_height_mm(org_decls, to_pt(org_decls.get("font-size")) or 10.0)
        # absolute bottom:N 以 .page 的 padding-box 为基准；正文区底边比页面底边
        # 高出 pad_bottom_mm，所以落款离正文区底边 = N - pad_bottom。
        bottom_mm = to_mm(org_decls.get("bottom")) or 0.0
        spacer = content_height_mm - above_mm - line_mm - max(0.0, bottom_mm - pad_bottom_mm)
        if spacer > 1:
            body.append(_spacer_paragraph(spacer))
        text = "".join(org_node.itertext()).strip().replace("\u00a0", " ")
        props = _run_properties(org_decls, {}, default_pt=10.0)
        body.append(
            _paragraph(
                jc=_alignment(org_decls.get("text-align")) or "center",
                spacing={
                    "before": "0",
                    "after": "0",
                    "line": _exact_line_twips(line_mm),
                    "lineRule": "exact",
                },
                runs=[_simple_run(text, props)] if text else None,
            )
        )


# ── 主流程 ────────────────────────────────────────────────────────────────


#: 视为"块级容器"的标签：里面还有块级子元素就往下递归，否则整块当一个段落
_BLOCK_TAGS = frozenset(
    ("p", "div", "section", "header", "footer", "article", "main", "li", "ul", "ol", "blockquote")
)


def _emit_flow(
    elements, styles: StyleResolver, out: list, *,
    content_width: int | None, images: list[tuple[str, str, bytes]],
) -> None:
    """把一个页面下的块级内容按文档顺序转写进 ``out``。

    打印模板里除了 ``h1`` 和 ``table``，还可能有 ``<p>`` 之类的说明段落
    （例如"该承包方名下暂无承包地块"的占位提示）—— 早先只认 h1/table，
    这类内容会被**静静地丢掉**，Word 件与打印件就对不上了。

    ``images`` 是调用方（``build``）持有的收集器；⚠️ 不要写 ``images or []``
    —— 空列表会取到右边的**新临时列表**，图片字节 append 进去直接丢弃
    （2026-11-09 示意图导出踩过：drawing 有了、media 却是空的）。
    """
    for element in elements:
        if not isinstance(element.tag, str):
            continue
        if SKIP_CLASSES & set(_classes_of(element)):
            continue
        tag = _tag_of(element)
        if tag == "img":
            para = _image_paragraph(
                element.get("src"), styles.resolve(element), images
            )
            if para is not None:
                out.append(para)
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            # h1（表单大标题）默认居中；h2 及以下（正文条款标题，如合同
            # "一、承包土地情况"）打印件里是左对齐，默认值跟着改左。
            align = "center" if tag == "h1" else None
            out.append(
                _title_paragraph(element, styles, default_pt=16.0, default_align=align)[0]
            )
        elif tag == "table":
            table = _build_table(
                element, styles, default_pt=10.5, content_width=content_width
            )
            if table is not None:
                out.append(table)
        elif tag in _BLOCK_TAGS:
            nested = [
                child for child in element if isinstance(child.tag, str) and _tag_of(child) in _BLOCK_TAGS
            ]
            if nested:
                _emit_flow(element, styles, out, content_width=content_width, images=images)
            else:
                out.append(_block_paragraph(element, styles, default_pt=10.5))
        elif tag != "br":
            # 直接挂在页面上的行内元素 / 未知标签：兜底成一段，宁可样式粗糙也别丢内容
            out.append(_block_paragraph(element, styles, default_pt=10.5))


class HtmlDocxBuilder:
    def build(self, html_text: str) -> bytes:
        document = lxml_html.fromstring(html_text)
        styles = StyleResolver(self._collect_rules(document))

        body = etree.Element(q("body"))
        pages = [el for el in document.iter() if isinstance(el.tag, str) and "page" in _classes_of(el)]
        sections: list[tuple[list[etree._Element], etree._Element]] = []
        images: list[tuple[str, str, bytes]] = []

        for page in pages:
            page_decls = styles.resolve(page)
            sect_pr, content_height = _section_properties(page_decls)
            content_width = (
                (_mm_to_twips(to_mm(page_decls.get("width")) or 210.0))
                - _mm_to_twips(to_mm(page_decls.get("padding-left")) or 0.0)
                - _mm_to_twips(to_mm(page_decls.get("padding-right")) or 0.0)
            )

            items: list[etree._Element] = []
            if "cover" in _classes_of(page):
                _emit_cover(
                    page,
                    styles,
                    content_height,
                    items,
                    pad_bottom_mm=to_mm(page_decls.get("padding-bottom")) or 0.0,
                )
            else:
                _emit_flow(page, styles, items, content_width=content_width, images=images)

            sections.append((items, sect_pr))

        if not sections:
            body.append(_paragraph())
            body.append(self._default_section())
            return self._package(body, images)

        # 分节属性必须**夹在该节内容末尾**（`pPr/sectPr` 表示"这一节到此为止"）。
        # 全部堆到最后会让所有内容落进第一节，多出来的节各自占一张空白页。
        for items, sect_pr in sections[:-1]:
            body.extend(items)
            body.append(_zero_height_section_paragraph(sect_pr))
        last_items, last_sect_pr = sections[-1]
        body.extend(last_items)
        # OOXML 的表格标签是 w:tbl（不是 w:table）
        if last_items and last_items[-1].tag == q("tbl"):
            body.append(_zero_height_paragraph())
        body.append(last_sect_pr)
        return self._package(body, images)

    # ── 内部 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _collect_rules(document) -> list[_Rule]:
        css = "\n".join(
            node.text or ""
            for node in document.iter()
            if isinstance(node.tag, str) and _tag_of(node) == "style"
        )
        return parse_css(css)

    @staticmethod
    def _default_section() -> etree._Element:
        sect = etree.Element(q("sectPr"))
        size = etree.SubElement(sect, q("pgSz"))
        size.set(q("w"), "11906")
        size.set(q("h"), "16838")
        margins = etree.SubElement(sect, q("pgMar"))
        for side, value in (("top", "1440"), ("right", "745"), ("bottom", "1440"), ("left", "745")):
            margins.set(q(side), value)
        for name in ("header", "footer", "gutter"):
            margins.set(q(name), "0")
        return sect

    @staticmethod
    def _package(
        body: etree._Element, images: list[tuple[str, str, bytes]] | None = None
    ) -> bytes:
        images = images or []
        document = etree.Element(
            q("document"),
            nsmap={"w": W_NS, "r": R_NS, "wp": WP_NS, "a": A_NS, "pic": PIC_NS},
        )
        document.append(body)
        document_xml = etree.tostring(
            document, xml_declaration=True, encoding="UTF-8", standalone=True
        )

        # 图片扩展名 → [Content_Types] 的 Default 声明（png / jpeg 各一条）
        image_exts = sorted({ext for _, ext, _ in images})
        image_content_types = "".join(
            f'<Default Extension="{ext}" ContentType="image/png"/>'
            if ext == "png"
            else f'<Default Extension="{ext}" ContentType="image/jpeg"/>'
            for ext in image_exts
        )
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            f"{image_content_types}"
            "</Types>"
        )
        rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>"
        )
        image_rels = "".join(
            f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image_{index + 1}.{ext}"/>'
            for index, (rid, ext, _) in enumerate(images)
        )
        document_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            f"{image_rels}"
            "</Relationships>"
        )
        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:styles xmlns:w="{W_NS}">'
            "<w:docDefaults><w:rPrDefault><w:rPr>"
            '<w:rFonts w:ascii="SimSun" w:hAnsi="SimSun" w:eastAsia="SimSun" w:cs="SimSun"/>'
            '<w:sz w:val="21"/><w:szCs w:val="21"/>'
            "</w:rPr></w:rPrDefault>"
            "<w:pPrDefault><w:pPr><w:spacing w:before=\"0\" w:after=\"0\"/></w:pPr></w:pPrDefault>"
            "</w:docDefaults>"
            "</w:styles>"
        )

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("_rels/.rels", rels)
            archive.writestr("word/document.xml", document_xml)
            archive.writestr("word/_rels/document.xml.rels", document_rels)
            archive.writestr("word/styles.xml", styles_xml)
            for index, (rid, ext, data) in enumerate(images):
                archive.writestr(f"word/media/image_{index + 1}.{ext}", data)
        return buffer.getvalue()


html_docx_builder = HtmlDocxBuilder()


def build_docx(html_text: str) -> bytes:
    """把打印模板渲染出的 HTML 转成 .docx 字节。"""
    return html_docx_builder.build(html_text)
