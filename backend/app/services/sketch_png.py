"""承包地块示意图页 → PNG 整页渲染（合同 Word 导出用）。

打印版式的示意图页是浏览器端 JS 现场画的 SVG（``contract.html`` 内嵌脚本），
``html_docx`` 无法转写 SVG，整页导出后只剩空白框。这里用 Pillow 按**同一版式**
逐像素复刻整页（版式基准 = ``contract.html`` 的 ``sketch-*`` CSS，96dpi px 坐标
再按 ``SCALE`` 放大渲染）：

* 横版 A4（297×210mm），内框 sheet = 标题栏 + 内容区 + 页脚；
* 首页 = 左列（地块总览图 + 指北针 + 承包方信息表）+ 右侧 3×2 地块小图；
* 续页 = 4×2 地块小图；每格含四邻标注（东西向竖排）与「编码：面积亩」角标。

几何映射与前端 JS 完全同构：GeoJSON 环 → 共享/独立包围盒 → 等比缩放居中
（viewBox 0 0 1000 1000 + preserveAspectRatio meet 的两步映射）。

⚠️ 坐标约定：**所有布局计算一律用 CSS px（96dpi）**，只在调用 PIL 画图前
乘 ``SCALE``。任何一处提前乘了 SCALE 都会导致二次放大、内容跑出画布。
渲染失败时调用方应整页摘除兜底，不得让 Word 导出中断。
"""

from __future__ import annotations

import io
import json
import math
import os

from PIL import Image, ImageDraw, ImageFont
from lxml import html as lxml_html

# ── 版式常量（CSS px @96dpi，与 contract.html 的 sketch-* 规则一一对应） ──

PX_PER_MM = 96.0 / 25.4

PAGE_W = 1122.5          # 297mm
PAGE_H = 793.7           # 210mm
SHEET_X = 50.0           # .sketch-page padding: 100px 50px 0
SHEET_Y = 100.0
SHEET_W = PAGE_W - 2 * SHEET_X   # 1022.5
TITLE_H = 48.0           # .sketch-sheet grid-template-rows: 48px 530px 22px
CONTENT_H = 530.0
FOOTER_H = 22.0
OVERVIEW_W = 90.0 * PX_PER_MM    # .sketch-content.first: 90mm 1fr
INFO_H = 44.0 * PX_PER_MM        # .overview-column rows: 1fr 44mm
INFO_ROWS = 4
INFO_TH_W = 37.0 * PX_PER_MM     # .info-table th width
INFO_ROW_H = INFO_H / INFO_ROWS  # 11mm ≈ 41.6px
MAP_PAD_TB = 6.0 * PX_PER_MM     # .overview-map padding: 6mm 5mm
MAP_PAD_LR = 5.0 * PX_PER_MM
ARROW_W = 9.0 * PX_PER_MM        # .north-arrow width/height
ARROW_H = 15.0 * PX_PER_MM
ARROW_RIGHT = 4.0 * PX_PER_MM
ARROW_BOTTOM = 5.0 * PX_PER_MM
PLOT_INSET = 8.0 * PX_PER_MM     # .plot-map inset 8mm
FOOTER_PAD = 1.5 * PX_PER_MM     # .sketch-footer > div padding 0 1.5mm
NEIGHBOR_N_TOP = 4.0 * PX_PER_MM     # .neighbor.north top
NEIGHBOR_S_BOTTOM = 3.5 * PX_PER_MM  # .neighbor.south bottom
NEIGHBOR_WE_INSET = 2.0 * PX_PER_MM  # .neighbor.west/east left/right
NEIGHBOR_MAX_RATIO = 0.43            # .neighbor max-width 43%
UNIT_CELL_W = 11.0 * PX_PER_MM       # 信息表末格（块/亩）宽
CELL_PAD_LR = 2.0 * PX_PER_MM        # th/td 水平 padding

COLOR_PLOT = (0, 0, 255)         # .plot-svg .parcel-line #0000ff
COLOR_OVERVIEW = (88, 183, 255)  # .overview-svg .parcel-line #58b7ff
COLOR_HIGHLIGHT = (255, 45, 45)  # .highlight-line #ff2d2d
COLOR_LINE = (0, 0, 0)

#: 渲染放大倍数（2.5 × 96dpi ≈ 240dpi，足够 Word 打印清晰）
SCALE = 2.5

_FONT_DIRS = [
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
]


def _load_font(names: list[str], size_css_px: float):
    """按候选文件名加载字体（尺寸按 SCALE 放大）；全缺时回落 PIL 默认。"""
    size = max(1, round(size_css_px * SCALE))
    for name in names:
        for directory in _FONT_DIRS:
            path = os.path.join(directory, name)
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
    try:
        return ImageFont.load_default(size)
    except TypeError:  # 旧版 Pillow 的 load_default 不带 size
        return ImageFont.load_default()


def _text_font(size_css_px: float = 13.0):
    return _load_font(["simsun.ttc", "msyh.ttc", "arial.ttf"], size_css_px)


def _title_font(size_css_px: float = 24.0):
    return _load_font(["simhei.ttf", "msyhbd.ttc", "simsun.ttc"], size_css_px)


def _info_font(size_css_px: float = 14.0):
    return _load_font(["simsun.ttc", "msyh.ttc"], size_css_px)


def _mono_font(size_css_px: float = 13.0):
    return _load_font(["cour.ttf", "consola.ttf", "arial.ttf"], size_css_px)


# ── 几何映射（与 contract.html 内嵌 JS 同构） ─────────────────────────────


def _parse_geo(value):
    """镜像前端 parseData：字符串形式的 JSON 也解一层；接受对象或数组。"""
    if value is None or value == "null" or value == "":
        return None
    data = value
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            return None
    if isinstance(data, str) and data.strip().startswith(("{", "[")):
        try:
            data = json.loads(data)
        except ValueError:
            return None
    return data if isinstance(data, (dict, list)) else None


def _collect_rings(geometry, rings: list) -> list:
    if not isinstance(geometry, dict):
        return rings
    kind = geometry.get("type")
    if kind == "Feature":
        return _collect_rings(geometry.get("geometry"), rings)
    if kind == "FeatureCollection":
        for feature in geometry.get("features") or []:
            _collect_rings(feature, rings)
        return rings
    if kind == "GeometryCollection":
        for item in geometry.get("geometries") or []:
            _collect_rings(item, rings)
        return rings
    if kind == "Polygon":
        rings.extend(geometry.get("coordinates") or [])
        return rings
    if kind == "MultiPolygon":
        for polygon in geometry.get("coordinates") or []:
            rings.extend(polygon or [])
    return rings


def _bounds_for(rings: list):
    min_x = min_y = math.inf
    max_x = max_y = -math.inf
    for ring in rings:
        for point in ring or []:
            try:
                x, y = float(point[0]), float(point[1])
            except (TypeError, ValueError, IndexError):
                continue
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if not math.isfinite(min_x):
        return None
    if max_x == min_x:
        max_x += 1
    if max_y == min_y:
        max_y += 1
    return (min_x, min_y, max_x, max_y)


def _ring_to_box(ring, bounds, box_w: float, box_h: float, padding_css: float) -> list[tuple[float, float]]:
    """GeoJSON 环 → 盒子（CSS px）内的折线，y 翻转、等比居中。

    与浏览器两步映射等效：
    1. JS ``pathForRing``：等比缩进 viewBox 0 0 1000 1000（含 padding、y 翻转）；
    2. SVG ``preserveAspectRatio: xMidYMid meet``：viewBox 等比贴进盒子并居中。
    JS 的 viewBox padding ``p`` 单位贴进 ``min(box_w, box_h)`` 后 ≈
    ``p * min(box_w, box_h) / 1000`` 个 CSS px —— 调用方按此换算传入。
    """
    min_x, min_y, max_x, max_y = bounds
    dx, dy = max_x - min_x, max_y - min_y
    inner_w = box_w - 2 * padding_css
    inner_h = box_h - 2 * padding_css
    if inner_w <= 0 or inner_h <= 0:
        return []
    scale = min(inner_w / dx, inner_h / dy)
    offset_x = (box_w - dx * scale) / 2
    offset_y = (box_h - dy * scale) / 2
    points = []
    for point in ring or []:
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError, IndexError):
            continue
        px = offset_x + (x - min_x) * scale
        py = offset_y + (max_y - y) * scale  # y 翻转
        points.append((px, py))
    return points


def _draw_polyline_css(draw, points_css, color, width_css: float) -> None:
    """CSS px 折线 → 放大绘制（闭环）。这是唯一做 px→render 换算的画线入口。"""
    if len(points_css) < 2:
        return
    scaled = [(x * SCALE, y * SCALE) for x, y in points_css]
    scaled.append(scaled[0])
    draw.line(scaled, fill=color, width=max(1, round(width_css * SCALE)), joint="curve")


def _px(value_css: float) -> float:
    return value_css * SCALE


# ── HTML 解析：从渲染好的合同 HTML 里抽出每页示意图的数据 ─────────────────


def _has_class(element, name: str) -> bool:
    return name in (element.get("class") or "").split()


def _find_class(element, name: str):
    for node in element.iter():
        if isinstance(node.tag, str) and _has_class(node, name):
            return node
    return None


def _find_all_class(element, name: str) -> list:
    return [
        node
        for node in element.iter()
        if isinstance(node.tag, str) and _has_class(node, name)
    ]


def _text_of(element) -> str:
    if element is None:
        return ""
    return (element.text_content() or "").replace("\u00a0", " ").strip()


def parse_sketch_sections(html_text: str) -> list[dict]:
    """抽出每个 ``.sketch-page`` 的渲染数据（几何 / 四邻 / 页脚 / 信息表）。"""
    document = lxml_html.fromstring(html_text)
    pages: list[dict] = []
    for section in document.xpath(
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' sketch-page ')]"
    ):
        page: dict = {"footer": [], "cells": [], "info_rows": [], "overview": None}

        title = _find_class(section, "sketch-title")
        page["title"] = _text_of(title)

        footer = _find_class(section, "sketch-footer")
        if footer is not None:
            page["footer"] = [_text_of(child) for child in footer if isinstance(child.tag, str)]

        info_table = _find_class(section, "info-table")
        if info_table is not None:
            for tr in info_table.iter("tr"):
                row = [
                    _text_of(cell)
                    for cell in tr
                    if isinstance(cell.tag, str) and (cell.tag in ("th", "td"))
                ]
                if row:
                    page["info_rows"].append(row)

        overview_node = None
        for node in _find_all_class(section, "js-geo-map"):
            if (node.get("data-map-kind") or "") == "overview":
                overview_node = node
                break
        if overview_node is not None:
            page["overview"] = {
                "plots": _parse_geo(overview_node.get("data-plots")) or [],
                "highlight": _parse_geo(overview_node.get("data-highlight-plots")) or [],
            }

        for cell in _find_all_class(section, "plot-cell"):
            if _has_class(cell, "empty-cell"):
                continue
            entry: dict = {"north": "", "south": "", "west": "", "east": "", "label": ""}
            for neighbor in cell.iter():
                if not isinstance(neighbor.tag, str) or not _has_class(neighbor, "neighbor"):
                    continue
                classes = (neighbor.get("class") or "").split()
                for side in ("north", "south", "west", "east"):
                    if side in classes:
                        entry[side] = _text_of(neighbor)
            map_node = _find_class(cell, "js-geo-map")
            if map_node is not None:
                entry["geometry"] = _parse_geo(map_node.get("data-geometry"))
            label = _find_class(cell, "plot-label")
            entry["label"] = _text_of(label)
            page["cells"].append(entry)

        pages.append(page)
    return pages


# ── 文本绘制助手（坐标一律 CSS px，内部乘 SCALE） ─────────────────────────


def _wrap_text(text: str, font, max_width_css: float) -> list[str]:
    """CJK 按字折行（与 CSS word-break: break-all 一致）。宽度按渲染 px 量。"""
    lines: list[str] = []
    current = ""
    for char in text:
        if char == "\n":
            lines.append(current)
            current = ""
            continue
        candidate = current + char
        if font.getlength(candidate) <= max_width_css * SCALE or not current:
            current = candidate
        else:
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines or [""]


def _draw_mixed(draw, x_css: float, y_css: float, text, ascii_font, cjk_font, fill=COLOR_LINE):
    """ASCII 走等宽字体、CJK 走中文字体，逐字排版（复刻浏览器字体回退）。"""
    x = _px(x_css)
    y = _px(y_css)
    for char in text:
        font = cjk_font if ord(char) > 0x2E7F else ascii_font
        draw.text((x, y), char, font=font, fill=fill)
        x += font.getlength(char)


def _mixed_width(text, ascii_font, cjk_font) -> float:
    return sum(
        (cjk_font if ord(ch) > 0x2E7F else ascii_font).getlength(ch) for ch in text
    ) / SCALE


def _draw_centered_mixed(draw, cx_css, cy_css, text, ascii_font, cjk_font, fill=COLOR_LINE):
    total = _mixed_width(text, ascii_font, cjk_font)
    _draw_mixed(draw, cx_css - total / 2, cy_css, text, ascii_font, cjk_font, fill)


def _draw_vertical_text(draw, cx_css, cy_css, text, font, fill=COLOR_LINE):
    """竖排（writing-mode: vertical-rl + upright）：逐字下排，整块垂直居中。"""
    step = font.size / SCALE
    total_h = step * len(text)
    y = cy_css - total_h / 2
    for char in text:
        draw.text(
            (_px(cx_css - font.getlength(char) / SCALE / 2), _px(y)),
            char,
            font=font,
            fill=fill,
        )
        y += step


def _draw_north_arrow(draw, right_x_css: float, bottom_y_css: float):
    """指北针：圆 + 空心箭头 + 中线（对应模板里的静态 SVG，viewBox 0 0 40 66）。"""
    w, h = ARROW_W, ARROW_H
    x1 = right_x_css - w
    y1 = bottom_y_css - h
    width = max(1, round(2 * SCALE))
    cx = _px(x1 + w / 2)
    circle_cy = _px(y1 + (43 / 66) * h)
    circle_r = (16 / 66) * h * SCALE
    draw.ellipse(
        (cx - circle_r, circle_cy - circle_r, cx + circle_r, circle_cy + circle_r),
        outline=COLOR_LINE,
        width=width,
    )
    arrow = [
        (_px(x1 + (20 / 40) * w), _px(y1 + (2 / 66) * h)),
        (_px(x1 + (31 / 40) * w), _px(y1 + (57 / 66) * h)),
        (_px(x1 + (20 / 40) * w), _px(y1 + (47 / 66) * h)),
        (_px(x1 + (9 / 40) * w), _px(y1 + (57 / 66) * h)),
        (_px(x1 + (20 / 40) * w), _px(y1 + (2 / 66) * h)),
    ]
    draw.line(arrow, fill=COLOR_LINE, width=width, joint="curve")
    draw.line((cx, _px(y1 + (8 / 66) * h), cx, _px(y1 + (47 / 66) * h)), fill=COLOR_LINE, width=width)
    draw.text(
        (cx, _px(y1)),
        "N",
        font=_load_font(["arial.ttf", "cour.ttf"], 12),
        fill=COLOR_LINE,
        anchor="ms",
    )


def _draw_map_box(draw, geometry_list, highlight_list, box, *, padding_css,
                  plot_width, overview_width=None):
    """在盒子里画地块折线（box = (x, y, w, h)，CSS px）。

    共享包围盒（总览图）或独立包围盒（单地块小格）；
    ``overview_width`` 为 None 时按单地块模式画蓝线，否则总览浅蓝 + 高亮红。
    """
    x0, y0, box_w, box_h = box
    rings: list = []
    for geometry in geometry_list:
        _collect_rings(geometry, rings)
    hl_rings: list = []
    for geometry in highlight_list:
        _collect_rings(geometry, hl_rings)
    bounds = _bounds_for(rings + hl_rings)
    if bounds is None:
        return

    def offset_points(ring):
        points = _ring_to_box(ring, bounds, box_w, box_h, padding_css)
        return [(x0 + px, y0 + py) for px, py in points]

    if overview_width is None:
        for ring in rings:
            _draw_polyline_css(draw, offset_points(ring), COLOR_PLOT, plot_width)
    else:
        for ring in rings:
            _draw_polyline_css(draw, offset_points(ring), COLOR_OVERVIEW, overview_width)
        for ring in hl_rings:
            _draw_polyline_css(draw, offset_points(ring), COLOR_HIGHLIGHT, plot_width)


def _draw_plot_cell(draw, cell: dict, x0: float, y0: float, w: float, h: float, body_font):
    """一个地块小格（坐标 CSS px）：边框 + 四邻标注 + 地块折线 + 中央角标。

    格线直接画满格（相邻格共边重叠 1px，与 CSS 每格 border-right/bottom 视觉一致）。
    """
    draw.rectangle((_px(x0), _px(y0), _px(x0 + w), _px(y0 + h)), outline=COLOR_LINE, width=1)

    # 地块折线（inset 8mm；padding 与 JS 的 viewBox 10 单位等效换算）
    map_w = w - 2 * PLOT_INSET
    map_h = h - 2 * PLOT_INSET
    geometry = cell.get("geometry")
    if geometry:
        _draw_map_box(
            draw,
            [geometry],
            [],
            (x0 + PLOT_INSET, y0 + PLOT_INSET, max(1.0, map_w), max(1.0, map_h)),
            padding_css=10 * min(map_w, map_h) / 1000,
            plot_width=1.6,
        )

    # 四邻标注
    north = cell.get("north") or ""
    south = cell.get("south") or ""
    west = cell.get("west") or ""
    east = cell.get("east") or ""
    line_step = body_font.size / SCALE * 1.15
    if north:
        ty = y0 + NEIGHBOR_N_TOP
        for line in _wrap_text(north, body_font, w * NEIGHBOR_MAX_RATIO):
            draw.text(
                (_px(x0 + w / 2), _px(ty)),
                line,
                font=body_font,
                fill=COLOR_LINE,
                anchor="ma",
            )
            ty += line_step
    if south:
        lines = _wrap_text(south, body_font, w * NEIGHBOR_MAX_RATIO)
        ty = y0 + h - NEIGHBOR_S_BOTTOM - line_step * len(lines)
        for line in lines:
            draw.text(
                (_px(x0 + w / 2), _px(ty)),
                line,
                font=body_font,
                fill=COLOR_LINE,
                anchor="ma",
            )
            ty += line_step
    if west:
        _draw_vertical_text(draw, x0 + NEIGHBOR_WE_INSET + body_font.size / SCALE / 2, y0 + h / 2, west, body_font)
    if east:
        _draw_vertical_text(draw, x0 + w - NEIGHBOR_WE_INSET - body_font.size / SCALE / 2, y0 + h / 2, east, body_font)

    # 中央角标「编码：面积亩」（打印件背景是 65% 白，视觉接近纯白留白）
    label = cell.get("label") or ""
    if label:
        mono = _mono_font()
        total = _mixed_width(label, mono, body_font)
        bg_h = body_font.size / SCALE + 2
        draw.rectangle(
            (
                _px(x0 + w / 2 - total / 2 - 2), _px(y0 + h / 2 - bg_h / 2),
                _px(x0 + w / 2 + total / 2 + 2), _px(y0 + h / 2 + bg_h / 2),
            ),
            fill=(255, 255, 255),
        )
        _draw_centered_mixed(draw, x0 + w / 2, y0 + h / 2, label, mono, body_font)


def render_sketch_page_png(page: dict) -> bytes:
    """一页示意图数据 → 整页 PNG（横版 A4，240dpi）。"""
    width = round(PAGE_W * SCALE)
    height = round(PAGE_H * SCALE)
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    body_font = _text_font()
    title_font = _title_font()
    info_font = _info_font()

    # 内框 sheet（CSS px 布局）
    sheet_x, sheet_y = SHEET_X, SHEET_Y
    sheet_w = SHEET_W
    sheet_h = TITLE_H + CONTENT_H + FOOTER_H
    draw.rectangle(
        (_px(sheet_x), _px(sheet_y), _px(sheet_x + sheet_w), _px(sheet_y + sheet_h)),
        outline=COLOR_LINE,
        width=round(SCALE),
    )

    # 标题栏
    title_bottom = sheet_y + TITLE_H
    draw.line(
        (_px(sheet_x), _px(title_bottom), _px(sheet_x + sheet_w), _px(title_bottom)),
        fill=COLOR_LINE,
        width=round(SCALE),
    )
    title = page.get("title") or "承包地块示意图"
    draw.text(
        (_px(sheet_x + sheet_w / 2), _px(sheet_y + TITLE_H / 2)),
        title,
        font=title_font,
        fill=COLOR_LINE,
        anchor="mm",
    )

    content_y = title_bottom
    content_h = CONTENT_H
    cells = page.get("cells") or []
    first_page = bool(page.get("info_rows") or page.get("overview"))
    frame_w = max(1, round(SCALE))

    if first_page:
        col_w = OVERVIEW_W
        # 左列右边框
        draw.line(
            (_px(sheet_x + col_w), _px(content_y), _px(sheet_x + col_w), _px(content_y + content_h)),
            fill=COLOR_LINE,
            width=frame_w,
        )

        # 总览区（上）：地块折线（浅蓝 + 高亮红）+ 指北针
        overview_h = content_h - INFO_H
        map_x = sheet_x + MAP_PAD_LR
        map_y = content_y + MAP_PAD_TB
        map_w = col_w - 2 * MAP_PAD_LR - 1
        map_h = overview_h - 2 * MAP_PAD_TB
        overview = page.get("overview") or {}
        plot_geoms = [
            item.get("geometry") or item.get("geojson")
            for item in (overview.get("plots") or [])
            if isinstance(item, dict)
        ]
        highlight_geoms = [
            item.get("geometry") or item.get("geojson")
            for item in (overview.get("highlight") or [])
            if isinstance(item, dict)
        ]
        _draw_map_box(
            draw,
            [g for g in plot_geoms if g],
            [g for g in highlight_geoms if g],
            (map_x, map_y, max(1.0, map_w), max(1.0, map_h)),
            padding_css=28 * min(map_w, map_h) / 1000,
            plot_width=1.4,
            overview_width=0.75,
        )
        _draw_north_arrow(draw, sheet_x + col_w - ARROW_RIGHT, content_y + overview_h - ARROW_BOTTOM)

        # 信息表（下）：固定 4 行 × 11mm，行数据不足补空行
        table_y = content_y + overview_h
        th_w = INFO_TH_W
        rows = list(page["info_rows"][:INFO_ROWS])
        while len(rows) < INFO_ROWS:
            rows.append([])
        for index, row in enumerate(rows):
            top = table_y + INFO_ROW_H * index
            bottom = top + INFO_ROW_H
            # th 格
            draw.rectangle((_px(sheet_x), _px(top), _px(sheet_x + th_w), _px(bottom)), outline=COLOR_LINE, width=1)
            if row:
                draw.text(
                    (_px(sheet_x + CELL_PAD_LR), _px(top + INFO_ROW_H / 2)),
                    row[0],
                    font=info_font,
                    fill=COLOR_LINE,
                    anchor="lm",
                )
            # td 区
            td_x0 = sheet_x + th_w
            td_x1 = sheet_x + col_w - 1
            draw.line((_px(td_x1), _px(top), _px(td_x1), _px(bottom)), fill=COLOR_LINE, width=1)
            if index == 0:
                draw.line((_px(td_x0), _px(top), _px(td_x1), _px(top)), fill=COLOR_LINE, width=1)
            if index < INFO_ROWS - 1:
                draw.line((_px(td_x0), _px(bottom), _px(td_x1), _px(bottom)), fill=COLOR_LINE, width=1)
            values = row[1:]
            if not values:
                continue
            if len(values) >= 2:
                # 末格是单位格（块 / 亩）：右对齐，前值合并显示
                unit = values[-1]
                value = "".join(values[:-1])
                unit_x0 = td_x1 - UNIT_CELL_W
                draw.line((_px(unit_x0), _px(top), _px(unit_x0), _px(bottom)), fill=COLOR_LINE, width=1)
                draw.text(
                    (_px(td_x1 - CELL_PAD_LR), _px(top + INFO_ROW_H / 2)),
                    unit,
                    font=info_font,
                    fill=COLOR_LINE,
                    anchor="rm",
                )
                draw.text(
                    (_px(td_x0 + CELL_PAD_LR), _px(top + INFO_ROW_H / 2)),
                    value,
                    font=info_font,
                    fill=COLOR_LINE,
                    anchor="lm",
                )
            else:
                draw.text(
                    (_px(td_x0 + CELL_PAD_LR), _px(top + INFO_ROW_H / 2)),
                    values[0],
                    font=info_font,
                    fill=COLOR_LINE,
                    anchor="lm",
                )

        # 右侧地块格：3 列 × 2 行（⚠️ 空位不画边框 —— 模板续页不补 empty-cell，
        # 打印件空位就是留白；首页有 padding 补齐循环，实际满格）
        grid_x0 = sheet_x + col_w + 1
        grid_w = sheet_w - col_w - 1
        cols, rows_n = 3, 2
        cell_w = grid_w / cols
        cell_h = content_h / rows_n
        for index, cell in enumerate(cells[: cols * rows_n]):
            col, row = index % cols, index // cols
            _draw_plot_cell(
                draw, cell,
                grid_x0 + col * cell_w, content_y + row * cell_h,
                cell_w, cell_h,
                body_font,
            )
    else:
        # 续页：4 列 × 2 行（同样只画有数据的格子）
        cols, rows_n = 4, 2
        cell_w = sheet_w / cols
        cell_h = content_h / rows_n
        for index, cell in enumerate(cells[: cols * rows_n]):
            col, row = index % cols, index // cols
            _draw_plot_cell(
                draw, cell,
                sheet_x + col * cell_w, content_y + row * cell_h,
                cell_w, cell_h,
                body_font,
            )

    # 页脚：4 等分，竖线分隔，末格居中
    footer_y = content_y + content_h
    footer_texts = (page.get("footer") or ["", "", "", ""])[:4]
    while len(footer_texts) < 4:
        footer_texts.append("")
    foot_w = sheet_w / 4
    for index, text in enumerate(footer_texts):
        x0 = sheet_x + index * foot_w
        if index:
            draw.line((_px(x0), _px(footer_y), _px(x0), _px(footer_y + FOOTER_H)), fill=COLOR_LINE, width=1)
        if index == 3:
            draw.text(
                (_px(x0 + foot_w / 2), _px(footer_y + FOOTER_H / 2)),
                text,
                font=body_font,
                fill=COLOR_LINE,
                anchor="mm",
            )
        else:
            draw.text(
                (_px(x0 + FOOTER_PAD), _px(footer_y + FOOTER_H / 2)),
                text,
                font=body_font,
                fill=COLOR_LINE,
                anchor="lm",
            )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
