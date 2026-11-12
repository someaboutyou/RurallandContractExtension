"""村组公示公告（村组公告表）导出。

对齐 CS 版「承包台账 → 调查报表 → 导出村组公示公告」：

- 一个发包方（村民小组）一份公告，正文统计该组承包方户数、宗地块数与确权总面积；
- 公告日期 / 截止日期 / 盖章单位 / 地址由导出对话框传入（CS 版
  「公示公告信息设置」同款字段）；
- 标题固定为「{单位全称}农村土地承包经营权确权登记颁证第一轮公示公告」，
  版式复刻甲方样张（标题方正小标宋 22pt、正文仿宋 16pt、首行缩进两字符、
  1.5 倍 / 固定 33pt 行距），全部样式在打印模板里维护。

Word 仍走 ``html_docx``（HTML 母版 ``app/templates/village_announcement.html``
→ .docx），不依赖 Office。
"""

from __future__ import annotations

import re
import calendar
from datetime import date
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.fbf import Fbf
from app.models.region import Region
from app.models.survey import SurveyCbdkxxResult, SurveyCbfResult, SurveyFbfResult
from app.services import html_docx

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|]')

#: 版式统一收敛到打印模板（2026-11-12：原先内联手搓 HTML 不走母版，
#: @page/.page 几何、行距、text-indent 全部被 html_docx 丢弃，样式怪异）。
_TEMPLATE = Environment(
    loader=FileSystemLoader(str(Path(__file__).resolve().parent.parent / "templates")),
    autoescape=False,
).get_template("village_announcement.html")


def _text(value) -> str:
    return str(value if value is not None else "").strip()


def _region_parts(full_name: str) -> list[str]:
    return [part.strip() for part in re.split(r"[/、]", full_name or "") if part.strip()]


def _chinese_date(value: date) -> str:
    return f"{value.year} 年 {value.month} 月 {value.day} 日"


def _compact_date(value: date) -> str:
    return f"{value.year}年{value.month}月{value.day}日"


def _add_months(value: date, months: int) -> date:
    """加 N 个月，月末溢出自动收敛（1 月 31 日 + 1 月 → 2 月末）。"""
    index = value.month - 1 + months
    year = value.year + index // 12
    month = index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(value.day, last_day))


def _ends_with_committee(text: str) -> bool:
    """区域名是否已自带「委员会 / 村委会 / 委会」类后缀。"""
    return text.endswith(("委员会", "村委会", "委会"))


def _with_committee(village_name: str) -> str:
    """盖章单位：区域名已带委员会后缀则原样用，否则补「村委会」。

    区域表村级的 name 存的是「XX村村民委员会」这类全称（相对名口径），
    直接拼「村委会」会出现「XX村村民委员会村委会」。
    """
    name = village_name.strip()
    if _ends_with_committee(name):
        return name
    return f"{name}村委会"


class VillageAnnouncementExportService:
    def _issuer_meta(self, db: Session, code: str) -> dict:
        """发包方与所属村组信息（优先主表 fbf，其次调查成果表）。"""
        fbf = db.get(Fbf, code)
        tenant_code = getattr(fbf, "tenant_code", None)
        if fbf is None:
            survey_issuer = db.scalars(
                select(SurveyFbfResult)
                .where(SurveyFbfResult.fbfbm == code)
                .order_by(SurveyFbfResult.id.desc())
            ).first()
            if survey_issuer is not None:
                tenant_code = survey_issuer.tenant_code
            name = survey_issuer.fbfmc if survey_issuer else code
            address = survey_issuer.fbfdz if survey_issuer else ""
        else:
            name = fbf.fbfmc or code
            address = fbf.fbfdz or ""

        group_region = db.scalars(
            select(Region).where(Region.code == code[:14])
        ).first()
        village_region = None
        if group_region is not None and group_region.parent_id:
            village_region = db.get(Region, group_region.parent_id)
        village_name = (
            village_region.name if village_region is not None else name
        )
        full_parts = _region_parts(
            village_region.full_name if village_region is not None else ""
        )
        county = next((part for part in full_parts if part.endswith("县")), "")
        town = next(
            (part for part in full_parts if part.endswith(("镇", "乡", "街道"))), ""
        )
        village_display = f"{county}{town}{village_name}"
        stamp_unit = _with_committee(village_name)
        unit_name = (
            group_region.name if group_region is not None else name
        )
        group_short = unit_name
        for prefix in (county, town):
            if prefix and group_short.startswith(prefix):
                group_short = group_short[len(prefix):]
        address_display = (
            village_display
            if _ends_with_committee(village_display)
            else f"{village_display}委会"
        )
        return {
            "code": code,
            "tenantCode": tenant_code or "",
            "name": name,
            "address": address,
            "unitName": unit_name,
            "groupName": group_short or name,
            "stampUnit": stamp_unit,
            "requestAddress": f"{stamp_unit}(地址:{address_display})",
        }

    def defaults(self, db: Session, code: str) -> dict:
        """导出对话框默认值（盖章单位、地址由村组层级推导，可人工修改）。"""
        meta = self._issuer_meta(db, code)
        today = date.today()
        return {
            **meta,
            "announceDate": today.isoformat(),
            "endDate": _add_months(today, 1).isoformat(),
        }

    def export(
        self,
        db: Session,
        code: str,
        announce_date: date,
        end_date: date,
        stamp_unit: str,
        address: str,
    ) -> tuple[str, bytes]:
        meta = self._issuer_meta(db, code)
        tenant_code = meta["tenantCode"]

        conditions = [SurveyCbdkxxResult.fbfbm == code]
        if tenant_code:
            conditions.append(SurveyCbdkxxResult.tenant_code == tenant_code)
        households, parcels, area = db.execute(
            select(
                func.count(func.distinct(SurveyCbdkxxResult.cbfbm)),
                func.count(SurveyCbdkxxResult.id),
                func.coalesce(
                    func.sum(
                        func.coalesce(
                            SurveyCbdkxxResult.htmjm,
                            SurveyCbdkxxResult.yhtmjm,
                            0,
                        )
                    ),
                    0,
                ),
            ).where(*conditions)
        ).one()
        if not parcels:
            contractor_conditions = [SurveyCbfResult.cbfbm.like(f"{code}%")]
            if tenant_code:
                contractor_conditions.append(SurveyCbfResult.tenant_code == tenant_code)
            households = db.scalar(
                select(func.count(func.distinct(SurveyCbfResult.cbfbm))).where(
                    *contractor_conditions
                )
            ) or 0
        total_area = float(Decimal(str(area or 0)))
        area_text = f"{total_area:.2f}".rstrip("0").rstrip(".") or "0"

        unit_name = meta["unitName"]
        group_name = meta["groupName"]
        stamp = stamp_unit.strip()
        body = _TEMPLATE.render(
            unit_name=unit_name,
            group_name=group_name,
            stamp_unit=stamp,
            address=address.strip(),
            households=households,
            parcels=parcels,
            area_text=area_text,
            end_date_cn=_chinese_date(end_date),
            announce_date_cn=_compact_date(announce_date),
        )
        content = html_docx.build_docx(body)
        filename = _UNSAFE_FILENAME.sub(
            "_", f"{group_name}农村土地承包经营权村组公示公告.docx"
        )
        return filename, content


village_announcement_export_service = VillageAnnouncementExportService()
