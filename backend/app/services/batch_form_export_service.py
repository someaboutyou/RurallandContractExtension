"""调查批次：按选中发包方批量导出调查表单。

入口在「调查批次管理 → 本批次发包方清单」下方，导出范围由前端勾选发包方决定。
Excel 表单复用现有导出/生成逻辑；Word 表单复用已复刻的 HTML 母版。
"""

from __future__ import annotations

import html
import io
import logging
import zipfile
from datetime import date, datetime
from decimal import Decimal

import xlwt
from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyBatch,
    SurveyCbfBase,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyCbdkxxResult,
    SurveyDkResult,
    SurveyFbfResult,
)
from app.models.user import User
from app.services import html_docx
from app.services.contractor_survey_docx_service import contractor_survey_docx_service
from app.services.data_access_service import data_access_service
from app.services.dictionary_service import dictionary_service
from app.services.issuer_survey_docx_service import issuer_survey_docx_service
from app.services.parcel_survey_docx_service import parcel_survey_docx_service
from app.services.survey import survey_service
from app.services.survey.excel_transfer import (
    CONTRACTOR_TYPE_LABELS,
    GENDER_LABELS,
    ID_TYPE_LABELS,
)
from app.services.survey.issuer_excel_transfer import (
    ISSUER_ID_TYPE_LABELS,
    IssuerXlsTemplate,
)

logger = logging.getLogger(__name__)

XLS_MEDIA_TYPE = "application/vnd.ms-excel"
DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
ZIP_MEDIA_TYPE = "application/zip"
SQM_PER_MU = Decimal("666.6666667")

#: 二级地类（GB/T 21010）代码 → 名称，与承包地块调查表口径一致。
TDLYLX_LABELS = {
    "011": "水田", "012": "水浇地", "013": "旱地",
    "021": "果园", "022": "茶园", "023": "其他园地",
    "031": "有林地", "032": "灌木林地", "033": "其他林地",
    "041": "天然牧草地", "042": "人工牧草地",
    "111": "设施农用地", "114": "坑塘水面", "117": "沟渠",
}

#: 延包调查信息公示表列定义（列宽单位：字符）。
#: 严格对齐 CS 版「承包台账 → 调查报表 → 延包调查信息公示表」的输出样张
#: （模板文件 Template/农村土地承包经营权调查信息公示表.xlt，共 18 列）。
DELAY_NOTICE_COLUMNS = [
    ("编号", 5), ("承包方名称", 10), ("承包方编码（缩略码）", 11), ("联系电话", 11),
    ("成员数", 6), ("姓名", 9), ("证件号码", 15), ("家庭关系", 9), ("成员备注", 9),
    ("地块名称", 10), ("地块编码", 10), ("东至", 10), ("南至", 10), ("西至", 10),
    ("北至", 10), ("合同面积", 8), ("实测面积", 8), ("地块备注", 10),
]

#: 表头分组：(标题, 起始列, 结束列)；未列出的列在表头两行纵向合并。
DELAY_NOTICE_GROUPS = [
    ("家庭成员情况（含户主）", 4, 8),
    ("农村土地承包经营权承包地块详细信息", 9, 16),
]

#: 表头两行纵向合并的列（编号、承包方名称、缩略码、联系电话、地块备注）。
DELAY_NOTICE_HEADER_MERGE_COLUMNS = {0, 1, 2, 3, 17}

#: 同一承包方多行时纵向合并的列（户级信息）。
DELAY_NOTICE_MERGE_COLUMNS = {0, 1, 2, 3, 4}

FORM_LABELS = {
    "issuer_excel": "发包方调查表（Excel）",
    "contractor_excel": "承包方调查表（Excel）",
    "parcel_excel": "承包地块调查表（Excel）",
    "notice_excel": "摸底调查公示表（Excel）",
    "delay_notice_excel": "延包调查信息公示表（Excel）",
    "baseline_excel": "摸底调查核实表（Excel）",
    "baseline_print_excel": "摸底调查核实表（打印版）",
    "issuer_word": "发包方调查表（Word）",
    "contractor_word": "承包方调查表（Word）",
    "parcel_word": "承包地块调查表（Word）",
    "public_notice_word": "公示结果归户表（Word）",
}
FORM_ORDER = list(FORM_LABELS)


def _mu(value) -> float:
    if value is None:
        return 0.0
    return round(float(Decimal(str(value)) / SQM_PER_MU), 2)


def _area_mu(mu_value, sqm_value) -> float:
    """面积取值：优先直接使用库内「亩」字段，否则由平方米换算。"""
    if mu_value is not None:
        return round(float(Decimal(str(mu_value))), 2)
    if sqm_value is not None:
        return _mu(sqm_value)
    return 0.0


def _num(value) -> float:
    try:
        return float(Decimal(str(value or 0)))
    except Exception:  # noqa: BLE001
        return 0.0


def _text(value) -> str:
    return str(value or "").strip()


class BatchFormExportService:
    def __init__(self) -> None:
        self._style_cache: dict[object, xlwt.XFStyle] = {}

    def export(
        self,
        db: Session,
        batch_id: int,
        issuer_uids: list[str],
        forms: list[str],
        current_user: User,
    ) -> tuple[str, bytes, str]:
        batch = db.get(SurveyBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="调查批次不存在")
        selected = [form for form in forms if form]
        unknown = [form for form in selected if form not in FORM_LABELS]
        if unknown:
            raise HTTPException(status_code=400, detail=f"不支持的导出表单：{'、'.join(unknown)}")
        if not selected:
            raise HTTPException(status_code=400, detail="请至少勾选一种表单")

        unique_uids = list(dict.fromkeys(str(uid).strip() for uid in issuer_uids if str(uid or "").strip()))
        issuers = db.scalars(
            select(SurveyFbfResult)
            .where(
                SurveyFbfResult.tenant_code == batch.tenant_code,
                SurveyFbfResult.issuer_uid.in_(unique_uids),
            )
            .order_by(SurveyFbfResult.fbfbm.asc())
            .execution_options(skip_tenant_scope=True)
        ).all() if unique_uids else []
        if not issuers:
            raise HTTPException(status_code=404, detail="未找到选中的发包方")
        for issuer in issuers:
            data_access_service.ensure_code_in_scope(
                current_user, issuer.fbfbm, detail="发包方不在当前数据权限范围内"
            )

        fbfbms = [issuer.fbfbm for issuer in issuers]
        like_conditions = [SurveyCbfBase.cbfbm.like(f"{code}%") for code in fbfbms if code]
        bases = db.scalars(
            select(SurveyCbfBase)
            .where(
                SurveyCbfBase.tenant_code == batch.tenant_code,
                SurveyCbfBase.batch_id == batch_id,
                or_(*like_conditions),
            )
            .order_by(SurveyCbfBase.cbfbm.asc(), SurveyCbfBase.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).all() if like_conditions else []
        uids = list(dict.fromkeys(base.contractor_uid for base in bases if base.contractor_uid))
        results = db.scalars(
            select(SurveyCbfResult)
            .where(
                SurveyCbfResult.tenant_code == batch.tenant_code,
                SurveyCbfResult.contractor_uid.in_(uids),
            )
            .order_by(SurveyCbfResult.cbfbm.asc())
            .execution_options(skip_tenant_scope=True)
        ).all() if uids else []
        members_by_uid: dict[str, list[SurveyCbfJtcyResult]] = {}
        if uids:
            for member in db.scalars(
                select(SurveyCbfJtcyResult)
                .where(
                    SurveyCbfJtcyResult.tenant_code == batch.tenant_code,
                    SurveyCbfJtcyResult.contractor_uid.in_(uids),
                )
                .order_by(SurveyCbfJtcyResult.cyxm.asc())
                .execution_options(skip_tenant_scope=True)
            ).all():
                members_by_uid.setdefault(member.contractor_uid, []).append(member)
        parcels_by_fbfbm: dict[str, list[SurveyCbdkxxResult]] = {}
        for relation in db.scalars(
            select(SurveyCbdkxxResult)
            .where(
                SurveyCbdkxxResult.tenant_code == batch.tenant_code,
                SurveyCbdkxxResult.fbfbm.in_(fbfbms),
            )
            .order_by(SurveyCbdkxxResult.cbfbm.asc(), SurveyCbdkxxResult.dkbm.asc())
            .execution_options(skip_tenant_scope=True)
        ).all():
            parcels_by_fbfbm.setdefault(relation.fbfbm, []).append(relation)
        dk_by_dkbm: dict[str, SurveyDkResult] = {}
        dkbms = [rel.dkbm for rels in parcels_by_fbfbm.values() for rel in rels]
        if dkbms:
            for parcel in db.scalars(
                select(SurveyDkResult)
                .where(
                    SurveyDkResult.tenant_code == batch.tenant_code,
                    SurveyDkResult.dkbm.in_(list(dict.fromkeys(dkbms))),
                )
                .execution_options(skip_tenant_scope=True)
            ).all():
                dk_by_dkbm[parcel.dkbm] = parcel

        files: list[tuple[str, bytes, str]] = []
        for form in FORM_ORDER:
            if form not in selected:
                continue
            if form == "issuer_excel":
                files.append((
                    f"发包方调查表_{batch.batch_no or batch_id}.xls",
                    self._issuer_workbook(issuers),
                    XLS_MEDIA_TYPE,
                ))
            elif form == "contractor_excel":
                filename, content = survey_service.export_contractors_xls(
                    db, batch_id, current_user, contractor_uids=uids
                )
                files.append((filename, content, XLS_MEDIA_TYPE))
            elif form == "parcel_excel":
                files.append((
                    f"承包地块调查表_{batch.batch_no or batch_id}.xls",
                    self._parcel_survey_workbook(issuers, results, members_by_uid, parcels_by_fbfbm, dk_by_dkbm),
                    XLS_MEDIA_TYPE,
                ))
            elif form == "notice_excel":
                files.append((
                    f"摸底调查公示表_{batch.batch_no or batch_id}.xls",
                    self._notice_workbook(issuers, results, members_by_uid, parcels_by_fbfbm, dk_by_dkbm),
                    XLS_MEDIA_TYPE,
                ))
            elif form == "delay_notice_excel":
                for issuer in issuers:
                    issuer_results = [
                        item for item in results if item.cbfbm.startswith(issuer.fbfbm)
                    ]
                    if not issuer_results:
                        continue
                    files.append((
                        f"{issuer.fbfmc}_延包调查信息公示表.xls",
                        self._delay_notice_workbook(
                            db, issuer, issuer_results,
                            members_by_uid, parcels_by_fbfbm, dk_by_dkbm,
                        ),
                        XLS_MEDIA_TYPE,
                    ))
            elif form in {"baseline_excel", "baseline_print_excel"}:
                print_version = form == "baseline_print_excel"
                files.append((
                    f"{'摸底调查核实表（打印版）' if print_version else '摸底调查核实表'}_{batch.batch_no or batch_id}.xls",
                    self.build_baseline_workbook(
                        db, issuers, results, members_by_uid, parcels_by_fbfbm, dk_by_dkbm,
                        print_version,
                    ),
                    XLS_MEDIA_TYPE,
                ))
            elif form == "issuer_word":
                for issuer in issuers:
                    try:
                        content, filename = issuer_survey_docx_service.render(
                            db, fbfbm=issuer.fbfbm, batch_id=batch_id
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("发包方调查表 Word 生成失败 fbfbm=%s", issuer.fbfbm)
                        continue
                    files.append((filename, content, DOCX_MEDIA_TYPE))
            elif form == "contractor_word":
                for result in results:
                    try:
                        content, filename = contractor_survey_docx_service.render(
                            db, cbfbm=result.cbfbm, batch_id=batch_id
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("承包方调查表 Word 生成失败 cbfbm=%s", result.cbfbm)
                        continue
                    files.append((filename, content, DOCX_MEDIA_TYPE))
            elif form == "parcel_word":
                for relations in parcels_by_fbfbm.values():
                    for relation in relations:
                        try:
                            content, filename = parcel_survey_docx_service.render(
                                db, cbfbm=relation.cbfbm, dkbm=relation.dkbm, batch_id=batch_id
                            )
                        except Exception:  # noqa: BLE001
                            logger.exception("承包地块调查表 Word 生成失败 dkbm=%s", relation.dkbm)
                            continue
                        files.append((filename, content, DOCX_MEDIA_TYPE))
            elif form == "public_notice_word":
                for result in results:
                    try:
                        content, filename = self._public_notice_docx(
                            result,
                            members_by_uid.get(result.contractor_uid, []),
                            parcels_by_fbfbm.get(result.cbfbm[:14], []),
                            dk_by_dkbm,
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("公示结果归户表 Word 生成失败 cbfbm=%s", result.cbfbm)
                        continue
                    files.append((filename, content, DOCX_MEDIA_TYPE))

        if not files:
            raise HTTPException(status_code=404, detail="没有可导出的表单数据")
        files = [(self._safe_filename(filename), content, media) for filename, content, media in files]
        if len(files) == 1:
            return files[0]
        buffer = io.BytesIO()
        seen: set[str] = set()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for filename, content, _ in files:
                archive.writestr(self._unique_name(filename, seen), content)
        zip_name = self._safe_filename(f"调查表单_{batch.region_name or batch.batch_no or batch_id}.zip")
        return zip_name, buffer.getvalue(), ZIP_MEDIA_TYPE

    @staticmethod
    def _safe_filename(filename: str) -> str:
        return (
            str(filename or "表单")
            .replace(" / ", "_")
            .replace("/", "_")
            .translate(str.maketrans({char: "_" for char in '\\:*?"<>|'}))
        )

    @staticmethod
    def _unique_name(filename: str, seen: set[str]) -> str:
        if filename not in seen:
            seen.add(filename)
            return filename
        stem, dot, suffix = filename.rpartition(".")
        index = 2
        while True:
            candidate = f"{stem}({index}){dot}{suffix}"
            if candidate not in seen:
                seen.add(candidate)
                return candidate
            index += 1

    def _style(self, bold: bool = False, wrap: bool = False) -> xlwt.XFStyle:
        key = (bold, wrap)
        cached = self._style_cache.get(key)
        if cached is not None:
            return cached
        font = xlwt.Font()
        font.name = "宋体"
        font.height = 200
        font.bold = bold
        borders = xlwt.Borders()
        borders.left = borders.right = borders.top = borders.bottom = 1
        alignment = xlwt.Alignment()
        alignment.horz = xlwt.Alignment.HORZ_CENTER
        alignment.vert = xlwt.Alignment.VERT_CENTER
        alignment.wrap = 1 if wrap else 0
        style = xlwt.XFStyle()
        style.font = font
        style.borders = borders
        style.alignment = alignment
        self._style_cache[key] = style
        return style

    def _left_style(self) -> xlwt.XFStyle:
        """左对齐带框线样式（表头单位、填表说明等）。"""
        cached = self._style_cache.get("left")
        if cached is not None:
            return cached
        font = xlwt.Font()
        font.name = "宋体"
        font.height = 200
        borders = xlwt.Borders()
        borders.left = borders.right = borders.top = borders.bottom = 1
        alignment = xlwt.Alignment()
        alignment.horz = xlwt.Alignment.HORZ_LEFT
        alignment.vert = xlwt.Alignment.VERT_CENTER
        alignment.wrap = 1
        style = xlwt.XFStyle()
        style.font = font
        style.borders = borders
        style.alignment = alignment
        self._style_cache["left"] = style
        return style

    def _title_style(self) -> xlwt.XFStyle:
        """无框线大标题样式（单户摸底调查表）。"""
        cached = self._style_cache.get("title")
        if cached is not None:
            return cached
        font = xlwt.Font()
        font.name = "宋体"
        font.height = 360
        font.bold = True
        alignment = xlwt.Alignment()
        alignment.horz = xlwt.Alignment.HORZ_CENTER
        alignment.vert = xlwt.Alignment.VERT_CENTER
        style = xlwt.XFStyle()
        style.font = font
        style.alignment = alignment
        self._style_cache["title"] = style
        return style

    def _area_style(self) -> xlwt.XFStyle:
        """面积列样式：与数据单元格一致，但固定两位小数（0.80 而非 0.8）。"""
        cached = self._style_cache.get("area")
        if cached is not None:
            return cached
        font = xlwt.Font()
        font.name = "宋体"
        font.height = 200
        borders = xlwt.Borders()
        borders.left = borders.right = borders.top = borders.bottom = 1
        alignment = xlwt.Alignment()
        alignment.horz = xlwt.Alignment.HORZ_CENTER
        alignment.vert = xlwt.Alignment.VERT_CENTER
        style = xlwt.XFStyle()
        style.font = font
        style.borders = borders
        style.alignment = alignment
        style.num_format_str = "0.00"
        self._style_cache["area"] = style
        return style

    def _new_workbook(self):
        return xlwt.Workbook(encoding="utf-8")

    def _issuer_workbook(self, issuers: list[SurveyFbfResult]) -> bytes:
        rows = [
            {
                "code": issuer.fbfbm or "",
                "name": issuer.fbfmc or "",
                "responsible_name": issuer.fbffzrxm or "",
                "mobile": issuer.lxdh or "",
                "address": issuer.fbfdz or "",
                "postcode": issuer.yzbm or "",
                "id_type": ISSUER_ID_TYPE_LABELS.get(issuer.fzrzjlx, issuer.fzrzjlx or ""),
                "id_no": issuer.fzrzjhm or "",
                "surveyor": issuer.fbfdcy or "",
                "survey_date": issuer.fbfdcrq.date().isoformat() if issuer.fbfdcrq else "",
                "survey_note": issuer.fbfdcjs or "",
                "remark": "",
            }
            for issuer in issuers
        ]
        wb = IssuerXlsTemplate.build_workbook(rows)
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    def _parcel_survey_workbook(self, issuers, results, members_by_uid, parcels_by_fbfbm, dk_by_dkbm) -> bytes:
        wb = self._new_workbook()
        sh = wb.add_sheet("鱼鳞图")
        headers = [
            "承包方编号", "承包方名称", "承包方类型", "家庭成员情况(含承包方名称)",
            "承包方调查审核情况", "承包地块情况",
        ]
        widths = [18, 16, 8, 22, 22, 22, 10, 10, 12, 18, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12,
                  16, 19, 10, 12, 12, 14, 14, 14, 14, 10, 10, 12, 10, 12, 12, 20, 10, 12, 20, 10, 12, 20]
        for index, width in enumerate(widths):
            sh.col(index).width = 256 * width
        sh.write_merge(0, 0, 0, 41, "农村土地承包经营权承包地块调查表", self._style(bold=True))
        sh.write_merge(1, 1, 0, 41, f"填写单位：{issuers[0].fbfmc if issuers else ''}    日期：{date.today().isoformat()}", self._style())
        sh.write_merge(2, 2, 3, 10, "家庭成员情况(含承包方名称)", self._style(bold=True))
        sh.write_merge(2, 2, 11, 19, "承包方调查审核情况", self._style(bold=True))
        sh.write_merge(2, 2, 20, 41, "承包地块情况", self._style(bold=True))
        column_headers = [
            "承包方编号", "承包方名称", "承包方类型", "成员个数", "成员姓名", "成员性别", "证件类型",
            "证件号码", "家庭关系", "是否共有人", "备注", "承包方地址", "邮政编码", "联系电话", "调查员",
            "调查日期", "调查记事", "审核人", "审核日期", "审核意见", "地块名称", "地块编码", "图幅编号",
            "二轮合同面积", "实测面积", "四至东", "四至南", "四至西", "四至北", "土地用途", "地力等级",
            "土地利用类型", "是否基本农田", "指界人", "地块类别", "备注", "调查员", "调查日期", "调查记事",
            "审核人", "审核日期", "审核意见",
        ]
        for column, header in enumerate(column_headers):
            sh.write(3, column, header, self._style(bold=True, wrap=True))
        row = 5
        for result in results:
            members = members_by_uid.get(result.contractor_uid, [])
            relations = []
            for issuer in issuers:
                if result.cbfbm.startswith(issuer.fbfbm):
                    relations = parcels_by_fbfbm.get(issuer.fbfbm, [])
                    relations = [rel for rel in relations if rel.cbfbm == result.cbfbm]
                    break
            if not relations:
                relations = [None]
            for rel_index, relation in enumerate(relations):
                parcel = dk_by_dkbm.get(relation.dkbm) if relation else None
                member = members[rel_index] if rel_index < len(members) else None
                values = [
                    result.cbfbm, result.cbfmc,
                    CONTRACTOR_TYPE_LABELS.get(result.cbflx, result.cbflx or ""),
                ]
                if member:
                    values += [
                        str(len(members)), member.cyxm or "", GENDER_LABELS.get(member.cyxb, ""),
                        ID_TYPE_LABELS.get(member.cyzjlx, ""), member.cyzjhm or "",
                        member.yhzgx or "", "是" if member.sfgyr == "1" else "否", member.cybzsm or "",
                    ]
                else:
                    values += [str(len(members))] + [""] * 8
                values += [
                    result.cbfdz or "", result.yzbm or "", result.lxdh or "", result.cbfdcy or "",
                    result.cbfdcrq.date().isoformat() if result.cbfdcrq else "", result.cbfdcjs or "",
                    result.gsshr or "", result.gsshrq.date().isoformat() if result.gsshrq else "", result.gsjs or "",
                ]
                if parcel:
                    values += [
                        parcel.dkmc or "", parcel.dkbm or "", parcel.image_number or "",
                        _mu(relation.htmj), _mu(parcel.scmj),
                        parcel.dkdz or "", parcel.dknz or "", parcel.dkxz or "", parcel.dkbz or "",
                        parcel.tdyt or "", parcel.dldj or "", parcel.tdlylx or "", parcel.sfjbnt or "",
                        parcel.zjrxm or "", parcel.dklb or "", parcel.dkbzxx or "",
                        parcel.survey_person or result.cbfdcy or "",
                        parcel.survey_date.isoformat() if parcel.survey_date else (result.cbfdcrq.date().isoformat() if result.cbfdcrq else ""),
                        parcel.survey_note or result.cbfdcjs or "",
                        parcel.check_person or result.gsshr or "",
                        parcel.check_date.isoformat() if parcel.check_date else (result.gsshrq.date().isoformat() if result.gsshrq else ""),
                        parcel.check_opinion or result.gsjs or "",
                    ]
                else:
                    values += [""] * 22
                for column, value in enumerate(values[:42]):
                    sh.write(row, column, value, self._style(wrap=column in {9, 16, 35, 38, 41}))
                row += 1
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    def _notice_workbook(self, issuers, results, members_by_uid, parcels_by_fbfbm, dk_by_dkbm) -> bytes:
        wb = self._new_workbook()
        sh = wb.add_sheet("公示表")
        widths = [14, 12, 10, 12, 8, 12, 10, 10, 12, 12, 10, 18, 12, 12, 12, 12, 18]
        for index, width in enumerate(widths):
            sh.col(index).width = 256 * width
        sh.write_merge(0, 0, 0, 16, "农村土地承包经营权摸底调查公示表", self._style(bold=True))
        sh.write_merge(1, 1, 0, 12, f"单位：{issuers[0].fbfmc if issuers else ''}", self._style())
        sh.write_merge(1, 1, 13, 16, f"日期：{date.today().isoformat()}", self._style())
        sh.write_merge(2, 2, 2, 6, "家庭成员情况（含户主）", self._style(bold=True))
        sh.write_merge(2, 2, 7, 15, "二轮承包情况（面积：亩）", self._style(bold=True))
        headers = ["编号", "户主姓名", "家庭成员数", "姓名", "性别", "与户主关系", "备注", "承包人口", "台帐总面积", "台帐面积", "地类", "坐落地名(小地名)", "四至上", "四至下", "四至左", "四至右", "备注"]
        for column, header in enumerate(headers):
            sh.write(3, column, header, self._style(bold=True, wrap=True))
        row = 5
        for result in results:
            members = members_by_uid.get(result.contractor_uid, [])
            relations = []
            for issuer in issuers:
                if result.cbfbm.startswith(issuer.fbfbm):
                    relations = [rel for rel in parcels_by_fbfbm.get(issuer.fbfbm, []) if rel.cbfbm == result.cbfbm]
                    break
            total_area = sum(_mu(rel.htmj) for rel in relations)
            rows = max(len(members), len(relations), 1)
            for index in range(rows):
                member = members[index] if index < len(members) else None
                relation = relations[index] if index < len(relations) else None
                parcel = dk_by_dkbm.get(relation.dkbm) if relation else None
                values = [
                    result.cbfbm, result.cbfmc, str(len(members)),
                    member.cyxm if member else "", GENDER_LABELS.get(member.cyxb, "") if member else "",
                    member.yhzgx if member else "", member.cybzsm if member else "",
                    str(len(members)), total_area,
                    _mu(relation.htmj) if relation else "", parcel.dklb if parcel else "",
                    parcel.dkmc if parcel else "", parcel.dkxz if parcel else "", parcel.dknz if parcel else "",
                    parcel.dkbz if parcel else "", parcel.dkbzxx if parcel else "", "",
                ]
                for column, value in enumerate(values):
                    sh.write(row, column, value, self._style(wrap=column in {11, 16}))
                row += 1
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def _mask_middle(value, head: int, tail: int) -> str:
        """按 CS 版公示表脱敏：保留首尾，中间用 * 代替（电话/证件号码）。"""
        text = str(value or "").strip()
        if len(text) <= head + tail:
            return text
        return f"{text[:head]}{'*' * (len(text) - head - tail)}{text[-tail:]}"

    @staticmethod
    def _short_code(value, length: int) -> str:
        text = str(value or "").strip()
        return text[-length:] if text else ""

    def _delay_notice_workbook(
        self, db, issuer, results, members_by_uid, parcels_by_fbfbm, dk_by_dkbm
    ) -> bytes:
        """延包调查信息公示表（按发包方逐户输出）。

        版式对齐 CS 版「承包台账 → 调查报表 → 延包调查信息公示表」：
        18 列，含「家庭成员情况（含户主）」与「农村土地承包经营权承包地块详细信息」
        两组表头，户内多行纵向合并；联系电话、证件号码按 CS 版脱敏，
        承包方编码（缩略码）取编码后 4 位，地块编码取后 5 位。
        """
        relation_labels: dict[str, str] = {}
        relation_order: dict[str, int] = {}
        try:
            options = dictionary_service.get_options(db, "nyt2539_c20_relation_to_head")
        except Exception:  # noqa: BLE001
            options = []
        for index, item in enumerate(options):
            value = str(item.get("value"))
            relation_labels[value] = str(item.get("label"))
            relation_order[value] = index

        wb = self._new_workbook()
        sh = wb.add_sheet("公示表")
        total_cols = len(DELAY_NOTICE_COLUMNS)
        for index, (_, width) in enumerate(DELAY_NOTICE_COLUMNS):
            sh.col(index).width = 256 * width
        for index, height in ((0, 34), (1, 24), (2, 22), (3, 32)):
            sh.row(index).height_mismatch = True
            sh.row(index).height = height * 20

        sh.write_merge(
            0, 0, 0, total_cols - 1,
            "第二轮土地承包到期后再延长三十年调查信息公示表",
            self._style(bold=True, wrap=True),
        )
        sh.write_merge(1, 1, 0, 3, f"发包方名称：{issuer.fbfmc or ''}", self._style(wrap=True))
        sh.write_merge(1, 1, 4, 7, f"发包方编码：{issuer.fbfbm or ''}", self._style(wrap=True))
        sh.write_merge(
            1, 1, 8, 14, f"发包方负责人姓名：{issuer.fbffzrxm or ''}", self._style(wrap=True)
        )
        sh.write_merge(1, 1, 15, total_cols - 1, "日期：", self._style())

        for title, start, end in DELAY_NOTICE_GROUPS:
            sh.write_merge(2, 2, start, end, title, self._style(bold=True))
        for column in DELAY_NOTICE_HEADER_MERGE_COLUMNS:
            sh.write_merge(
                2, 3, column, column,
                DELAY_NOTICE_COLUMNS[column][0],
                self._style(bold=True, wrap=True),
            )
        for column, (header, _) in enumerate(DELAY_NOTICE_COLUMNS):
            if column in DELAY_NOTICE_HEADER_MERGE_COLUMNS:
                continue
            sh.write(3, column, header, self._style(bold=True, wrap=True))

        wrap_columns = {1, 9, 17}
        merged_columns = DELAY_NOTICE_MERGE_COLUMNS
        row = 4

        for seq, result in enumerate(results, start=1):
            members = list(members_by_uid.get(result.contractor_uid, []))
            members.sort(
                key=lambda item: (
                    0 if item.is_household_head else 1,
                    relation_order.get(str(item.yhzgx or ""), 999),
                    str(item.cyxm or ""),
                )
            )
            relations: list[SurveyCbdkxxResult] = [
                rel for rel in parcels_by_fbfbm.get(issuer.fbfbm, [])
                if rel.cbfbm == result.cbfbm
            ]
            parcels = [dk_by_dkbm.get(rel.dkbm) for rel in relations]
            row_count = max(len(members), len(relations), 1)
            start_row = row

            merged_values = {
                0: seq,
                1: result.cbfmc or "",
                2: self._short_code(result.cbfbm, 4),
                3: self._mask_middle(result.lxdh, 3, 4),
                4: str(len(members) or int(result.cbfcysl or 0)),
            }

            for offset in range(row_count):
                member = members[offset] if offset < len(members) else None
                relation = relations[offset] if offset < len(relations) else None
                parcel = parcels[offset] if offset < len(parcels) else None
                values: dict[int, object] = {}
                if member is not None:
                    values[5] = member.cyxm or ""
                    values[6] = self._mask_middle(member.cyzjhm, 6, 4)
                    values[7] = relation_labels.get(
                        str(member.yhzgx or ""), member.yhzgx or ""
                    )
                    values[8] = member.cybzsm or ""
                if relation is not None:
                    values[10] = self._short_code(relation.dkbm, 5)
                    values[15] = _mu(relation.htmj)
                if parcel is not None:
                    values[9] = parcel.dkmc or ""
                    values[11] = parcel.dkdz or ""
                    values[12] = parcel.dknz or ""
                    values[13] = parcel.dkxz or ""
                    values[14] = parcel.dkbz or ""
                    values[16] = _mu(parcel.scmj)
                    values[17] = parcel.dkbzxx or ""
                for column in range(total_cols):
                    if column in merged_columns:
                        continue
                    style = (
                        self._area_style()
                        if column in {15, 16}
                        else self._style(wrap=column in wrap_columns)
                    )
                    sh.write(start_row + offset, column, values.get(column, ""), style)

            for column in sorted(merged_columns):
                value = merged_values.get(column, "")
                style = self._style(wrap=column in wrap_columns)
                if row_count > 1:
                    sh.write_merge(start_row, start_row + row_count - 1, column, column, value, style)
                else:
                    sh.write(start_row, column, value, style)

            row += row_count

        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    def build_baseline_workbook(self, db, issuers, results, members_by_uid, parcels_by_fbfbm, dk_by_dkbm, print_version: bool) -> bytes:
        def labels(dict_type: str) -> dict[str, str]:
            try:
                options = dictionary_service.get_options(db, dict_type)
            except Exception:  # noqa: BLE001
                return {}
            return {str(item.get("value")): str(item.get("label")) for item in options}

        ownership_labels = labels("nyt2539_c06_ownership_property")
        category_labels = labels("nyt2539_c07_parcel_category")
        grade_labels = labels("nyt2539_c08_land_grade")
        land_use_labels = labels("nyt2539_c09_land_use")
        contractor_type_labels = labels("nyt2539_c16_contractor_type") or CONTRACTOR_TYPE_LABELS
        relation_labels = labels("nyt2539_c20_relation_to_head")
        id_type_labels = labels("nyt2539_c15_id_document_type") or ID_TYPE_LABELS
        relation_order = {value: index for index, value in enumerate(relation_labels)}

        wb = self._new_workbook()
        sh = wb.add_sheet("Sheet1")
        widths = [8, 16, 8, 18, 14, 24, 8, 10, 6, 10, 12, 20, 12, 12, 20, 16, 19, 12, 12, 12, 10, 10, 10, 12, 12, 12, 12, 12, 10, 10, 10, 10, 20, 10, 12]
        for index, width in enumerate(widths):
            sh.col(index).width = 256 * width
        title = "农村土地承包经营权摸底调查表" if print_version else "农村土地承包经营权摸底成果表"
        sh.write_merge(0, 0, 0, 34, title, self._style(bold=True))
        issuer = issuers[0] if issuers else None
        sh.write(2, 0, "发包方名称", self._style(bold=True))
        sh.write_merge(2, 2, 1, 4, issuer.fbfmc if issuer else "", self._style())
        sh.write(2, 5, "发包方编码", self._style(bold=True))
        sh.write_merge(2, 2, 6, 6, issuer.fbfbm if issuer else "", self._style())
        sh.write(2, 7, "发包方负责人姓名", self._style(bold=True))
        sh.write_merge(2, 2, 8, 10, issuer.fbffzrxm if issuer else "", self._style())
        sh.write(2, 11, "证件类型", self._style(bold=True))
        sh.write(2, 14, "证件号码", self._style(bold=True))
        sh.write_merge(2, 2, 15, 18, issuer.fzrzjhm if issuer else "", self._style())
        sh.write(2, 19, "联系电话", self._style(bold=True))
        sh.write_merge(2, 2, 20, 21, issuer.lxdh if issuer else "", self._style())
        sh.write(2, 22, "发包方地址", self._style(bold=True))
        sh.write_merge(2, 2, 23, 27, issuer.fbfdz if issuer else "", self._style())
        sh.write(2, 28, "邮政编码", self._style(bold=True))
        sh.write(2, 30, "调查员", self._style(bold=True))
        sh.write(2, 33, "调查日期", self._style(bold=True))
        sh.write(2, 34, issuer.fbfdcrq.date().isoformat() if issuer and issuer.fbfdcrq else "", self._style())

        sh.write_merge(3, 3, 6, 14, "家庭成员情况（含户主）", self._style(bold=True))
        sh.write_merge(3, 3, 15, 33, "农村土地承包经营权承包地块详细信息", self._style(bold=True))
        headers = [
            "编号", "承包方名称", "承包方类型", "承包方编码", "承包方联系电话", "承包方地址", "成员数（人）",
            "姓名", "性别", "联系电话", "证件类型", "证件号码", "家庭关系", "成员备注", "成员备注说明",
            "地块名称", "地块编码", "所有权性质", "地块类别", "土地利用类型", "地力等级", "土地用途",
            "是否基本农田", "原合同总面积（亩）", "确权面积（亩）", "确权总面积（亩）", "实测面积（亩）",
            "实测总面积（亩）", "四至东", "四至南", "四至西", "四至北", "地块备注", "备注", "变化情况",
        ]
        for column, header in enumerate(headers):
            sh.write(4, column, header, self._style(bold=True, wrap=True))
        merged_columns = {0, 1, 2, 3, 4, 5, 6, 23, 25, 27, 34}
        row = 6
        for seq, result in enumerate(results, start=1):
            members = list(members_by_uid.get(result.contractor_uid, []))
            members.sort(
                key=lambda item: (
                    0 if item.is_household_head else 1,
                    relation_order.get(str(item.yhzgx or ""), 999),
                    str(item.cyxm or ""),
                )
            )
            relations = []
            for item in issuers:
                if result.cbfbm.startswith(item.fbfbm):
                    relations = [rel for rel in parcels_by_fbfbm.get(item.fbfbm, []) if rel.cbfbm == result.cbfbm]
                    break
            parcels = [dk_by_dkbm.get(rel.dkbm) for rel in relations]
            rows = max(len(members), len(relations), 1)
            start_row = row
            member_count = len(members) or int(result.cbfcysl or 0)
            contract_total = round(
                sum(_area_mu(rel.yhtmjm, rel.yhtmj) for rel in relations), 2
            )
            aware_total = round(
                sum(
                    _area_mu(rel.htmjm, rel.htmj)
                    for rel in relations
                    if (dk_by_dkbm.get(rel.dkbm).dklb if dk_by_dkbm.get(rel.dkbm) else None) == "10"
                ),
                2,
            )
            actual_total = round(
                sum(_mu(parcel.scmj) for parcel in parcels if parcel is not None), 2
            )
            merged_values = {
                0: seq,
                1: result.cbfmc or "",
                2: contractor_type_labels.get(result.cbflx, result.cbflx or ""),
                3: result.cbfbm or "",
                4: result.lxdh or "",
                5: result.cbfdz or "",
                6: member_count,
                23: contract_total,
                25: aware_total,
                27: actual_total,
                34: "",
            }
            for index in range(rows):
                member = members[index] if index < len(members) else None
                relation = relations[index] if index < len(relations) else None
                parcel = parcels[index] if index < len(parcels) else None
                values: dict[int, object] = {}
                if member is not None:
                    values[7] = member.cyxm or ""
                    values[8] = GENDER_LABELS.get(member.cyxb, "")
                    values[9] = ""
                    values[10] = id_type_labels.get(member.cyzjlx, "")
                    values[11] = member.cyzjhm or ""
                    values[12] = relation_labels.get(str(member.yhzgx or ""), member.yhzgx or "")
                    values[13] = member.cybzsm or ""
                    values[14] = ""
                if relation is not None:
                    values[24] = (
                        _area_mu(relation.htmjm, relation.htmj)
                        if parcel is not None and parcel.dklb == "10"
                        else 0
                    )
                if parcel is not None:
                    values[15] = parcel.dkmc or ""
                    values[16] = parcel.dkbm or ""
                    values[17] = ownership_labels.get(parcel.syqxz, parcel.syqxz or "")
                    values[18] = category_labels.get(parcel.dklb, parcel.dklb or "")
                    values[19] = TDLYLX_LABELS.get(parcel.tdlylx, parcel.tdlylx or "")
                    values[20] = grade_labels.get(parcel.dldj, parcel.dldj or "")
                    values[21] = land_use_labels.get(parcel.tdyt, parcel.tdyt or "")
                    values[22] = "是" if parcel.sfjbnt == "1" else ("否" if parcel.sfjbnt else "")
                    values[26] = _mu(parcel.scmj)
                    values[28] = parcel.dkdz or ""
                    values[29] = parcel.dknz or ""
                    values[30] = parcel.dkxz or ""
                    values[31] = parcel.dkbz or ""
                    values[32] = parcel.dkbzxx or ""
                    values[33] = result.remark or ""
                    values[39] = parcel.survey_person or result.cbfdcy or ""
                    values[40] = (
                        parcel.survey_date.isoformat()
                        if parcel.survey_date
                        else (result.cbfdcrq.date().isoformat() if result.cbfdcrq else "")
                    )
                    values[41] = parcel.survey_note or result.cbfdcjs or ""
                    values[42] = parcel.check_person or result.gsshr or ""
                    values[43] = (
                        parcel.check_date.isoformat()
                        if parcel.check_date
                        else (result.gsshrq.date().isoformat() if result.gsshrq else "")
                    )
                    values[44] = parcel.check_opinion or result.gsjs or ""
                for column in range(len(headers)):
                    if column in merged_columns:
                        continue
                    sh.write(
                        start_row + index,
                        column,
                        values.get(column, ""),
                        self._style(wrap=column in {5, 11, 32, 33}),
                    )
            for column in sorted(merged_columns):
                value = merged_values.get(column, "")
                style = self._style(wrap=column in {5, 11, 32, 33})
                if rows > 1:
                    sh.write_merge(start_row, start_row + rows - 1, column, column, value, style)
                else:
                    sh.write(start_row, column, value, style)
            row += rows
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    def build_single_household_workbook(
        self, db, issuer, result, members, relations, dk_by_dkbm
    ) -> bytes:
        """单户「摸底调查核实表」。

        版式对齐 CS 版「承包台账 → 调查报表 → 摸底调查核实表（单户）」所使用的
        ``土地延包农户基本情况摸底调查表.xlt``：17 列，每户一份，成员与地块
        分别向下展开；承包方编号/名称、承包地情况纵向合并，末尾为签名行与填表说明。
        """
        def labels(dict_type: str) -> dict[str, str]:
            try:
                options = dictionary_service.get_options(db, dict_type)
            except Exception:  # noqa: BLE001
                return {}
            return {str(item.get("value")): str(item.get("label")) for item in options}

        gender_labels = labels("nyt2539_c17_gender")
        relation_labels = labels("nyt2539_c20_relation_to_head")

        wb = self._new_workbook()
        sh = wb.add_sheet("摸底调查表")
        widths = [8, 14, 12, 8, 18, 8, 12, 10, 12, 12, 18, 10, 10, 10, 10, 10, 10]
        for index, width in enumerate(widths):
            sh.col(index).width = 256 * width
        for index, height in ((0, 40), (1, 24), (2, 22), (3, 28), (4, 20)):
            sh.row(index).height_mismatch = True
            sh.row(index).height = height * 20

        header_style = self._style(bold=True, wrap=True)
        data_style = self._style(wrap=True)

        sh.write_merge(0, 0, 0, 16, "土地延包农户基本情况摸底调查表", self._title_style())
        sh.write_merge(1, 1, 0, 4, f"单位:{issuer.fbfmc or ''}", self._left_style())
        sh.write_merge(1, 1, 5, 16, "", self._left_style())

        sh.write_merge(2, 4, 0, 0, "承包方编号", header_style)
        sh.write_merge(2, 4, 1, 1, "承包方名称", header_style)
        sh.write_merge(2, 2, 2, 5, "", header_style)
        sh.write_merge(3, 4, 2, 2, "姓名", header_style)
        sh.write_merge(3, 4, 3, 3, "性别", header_style)
        sh.write_merge(3, 4, 4, 4, "证件号码", header_style)
        sh.write_merge(3, 4, 5, 5, "家庭关系", header_style)
        sh.write_merge(3, 4, 6, 6, "是/否本集体经济组织成员", header_style)
        sh.write_merge(3, 4, 7, 7, "备注", header_style)
        sh.write_merge(3, 4, 8, 8, "承包地情况", header_style)
        sh.write_merge(2, 2, 9, 15, "农村土地承包经营权承包地块详细信息", header_style)
        sh.write(2, 6, "", header_style)
        sh.write(2, 7, "", header_style)
        sh.write(2, 8, "", header_style)
        sh.write(2, 16, "", header_style)
        sh.write_merge(3, 4, 9, 9, "地块名称", header_style)
        sh.write_merge(3, 4, 10, 10, "地块编码", header_style)
        sh.write_merge(3, 4, 11, 11, "确权面积", header_style)
        sh.write_merge(3, 3, 12, 15, "四至", header_style)
        for column, title in ((12, "东"), (13, "南"), (14, "西"), (15, "北")):
            sh.write(4, column, title, header_style)
        sh.write_merge(3, 4, 16, 16, "备注", header_style)

        tail = str(result.cbfbm or "")[-4:]
        try:
            family_number = str(int(tail))
        except ValueError:
            family_number = tail
        total_area = round(
            sum(_area_mu(rel.htmjm, rel.htmj) for rel in relations), 2
        )
        data_rows = max(len(members), len(relations), 1) + 2
        start_row = 5
        for index in range(data_rows):
            sh.row(start_row + index).height_mismatch = True
            sh.row(start_row + index).height = 28 * 20

        sh.write_merge(
            start_row, start_row + data_rows - 1, 0, 0, family_number, data_style
        )
        sh.write_merge(
            start_row, start_row + data_rows - 1, 1, 1, result.cbfmc or "", data_style
        )
        sh.write_merge(
            start_row, start_row + data_rows - 1, 8, 8,
            f"合计：{len(relations)}块\r\n总面积{total_area:g}亩",
            data_style,
        )
        row_values: dict[tuple[int, int], object] = {}
        for index, member in enumerate(members[:data_rows]):
            row_index = start_row + index
            gender = gender_labels.get(str(member.cyxb or ""), GENDER_LABELS.get(member.cyxb, ""))
            row_values[(row_index, 2)] = member.cyxm or "/"
            row_values[(row_index, 3)] = f"{gender}性" if gender else ""
            row_values[(row_index, 4)] = member.cyzjhm or ""
            row_values[(row_index, 5)] = relation_labels.get(
                str(member.yhzgx or ""), member.yhzgx or ""
            )
            row_values[(row_index, 6)] = ""
            row_values[(row_index, 7)] = ""

        for index, relation in enumerate(relations[:data_rows]):
            row_index = start_row + index
            parcel = dk_by_dkbm.get(relation.dkbm)
            area = _area_mu(relation.htmjm, relation.htmj)
            row_values[(row_index, 9)] = (parcel.dkmc if parcel else "") or "/"
            row_values[(row_index, 10)] = relation.dkbm or ""
            row_values[(row_index, 11)] = area if area else ""
            row_values[(row_index, 12)] = (parcel.dkdz if parcel else "") or "/"
            row_values[(row_index, 13)] = (parcel.dknz if parcel else "") or "/"
            row_values[(row_index, 14)] = (parcel.dkxz if parcel else "") or "/"
            row_values[(row_index, 15)] = (parcel.dkbz if parcel else "") or "/"
            row_values[(row_index, 16)] = ""

        for index in range(data_rows):
            row_index = start_row + index
            for column in range(17):
                if column in {0, 1, 8}:
                    continue
                sh.write(row_index, column, row_values.get((row_index, column), ""), data_style)

        footer_row = start_row + data_rows
        sh.row(footer_row).height_mismatch = True
        sh.row(footer_row).height = 28 * 20
        sh.write_merge(footer_row, footer_row, 0, 1, "户主签名(按印)：", data_style)
        sh.write_merge(footer_row, footer_row, 2, 3, "", data_style)
        sh.write_merge(footer_row, footer_row, 4, 6, f"联系电话：{result.lxdh or ''}", data_style)
        sh.write_merge(footer_row, footer_row, 7, 8, "摸底人员签名(按印):", data_style)
        sh.write_merge(footer_row, footer_row, 9, 10, "", data_style)
        sh.write_merge(footer_row, footer_row, 11, 12, "是否同意延包：", data_style)
        sh.write(footer_row, 13, "日期:", data_style)
        sh.write_merge(footer_row, footer_row, 14, 16, "", data_style)

        note_row = footer_row + 1
        sh.row(note_row).height_mismatch = True
        sh.row(note_row).height = 30 * 20
        sh.write_merge(
            note_row, note_row, 0, 16,
            "填表说明：本表数据来源于土地确权数据库，摸底时人口、地块有增减和变动的，"
            "要做相应修改更正。整户无地的也要做补充摸底登记。",
            self._left_style(),
        )

        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    def _public_notice_docx(self, result, members, relations, dk_by_dkbm):
        rows = []
        for index, relation in enumerate(relations):
            parcel = dk_by_dkbm.get(relation.dkbm)
            rows.append(
                "<tr>"
                f"<td>{html.escape(parcel.dkmc if parcel else '')}</td>"
                f"<td>{html.escape(relation.dkbm)}</td>"
                f"<td>{_mu(relation.htmj)}</td>"
                f"<td>{_mu(parcel.scmj) if parcel else 0}</td>"
                f"<td>{html.escape((parcel.dkdz if parcel else '') or '')}</td>"
                f"<td>{html.escape((parcel.dknz if parcel else '') or '')}</td>"
                f"<td>{html.escape((parcel.dkxz if parcel else '') or '')}</td>"
                f"<td>{html.escape((parcel.dkbz if parcel else '') or '')}</td>"
                "</tr>"
            )
        member_names = "、".join(member.cyxm or "" for member in members)
        content = f"""
<h1>农村土地承包经营权公示结果归户表</h1>
<table>
<tr><td class="lbl">承包方名称</td><td>{html.escape(result.cbfmc or '')}</td><td class="lbl">承包方编码</td><td>{html.escape(result.cbfbm or '')}</td></tr>
<tr><td class="lbl">证件号码</td><td>{html.escape(result.cbfzjhm or '')}</td><td class="lbl">联系电话</td><td>{html.escape(result.lxdh or '')}</td></tr>
<tr><td class="lbl">承包方地址</td><td colspan="3">{html.escape(result.cbfdz or '')}</td></tr>
<tr><td class="lbl">家庭成员</td><td colspan="3">{html.escape(member_names)}</td></tr>
<tr><td class="lbl">地块数</td><td>{len(relations)}</td><td class="lbl">承包面积（亩）</td><td>{sum(_mu(rel.htmj) for rel in relations)}</td></tr>
<tr><td class="lbl">公示结果</td><td colspan="3">{html.escape(result.gsjs or '无异议')}</td></tr>
<tr><td class="lbl">公示日期</td><td colspan="3">{result.gsshrq.date().isoformat() if result.gsshrq else ''}</td></tr>
</table>
<h2>承包地块明细</h2>
<table>
<thead><tr><th>地块名称</th><th>地块编码</th><th>合同面积(亩)</th><th>实测面积(亩)</th><th>东</th><th>南</th><th>西</th><th>北</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
<p class="sign">承包方（签字）：____________</p>
<p class="sign">日期：____年__月__日</p>
"""
        payload = html_docx.build_docx(
            "<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
            "body{font-family:SimSun,serif;font-size:12pt;line-height:1.8}"
            "h1{text-align:center;font-size:20pt}h2{font-size:14pt;margin-top:18pt}"
            "table{width:100%;border-collapse:collapse;margin-top:10pt}"
            "td,th{border:1px solid #000;padding:4pt 6pt;text-align:center;line-height:1.6}"
            ".lbl{width:22%;font-weight:bold;background:#f2f2f2}"
            ".sign{text-align:right;margin-top:20pt}</style></head><body>"
            f"<div class='page'>{content}</div></body></html>"
        )
        filename = f"{result.cbfbm}{result.cbfmc}公示结果归户表.docx"
        return payload, filename.translate(str.maketrans({char: "_" for char in '\\/:*?"<>|'}))


batch_form_export_service = BatchFormExportService()
