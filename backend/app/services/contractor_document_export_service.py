"""承包方资料批量导出：Excel / 承包方调查表 Word / 声明书 / 测绘申请书。

导出对象是承包方管理列表中勾选的承包方。Word 文档统一走
``html_docx``（HTML 母版 → .docx），不依赖 Office/Aspose。
"""

from __future__ import annotations

import html
import io
import re
import zipfile
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyBatch,
    SurveyCbfBase,
    SurveyCbfResult,
    SurveyCbfJtcyResult,
    SurveyCbdkxxResult,
    SurveyDkResult,
    SurveyFbfBase,
    SurveyFbfResult,
)
from app.models.user import User
from app.services import html_docx
from app.services.contractor_survey_docx_service import (
    DOCX_MEDIA_TYPE,
    contractor_survey_docx_service,
)
from app.services.survey.excel_transfer import GENDER_LABELS
from app.services.survey import survey_service

XLS_MEDIA_TYPE = "application/vnd.ms-excel"
ZIP_MEDIA_TYPE = "application/zip"

DOC_CONTRACTOR_EXCEL = "contractor_excel"
DOC_BASELINE_VERIFY = "baseline_verify_excel"
DOC_CONTRACTOR_WORD = "contractor_word"
DOC_HOUSEHOLDER = "householder_declaration"
DOC_AUTHORIZATION = "authorization_declaration"
DOC_NO_OBJECTION = "no_objection_declaration"
DOC_SURVEY_APPLICATION = "survey_application"

DOC_LABELS = {
    DOC_CONTRACTOR_EXCEL: "承包方信息表（Excel）",
    DOC_BASELINE_VERIFY: "摸底调查核实表（单户）",
    DOC_CONTRACTOR_WORD: "承包方调查表（Word）",
    DOC_HOUSEHOLDER: "户主声明书",
    DOC_AUTHORIZATION: "委托声明书",
    DOC_NO_OBJECTION: "无异议声明书",
    DOC_SURVEY_APPLICATION: "测绘申请书",
}

#: ZIP 内按导出文件类型建的子文件夹。
DOC_FOLDERS = {
    DOC_CONTRACTOR_EXCEL: "承包方信息表",
    DOC_BASELINE_VERIFY: "摸底调查核实表",
    DOC_CONTRACTOR_WORD: "承包方调查表",
    DOC_HOUSEHOLDER: "户主声明书",
    DOC_AUTHORIZATION: "委托声明书",
    DOC_NO_OBJECTION: "无异议声明书",
    DOC_SURVEY_APPLICATION: "测绘申请书",
}

_DOC_ORDER = [
    DOC_CONTRACTOR_EXCEL,
    DOC_BASELINE_VERIFY,
    DOC_CONTRACTOR_WORD,
    DOC_HOUSEHOLDER,
    DOC_AUTHORIZATION,
    DOC_NO_OBJECTION,
    DOC_SURVEY_APPLICATION,
]

#: 逐户生成、不进入 Word 文档循环的导出类型。
_PER_HOUSEHOLD_DOCS = {DOC_BASELINE_VERIFY}

_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|]')

_PAGE_CSS = """
@page { size: A4; margin: 22mm 20mm; }
body { font-family: "SimSun", "宋体", serif; font-size: 14pt; line-height: 2; color: #000; }
h1 { text-align: center; font-size: 22pt; font-weight: bold; margin: 0 0 18pt; }
p { margin: 0 0 10pt; text-indent: 2em; }
p.plain { text-indent: 0; }
.sign { margin-top: 36pt; text-align: right; line-height: 2.2; }
.date { margin-top: 12pt; text-align: right; }
"""


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _wrap_html(body: str) -> str:
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        f"<style>{_PAGE_CSS}</style></head><body>"
        f"<div class=\"page\">{body}</div>"
        "</body></html>"
    )


def _age_from_id(id_no: str) -> str:
    digits = re.sub(r"\D", "", id_no or "")
    try:
        if len(digits) == 18:
            birth = date(int(digits[6:10]), int(digits[10:12]), int(digits[12:14]))
        elif len(digits) == 15:
            birth = date(1900 + int(digits[6:8]), int(digits[8:10]), int(digits[10:12]))
        else:
            return ""
    except ValueError:
        return ""
    today = date.today()
    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    return str(age) if 0 <= age <= 150 else ""


def _region_parts(region_name: str) -> list[str]:
    return [part.strip() for part in re.split(r"[/、]", region_name or "") if part.strip()]


def _pick_town(region_name: str) -> str:
    parts = _region_parts(region_name)
    for part in parts:
        if part.endswith(("镇", "乡", "街道")):
            return part
    return parts[-2] if len(parts) >= 2 else (parts[-1] if parts else "")


class ContractorDocumentExportService:
    def export(
        self,
        db: Session,
        batch_id: int,
        contractor_uids: list[str],
        documents: list[str],
        current_user: User,
        group_by_issuer: bool = False,
    ) -> tuple[str, bytes, str]:
        uids = list(dict.fromkeys(str(uid).strip() for uid in contractor_uids if str(uid or "").strip()))
        requested = {doc for doc in documents if doc}
        unknown = requested - set(DOC_LABELS)
        if unknown:
            raise HTTPException(status_code=400, detail=f"不支持的导出类型：{'、'.join(sorted(unknown))}")

        batch = db.get(SurveyBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调查批次不存在")

        # 未勾选任何承包方 = 导出该批次全部承包方（与调查录入列表同口径：
        # 当前用户数据权限内、排除已注销户，按承包方编码排序）。
        if not uids:
            uids = self._all_batch_contractor_uids(db, batch, current_user)
            if not uids:
                raise HTTPException(status_code=400, detail="该批次暂无承包方可供导出")

        # 按发包方分组：每个发包方一个文件夹，文件夹内放该发包方下承包方的全部导出文件。
        if group_by_issuer:
            groups = self._group_uids_by_issuer(db, batch, uids)
            folder_names = self._issuer_folder_names(db, batch, list(groups))
        else:
            groups = {"": uids}
            folder_names = {}

        files: list[tuple[str, str, str, bytes, str]] = []  # (issuer_folder, type_folder, filename, content, media_type)
        for issuer_code, group_uids in groups.items():
            folder = folder_names.get(issuer_code, "") if issuer_code else ""
            if DOC_CONTRACTOR_EXCEL in requested:
                filename, content = survey_service.export_contractors_xls(
                    db, batch_id, current_user, contractor_uids=group_uids
                )
                # 本对话框里 Excel 项叫「承包方信息表」，下载文件名保持同名。
                if filename.startswith("承包方调查表"):
                    filename = filename.replace("承包方调查表", "承包方信息表", 1)
                files.append((folder, DOC_FOLDERS[DOC_CONTRACTOR_EXCEL], filename, content, XLS_MEDIA_TYPE))

            if DOC_BASELINE_VERIFY in requested:
                for filename, content, media_type in self._export_baseline_verify(
                    db, batch, group_uids, current_user
                ):
                    files.append((folder, DOC_FOLDERS[DOC_BASELINE_VERIFY], filename, content, media_type))

            word_docs = [
                doc for doc in _DOC_ORDER
                if doc in requested and doc not in (DOC_CONTRACTOR_EXCEL, *_PER_HOUSEHOLD_DOCS)
            ]
            if word_docs:
                for uid in group_uids:
                    result = survey_service.get_result(db, batch_id, uid, current_user)
                    context = self._build_context(batch, result)
                    base_name = _UNSAFE_FILENAME.sub(
                        "_", f"{context['code']}{context['name']}"
                    )
                    for doc in word_docs:
                        if doc == DOC_CONTRACTOR_WORD:
                            content, filename = contractor_survey_docx_service.render(
                                db, cbfbm=context["code"], batch_id=batch_id
                            )
                        else:
                            content = html_docx.build_docx(self._render_document(doc, context))
                            filename = f"{base_name}-{DOC_LABELS[doc]}.docx"
                        files.append((folder, DOC_FOLDERS[doc], filename, content, DOCX_MEDIA_TYPE))

        if not files:
            raise HTTPException(status_code=400, detail="请至少选择一种导出内容")

        # 只有「单个文件且不按发包方分组」才直接返回文件；其余都打包 ZIP，
        # ZIP 内先按发包方（可选）再按导出文件类型分文件夹。
        if not group_by_issuer and len(files) == 1:
            return files[0][2], files[0][3], files[0][4]

        buffer = io.BytesIO()
        seen: set[str] = set()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for folder, type_folder, filename, content, _media in files:
                parts = [part for part in (folder, type_folder) if part]
                name = "/".join([*parts, filename]) if parts else filename
                archive.writestr(self._unique_name(name, seen), content)
        scope = _UNSAFE_FILENAME.sub("_", batch.region_name or batch.batch_no or str(batch_id))
        prefix = "承包方资料_按发包方分组" if group_by_issuer else "承包方资料"
        return f"{prefix}_{scope}.zip", buffer.getvalue(), ZIP_MEDIA_TYPE

    def _group_uids_by_issuer(
        self, db: Session, batch: SurveyBatch, uids: list[str]
    ) -> dict[str, list[str]]:
        """按发包方（承包方编码前 14 位）把 uid 分组，保持编码顺序稳定。"""
        rows = db.scalars(
            select(SurveyCbfResult)
            .where(
                SurveyCbfResult.tenant_code == batch.tenant_code,
                SurveyCbfResult.contractor_uid.in_(uids),
            )
            .order_by(SurveyCbfResult.id.asc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        code_by_uid = {row.contractor_uid: row.cbfbm for row in rows}
        groups: dict[str, list[str]] = {}
        for uid in uids:
            code = str(code_by_uid.get(uid) or "")
            issuer_code = code[:14] if len(code) >= 14 else (code or "未知发包方")
            groups.setdefault(issuer_code, []).append(uid)
        return dict(sorted(groups.items()))

    def _issuer_folder_names(
        self, db: Session, batch: SurveyBatch, issuer_codes: list[str]
    ) -> dict[str, str]:
        """发包方编码 → 文件夹名（名称_编码）。"""
        codes = [code for code in issuer_codes if code and code != "未知发包方"]
        names: dict[str, str] = {}
        if codes:
            rows = db.scalars(
                select(SurveyFbfBase)
                .where(
                    SurveyFbfBase.batch_id == batch.id,
                    SurveyFbfBase.fbfbm.in_(codes),
                )
                .execution_options(skip_tenant_scope=True)
            ).all()
            for row in rows:
                names.setdefault(row.fbfbm, row.fbfmc or row.fbfbm)
            missing = [code for code in codes if code not in names]
            if missing:
                result_rows = db.scalars(
                    select(SurveyFbfResult)
                    .where(
                        SurveyFbfResult.tenant_code == batch.tenant_code,
                        SurveyFbfResult.fbfbm.in_(missing),
                    )
                    .order_by(SurveyFbfResult.id.desc())
                    .execution_options(skip_tenant_scope=True)
                ).all()
                for row in result_rows:
                    names.setdefault(row.fbfbm, row.fbfmc or row.fbfbm)
            # 发包方快照/结果都缺失时（只导入了承包方），退回承包方所属组名称，
            # 避免文件夹只剩一串编码。
            for code in codes:
                if code in names:
                    continue
                row = db.scalars(
                    select(SurveyCbfResult)
                    .where(
                        SurveyCbfResult.tenant_code == batch.tenant_code,
                        SurveyCbfResult.cbfbm.like(f"{code}%"),
                    )
                    .order_by(SurveyCbfResult.id.desc())
                    .limit(1)
                    .execution_options(skip_tenant_scope=True)
                ).first()
                if row is not None:
                    short = (row.group_region_name or "").split("/")[-1].strip()
                    if short:
                        names[code] = short
        folders: dict[str, str] = {}
        for code in issuer_codes:
            name = names.get(code) or ""
            label = f"{name}_{code}" if name and name != code else (code or "未知发包方")
            folders[code] = _UNSAFE_FILENAME.sub("_", label)
        return folders

    def _all_batch_contractor_uids(
        self, db: Session, batch: SurveyBatch, current_user: User
    ) -> list[str]:
        """批次全部承包方 uid（与调查录入列表同口径：数据权限内、排除已注销）。"""
        from app.services.data_access_service import data_access_service

        filters = [
            SurveyCbfBase.tenant_code == batch.tenant_code,
            SurveyCbfBase.batch_id == batch.id,
            SurveyCbfBase.task_status != "deregistered",
        ]
        filters.extend(
            data_access_service.build_code_scope_filters(SurveyCbfResult.cbfbm, current_user)
        )
        rows = db.scalars(
            select(SurveyCbfBase.contractor_uid)
            .select_from(SurveyCbfBase)
            .join(
                SurveyCbfResult,
                SurveyCbfResult.contractor_uid == SurveyCbfBase.contractor_uid,
            )
            .where(*filters)
            .order_by(SurveyCbfBase.cbfbm.asc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        return list(dict.fromkeys(uid for uid in rows if uid))

    def _export_baseline_verify(
        self,
        db: Session,
        batch: SurveyBatch,
        uids: list[str],
        current_user: User,
    ) -> list[tuple[str, bytes, str]]:
        """按户导出「摸底调查核实表（单户）」。

        版式与调查批次管理中的摸底调查核实表一致（CS 版承包台账-调查报表-
        摸底调查核实表单户口径）：每户单独一个 xls，表头取该户所属发包方信息，
        户内成员与承包地块逐行展开。
        """
        from app.services.batch_form_export_service import batch_form_export_service

        files: list[tuple[str, bytes, str]] = []
        for uid in uids:
            # 先走统一结果读取，复用数据权限校验（越权时抛 403）。
            detail = survey_service.get_result(db, batch.id, uid, current_user)
            result = db.scalars(
                select(SurveyCbfResult)
                .where(
                    SurveyCbfResult.tenant_code == batch.tenant_code,
                    SurveyCbfResult.contractor_uid == uid,
                )
                .order_by(SurveyCbfResult.id.desc())
            ).first()
            if result is None:
                continue
            members = list(
                db.scalars(
                    select(SurveyCbfJtcyResult)
                    .where(
                        SurveyCbfJtcyResult.tenant_code == batch.tenant_code,
                        SurveyCbfJtcyResult.contractor_uid == uid,
                    )
                    .order_by(SurveyCbfJtcyResult.cyxm.asc())
                ).all()
            )
            relations = list(
                db.scalars(
                    select(SurveyCbdkxxResult)
                    .where(
                        SurveyCbdkxxResult.tenant_code == batch.tenant_code,
                        SurveyCbdkxxResult.cbfbm == result.cbfbm,
                    )
                    .order_by(SurveyCbdkxxResult.dkbm.asc())
                ).all()
            )
            dk_by_dkbm: dict[str, SurveyDkResult] = {}
            dkbms = list(dict.fromkeys(rel.dkbm for rel in relations if rel.dkbm))
            if dkbms:
                for parcel in db.scalars(
                    select(SurveyDkResult).where(
                        SurveyDkResult.tenant_code == batch.tenant_code,
                        SurveyDkResult.dkbm.in_(dkbms),
                    )
                ).all():
                    dk_by_dkbm[parcel.dkbm] = parcel
            fbfbm = (result.cbfbm or "")[:14]
            issuer = db.scalars(
                select(SurveyFbfResult)
                .where(
                    SurveyFbfResult.tenant_code == batch.tenant_code,
                    SurveyFbfResult.fbfbm == fbfbm,
                )
                .order_by(SurveyFbfResult.id.desc())
            ).first()
            if issuer is None:
                continue
            content = batch_form_export_service.build_single_household_workbook(
                db, issuer, result, members, relations, dk_by_dkbm
            )
            name = detail.get("name") or result.cbfmc or ""
            tail = str(result.cbfbm or "")[-4:]
            try:
                family_number = str(int(tail))
            except ValueError:
                family_number = tail
            filename = _UNSAFE_FILENAME.sub(
                "_", f"{family_number}-{name}-单户摸底调查表.xls"
            )
            files.append((filename, content, XLS_MEDIA_TYPE))
        return files

    @staticmethod
    def _unique_name(filename: str, seen: set[str]) -> str:
        if filename not in seen:
            seen.add(filename)
            return filename
        stem, dot, suffix = filename.rpartition(".")
        seq = 2
        while True:
            candidate = f"{stem}({seq}){dot}{suffix}"
            if candidate not in seen:
                seen.add(candidate)
                return candidate
            seq += 1

    @staticmethod
    def _build_context(batch: SurveyBatch, result: dict) -> dict:
        members = result.get("familyMembers") or []
        head = next((m for m in members if m.get("isHouseholdHead")), None)
        if head is None and members:
            head = members[0]

        name = (head or {}).get("name") or result.get("name") or ""
        id_no = (head or {}).get("idNo") or result.get("idNo") or ""
        gender = GENDER_LABELS.get((head or {}).get("gender") or "", "")
        member_names = "、".join(m.get("name") or "" for m in members if m.get("name"))
        member_count = len(members) or int(result.get("memberCount") or 0)
        region_name = batch.region_name or result.get("groupRegionName") or ""
        parts = _region_parts(region_name)

        public_date = result.get("publicNoticeReviewDate")
        try:
            public = date.fromisoformat(public_date) if public_date else date.today()
        except ValueError:
            public = date.today()
        today = date.today()

        return {
            "code": result.get("code") or "",
            "name": name,
            "id_no": id_no,
            "gender": gender,
            "age": _age_from_id(id_no),
            "address": result.get("address") or "",
            "phone": result.get("mobile") or "",
            "region_name": region_name,
            "short_region_name": parts[-1] if parts else region_name,
            "town": _pick_town(region_name),
            "member_names": member_names,
            "member_count": member_count,
            "year": today.year,
            "month": today.month,
            "day": today.day,
            "public_year": public.year,
            "public_month": public.month,
            "public_day": public.day,
        }

    def _render_document(self, doc: str, ctx: dict) -> str:
        if doc == DOC_HOUSEHOLDER:
            return self._render_householder(ctx)
        if doc == DOC_AUTHORIZATION:
            return self._render_authorization(ctx)
        if doc == DOC_NO_OBJECTION:
            return self._render_no_objection(ctx)
        if doc == DOC_SURVEY_APPLICATION:
            return self._render_survey_application(ctx)
        raise HTTPException(status_code=400, detail="不支持的导出类型")

    @staticmethod
    def _render_householder(ctx: dict) -> str:
        body = f"""
<h1>户主声明书</h1>
<p>声明人：{_esc(ctx['name'])}，性别：{_esc(ctx['gender'])}，系 {_esc(ctx['short_region_name'])} 村民，身份证号码：{_esc(ctx['id_no'])}。</p>
<p>为配合办理 {_esc(ctx['region_name'])} 第二轮土地承包到期后再延长30年的相关事宜，本人作如下声明：</p>
<p>1、我户有家庭成员：{_esc(ctx['member_names'])}，共计 {_esc(ctx['member_count'])} 人；</p>
<p>2、本人有权代表本户所涉及的全部家庭成员在本次第二轮土地承包到期后再延长30年过程中签收相关法律文书；</p>
<p>3、本人有权委托他人办理前述两条事宜。</p>
<p>前述声明内容是家庭全体成员自愿、真实的意思表示，本人承诺对此承担法律责任。本声明不可撤销，自签字时生效。</p>
<p class="plain">特此声明</p>
<div class="sign">声明人（签字摁印）：<br><br>{ctx['year']} 年 {ctx['month']} 月 {ctx['day']} 日</div>
"""
        return _wrap_html(body)

    @staticmethod
    def _render_authorization(ctx: dict) -> str:
        body = f"""
<h1>户主委托书</h1>
<p>委托人：{_esc(ctx['name'])}　性别：{_esc(ctx['gender'])}　年龄：{_esc(ctx['age'])}　身份证号码：{_esc(ctx['id_no'])}　承包地地址：{_esc(ctx['address'])}，联系电话：{_esc(ctx['phone'])}。</p>
<p>代理人：____________　与委托人关系：____________　性别：______　年龄：______　身份证号码：________________________</p>
<p>住址：____________________________________　联系电话：________________</p>
<p>因委托人（□外出/□身体欠佳/□文化水平有限/□其他原因________________），特委托____________作为我在办理第二轮土地承包到期后再延长30年事宜中的代理人，其代理权限如下：</p>
<p>1、代表委托人在《农村土地（耕地）承包合同（家庭承包方式）》上签字。</p>
<p>2、代表委托人在本次第二轮土地承包到期后再延长30年过程中签收相关法律文书。</p>
<div class="sign">委托人（签字按印）：<br><br>{ctx['year']} 年 {ctx['month']} 月 {ctx['day']} 日</div>
"""
        return _wrap_html(body)

    @staticmethod
    def _render_no_objection(ctx: dict) -> str:
        body = f"""
<h1>公示无异议声明书</h1>
<p>本人 {_esc(ctx['name'])} 系 {_esc(ctx['short_region_name'])} 村民，性别：{_esc(ctx['gender'])}，身份证号：{_esc(ctx['id_no'])}。</p>
<p>我已对 {_esc(ctx['region_name'])} 于 {ctx['public_year']} 年 {ctx['public_month']} 月 {ctx['public_day']} 日就农村土地承包经营权确权登记公示结果进行了认真核实，经全体家庭成员确认，特作如下声明：</p>
<p>户主（权利人）签字无异议；</p>
<p>本户家庭成员人口数无异议；</p>
<p>本户承包地田块分布位置和登记面积无异议；</p>
<p>本户对本组公示的集体经济组织成员名单无异议。</p>
<p class="plain">特此声明</p>
<div class="sign">声明人：{_esc(ctx['name'])}<br><br>{ctx['year']} 年 {ctx['month']} 月 {ctx['day']} 日</div>
"""
        return _wrap_html(body)

    @staticmethod
    def _render_survey_application(ctx: dict) -> str:
        body = f"""
<h1>测 绘 申 请 书</h1>
<p class="plain">{_esc(ctx['town'])}人民政府：</p>
<p>在农村土地承包经营权确权登记工作中，为办理农村土地相关权证，经我户所有家庭成员一致商定同意，自愿申请由农村土地承包经营权确权登记工作的相关测绘作业单位或队伍按照有关规定和程序，对我户相关宗地的权利人、四至、面积进行调查和测绘，并对测绘结果进行认定。</p>
<p class="plain">特此申请</p>
<div class="sign">申请人（户主）：{_esc(ctx['name'])}<br><br>{ctx['year']} 年 {ctx['month']} 月 {ctx['day']} 日</div>
"""
        return _wrap_html(body)


contractor_document_export_service = ContractorDocumentExportService()
