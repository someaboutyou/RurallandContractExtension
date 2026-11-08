"""村组公示公告（村组公告表）导出。

对齐 CS 版「承包台账 → 调查报表 → 导出村组公示公告」：

- 一个发包方（村民小组）一份公告，正文统计该组承包方户数、宗地块数与确权总面积；
- 公告日期 / 截止日期 / 盖章单位 / 地址由导出对话框传入（CS 版
  「公示公告信息设置」同款字段）；
- 标题固定为「{单位全称}农村土地承包经营权确权登记颁证第一轮公示公告」，
  正文字号、行距、首行缩进按 CS 样张（宋体小四、两倍行距、两端对齐）。

Word 仍走 ``html_docx``（HTML 母版 → .docx），不依赖 Office。
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

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

#: 与 CS 版样张一致的页面与正文样式。
_PAGE_CSS = """
@page { size: A4; margin: 32mm 26mm; }
body { font-family: SimSun, "宋体", serif; font-size: 16pt; line-height: 2; color: #000; }
h1 { font-family: SimHei, "黑体", sans-serif; font-size: 22pt; font-weight: bold;
     text-align: center; line-height: 1.5; margin: 0 0 30pt; }
p.body { text-indent: 2em; text-align: justify; margin: 0 0 12pt; }
p.gap { margin: 0 0 48pt; }
p.sign { text-align: right; text-indent: 0; margin: 0 0 4pt; }
"""


def _text(value) -> str:
    return str(value if value is not None else "").strip()


def _region_parts(full_name: str) -> list[str]:
    return [part.strip() for part in re.split(r"[/、]", full_name or "") if part.strip()]


def _chinese_date(value: date) -> str:
    return f"{value.year} 年 {value.month} 月 {value.day} 日"


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
        stamp_unit = f"{village_name}村委会"
        unit_name = (
            group_region.name if group_region is not None else name
        )
        group_short = unit_name
        for prefix in (county, town):
            if prefix and group_short.startswith(prefix):
                group_short = group_short[len(prefix):]
        return {
            "code": code,
            "tenantCode": tenant_code or "",
            "name": name,
            "address": address,
            "unitName": unit_name,
            "groupName": group_short or name,
            "stampUnit": stamp_unit,
            "requestAddress": f"{stamp_unit}(地址:{village_display}委会)",
        }

    def defaults(self, db: Session, code: str) -> dict:
        """导出对话框默认值（盖章单位、地址由村组层级推导，可人工修改）。"""
        meta = self._issuer_meta(db, code)
        today = date.today()
        return {
            **meta,
            "announceDate": today.isoformat(),
            "endDate": today.isoformat(),
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
        body = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{_PAGE_CSS}</style></head><body><div class="page">
<h1>{unit_name}农村土地承包经营权确权登记颁证第一轮公示公告</h1>
<p class="body">{unit_name}农村土地承包经营权确权登记资料已经我村民小组审核完毕，现予以公示公告。我村民小组共计 {households} 户，共计宗地 {parcels} 块，总面积 {area_text} 亩。详见{group_name}农村土地承包权经营权调查信息公示表和公示图。</p>
<p class="body">对公示内容有异议的单位或个人，请于 {_chinese_date(end_date)}前，以书面形式向{address.strip()}提出申请，逾期没有提出异议的，将按公示内容予以确认。</p>
<p class="gap">&nbsp;</p>
<p class="sign">{stamp}（盖章）</p>
<p class="sign">{_chinese_date(announce_date)}</p>
</div></body></html>"""
        content = html_docx.build_docx(body)
        filename = _UNSAFE_FILENAME.sub(
            "_", f"{group_name}农村土地承包经营权村组公示公告.docx"
        )
        return filename, content


village_announcement_export_service = VillageAnnouncementExportService()
