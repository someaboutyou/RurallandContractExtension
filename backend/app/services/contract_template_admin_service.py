from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, status
from jinja2 import Environment, TemplateSyntaxError

from app.db.session import SessionLocal
from app.services import html_docx
from app.services.contract_template_service import (
    CADASTRAL_MEMBER_MIN_ROWS,
    CADASTRAL_POINTS_PER_PAGE,
    blank_boundary_flags,
)
from app.services.dictionary_service import (
    DEFAULT_SURVEY_ORG,
    SURVEY_ORG_DICT_TYPE,
    dictionary_service,
)
from app.services.survey.boundary import (
    CADASTRAL_LINE_CATEGORY_COLUMNS,
    CADASTRAL_LINE_POSITION_COLUMNS,
    CADASTRAL_MARK_TYPE_COLUMNS,
    CADASTRAL_MARK_TYPE_FALLBACK,
    boundary_column_flags,
)


class ContractTemplateAdminService:
    def __init__(self) -> None:
        self.template_dir = Path(__file__).resolve().parent.parent / "templates"
        # 打印模板母版清单（2026-11-06 统一设计，2026-11-07 拆分调查表条目）：
        # - 每个条目对应 templates/ 下一个真实 .html 母版，管理页左侧面板按 group 分组展示；
        # - 《发包方/承包方/承包地块调查表》三张表复刻在 cadastral_survey.html 内，
        #   用 flags（issuer_only/contractor_only/parcel_only）切页 —— 三个条目共享
        #   同一母版文件：预览与空白 Word 只出对应页，编辑保存的是整份母版；
        # - 声明书 / 测绘申请书从 survey_forms/*.dot 移植为 HTML 母版，纯空白文书、
        #   不含 Jinja 数据变量。
        self.template_registry = {
            "contract": {"name": "合同模板", "filename": "contract.html", "group": "出件文书"},
            "plot-sketch-map": {"name": "承包地块示意图模板", "filename": "poltsketchmap.html", "group": "出件文书"},
            "registration-application": {"name": "不动产登记申请书模板", "filename": "registration_application.html", "group": "出件文书"},
            "village-publicity": {
                "name": "村组公示签字表模板",
                "filename": "village_publicity.html",
                "group": "公示签字表",
                "note": "村组（发包方）基本情况公示表：发包方信息、调查记事、调查员与审核意见。版式取自 CS 版数据导出样张。",
            },
            "village-announcement": {
                "name": "村组公告表模板",
                "filename": "village_announcement.html",
                "group": "公示签字表",
                "blank_filename": "村组公示公告.docx",
                "note": "村组（发包方）第一轮公示公告：户数 / 宗地块数 / 总面积按调查成果自动统计，公告与截止日期由导出对话框传入。版式复刻甲方样张（2026-11-12 收敛到母版）。",
            },
            "cadastral-survey": {
                "name": "地籍调查表模板（全册）",
                "filename": "cadastral_survey.html",
                "group": "调查表",
                "blank_filename": "地籍调查表.docx",
                "note": "发包方 / 承包方 / 承包地块三张调查表的共用母版，此条目预览全册。",
            },
            "issuer-survey": {
                "name": "发包方调查表模板",
                "filename": "cadastral_survey.html",
                "group": "调查表",
                "flags": {"issuer_only": True},
                "note": "与承包方 / 承包地块调查表共用同一母版文件（cadastral_survey.html），编辑保存会影响三张表；预览与空白 Word 仅出发包方页。",
            },
            "contractor-survey": {
                "name": "承包方调查表模板",
                "filename": "cadastral_survey.html",
                "group": "调查表",
                "flags": {"contractor_only": True},
                "note": "与发包方 / 承包地块调查表共用同一母版文件（cadastral_survey.html），编辑保存会影响三张表；预览与空白 Word 仅出承包方页。",
            },
            "parcel-survey": {
                "name": "承包地块调查表模板",
                "filename": "cadastral_survey.html",
                "group": "调查表",
                "flags": {"parcel_only": True},
                "note": "与发包方 / 承包方调查表共用同一母版文件（cadastral_survey.html），编辑保存会影响三张表；预览与空白 Word 仅出地块页。",
            },
            "land-change-sheet": {"name": "包地变化摸底表模板", "filename": "land_change_sheet.html", "group": "摸底表"},
            "member-change-sheet": {"name": "家庭成员变化摸底表模板", "filename": "member_change_sheet.html", "group": "摸底表"},
            "householder-declaration": {"name": "户主声明书模板", "filename": "householder_declaration.html", "group": "声明与申请"},
            "proxy-declaration": {"name": "户主委托书模板", "filename": "proxy_declaration.html", "group": "声明与申请"},
            "no-objection-declaration": {"name": "公示无异议声明书模板", "filename": "no_objection_declaration.html", "group": "声明与申请"},
            "survey-application": {"name": "测绘申请书模板", "filename": "survey_application.html", "group": "声明与申请"},
            # 登记申请书（2026-11-08）：复刻 CS 版 Template/*.dot，承包合同管理页
            # 可按批次（集体）/按户（单户）填充数据打印或导出 Word。
            "collective-registration-application": {
                "name": "集体登记申请书模板",
                "filename": "collective_registration_application.html",
                "group": "声明与申请",
                "note": "农村土地承包经营权证（家庭承包方式）申请书：封面 + 正文。变量：县/镇/村/组名、申请编号（镇农地证请［年］第 N 号）、集体土地总面积、承包期限、农户数、落款日期。版式复刻自 CS 版集体登记申请书.dot。",
            },
            "household-registration-application": {
                "name": "单户登记申请书模板",
                "filename": "household_registration_application.html",
                "group": "声明与申请",
                "note": "第二轮土地承包到期后再延长三十年登记申请表：发包方/申请人信息、合同编号、申请内容、四级意见栏（村民小组/村委会/乡镇政府/县农业农村局）。变量：发包方负责人、申请人、合同编号、人口/地块/面积/期限。版式复刻自 CS 版单户登记申请书.dot。",
            },
        }

    def get_contract_template(self) -> dict:
        return self.get_print_template("contract")

    def get_print_template(self, template_key: str) -> dict:
        meta, path = self._resolve_print_template_path(template_key)
        stat = path.stat()
        return {
            "key": template_key,
            "title": meta["name"],
            "name": meta["filename"],
            "content": path.read_text(encoding="utf-8"),
            "updatedAt": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size": stat.st_size,
        }

    def update_contract_template(self, content: str) -> dict:
        return self.update_print_template("contract", content)

    def update_print_template(self, template_key: str, content: str) -> dict:
        self._validate_template(content)
        _, path = self._resolve_print_template_path(template_key)
        path.write_text(content, encoding="utf-8", newline="\n")
        return self.get_print_template(template_key)

    def preview_contract_template(self, content: str) -> dict:
        return self.preview_print_template("contract", content)

    def preview_print_template(self, template_key: str, content: str) -> dict:
        meta = self._resolve_template_meta(template_key)
        self._validate_template(content)
        context = self._sample_context()
        # 调查表三兄弟共用母版：条目 flags 决定预览只出对应页（发包方/承包方/地块）。
        context.update(meta.get("flags") or {})
        try:
            rendered = Environment(autoescape=False).from_string(content).render(**context)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"模板渲染失败：{exc}",
            ) from exc
        return {"renderedHtml": rendered}

    # ── 空白 Word 下载（2026-11-06 统一设计） ─────────────────────────────

    def list_print_templates(self) -> list[dict]:
        """模板管理页左侧清单：registry 顺序即展示顺序，文件缺失标 available=False。"""
        items = []
        for key, meta in self.template_registry.items():
            path = self.template_dir / meta["filename"]
            available = path.is_file()
            stat = path.stat() if available else None
            items.append({
                "key": key,
                "title": meta["name"],
                "group": meta.get("group", "其他"),
                "filename": meta["filename"],
                "note": meta.get("note"),
                "updatedAt": (
                    datetime.fromtimestamp(stat.st_mtime).isoformat() if stat else None
                ),
                "size": stat.st_size if stat else 0,
                "available": available,
            })
        return items

    def render_blank_word(
        self, template_key: str, extra_context: dict | None = None
    ) -> bytes:
        """渲染模板（空白上下文）并转写成 .docx —— 「无内容数据的 Word」。

        - 声明书 / 申请书类母版不含数据变量，渲染结果即原 .dot 的空白文书；
        - 数据类母版用 `_blank_context()`（字段全空、列表为空、调查表给一个
          空白 packet 撑出表框），得到的 Word 只有版式没有业务数据。
        """
        meta, path = self._resolve_print_template_path(template_key)
        context = self._blank_context()
        # 条目 flags（调查表切页）优先应用，extra_context 可再覆盖。
        context.update(meta.get("flags") or {})
        if extra_context:
            context.update(extra_context)
        try:
            rendered = (
                Environment(autoescape=False)
                .from_string(path.read_text(encoding="utf-8"))
                .render(**context)
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"空白模板渲染失败：{exc}",
            ) from exc
        return html_docx.build_docx(rendered)

    def _blank_context(self) -> dict:
        """空白渲染上下文：与 `_sample_context` 同键，值全部置空。

        - 字符串 → ""、布尔 → False、普通数值 → 0；
        - `member_min_rows` / `points_per_page` / `land_min_rows` 是**版式常量**
          （空白表格要保留空行数），保留样例值；
        - `packets` 特殊：给一个空白 packet（空发包方/承包方/地块 + 预留空行
          的界址点表），否则数据类调查表会渲染成零页空白 Word。
        """
        blank = _blank_value(self._sample_context())
        blank["packets"] = [_blank_cadastral_packet()]
        return blank

    def _resolve_template_meta(self, template_key: str) -> dict:
        meta = self.template_registry.get(template_key)
        if meta is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="打印模板类型不存在")
        return meta

    def _resolve_print_template_path(self, template_key: str) -> tuple[dict, Path]:
        meta = self._resolve_template_meta(template_key)
        path = (self.template_dir / meta["filename"]).resolve()
        template_root = self.template_dir.resolve()
        if not path.is_file() or template_root not in path.parents:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{meta['name']}文件不存在")
        return meta, path

    def _validate_template(self, content: str) -> None:
        try:
            Environment(autoescape=False).parse(content)
        except TemplateSyntaxError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"模板语法错误：第 {exc.lineno} 行，{exc.message}",
            ) from exc

    def _sample_context(self) -> dict:
        parcels = [
            {
                "dkmc": "大梨园东西路南",
                "dkbm": "0000001032010100287",
                "dkbm_prefix": "00000010320101",
                "dkbm_suffix": "00287",
                "dkdz": "邻户丁",
                "dkxz": "邻户甲",
                "dknz": "邻户乙、邻户辛",
                "dkbz": "邻户丙、邻户壬等",
                "scmj_mu": "0.68",
                "dldj_text": "三等地",
                "code": "00287",
                "area": "0.68",
                "area_mu": "0.68",
                "boundaries": "东至邻户丁，南至邻户乙，西至邻户甲，北至邻户丙",
                "is_basic_farmland": True,
                "remarks": "",
            },
            {
                "dkmc": "富士地（东）南段",
                "dkbm": "0000001032010100072",
                "dkbm_prefix": "00000010320101",
                "dkbm_suffix": "00072",
                "dkdz": "邻户戊、邻户己",
                "dkxz": "邻户甲",
                "dknz": "××居民地",
                "dkbz": "机耕路",
                "scmj_mu": "0.95",
                "dldj_text": "三等地",
                "code": "00072",
                "area": "0.95",
                "area_mu": "0.95",
                "boundaries": "东至邻户戊，南至××居民地，西至邻户甲，北至机耕路",
                "is_basic_farmland": False,
                "remarks": "",
            },
            {
                "dkmc": "东北河湾地",
                "dkbm": "0000001032010100014",
                "dkbm_prefix": "00000010320101",
                "dkbm_suffix": "00014",
                "dkdz": "邻户庚",
                "dkxz": "邻户甲",
                "dknz": "机耕路",
                "dkbz": "××居民地",
                "scmj_mu": "1.20",
                "dldj_text": "三等地",
                "code": "00014",
                "area": "1.20",
                "area_mu": "1.20",
                "boundaries": "东至邻户庚，南至机耕路，西至邻户甲，北至居民地",
                "is_basic_farmland": True,
                "remarks": "",
            },
        ]
        family_members = [
            {
                "name": "张某",
                "id_type": "身份证",
                "id_number": "342221********4018",
                "relation": "户主",
                "phone": "153****6993",
                "cyxm": "张某",
                "relation_text": "户主",
                "cyzjhm": "342221********4018",
                "remark": "",
            },
            {
                "name": "李某",
                "id_type": "身份证",
                "id_number": "342221********4060",
                "relation": "配偶",
                "phone": "",
                "cyxm": "李某",
                "relation_text": "配偶",
                "cyzjhm": "342221********4060",
                "remark": "",
            },
        ]
        return {
            "authentication_no": "××NO.000104",
            "cbhtbm": "000000103201010028J",
            "fbfbm": "00000010320101",
            "fbfmc": "××县××镇××村股份经济合作社",
            "fbf_social_credit_code": "N0000000MF0000000",
            "fbf_fzr": "刘某",
            "fbf_fzr_zjhm": "342221********4238",
            "fbf_lxdh": "137****8699",
            "cbfbm": "000000103201010028",
            "cbfmc": "张某",
            "cbfzjhm": "342221********4018",
            "lxdh": "153****6993",
            "cbfdz": "××省××市××县××镇××村××组",
            "contract_years": "30",
            "cbqxq_iso": "2028-12-31",
            "cbqxz_iso": "2058-12-30",
            "qdsj_cn": "2026年2月9日",
            "htzmjm": "2.83",
            "cbdkzs": 3,
            "group_region_name": "××村××组",
            "family_members": family_members,
            "parcels": parcels,
            # 合同末页附件「承包地块示意图」；版式与 poltsketchmap.html 一致
            "sketch": _sample_sketch_context(parcels),
            "right_type": "land_contract",
            "reg_type": "first",
            "contract_method": "family",
            "rep_name": "张某",
            "rep_id_type": "身份证",
            "rep_id_number": "342221********4018",
            "rep_phone": "153****6993",
            "issuer_name": "××县××镇××村股份经济合作社",
            "issuer_id_type": "统一社会信用代码",
            "issuer_id_number": "N0000000MF0000000",
            "issuer_phone": "137****8699",
            "auditor": "审核者：××村××组　2026年2月9日",
            "mapper": "制图者：××村××组　2026年2月9日",
            "compile_unit": _survey_org_setting(),
            "right_start_date": "2028-12-31",
            "right_end_date": "2058-12-30",
            "applicant_remarks": "",
            "total_area_mu": "2.83",
            "total_parcels": 3,
            "inquiry_q1": "yes",
            "inquiry_q2": "no",
            "inquiry_q3": "无",
            "survey_org": _survey_org_setting(),
            "member_min_rows": CADASTRAL_MEMBER_MIN_ROWS,
            "points_per_page": CADASTRAL_POINTS_PER_PAGE,
            "packets": [_sample_cadastral_packet(parcels, family_members)],
            # ── 集体/单户登记申请书预览样例（值一律脱敏，禁止真实个人信息） ──
            "county_name": "××县",
            "town_name": "××镇",
            "village_name": "××居",
            "group_name": "一××组",
            "apply_year": "2026",
            "apply_number": "1",
            "sign_year": "",
            "sign_month": "",
            "sign_day": "",
            "land_area_mu": "729.13",
            "term_start": "1995年12月31日",
            "term_end": "2025年12月31日",
            "family_number": "89",
            "fbf_zjhm": "342221********4238",
            "cbf_lxdh": "153****6993",
            "contract_code": "000000103201010028J",
            "old_term_end": "2028年12月31日",
            "family_count": "5",
            "parcel_count": "3",
            "area_mu": "2.83",
            "contract_term_start": "2025年1月1日",
            "contract_term_end": "2054年12月31日",
            "applicant_date": "2026年11月9日",
            # ── 两张摸底表的预览样例（字段与 survey/sheet.py 的上下文同键） ──
            **_sample_sheet_context(),
            # ── 村组公示签字表预览样例（值一律脱敏，禁止真实个人信息） ──
            **_sample_publicity_context(),
            # ── 村组公告表预览样例（键与 village_announcement_export_service 同源） ──
            **_sample_announcement_context(),
        }


def _sample_announcement_context() -> dict:
    """村组公告表预览样例（2026-11-12 与导出上下文同键，值脱敏）。"""
    return {
        "unit_name": "示范县样例镇样例村村民委员会",
        "group_name": "样例村第一村民小组",
        "stamp_unit": "样例村村民委员会",
        "address": "样例村村民委员会(地址:示范县样例镇样例村村委会)",
        "households": 89,
        "parcels": 594,
        "area_text": "729.13",
        "end_date_cn": "2026 年 12 月 12 日",
        "announce_date_cn": "2026年11月12日",
    }


def _sample_sheet_context() -> dict:
    """两张摸底表预览样例（键与 ``survey/sheet.py`` 的打印上下文同源）。"""
    return {
        "land_min_rows": 6,
        # 与模板默认一致：代号行下预留 7 行（2026-10-15 用户批注），不含合计行
        "member_min_rows": 7,
        "totals": {"originalAreaMu": "2.87", "currentAreaMu": "2.87"},
        # 调查记事预印句式（与 survey/sheet.py::build_land_change_context 的 note 同键）
        "note": {
            "memberCount": "2",
            "secondRoundAreaMu": "2.87",
            "perCapitaMu": "1.44",
            "confirmAreaMu": "2.87",
            "expropriationAreaMu": "1.20",
            "expropriationYear": "2017",
        },
        "sheet": {
            "contractNo": "000000103201010028J",
            "originalContractNo": "",
            "hasContract": True,
            "contractSignDate": "1998-09-15",
            "contractStartDate": "1998-09-15",
            "familyContractMode": "family",
            "hasCertificate": True,
            "certificateNo": "000000103201010028J",
            "originalRepresentative": "",
            "surveyNote": "",
            "auditNote": "",
            "auditorName": "",
            "auditDate": "",
            "remark": "",
            "surveyorName": "刘某",
            "surveyDate": "2026-03-12",
        },
        "items": [
            {
                "dkbm": "0000001032010100287",
                "dkmc": "大梨园东西路南",
                "east": "邻户丁", "south": "邻户乙", "west": "邻户甲", "north": "邻户丙",
                "areaMu": "0.68", "originalAreaMu": "0.68",
                "registeredAreaMu": "0.68", "currentAreaMu": "0.68",
                "reasonIndex": None,
                "changeReasonText": "", "changeTime": "", "remark": "",
            },
            {
                "dkbm": "0000001032010100072",
                "dkmc": "富士地（东）南段",
                "east": "邻户戊", "south": "××居民地", "west": "邻户甲", "north": "机耕路",
                "areaMu": "0.95", "originalAreaMu": "0.95",
                "registeredAreaMu": "0.95", "currentAreaMu": "0.95",
                "reasonIndex": 1,
                "changeReasonText": "互换", "changeTime": "2026-03-12", "remark": "",
            },
        ],
        "rows": [
            {
                "memberName": "张某", "idNo": "342221********4018", "phone": "",
                "relationText": "户主",
                "participatedSecondRound": True, "inRegister": True, "is1996Member": True,
                "srEventType": "", "srEventDate": "", "srCompensated": False, "srWithdraw": False,
                "extEventType": "", "extEventDate": "", "extCompensated": False, "extWithdraw": False,
                "changeTime": "", "inHousehold": True, "economicRelation": "",
                "isFiscalSupported": False, "isCivilServant": False, "remark": "",
            },
            {
                "memberName": "张小某", "idNo": "342221********4017", "phone": "153****6993",
                "relationText": "之子",
                "participatedSecondRound": False, "inRegister": True, "is1996Member": False,
                "srEventType": "add_birth", "srEventDate": "1995-02-11", "srCompensated": True, "srWithdraw": False,
                "extEventType": "", "extEventDate": "", "extCompensated": False, "extWithdraw": False,
                "changeTime": "1995.02", "inHousehold": True, "economicRelation": "本户成员",
                "isFiscalSupported": False, "isCivilServant": False, "remark": "",
            },
            {
                "memberName": "周某", "idNo": "", "phone": "",
                "relationText": "母亲",
                "participatedSecondRound": True, "inRegister": True, "is1996Member": True,
                "srEventType": "sub_death", "srEventDate": "2012-06-18", "srCompensated": False, "srWithdraw": False,
                "extEventType": "", "extEventDate": "", "extCompensated": False, "extWithdraw": False,
                "changeTime": "2012.06", "inHousehold": False, "economicRelation": "",
                "isFiscalSupported": False, "isCivilServant": False, "remark": "2012 年去世",
            },
        ],
        "noteStats": {
            "rep1996": "",
            "rep2018": "张某",
            "pop1996": 2,
            "joinExt": 2,
            "addCount": 1,
            "subCount": 1,
            "currentCount": 2,
            "registerCount": 3,
            "collectiveCount": 1,
            "fiscalCount": 0,
            "civilCount": 0,
            "compensatedCount": 0,
            "withdrawCount": 0,
        },
        "contractor": {
            "name": "张某",
            "repIdNo": "342221********4019",
            "code": "000000103201010028",
            "groupName": "××村××组　",
            "postcode": "000000",
            "issuerName": "××县××镇××村××组",
            "issuerCounty": "××县",
            "issuerTown": "××镇",
            "issuerVillage": "××村",
            "issuerHamlet": "××组",
            "issuerCode": "00000010000102",
        },
    }


def _sample_publicity_context() -> dict:
    """村组公示签字表预览样例（键与 ``village_publicity.html`` 同源）。

    ⚠️ 样例值必须脱敏（张某 / 138****0000 / ××县），不得使用真实个人信息——
    见 2026-11-07 预览样例脱敏约定。
    """
    return {
        "issuer": {
            "name": "××县××镇××村××组",
            "code": "00000010002201",
            "head": "张某",
            "phone": "138****0000",
            "address": "××省××市××县××镇××村××组",
            "postcode": "000000",
            "id_type": "身份证",
            "id_no": "320000********0000",
        },
        "note_text": (
            "1995年二轮承包土地时，本组共有土地面积＿＿＿＿亩，承包人口＿＿＿＿人，"
            "其中包括得0.5亩口粮田＿＿人；2007年修建省道被征用土地＿＿亩，"
            "现本组剩余土地＿＿＿＿亩。"
        ),
        "surveyors": "刘某、李某、王某",
        "survey_date": "2015年2月10日",
        "audit_note": "／",
        "auditor": "／",
        "audit_date": "年   月  日",
    }


def _survey_org_setting() -> str:
    """模板管理页预览用的「调查单位（机构）」。

    与实际打印读同一个字典项（``survey_org``），避免"预览一个名字、打印另一个名字"。
    预览属于辅助功能，数据库不可用时直接退回默认值，不让整个预览失败。
    """
    try:
        with SessionLocal() as db:
            value = dictionary_service.get_setting(db, SURVEY_ORG_DICT_TYPE, DEFAULT_SURVEY_ORG)
    except Exception:  # noqa: BLE001 - 预览不应因取配置失败而报错
        return DEFAULT_SURVEY_ORG
    return value or DEFAULT_SURVEY_ORG


def _sample_sketch_context(parcels: list[dict]) -> dict:
    """合同末页附件「承包地块示意图」的样例数据（模板管理页预览用）。

    键名必须与 ``contract_template_service.build_plot_sketch_data`` 的返回一致，
    否则预览会静默少画图。图形只用于预览，取的是 poltsketchmap.html 里那批样例
    多边形，不代表任何真实地块。
    """
    geometries = [
        [[0, 0], [62, 6], [118, 5], [119, 24], [57, 23], [0, 18], [0, 0]],
        [[31, 0], [75, 2], [55, 118], [8, 127], [31, 0]],
        [[48, 0], [61, 1], [43, 126], [31, 126], [48, 0]],
        [[42, 0], [74, 5], [52, 82], [42, 82], [28, 133], [52, 135], [42, 0]],
        [[0, 0], [114, 0], [109, 118], [0, 121], [0, 0]],
    ]
    plots = []
    for index, parcel in enumerate(parcels):
        plots.append({
            "code": parcel.get("dkbm_suffix") or parcel.get("dkbm", ""),
            "dkbm": parcel.get("dkbm", ""),
            "area": parcel.get("scmj_mu", ""),
            "north": parcel.get("dkbz", ""),
            "south": parcel.get("dknz", ""),
            "west": parcel.get("dkxz", ""),
            "east": parcel.get("dkdz", ""),
            "geometry": {"type": "Polygon", "coordinates": [geometries[index % len(geometries)]]},
        })
    overview = plots + [
        {
            "dkbm": "0000001032010100200",
            "geometry": {"type": "Polygon", "coordinates": [geometries[3]]},
        },
        {
            "dkbm": "0000001032010100201",
            "geometry": {"type": "Polygon", "coordinates": [geometries[4]]},
        },
    ]
    return {
        "plots": plots,
        "overview": overview,
        "highlight": plots,
        "village_name": "××村××组",
        "auditor": "审核者：刘某　2026年02月09日",
        "mapper": "制图者：刘某　2026年02月09日",
        "compile_unit": _survey_org_setting(),
        "audit_date": "2026年02月09日",
        "map_date": "2026年02月09日",
    }


def _sample_cadastral_packet(parcels: list[dict], family_members: list[dict]) -> dict:
    """Sample context for the cadastral-survey template (template管理页预览用）。

    这份样例必须与真实打印件（``contract_template_service._build_cadastral_packet``）
    **保持同一套键**，否则预览会报错或"静默少列"。凡是列排布/勾选结构，
    一律调真实打印用的同一个函数，不要在这里另写一套。
    """

    def make_points(count: int) -> list[dict]:
        base_x, base_y = 3685858.192, 39591674.606
        # 界标类型 / 界址线类别 / 界址线位置 是甲方表上的**固定勾选格**，
        # 列跨度由 CADASTRAL_*_COLUMNS 决定。预览要让三种情况各出现一次：
        #   · 第 1 行：木桩（C.12 码值 5） + 沟渠（02） + 内（01）→ 都是"码值命中"；
        #   · 第 2 行：水泥桩（码值 2，甲方表上没这格）→ 走 fallback 落「埋石」；
        #   · 第 3 行起：界标类型为空 → 走 fallback 落「无」，界址线两组留空。
        # 这样一眼能看出「界标类型三选一」与「其他两组只勾命中项」的差别。
        mark_samples: tuple[str | None, ...] = ("5", "2", None)
        line_samples: tuple[str | None, ...] = ("02", "01", None)
        pos_samples: tuple[str | None, ...] = ("01", "02", None)
        points = []
        for index in range(count):
            mark = mark_samples[index] if index < len(mark_samples) else None
            line = line_samples[index] if index < len(line_samples) else None
            pos = pos_samples[index] if index < len(pos_samples) else None
            points.append({
                "seq": index + 1,
                "code": f"J{index + 1}",
                "x": f"{base_x + index * 12.345:.3f}",
                "y": f"{base_y + index * 9.876:.3f}",
                "edge": f"{15.4 + index:.3f}",
                "remark": "",
                "jzdh": "",
                "mark_flags": boundary_column_flags(
                    CADASTRAL_MARK_TYPE_COLUMNS,
                    mark,
                    fallback=CADASTRAL_MARK_TYPE_FALLBACK,
                ),
                "line_flags": boundary_column_flags(
                    CADASTRAL_LINE_CATEGORY_COLUMNS, line,
                ),
                "pos_flags": boundary_column_flags(
                    CADASTRAL_LINE_POSITION_COLUMNS, pos,
                ),
                "line_note": "",
            })
        return points

    members = [
        {
            "name": item.get("cyxm") or item.get("name") or "",
            "relation": item.get("relation_text") or item.get("relation") or "",
            "id_no": item.get("cyzjhm") or item.get("id_number") or "",
            "remark": item.get("remark") or "",
        }
        for item in family_members
    ]

    sample_parcels = []
    for index, parcel in enumerate(parcels):
        points = make_points(4 + index)
        sample_parcels.append({
            "dkbm": parcel.get("dkbm", ""),
            "dkmc": parcel.get("dkmc", ""),
            "dklb_text": "承包地块",
            "fbfbm": "00000010320101",
            "htmjm": parcel.get("scmj_mu", ""),
            "scmj": parcel.get("scmj", ""),
            "area_mu": parcel.get("scmj_mu", ""),
            "east": parcel.get("dkdz", ""),
            "south": parcel.get("dknz", ""),
            "west": parcel.get("dkxz", ""),
            "north": parcel.get("dkbz", ""),
            "boundary_note": "",
            "use_text": "种植业",
            "use_flags": [
                {"label": "种植业", "checked": True},
                {"label": "林业", "checked": False},
                {"label": "畜牧业", "checked": False},
                {"label": "渔业", "checked": False},
            ],
            "grade_text": "三等地",
            "landuse_text": parcel.get("tdlylx_text", "旱地"),
            "landuse_flags": [
                {"label": "水田", "checked": False},
                {"label": "旱地", "checked": True},
                {"label": "水浇地", "checked": False},
                {"label": "林地", "checked": False},
                {"label": "果园", "checked": False},
            ],
            "basic_farmland": bool(parcel.get("is_basic_farmland")),
            "sheet_no": "",
            "survey_note": "经调查该地块信息准确无误。",
            "audit_note": "同意。",
            "auditor": "",
            "audit_date_text": "",
            "points": points,
            "point_pages": [points],
            "table_points": points[:8],
            "table_point_rows": max(8, len(points[:8])),
            "hidden_point_count": max(0, len(points) - 8),
            "has_points": True,
            # 空行勾选列：与真实打印件共用同一个函数，列跨度不会跑偏。
            "blank_flags": blank_boundary_flags(),
        })

    return {
        "issuer": {
            "name": "××县××镇××村股份经济合作社",
            "code": "00000010320101",
            "head": "刘某",
            "head_id_type": "居民身份证",
            "head_id_no": "342221********4238",
            "head_phone": "137****8699",
            "address": "××省××市××县××镇××村",
            "postcode": "000000",
            "survey_note": "经调查该发包方基本情况属实，四至界线清晰无争议。",
            "surveyor": "刘某",
            "survey_date_text": "2026年02月09日",
            "audit_note": "合格。",
            "auditor": "刘某",
            "audit_date_text": "2026年02月09日",
        },
        "contractor": {
            "name": "张某",
            "code": "000000103201010028",
            "groupName": "××村××组　",
            "short_code": "0028",
            "type_text": "农户",
            "id_type": "居民身份证",
            "id_no": "342221********4018",
            "phone": "153****6993",
            "address": "××省××市××县××镇××村××组",
            "postcode": "000000",
            "has_contract": True,
            "contract_code": "000000103201010028J",
            "has_cert": True,
            "cert_code": "000000103201010028J",
            "acquire_method": "家庭承包",
            "acquire_code": "110",
            "term_begin": "2028年12月31日",
            "term_end": "2058年12月30日",
            "term_years": "30",
            "member_count": len(members),
            "members": members,
            "sheet_ysdm": "",
            "survey_note": (
                "承包方代表变更情况：无变更\n"
                "土地承包经营权权属特殊情况：无。\n"
                "农户内成员分家析产、合户或家庭成员其他情况：无。\n"
                "其他需要说明的情况：无。\n"
                "调查员：张某（签字并摁手印）\n"
                "日期：2026年02月09日"
            ),
            "audit_note": "合格。",
            "auditor": "刘某",
            "audit_date_text": "2026年02月09日",
        },
        "parcels": sample_parcels,
        "survey_date_text": "2026年02月09日",
    }


# ── 空白上下文构造 ────────────────────────────────────────────────────────

#: 空白渲染时保留数值的键：这些是"空白表格保留几行"的版式常量，不能归零。
_BLANK_KEEP_NUMERIC_KEYS = frozenset({"member_min_rows", "points_per_page", "land_min_rows"})


def _blank_value(value, key: str = ""):
    """递归把样例上下文置空：字符串→""、布尔→False、数值→0（版式常量除外）、
    列表→[]、字典→同键递归。"""
    if isinstance(value, str):
        return ""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)) and key not in _BLANK_KEEP_NUMERIC_KEYS:
        return 0
    if isinstance(value, list):
        return []
    if isinstance(value, dict):
        return {name: _blank_value(item, name) for name, item in value.items()}
    return value


def _blank_parcel() -> dict:
    """空白地块 packet：键与 `_sample_cadastral_packet` 的地块条目一致。

    勾选列（用途/地类/界标类型等）保留标签、全部不勾选——否则空白调查表的
    勾选格会整列消失，与甲方版式对不上；界址点表给 `table_point_rows` 个空行。
    """
    points: list[dict] = []
    return {
        "dkbm": "",
        "dkmc": "",
        "dklb_text": "",
        "fbfbm": "",
        "htmjm": "",
        "scmj": "",
        "area_mu": "",
        "east": "",
        "south": "",
        "west": "",
        "north": "",
        "boundary_note": "",
        "use_text": "",
        "use_flags": [
            {"label": "种植业", "checked": False},
            {"label": "林业", "checked": False},
            {"label": "畜牧业", "checked": False},
            {"label": "渔业", "checked": False},
        ],
        "grade_text": "",
        "landuse_text": "",
        "landuse_flags": [
            {"label": "水田", "checked": False},
            {"label": "旱地", "checked": False},
            {"label": "水浇地", "checked": False},
            {"label": "林地", "checked": False},
            {"label": "果园", "checked": False},
        ],
        "basic_farmland": False,
        "sheet_no": "",
        "survey_note": "",
        "audit_note": "",
        "auditor": "",
        "audit_date_text": "",
        "points": points,
        "point_pages": [points],
        "table_points": points,
        "table_point_rows": 8,
        "hidden_point_count": 0,
        "has_points": False,
        "blank_flags": blank_boundary_flags(),
    }


def _blank_cadastral_packet() -> dict:
    """空白调查表 packet：键与 `_sample_cadastral_packet` 返回一致，值全空。"""
    return {
        "issuer": {
            "name": "", "code": "", "head": "", "head_id_type": "",
            "head_id_no": "", "head_phone": "", "address": "", "postcode": "",
            "survey_note": "", "audit_note": "", "auditor": "", "audit_date_text": "",
            "surveyor": "", "survey_date_text": "",
        },
        "contractor": {
            "name": "", "code": "", "groupName": "", "short_code": "",
            "type_text": "", "id_type": "", "id_no": "", "phone": "",
            "address": "", "postcode": "",
            # 三态：None ⇒ 空白件「有/无」两框全空；真实数据为布尔时行为不变
            "has_contract": None, "contract_code": "",
            "has_cert": None, "cert_code": "", "acquire_method": "", "acquire_code": "",
            "term_begin": "", "term_end": "", "term_years": "", "member_count": 0,
            "members": [], "sheet_ysdm": "", "survey_note": "", "audit_note": "",
            "auditor": "", "audit_date_text": "",
        },
        "parcels": [_blank_parcel()],
        "survey_date_text": "",
    }


contract_template_admin_service = ContractTemplateAdminService()
