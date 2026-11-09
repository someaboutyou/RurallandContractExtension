"""
Contract template rendering service.

Renders the 农村土地承包合同 HTML template with live contract data,
supporting both screen preview and print-ready output.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.cbht import Cbht
from app.models.dictionary import DictionaryItem
from app.models.fbf import Fbf
from app.models.survey import (
    SurveyCbdkxxResult,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyDkResult,
    SurveyFbfResult,
)
from app.repositories.land_parcel_repository import land_parcel_repository
from app.services.dictionary_service import (
    DEFAULT_SURVEY_ORG,
    SURVEY_ORG_DICT_TYPE,
    dictionary_service,
)
from app.services.relation_codes import (
    FALLBACK_RELATION_LABELS,
    pick_household_head,
    relation_labels,
)
from app.services.survey.boundary import (
    CADASTRAL_LINE_CATEGORY_COLUMNS,
    CADASTRAL_LINE_POSITION_COLUMNS,
    CADASTRAL_MARK_TYPE_COLUMNS,
    CADASTRAL_MARK_TYPE_FALLBACK,
    boundary_column_flags,
    build_boundary_map,
)


def blank_boundary_flags() -> dict:
    """空行用的"全未勾选"列标记，列跨度与真实数据行完全一致。

    甲方《承包地块调查表》的勾选格是固定的（界标类型 3 格、界址线类别 12 格、
    界址线位置 4 格），列排布来自 :mod:`app.services.survey.boundary` 里的
    ``CADASTRAL_*_COLUMNS``，与真实数据行共用同一份定义。

    ⚠️ 这里**不传** ``fallback``：空行本身没有界址点（点号列也是空的），
    若给界标类型走兜底，每一行空白行都会印上一个「☑无」。

    模板管理页的预览（``contract_template_admin_service``）也调它，
    避免"预览用一套列、真打印用另一套列"。
    """
    return {
        "mark_flags": boundary_column_flags(CADASTRAL_MARK_TYPE_COLUMNS, None),
        "line_flags": boundary_column_flags(CADASTRAL_LINE_CATEGORY_COLUMNS, None),
        "pos_flags": boundary_column_flags(CADASTRAL_LINE_POSITION_COLUMNS, None),
    }

# ── 枚举值映射 ───────────────────────────────────────────

CBF_TYPE_MAP = {
    "1": "农户", "2": "个人", "3": "其他方式承包",
}
ZJLX_MAP = {
    "1": "居民身份证", "2": "户口簿", "3": "军官证",
    "4": "护照", "5": "统一社会信用代码", "9": "其他",
}
CBFS_MAP = {
    "001": "家庭承包", "002": "其他方式承包",
    "003": "招标", "004": "拍卖", "005": "公开协商",
}
CBJYQQDFS_MAP = {
    "001": "家庭承包", "002": "招标", "003": "拍卖",
    "004": "公开协商", "005": "转让", "006": "互换",
    "007": "赠与", "008": "继承", "009": "其他",
}
DK_LB_MAP = {
    "01": "耕地", "02": "园地", "03": "林地",
    "04": "草地", "05": "养殖水面", "09": "其他",
}
TDLYLX_MAP = {
    "011": "水田", "012": "水浇地", "013": "旱地",
    "021": "果园", "022": "茶园", "023": "其他园地",
    "031": "有林地", "032": "灌木林地", "033": "其他林地",
    "041": "天然牧草地", "042": "人工牧草地",
    "111": "设施农用地", "114": "坑塘水面",
}
SFJBNT_MAP = {"1": "是", "0": "否", "2": "否"}
DLDJ_MAP = {
    "1": "一等地", "2": "二等地", "3": "三等地", "4": "四等地",
    "5": "五等地", "6": "六等地", "7": "七等地", "8": "八等地",
    "9": "九等地", "10": "十等地",
    "01": "一等地", "02": "二等地", "03": "三等地", "04": "四等地",
    "05": "五等地", "06": "六等地", "07": "七等地", "08": "八等地",
    "09": "九等地",
}
# 与户主关系码 → 展示文案。
# ⛔ 这份兜底值**必须与字典 `nyt2539_c20_relation_to_head` 一致**（`02`=户主、`01`=本人）。
# 旧实现写的是 `01`=户主 / `02`=配偶（NY/T 2539 早期码序），与库内字典、与真实数据**全部错位**：
# 真实户主是 `02` ⇒ 合同成员表会把户主印成"配偶"、把配偶印成裸码 `10`（2026-09-25 修）。
# 运行时优先取字典，见 `relation_labels(db)`；这里直接复用同一份派生结果，避免第二份真相。
YHZGX_MAP = FALLBACK_RELATION_LABELS

# 二级地类补充表（survey_dk_result.tdlylx，GB/T 21010 二级类）
TDLYLX_FULL_MAP = {
    "011": "水田", "012": "水浇地", "013": "旱地",
    "021": "果园", "022": "茶园", "023": "其他园地",
    "031": "有林地", "032": "灌木林地", "033": "其他林地",
    "041": "天然牧草地", "042": "人工牧草地",
    "111": "设施农用地", "114": "坑塘水面", "117": "沟渠",
}

# 承包地块调查表 —— 土地用途（C.9）勾选项
CADASTRAL_LAND_USE_OPTIONS = (
    ("种植业", ("1",)),
    ("林业", ("2",)),
    ("畜牧业", ("3",)),
    ("渔业", ("4",)),
)
# 承包地块调查表 —— 土地利用类型勾选项（按二级地类归并）
CADASTRAL_LANDUSE_OPTIONS = (
    ("水田", ("011",)),
    ("旱地", ("013",)),
    ("水浇地", ("012",)),
    ("林地", ("031", "032", "033")),
    ("果园", ("021", "022", "023")),
)
# 界址点坐标成果表每页可容纳的点数。
#   甲方原表数据区是 28 行，但每 2 行才是「一个点」（跨行合并成视觉上一行、边长错开
#   一行），原表一页实际排 14 个点。我们按"填满正文区"重定标：
#     纵向页正文区 265mm − 标题 13.06mm − 表头 27.24mm = 224.70mm 给点位区，
#     每个点 10.90mm（两个 5.45mm 半行）⇒ 上限 20.6。
#   ⚠️ 上限不能取 20：Word 侧实测（Word COM 逐单元格量 y，样本户 4 个地块）
#     19 点时表格底 271.06mm / 正文底边 283mm，余量 11.94mm（够一行）；
#     20 点时余量只剩约 1mm，被 Word 的行高取整顶翻 —— 4 张成果表各多出一张
#     空白页（11 页 → 15 页）。取 19 是"几乎填满 + 仍留一整行余量"的折中。
#   半行高度 5.45mm 也不能再小：Word 表格行有最小行高（9pt 字体实测约 13pt
#   ≈ 4.59mm），给 2.60mm 会被顶到 4.59mm，一张 28 点的表直接溢出 111mm。
CADASTRAL_POINTS_PER_PAGE = 19
# 承包地块调查表界址点区单页最多可排的行数（原表数据区 8 行，超出部分见《界址点坐标成果表》）
CADASTRAL_PARCEL_POINT_ROWS = 8
# 承包方调查表家庭成员最少留白行数
CADASTRAL_MEMBER_MIN_ROWS = 6


class ContractTemplateService:
    """Render the contract HTML template with live data."""

    def __init__(self):
        template_dir = Path(__file__).resolve().parent.parent / "templates"
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=False,
        )

    # ── public ──────────────────────────────────────────

    def render_contract(
        self, db: Session, *, cbhtbm: str, batch_id: int | None = None,
    ) -> str:
        """Render contract HTML for given contract code.

        If batch_id is provided, pulls contractor & parcel data from survey
        result tables scoped to that batch.  Otherwise falls back to the
        first available survey result row or base data.
        """
        contract = _one(db, select(Cbht).where(Cbht.cbhtbm == cbhtbm))
        if contract is None:
            raise ValueError(f"Contract not found: {cbhtbm}")

        # ── 承包方 ──
        contractor = None
        if contract.cbfbm:
            cbf_query = select(SurveyCbfResult).where(
                SurveyCbfResult.cbfbm == contract.cbfbm
            ).order_by(SurveyCbfResult.id.desc())
            contractor = _one(db, cbf_query)

        # ── 发包方（从合同或承包方获取 fbfbm） ──
        issuer_fbfbm = contract.fbfbm
        if not issuer_fbfbm and contractor:
            issuer_fbfbm = getattr(contractor, "fbfbm", None)
        issuer = None
        if issuer_fbfbm:
            issuer = _one(db, select(Fbf).where(Fbf.fbfbm == issuer_fbfbm))

        # ── 瀹跺涵鎴愬憳 ──
        members = []
        if contractor:
            mq = select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.cbfbm == contract.cbfbm
            )
            members = db.scalars(mq).all()

        # 户主展示口径走统一助手（优先 户主 02 → 本人 01 → 兜底第一条）。
        # ⛔ 旧实现是 `[m for m in members if m.yhzgx == "01"]`，而真实户主是 `02`
        # ⇒ household_head 恒为空、合同"承包方代表"一栏失去数据来源（2026-09-25 修）。
        head_member = pick_household_head(members)
        household_head = (
            [{"cyxm": head_member.cyxm, "cyzjhm": head_member.cyzjhm}]
            if head_member is not None else []
        )
        # 出件文案优先取字典（与前端 useDictionary 同源），字典整类为空才退回内置兜底。
        relation_labels_map = relation_labels(db)
        family_members = [
            {
                "cyxm": m.cyxm or "",
                "relation_text": relation_labels_map.get(m.yhzgx or "", m.yhzgx or ""),
                "cyzjhm": m.cyzjhm or "",
                "remark": getattr(m, "remark", "") or "",
            }
            for m in members
        ]

        # ── 地块 ──
        parcels = self._load_parcels(db, contract.cbhtbm, batch_id)

        # ── 模板上下文 ──
        ctx = {
            # 合同
            "cbhtbm": contract.cbhtbm or "",
            "qdsj": _fmt_date(contract.qdsj),
            "qdsj_cn": _fmt_date_cn(contract.qdsj),
            "cbqxq": _fmt_date(contract.cbqxq),
            "cbqxz": _fmt_date(contract.cbqxz),
            "cbqxq_iso": _fmt_date_iso(contract.cbqxq),
            "cbqxz_iso": _fmt_date_iso(contract.cbqxz),
            "contract_years": _contract_years(contract.cbqxq, contract.cbqxz),
            "cbdkzs": contract.cbdkzs or 0,
            "htzmj": _fmt_decimal(contract.htzmj),
            "htzmjm": _fmt_decimal(contract.htzmjm),
            "yhtzmj": _fmt_decimal(contract.yhtzmj),
            "yhtzmjm": _fmt_decimal(contract.yhtzmjm),
            "cbfs_text": CBFS_MAP.get(contract.cbfs or "", contract.cbfs or ""),
            "cbjyqqdfs_text": "",

            # 发包方
            "fbfbm": issuer.fbfbm if issuer else "",
            "fbfmc": issuer.fbfmc if issuer else "",
            "fbf_fzr": issuer.fbffzrxm if issuer else "",
            "fbf_fzr_zjhm": issuer.fzrzjhm if issuer else "",
            "fbf_dz": issuer.fbfdz if issuer else "",
            "fbf_lxdh": issuer.lxdh if issuer else "",
            "fbf_social_credit_code": getattr(issuer, "tyshxydm", "") if issuer else "",

            # 承包方
            "cbfbm": contract.cbfbm or "",
            "cbfmc": contractor.cbfmc if contractor else "",
            "cbf_type_text": CBF_TYPE_MAP.get(
                contractor.cbflx if contractor else "", ""
            ),
            "cbf_zjlx_text": ZJLX_MAP.get(
                contractor.cbfzjlx if contractor else "", ""
            ),
            "cbfzjhm": contractor.cbfzjhm if contractor else "",
            "cbfdz": contractor.cbfdz if contractor else "",
            "lxdh": contractor.lxdh if contractor else "",
            "cbfcysl": contractor.cbfcysl if contractor else 0,

            # 地块
            "parcels": parcels,

            # 户主
            "household_head": household_head,
            "family_members": family_members,
        }
        template = self._env.get_template("contract.html")
        return template.render(**ctx)

    def render_survey_contract(
        self, db: Session, *, cbhtbm: str, batch_id: int, cbfbm: str,
        parcels_by_contractor: bool = False,
    ) -> str:
        """Render a contract preview from survey result data.

        This path is used by the survey screen where parcel results may already
        carry a contract code, even when the source ``cbht`` row was not imported.

        ``parcels_by_contractor=True`` 用于**平台生成的延包合同**：它的合同编码
        是新发的，地块关联表里仍留着上次承包合同的编码（导入数据保持原样、不改写），
        所以地块与面积要按承包方取当前有效关联，而不是按合同编码反查。
        """
        contract = _one(db, select(Cbht).where(Cbht.cbhtbm == cbhtbm))

        contractor = _one(
            db,
            select(SurveyCbfResult).where(
                SurveyCbfResult.cbfbm == cbfbm,
            ).order_by(SurveyCbfResult.id.desc()),
        )

        relation_filters = [
            SurveyCbdkxxResult.cbfbm == cbfbm,
            SurveyCbdkxxResult.result_status != "removed",
        ]
        if not parcels_by_contractor:
            relation_filters.append(SurveyCbdkxxResult.cbhtbm == cbhtbm)
        relations = db.scalars(select(SurveyCbdkxxResult).where(*relation_filters)).all()
        first_relation = relations[0] if relations else None

        issuer_fbfbm = (
            (contract.fbfbm if contract else None)
            or (first_relation.fbfbm if first_relation else None)
        )
        issuer = None
        if issuer_fbfbm:
            issuer = _one(
                db,
                select(SurveyFbfResult).where(
                    SurveyFbfResult.fbfbm == issuer_fbfbm,
                ),
            ) or _one(db, select(Fbf).where(Fbf.fbfbm == issuer_fbfbm))

        members = []
        if contractor:
            members = db.scalars(
                select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.cbfbm == cbfbm,
                )
            ).all()

        # 户主展示口径走统一助手（优先 户主 02 → 本人 01 → 兜底第一条）。
        # ⛔ 旧实现是 `[m for m in members if m.yhzgx == "01"]`，而真实户主是 `02`
        # ⇒ household_head 恒为空、合同"承包方代表"一栏失去数据来源（2026-09-25 修）。
        head_member = pick_household_head(members)
        household_head = (
            [{"cyxm": head_member.cyxm, "cyzjhm": head_member.cyzjhm}]
            if head_member is not None else []
        )
        # 出件文案优先取字典（与前端 useDictionary 同源），字典整类为空才退回内置兜底。
        relation_labels_map = relation_labels(db)
        family_members = [
            {
                "cyxm": m.cyxm or "",
                "relation_text": relation_labels_map.get(m.yhzgx or "", m.yhzgx or ""),
                "cyzjhm": m.cyzjhm or "",
                "remark": getattr(m, "remark", "") or "",
            }
            for m in members
        ]
        parcels = self._load_parcels(
            db, cbhtbm, batch_id,
            contractor_code=cbfbm if parcels_by_contractor else None,
        )
        htzmj = (
            contract.htzmj if contract and contract.htzmj is not None
            else sum(float(item.htmj or 0) for item in relations)
        )
        htzmjm = (
            contract.htzmjm if contract and contract.htzmjm is not None
            else (float(htzmj or 0) / 666.67 if htzmj else None)
        )
        cbfs = (contract.cbfs if contract else None) or (
            first_relation.cbjyqqdfs if first_relation else ""
        )

        ctx = {
            "cbhtbm": cbhtbm,
            "qdsj": _fmt_date(contract.qdsj if contract else None),
            "qdsj_cn": _fmt_date_cn(contract.qdsj if contract else None),
            "cbqxq": _fmt_date(contract.cbqxq if contract else None),
            "cbqxz": _fmt_date(contract.cbqxz if contract else None),
            "cbqxq_iso": _fmt_date_iso(contract.cbqxq if contract else None),
            "cbqxz_iso": _fmt_date_iso(contract.cbqxz if contract else None),
            "contract_years": _contract_years(
                contract.cbqxq if contract else None,
                contract.cbqxz if contract else None,
            ),
            "cbdkzs": (contract.cbdkzs if contract and contract.cbdkzs is not None else len(parcels)),
            "htzmj": _fmt_decimal(htzmj),
            "htzmjm": _fmt_decimal(htzmjm),
            "yhtzmj": _fmt_decimal(contract.yhtzmj if contract else None),
            "yhtzmjm": _fmt_decimal(contract.yhtzmjm if contract else None),
            "cbfs_text": CBFS_MAP.get(cbfs or "", cbfs or ""),
            "cbjyqqdfs_text": CBJYQQDFS_MAP.get(
                first_relation.cbjyqqdfs if first_relation else "",
                first_relation.cbjyqqdfs if first_relation else "",
            ),
            "fbfbm": getattr(issuer, "fbfbm", "") if issuer else "",
            "fbfmc": getattr(issuer, "fbfmc", "") if issuer else "",
            "fbf_fzr": getattr(issuer, "fbffzrxm", "") if issuer else "",
            "fbf_fzr_zjhm": getattr(issuer, "fzrzjhm", "") if issuer else "",
            "fbf_dz": getattr(issuer, "fbfdz", "") if issuer else "",
            "fbf_lxdh": getattr(issuer, "lxdh", "") if issuer else "",
            "fbf_social_credit_code": getattr(issuer, "tyshxydm", "") if issuer else "",
            "cbfbm": cbfbm,
            "cbfmc": contractor.cbfmc if contractor else "",
            "cbf_type_text": CBF_TYPE_MAP.get(
                contractor.cbflx if contractor else "", ""
            ),
            "cbf_zjlx_text": ZJLX_MAP.get(
                contractor.cbfzjlx if contractor else "", ""
            ),
            "cbfzjhm": contractor.cbfzjhm if contractor else "",
            "cbfdz": contractor.cbfdz if contractor else "",
            "lxdh": contractor.lxdh if contractor else "",
            "cbfcysl": contractor.cbfcysl if contractor else 0,
            "parcels": parcels,
            "household_head": household_head,
            "family_members": family_members,
            # 末页附件「承包地块示意图」的数据包（版式与「承包地块示意图」tab 一致）
            "sketch": self.build_plot_sketch_data(db, parcels=parcels, contractor=contractor),
        }
        template = self._env.get_template("contract.html")
        return template.render(**ctx)

    def render_plot_sketch_map(self, **ctx) -> str:
        """Render the contracted parcel sketch map HTML."""
        template = self._env.get_template("poltsketchmap.html")
        return template.render(**ctx)

    def build_plot_sketch_data(
        self, db: Session, *, parcels: list[dict], contractor,
    ) -> dict:
        """承包地块示意图（合同末页附件）的数据包。

        三块数据：

        · ``plots`` —— **与合同正文同一批地块**（``_load_parcels`` 的结果，即
          「一、承包土地情况」表和 ``htzmjm`` 总计的同一来源），每块补上 GeoJSON 图形。
          ⛔ 不要改用 ``land_parcel_service.get_survey_parcels``：那条路会把
          ``removed`` / ``split_source`` 的历史地块一并算进来，图上地块数会比合同
          正文的「总计」多，附件与正文自相矛盾。
        · ``overview`` —— 周边地块（含本户），给左上角总览图做底图；本户地块另行
          走 ``highlight`` 高亮，两者同源、同一坐标系，才能画在一张图上。
        · 页脚文字 —— 审核者 / 制图者取**公示审核人 + 公示审核日期**（与
          「承包地块示意图」tab 的打印件口径一致），编制单位取「调查单位（机构）」
          字典项（与地籍调查表同源）。

        图形一律取 EPSG:4326 的 GeoJSON 字符串（``land_parcel_repository`` 里已做
        ``ST_Transform``），前端按外接矩形缩放到 SVG，不关心投影。
        """
        codes = [item.get("dkbm") for item in parcels if item.get("dkbm")]
        geometry_map = _load_geometry_map(db, codes)

        plots = [
            {
                "code": item.get("dkbm_suffix") or (item.get("dkbm") or ""),
                "dkbm": item.get("dkbm") or "",
                "area": item.get("scmj_mu") or "",
                "north": item.get("dkbz") or "",
                "south": item.get("dknz") or "",
                "west": item.get("dkxz") or "",
                "east": item.get("dkdz") or "",
                "geometry": geometry_map.get(item.get("dkbm") or ""),
            }
            for item in parcels
        ]

        overview: list[dict] = []
        if codes:
            for row in land_parcel_repository.get_nearby_dk_by_codes(db, codes):
                overview.append({
                    "dkbm": row.get("dkbm") or "",
                    "geometry": _loads_geojson(row.get("geometry")),
                })

        reviewer = (getattr(contractor, "gsshr", None) or "") if contractor else ""
        review_date = (
            (getattr(contractor, "gsshrq", None) or getattr(contractor, "cbfdcrq", None))
            if contractor else None
        )
        date_text = _fmt_date_cn(review_date)
        village_name = (getattr(contractor, "group_region_name", None) or "") if contractor else ""

        return {
            "plots": plots,
            "overview": overview,
            "highlight": plots,
            "village_name": village_name,
            "auditor": f"审核者：{reviewer}　{date_text}" if reviewer and date_text else "",
            "mapper": f"制图者：{reviewer}　{date_text}" if reviewer and date_text else "",
            "compile_unit": dictionary_service.get_setting(
                db, SURVEY_ORG_DICT_TYPE, DEFAULT_SURVEY_ORG,
            ),
            "audit_date": date_text,
            "map_date": date_text,
        }


    def render_registration_application(
        self, db, *, batch_id, cbfbm, contractor_uid,
    ):
        """Render the registration application form from survey result data."""
        from sqlalchemy import select as sa_select
        from app.models.fbf import Fbf
        from app.models.cbht import Cbht
        from app.models.survey import (
            SurveyCbfResult,
            SurveyCbfJtcyResult,
            SurveyCbdkxxResult,
            SurveyFbfResult,
        )

        contractor = _one(
            db,
            sa_select(SurveyCbfResult).where(
                SurveyCbfResult.cbfbm == cbfbm,
            ).order_by(SurveyCbfResult.id.desc()),
        )

        relations = db.scalars(
            sa_select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.cbfbm == cbfbm,
                SurveyCbdkxxResult.result_status != "removed",
            )
        ).all()
        first_relation = relations[0] if relations else None

        cbhtbm = first_relation.cbhtbm if first_relation else None
        contract = None
        if cbhtbm:
            contract = _one(db, sa_select(Cbht).where(Cbht.cbhtbm == cbhtbm))

        issuer_fbfbm = (
            (contract.fbfbm if contract else None)
            or (first_relation.fbfbm if first_relation else None)
        )
        issuer = None
        if issuer_fbfbm:
            issuer = _one(
                db,
                sa_select(SurveyFbfResult).where(
                    SurveyFbfResult.fbfbm == issuer_fbfbm,
                ),
            ) or _one(db, sa_select(Fbf).where(Fbf.fbfbm == issuer_fbfbm))

        # Family members
        members = []
        if contractor:
            members = db.scalars(
                sa_select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.cbfbm == cbfbm,
                )
            ).all()

        # 出件文案优先取字典（与前端 useDictionary 同源），字典整类为空才退回内置兜底。
        # ⛔ 旧实现用硬编码 YHZGX_MAP，而它的码序与字典错位（01=户主 / 02=配偶），
        # 会把真实户主（02）印成"配偶"、把配偶（10）印成裸码（2026-09-25 修）。
        relation_labels_map = relation_labels(db)
        family_members = []
        for m in members:
            family_members.append({
                "name": m.cyxm or "",
                "id_type": ZJLX_MAP.get(m.cyzjlx or "", m.cyzjlx or ""),
                "id_number": m.cyzjhm or "",
                "relation": relation_labels_map.get(m.yhzgx or "", m.yhzgx or ""),
                "phone": "",
            })

        # Parcels
        parcels_raw = self._load_parcels(db, cbhtbm or "", batch_id) if cbhtbm else []
        total_area_mu = sum(float(p.get("scmj_mu", 0) or 0) for p in parcels_raw)

        parcels = []
        for p in parcels_raw:
            boundaries = "东" + (p.get("dkdz", "") or "") + " 西" + (p.get("dkxz", "") or "") + " 南" + (p.get("dknz", "") or "") + " 北" + (p.get("dkbz", "") or "")
            parcels.append({
                "code": p.get("dkbm", ""),
                "boundaries": boundaries,
                "area_mu": p.get("scmj_mu", ""),
                "is_basic_farmland": p.get("sfjbnt_text", "") == "是",
                "remarks": "",
            })

        # Contract method
        cbfs = (contract.cbfs if contract else None) or (first_relation.cbjyqqdfs if first_relation else "")
        contract_method = "family" if cbfs in ("001", "") else "other"

        ctx = {
            "right_type": "land_contract",
            "reg_type": "first",
            "rep_name": contractor.cbfmc if contractor else "",
            "rep_id_type": ZJLX_MAP.get(contractor.cbfzjlx, "") if contractor else "",
            "rep_id_number": contractor.cbfzjhm if contractor else "",
            "rep_phone": contractor.lxdh if contractor else "",
            "family_members": family_members,
            "agent1_name": "",
            "issuer_name": getattr(issuer, "fbfmc", "") if issuer else "",
            "issuer_id_type": "",
            "issuer_id_number": getattr(issuer, "tyshxydm", "") if issuer else "",
            "issuer_phone": getattr(issuer, "lxdh", "") if issuer else "",
            "agent2_name": "",
            "agent2_id_type": "身份证",
            "right_start_date": str(contract.cbqxq) if contract and contract.cbqxq else "",
            "right_end_date": str(contract.cbqxz) if contract and contract.cbqxz else "",
            "applicant_remarks": "",
            "contract_method": contract_method,
            "total_area_mu": f"{total_area_mu:.4f}" if total_area_mu else "",
            "total_parcels": str(len(parcels_raw)) if parcels_raw else "",
            "parcels": parcels,
            "inquiry_q1": "yes",
            "inquiry_q2": "yes",
            "inquiry_q3": "",
        }
        template = self._env.get_template("registration_application.html")
        return template.render(**ctx)

    # ── 登记（延包）申请书：集体 / 单户（承包合同管理页） ─────────

    def render_collective_application(self, db: Session, *, batch_id: int) -> str:
        """《农村土地承包经营权证（家庭承包方式）申请书》—— 集体口径（按批次）。

        版式复刻自 CS 版 ``Template/农村土地承包经营权集体登记申请书.dot``，
        字段口径对齐其书签：县名×3 / 镇名 / 村名 / 组名 / 申请编号 /
        集体土地总面积 / 承包期限 / 农户数 / 落款日期。
        承包期限默认取批次内**上次承包合同**（导入合同）的起止范围 —— 与
        CS 版样张（泗洪：1995-12-31 ~ 2025-12-31）一致；没有导入合同时
        回退现行延包合同。
        """
        from app.models.survey import SurveyBatch, SurveyCbfBase, SurveyCbdkxxBase
        from app.models.cbht import (
            CONTRACT_SOURCE_GENERATED,
            CONTRACT_SOURCE_IMPORTED,
        )

        batch = db.get(SurveyBatch, batch_id)
        if batch is None:
            raise ValueError(f"Survey batch not found: {batch_id}")

        county_name, town_name, village_name, group_name = self._resolve_region_chain(db, batch)

        # 农户数：批次内未注销户去重（与合同总览列表行口径一致）
        uids = db.scalars(
            select(SurveyCbfBase.contractor_uid).where(
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.tenant_code == batch.tenant_code,
                SurveyCbfBase.task_status != "deregistered",
            ).execution_options(skip_tenant_scope=True)
        ).all()
        family_number = len({uid for uid in uids if uid})

        # 集体土地总面积：批次导入地块快照合计（亩）
        area_rows = db.scalars(
            select(SurveyCbdkxxBase.htmj).where(
                SurveyCbdkxxBase.batch_id == batch_id,
                SurveyCbdkxxBase.tenant_code == batch.tenant_code,
            ).execution_options(skip_tenant_scope=True)
        ).all()
        area_sqm = sum(float(v or 0) for v in area_rows)
        land_area_mu = f"{area_sqm / 666.67:.2f}" if area_sqm else ""

        term_start, term_end = self._batch_contract_term_range(
            db, batch_id, batch.tenant_code,
            source=CONTRACT_SOURCE_IMPORTED, fallback_source=CONTRACT_SOURCE_GENERATED,
        )

        today = datetime.now()
        ctx = {
            "county_name": county_name,
            "town_name": town_name,
            "village_name": village_name,
            "group_name": group_name,
            "apply_year": str(today.year),
            "apply_number": "",  # 镇级申请书流水号：默认留空手工编号
            "sign_year": "",     # 落款日期：默认留空（盖章时手填）
            "sign_month": "",
            "sign_day": "",
            "land_area_mu": land_area_mu,
            "term_start": term_start,
            "term_end": term_end,
            "family_number": str(family_number) if family_number else "",
        }
        template = self._env.get_template("collective_registration_application.html")
        return template.render(**ctx)

    def render_household_application(self, db: Session, *, batch_id: int, contractor_uid: str) -> str:
        """《第二轮土地承包到期后再延长三十年登记申请表》—— 单户口径。

        版式复刻自 CS 版 ``Template/农村土地承包经营权单户登记申请书.dot``。
        发包方取该户地块关联 / 合同指向的发包方；申请人取承包方（户主）；
        期限取现行延包合同；未生成合同的户默认自申请之日（渲染当日）起
        30 年（止 = 起 + 30 年 − 1 天），不再沿用上次承包合同的旧期限，
        前端在打印/导出前会向用户提示这一默认口径。到期日（"于…到期"）
        仍取上次承包合同的期限止 —— 与 CS 样张「2024年12月31日到期…」一致。
        """
        from app.models.survey import SurveyBatch, SurveyCbfBase, SurveyCbdkxxBase
        from app.models.cbht import (
            CONTRACT_SOURCE_GENERATED,
            CONTRACT_SOURCE_IMPORTED,
        )

        batch = db.get(SurveyBatch, batch_id)
        if batch is None:
            raise ValueError(f"Survey batch not found: {batch_id}")

        contractor = _one(
            db,
            select(SurveyCbfBase).where(
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.tenant_code == batch.tenant_code,
                SurveyCbfBase.contractor_uid == contractor_uid,
            ).order_by(SurveyCbfBase.id.desc()).execution_options(skip_tenant_scope=True),
        )
        if contractor is None:
            raise ValueError(f"Survey contractor not found: batch={batch_id} uid={contractor_uid}")

        # 地块关联（导入快照）：发包方编码 + 合同编码 + 面积
        relations = db.scalars(
            select(SurveyCbdkxxBase).where(
                SurveyCbdkxxBase.batch_id == batch_id,
                SurveyCbdkxxBase.tenant_code == batch.tenant_code,
                SurveyCbdkxxBase.cbfbm == contractor.cbfbm,
            ).execution_options(skip_tenant_scope=True)
        ).all()
        first_relation = relations[0] if relations else None

        parcel_count = len(relations)
        area_sqm = sum(float(r.htmj or 0) for r in relations)
        area_mu = f"{area_sqm / 666.67:.2f}" if area_sqm else ""

        # 现行延包合同（本批次该户 active 的那条）
        generated = db.scalars(
            select(Cbht).where(
                Cbht.survey_batch_id == batch_id,
                Cbht.contractor_uid == contractor_uid,
                Cbht.contract_source == CONTRACT_SOURCE_GENERATED,
                Cbht.contract_status == "active",
            ).execution_options(skip_tenant_scope=True)
        ).all()
        current_contract = generated[0] if generated else None

        # 上次承包合同编码（导入关联 → 导入合同表）
        original_code = (first_relation.cbhtbm if first_relation else None) or None
        if not original_code:
            original_code = _one(
                db,
                select(Cbht).where(
                    Cbht.cbfbm == contractor.cbfbm,
                    Cbht.contract_source == CONTRACT_SOURCE_IMPORTED,
                ).execution_options(skip_tenant_scope=True),
            )
            original_code = original_code.cbhtbm if original_code else None
        original_row = db.get(Cbht, original_code) if original_code else None

        contract_code = (current_contract.cbhtbm if current_contract else None) or original_code or ""
        old_term_end = _fmt_date_cn(original_row.cbqxz) if original_row and original_row.cbqxz else ""

        # 申请日期 = 渲染当日（与 CS 版导出行为一致：样张「2026年11月8日」），中文不补零
        now = datetime.now()
        applicant_date = f"{now.year}年{now.month}月{now.day}日"

        # 期限口径：已签订 → 现行延包合同；未签订 → 默认自申请之日起 30 年
        #（止 = 起 + 30 年 − 1 天），不沿用上次承包合同的旧期限（前端会提示）。
        if current_contract is not None:
            contract_years = self._term_years(current_contract)
            contract_term_start = _fmt_date_cn(current_contract.cbqxq) if current_contract.cbqxq else ""
            contract_term_end = _fmt_date_cn(current_contract.cbqxz) if current_contract.cbqxz else ""
            no_contract = False
        else:
            try:
                end_dt = now.replace(year=now.year + 30)
            except ValueError:  # 2月29日申请、30 年后非闰年
                end_dt = now.replace(year=now.year + 30, day=28)
            term_end = end_dt - timedelta(days=1)
            contract_years = "30"
            contract_term_start = applicant_date
            contract_term_end = f"{term_end.year}年{term_end.month}月{term_end.day}日"
            no_contract = True

        # 发包方：合同 → 地块关联 → 发包方成果表
        issuer_fbfbm = (
            (current_contract.fbfbm if current_contract else None)
            or (original_row.fbfbm if original_row else None)
            or (first_relation.fbfbm if first_relation else None)
        )
        issuer = None
        if issuer_fbfbm:
            issuer = _one(
                db,
                select(SurveyFbfResult).where(SurveyFbfResult.fbfbm == issuer_fbfbm).execution_options(skip_tenant_scope=True),
            ) or _one(db, select(Fbf).where(Fbf.fbfbm == issuer_fbfbm))

        ctx = {
            "fbf_fzr": getattr(issuer, "fbffzrxm", "") or "",
            "fbf_lxdh": getattr(issuer, "lxdh", "") or "",
            "fbf_zjhm": getattr(issuer, "fzrzjhm", "") or "",
            "fbfmc": getattr(issuer, "fbfmc", "") or "",
            "cbfmc": contractor.cbfmc or "",
            "cbf_lxdh": contractor.lxdh or "",
            "cbf_zjhm": contractor.cbfzjhm or "",
            "contract_code": contract_code,
            "old_term_end": old_term_end,
            "family_count": str(contractor.cbfcysl or 0),
            "parcel_count": str(parcel_count) if parcel_count else "",
            "area_mu": area_mu,
            "contract_years": contract_years,
            "contract_term_start": contract_term_start,
            "contract_term_end": contract_term_end,
            "no_contract": no_contract,
            "applicant_date": applicant_date,
        }
        template = self._env.get_template("household_registration_application.html")
        return template.render(**ctx)

    def _resolve_region_chain(self, db: Session, batch) -> tuple[str, str, str, str]:
        """按编码段解析县/镇/村/组名称（region 表缺节点时逐级回落）。

        批次区域码可能是村（12 位）或组（14 位）级：县=前 6 位、镇=前 9 位、
        村=前 12 位、组=前 14 位。查不到的层级返回空串，模板自行留白。
        """
        from app.models.region import Region

        region_code = (getattr(batch, "region_code", None) or "").strip()

        def region_name(code: str) -> str:
            if not code:
                return ""
            row = db.scalars(
                select(Region).where(Region.code == code).execution_options(skip_tenant_scope=True)
            ).first()
            return row.name if row else ""

        if not region_code:
            # 没有编码就按 region_name 的「 / 」链兜底拆
            parts = [p.strip() for p in (batch.region_name or "").split("/") if p.strip()]
            return (
                parts[2] if len(parts) > 2 else "",
                parts[3] if len(parts) > 3 else "",
                parts[4] if len(parts) > 4 else "",
                parts[5] if len(parts) > 5 else "",
            )

        county_name = region_name(region_code[:6]) or region_name(region_code[:6].rstrip("0") or "")
        town_name = region_name(region_code[:9])
        village_name = region_name(region_code[:12])
        group_name = region_name(region_code[:14]) if len(region_code) >= 14 else ""
        return county_name, town_name, village_name, group_name

    def _batch_contract_term_range(
        self, db: Session, batch_id: int, tenant_code: str,
        *, source: str, fallback_source: str,
    ) -> tuple[str, str]:
        """批次内指定来源合同的期限起止范围（min 起 / max 止，中文日期）。"""
        rows = db.scalars(
            select(Cbht).where(
                Cbht.survey_batch_id == batch_id,
                Cbht.tenant_code == tenant_code,
                Cbht.contract_source == source,
            ).execution_options(skip_tenant_scope=True)
        ).all()
        if not rows:
            rows = db.scalars(
                select(Cbht).where(
                    Cbht.survey_batch_id == batch_id,
                    Cbht.tenant_code == tenant_code,
                    Cbht.contract_source == fallback_source,
                ).execution_options(skip_tenant_scope=True)
            ).all()
        starts = [r.cbqxq for r in rows if r.cbqxq]
        ends = [r.cbqxz for r in rows if r.cbqxz]
        return (
            _fmt_date_cn(min(starts)) if starts else "",
            _fmt_date_cn(max(ends)) if ends else "",
        )

    @staticmethod
    def _term_years(contract) -> str:
        """承包年限 = (止 − 起 + 1 天) 按 365.25 折算取整。

        兼容两种起止口径——「止 = 起 + N 年 − 1 天」（如 2026-09-30 ~ 2056-09-29
        → 30）与「整日历年」（如 2025-01-01 ~ 2054-12-31 → 30）：
        直接用 年份差+1 会把前者多算一年（31）。
        算不出（缺起止或倒挂）回退 30（二轮延包默认 30 年）。
        """
        if contract is None or not contract.cbqxq or not contract.cbqxz:
            return "30"
        start, end = contract.cbqxq, contract.cbqxz
        if end < start:
            return "30"
        total_days = (end - start).days + 1
        return str(max(1, round(total_days / 365.25)))

    # ── 地籍调查表（cadastral-survey） ────────────────────────────

    CADASTRAL_DICT_TYPES = (
        "nyt2539_c10_right_acquire_method",
        "nyt2539_c15_id_document_type",
        "nyt2539_c16_contractor_type",
        "nyt2539_c09_land_use",
        "nyt2539_c08_land_grade",
    )

    def render_cadastral_survey(
        self, db: Session, *, cbfbm: str, batch_id: int | None = None,
    ) -> str:
        """Render the 地籍调查表 packet (封面 + 发包方 + 承包方 + 每地块两表)."""
        return self._render_cadastral(db, cbfbms=[cbfbm], batch_id=batch_id)

    # ── 两张摸底表（2026-10-09 礼泉试点）：数据拼装在 survey/sheet.py ──────

    def render_land_change_sheet(self, db: Session, *, cbfbm: str) -> str:
        """《承包方承包地变化情况摸底表》HTML（自动带出 + 最新批次人工覆盖值）。"""
        from app.services.survey.sheet import survey_sheet_service

        ctx = survey_sheet_service.build_land_change_context(db, cbfbm=cbfbm)
        return self._env.get_template("land_change_sheet.html").render(**ctx)

    def render_member_change_sheet(self, db: Session, *, cbfbm: str) -> str:
        """《承包农户家庭成员变化情况摸底表》HTML。"""
        from app.services.survey.sheet import survey_sheet_service

        ctx = survey_sheet_service.build_member_change_context(db, cbfbm=cbfbm)
        return self._env.get_template("member_change_sheet.html").render(**ctx)

    def render_cadastral_survey_batch(
        self, db: Session, *, cbfbms: list[str], batch_id: int | None = None,
    ) -> str:
        """Render one print job containing several contractors' packets."""
        return self._render_cadastral(db, cbfbms=list(cbfbms), batch_id=batch_id)

    def build_cadastral_packet(
        self, db: Session, *, cbfbm: str, batch_id: int | None = None,
    ) -> dict:
        """一戶地籍调查表的数据包（Word 导出与 HTML 打印共用同一份口径）。"""
        options = self._cadastral_options(db)
        return self._build_cadastral_packet(
            db, cbfbm=cbfbm, batch_id=batch_id, options=options,
        )

    def build_cadastral_html(
        self, db: Session, *, cbfbm: str, batch_id: int | None = None,
    ) -> tuple[str, dict]:
        """一户：返回 ``(HTML, 数据包)``。

        Word 导出要同时拿到渲染结果和承包方名称（拼文件名），走这里可以只取一次数。
        """
        options = self._cadastral_options(db)
        packet = self._build_cadastral_packet(
            db, cbfbm=cbfbm, batch_id=batch_id, options=options,
        )
        return self._render_cadastral_html(db, [packet]), packet

    def _cadastral_options(self, db: Session) -> dict:
        return {key: _dictionary_map(db, key) for key in self.CADASTRAL_DICT_TYPES}

    def _render_cadastral(
        self, db: Session, *, cbfbms: list[str], batch_id: int | None,
    ) -> str:
        options = self._cadastral_options(db)
        packets = [
            self._build_cadastral_packet(db, cbfbm=code, batch_id=batch_id, options=options)
            for code in cbfbms
        ]
        return self._render_cadastral_html(db, packets)

    def _render_cadastral_html(
        self,
        db: Session,
        packets: list[dict],
        *,
        parcel_only: bool = False,
        issuer_only: bool = False,
        contractor_only: bool = False,
        include_point_sheets: bool = True,
    ) -> str:
        template = self._env.get_template("cadastral_survey.html")
        return template.render(
            packets=packets,
            # 「调查单位（机构）」不写死：取自字典项 survey_org，取不到才退回默认值。
            survey_org=dictionary_service.get_setting(
                db, SURVEY_ORG_DICT_TYPE, DEFAULT_SURVEY_ORG,
            ),
            member_min_rows=CADASTRAL_MEMBER_MIN_ROWS,
            points_per_page=CADASTRAL_POINTS_PER_PAGE,
            parcel_only=parcel_only,
            issuer_only=issuer_only,
            contractor_only=contractor_only,
            include_point_sheets=include_point_sheets,
        )

    def build_parcel_survey_html(
        self,
        db: Session,
        *,
        cbfbm: str,
        dkbms: list[str],
        batch_id: int | None = None,
    ) -> tuple[str, dict]:
        """只渲染指定地块的《承包地块调查表》（不含封面/发包方/承包方/坐标成果表）。"""
        options = self._cadastral_options(db)
        packet = self._build_cadastral_packet(
            db, cbfbm=cbfbm, batch_id=batch_id, options=options,
        )
        wanted = {str(code) for code in dkbms if code}
        packet["parcels"] = [
            parcel for parcel in packet.get("parcels", [])
            if parcel.get("dkbm") in wanted
        ]
        # 调查表最多展示 CADASTRAL_PARCEL_POINT_ROWS 个界址点；超出时表内会提示
        # “其余 N 个界址点见《界址点坐标成果表》”，因此必须把成果表一并输出。
        include_point_sheets = any(
            len(parcel.get("points") or []) > CADASTRAL_PARCEL_POINT_ROWS
            for parcel in packet["parcels"]
        )
        return (
            self._render_cadastral_html(
                db,
                [packet],
                parcel_only=True,
                include_point_sheets=include_point_sheets,
            ),
            packet,
        )

    def build_issuer_survey_html(
        self,
        db: Session,
        *,
        fbfbm: str,
        batch_id: int | None = None,
    ) -> tuple[str, dict]:
        """只渲染一个发包方的《发包方调查表》（Word 导出用）。"""
        source = _one(
            db,
            select(SurveyFbfResult)
            .where(SurveyFbfResult.fbfbm == fbfbm)
            .order_by(SurveyFbfResult.id.desc()),
        ) or _one(db, select(Fbf).where(Fbf.fbfbm == fbfbm))
        if source is None:
            raise ValueError(f"发包方不存在：{fbfbm}")

        options = self._cadastral_options(db)
        id_type_options = options["nyt2539_c15_id_document_type"]
        id_type_code = getattr(source, "fzrzjlx", "") or ""
        survey_date = getattr(source, "fbfdcrq", None)
        issuer = {
            "name": getattr(source, "fbfmc", "") or "",
            "code": getattr(source, "fbfbm", "") or fbfbm,
            "head": getattr(source, "fbffzrxm", "") or "",
            "head_id_type": id_type_options.get(id_type_code, id_type_code),
            "head_id_no": getattr(source, "fzrzjhm", "") or "",
            "head_phone": getattr(source, "lxdh", "") or "",
            "address": getattr(source, "fbfdz", "") or "",
            "postcode": getattr(source, "yzbm", "") or "",
            "survey_note": _cadastral_survey_note(
                getattr(source, "fbfdcjs", None),
                getattr(source, "fbfdcy", None),
                survey_date,
                include_change=False,
            ),
            "audit_note": "合格。",
            "auditor": getattr(source, "fbfdcy", "") or "",
            "audit_date_text": _fmt_date_cn(survey_date),
        }
        packet = {"issuer": issuer, "contractor": {}, "parcels": []}
        return (
            self._render_cadastral_html(db, [packet], issuer_only=True),
            issuer,
        )

    def build_contractor_survey_html(
        self,
        db: Session,
        *,
        cbfbm: str,
        batch_id: int | None = None,
    ) -> tuple[str, dict]:
        """只渲染一个承包方的《承包方调查表》（Word 导出用）。"""
        options = self._cadastral_options(db)
        packet = self._build_cadastral_packet(
            db, cbfbm=cbfbm, batch_id=batch_id, options=options,
        )
        return (
            self._render_cadastral_html(db, [packet], contractor_only=True),
            packet.get("contractor") or {},
        )

    def _build_cadastral_packet(
        self, db: Session, *, cbfbm: str, batch_id: int | None, options: dict,
    ) -> dict:
        contractor = _one(
            db,
            select(SurveyCbfResult)
            .where(SurveyCbfResult.cbfbm == cbfbm)
            .order_by(SurveyCbfResult.id.desc()),
        )

        members = []
        if contractor is not None:
            members = db.scalars(
                select(SurveyCbfJtcyResult)
                .where(SurveyCbfJtcyResult.cbfbm == cbfbm)
                .order_by(SurveyCbfJtcyResult.id.asc())
            ).all()

        relations = db.scalars(
            select(SurveyCbdkxxResult)
            .where(
                SurveyCbdkxxResult.cbfbm == cbfbm,
                SurveyCbdkxxResult.result_status != "removed",
            )
            .order_by(SurveyCbdkxxResult.dkbm.asc())
        ).all()
        first_relation = relations[0] if relations else None

        cbhtbm = first_relation.cbhtbm if first_relation else None
        contract = (
            _one(db, select(Cbht).where(Cbht.cbhtbm == cbhtbm)) if cbhtbm else None
        )

        issuer_fbfbm = (
            (contract.fbfbm if contract else None)
            or (first_relation.fbfbm if first_relation else None)
        )
        issuer = None
        if issuer_fbfbm:
            issuer = _one(
                db,
                select(SurveyFbfResult).where(SurveyFbfResult.fbfbm == issuer_fbfbm),
            ) or _one(db, select(Fbf).where(Fbf.fbfbm == issuer_fbfbm))

        id_type_options = options["nyt2539_c15_id_document_type"]
        member_options = _dictionary_map(db, "nyt2539_c20_relation_to_head")
        remark_options = _dictionary_map(db, "nyt2539_c18_member_remark")

        family_members = [
            {
                "name": m.cyxm or "",
                "relation": member_options.get(m.yhzgx or "", m.yhzgx or ""),
                "id_no": m.cyzjhm or "",
                "remark": remark_options.get(m.cybz or "", m.cybzsm or ""),
            }
            for m in members
        ]

        parcels = self._load_cadastral_parcels(db, relations=relations)
        points_by_dkbm = self._load_boundary_points(
            db,
            [p["dkbm"] for p in parcels],
            tenant_code=getattr(contractor, "tenant_code", None),
        )
        for parcel in parcels:
            points = points_by_dkbm.get(parcel["dkbm"], [])
            parcel["points"] = points
            parcel["point_pages"] = [
                points[index : index + CADASTRAL_POINTS_PER_PAGE]
                for index in range(0, len(points), CADASTRAL_POINTS_PER_PAGE)
            ] or [[]]
            shown = points[:CADASTRAL_PARCEL_POINT_ROWS]
            parcel["table_points"] = shown
            parcel["table_point_rows"] = max(8, len(shown))
            parcel["hidden_point_count"] = max(0, len(points) - len(shown))
            parcel["has_points"] = bool(points)
            parcel["blank_flags"] = blank_boundary_flags()

        acquire_options = options["nyt2539_c10_right_acquire_method"]
        acquire_code = (first_relation.cbjyqqdfs if first_relation else "") or (
            (contract.cbfs if contract else "") or ""
        )
        cbjyqzbm = first_relation.cbjyqzbm if first_relation else None
        sheet_ysdm = None

        member_count = (
            contractor.cbfcysl
            if contractor is not None and contractor.cbfcysl
            else len(family_members)
        )

        return {
            "issuer": {
                "name": getattr(issuer, "fbfmc", "") or "",
                "code": getattr(issuer, "fbfbm", "") or "",
                "head": getattr(issuer, "fbffzrxm", "") or "",
                "head_id_type": id_type_options.get(
                    getattr(issuer, "fzrzjlx", "") or "",
                    getattr(issuer, "fzrzjlx", "") or "",
                ),
                "head_id_no": getattr(issuer, "fzrzjhm", "") or "",
                "head_phone": getattr(issuer, "lxdh", "") or "",
                "address": getattr(issuer, "fbfdz", "") or "",
                "postcode": getattr(issuer, "yzbm", "") or "",
                "survey_note": _cadastral_survey_note(
                    getattr(issuer, "fbfdcjs", None),
                    getattr(issuer, "fbfdcy", None),
                    getattr(issuer, "fbfdcrq", None),
                    include_change=False,
                ),
                "audit_note": "合格。",
                "auditor": getattr(issuer, "fbfdcy", "") or "",
                "audit_date_text": _fmt_date_cn(getattr(issuer, "fbfdcrq", None)),
            },
            "contractor": {
                "name": contractor.cbfmc if contractor else "",
                "code": cbfbm,
                "short_code": (cbfbm or "")[-4:],
                "type_text": options["nyt2539_c16_contractor_type"].get(
                    contractor.cbflx if contractor else "", ""
                ),
                "id_type": id_type_options.get(
                    contractor.cbfzjlx if contractor else "", ""
                ),
                "id_no": contractor.cbfzjhm if contractor else "",
                "phone": contractor.lxdh if contractor else "",
                "address": contractor.cbfdz if contractor else "",
                "postcode": contractor.yzbm if contractor else "",
                "has_contract": bool(cbhtbm),
                "contract_code": cbhtbm or "",
                "has_cert": bool(cbjyqzbm),
                "cert_code": cbjyqzbm or "",
                "acquire_method": acquire_options.get(acquire_code, acquire_code),
                "acquire_code": acquire_code,
                "term_begin": _fmt_date(contract.cbqxq if contract else None),
                "term_end": _fmt_date(contract.cbqxz if contract else None),
                # 中文日期，供 Word 导出按「　年　月　日」排版使用
                "term_begin_cn": _fmt_date_cn(contract.cbqxq if contract else None),
                "term_end_cn": _fmt_date_cn(contract.cbqxz if contract else None),
                "term_years": (
                    _contract_years(contract.cbqxq, contract.cbqxz) if contract else ""
                ),
                "member_count": member_count,
                "members": family_members,
                "sheet_ysdm": sheet_ysdm or "",
                "survey_note": _cadastral_survey_note(
                    contractor.change_reason if contractor else None,
                    contractor.cbfdcy if contractor else None,
                    contractor.cbfdcrq if contractor else None,
                    include_change=True,
                ),
                "audit_note": "合格。",
                "auditor": (contractor.gsshr if contractor else "") or "",
                "audit_date_text": _fmt_date_cn(contractor.gsshrq if contractor else None),
            },
            "parcels": parcels,
            "survey_date_text": _fmt_date_cn(
                contractor.cbfdcrq if contractor else None
            ),
        }

    def _load_cadastral_parcels(self, db: Session, *, relations: list) -> list[dict]:
        """Load parcel rows for one contractor, keeping the relation order."""
        dkbms = [row.dkbm for row in relations if row.dkbm]
        if not dkbms:
            return []
        dk_rows = db.scalars(
            select(SurveyDkResult)
            .where(
                SurveyDkResult.dkbm.in_(dkbms),
                SurveyDkResult.result_status != "removed",
            )
            .order_by(SurveyDkResult.dkbm.asc(), SurveyDkResult.id.desc())
        ).all()
        dk_map: dict[str, SurveyDkResult] = {}
        for row in dk_rows:
            dk_map.setdefault(row.dkbm, row)

        use_options = _dictionary_map(db, "nyt2539_c09_land_use")
        grade_options = _dictionary_map(db, "nyt2539_c08_land_grade")
        category_options = _dictionary_map(db, "nyt2539_c07_parcel_category")

        parcels: list[dict] = []
        for relation in relations:
            dk = dk_map.get(relation.dkbm)
            scmj = float(dk.scmj) if dk is not None and dk.scmj is not None else 0.0
            if relation.htmjm is not None:
                htmjm = float(relation.htmjm)
            elif relation.htmj is not None:
                htmjm = float(relation.htmj) / 666.67
            else:
                htmjm = 0.0
            tdyt = (dk.tdyt if dk else "") or ""
            tdlylx = (dk.tdlylx if dk else "") or ""
            dldj = (dk.dldj if dk else "") or ""
            parcels.append({
                "dkbm": relation.dkbm or "",
                "dkmc": dk.dkmc if dk else "",
                "sheet_no": (dk.image_number if dk else "") or "",
                "dklb_text": category_options.get(dk.dklb if dk else "", ""),
                "fbfbm": relation.fbfbm or "",
                "htmjm": f"{htmjm:.2f}" if htmjm else "",
                "scmj": f"{scmj:.2f}" if scmj else "",
                "area_mu": f"{scmj / 666.67:.4f}" if scmj else "",
                "east": (dk.dkdz if dk else "") or "",
                "south": (dk.dknz if dk else "") or "",
                "west": (dk.dkxz if dk else "") or "",
                "north": (dk.dkbz if dk else "") or "",
                "boundary_note": (dk.dkbzxx if dk else "") or "",
                "use_text": use_options.get(tdyt, tdyt),
                "use_flags": [
                    {"label": label, "checked": tdyt in codes}
                    for label, codes in CADASTRAL_LAND_USE_OPTIONS
                ],
                "grade_text": grade_options.get(dldj, dldj),
                "landuse_text": TDLYLX_FULL_MAP.get(tdlylx, tdlylx),
                "landuse_flags": [
                    {"label": label, "checked": tdlylx in codes}
                    for label, codes in CADASTRAL_LANDUSE_OPTIONS
                ],
                "basic_farmland": (dk.sfjbnt if dk else "") == "1",
                "survey_note": (dk.survey_note if dk else "") or "",
                "audit_note": (dk.check_opinion if dk else "") or "",
                "auditor": (dk.check_person if dk else "") or "",
                "audit_date_text": (
                    dk.check_date.strftime("%Y年%m月%d日")
                    if dk is not None and dk.check_date
                    else ""
                ),
            })
        return parcels

    def _load_boundary_points(
        self, db: Session, dkbms: list[str], *, tenant_code: str | None = None,
    ) -> dict[str, list[dict]]:
        """Dump parcel boundary points (界址点) with their maintained attributes.

        ``survey_dk_result.geom`` is stored in the deployment target SRID (CGCS2000 3-degree, see app/core/crs.py;
        Gauss-Kruger, metres), so values are printed as-is: X = 北坐标 (northing),
        Y = 东坐标 (easting, carries the 39 zone prefix).

        界标类型 / 界址线类别 / 界址线位置 来自界址点、界址线成果表（在
        ``/surveys`` 的"界址点/界址线维护"里录入）。打印时把"从第 i 个界址点
        出发的那条界址线"的属性填在第 i 行，与调查表逐行对应。
        """
        codes = [code for code in dict.fromkeys(dkbms) if code]
        if not codes:
            return {}

        boundary_map = build_boundary_map(db, codes, tenant_code=tenant_code)

        result: dict[str, list[dict]] = {}
        for dkbm, boundary in boundary_map.items():
            line_by_seq = {line["seq"]: line for line in boundary["lines"]}
            points: list[dict] = []
            for point in boundary["points"]:
                line = line_by_seq.get(point["seq"]) or {}
                points.append({
                    "seq": point["seq"],
                    "code": point["code"],
                    "x": point["x"],
                    "y": point["y"],
                    "edge": point.get("edge") or "",
                    "remark": point.get("bz") or "",
                    "jzdh": point.get("jzdh") or "",
                    # 库里存的是国标字典码值（C.12 / C.13 / C.14），
                    # 打印时按甲方 docx 的固定勾选格做映射（见 CADASTRAL_*_COLUMNS）。
                    # 界标类型三格**三选一**（木桩 / 埋石 / 无），走 fallback 兜底；
                    # 界址线类别、位置两组维持"能勾就勾、勾不到留空"。
                    "mark_flags": boundary_column_flags(
                        CADASTRAL_MARK_TYPE_COLUMNS,
                        point.get("jblx"),
                        fallback=CADASTRAL_MARK_TYPE_FALLBACK,
                    ),
                    "line_flags": boundary_column_flags(
                        CADASTRAL_LINE_CATEGORY_COLUMNS, line.get("jzxlb")
                    ),
                    "pos_flags": boundary_column_flags(
                        CADASTRAL_LINE_POSITION_COLUMNS, line.get("jzxwz")
                    ),
                    "line_note": line.get("jzxsm") or "",
                })
            result[dkbm] = points
        return result


    # ── helpers ─────────────────────────────────────────

    def _load_parcels(
        self, db: Session, cbhtbm: str, batch_id: int | None,
        contractor_code: str | None = None,
    ) -> list[dict]:
        """Load parcel list for one contract from survey result tables.

        ``contractor_code`` 传入时改为按承包方取地块（用于平台生成的延包合同，
        其合同编码尚未写回地块关联表）。
        """
        j = SurveyCbdkxxResult
        d = SurveyDkResult
        filters = [j.result_status != "removed"]
        filters.append(j.cbfbm == contractor_code if contractor_code else j.cbhtbm == cbhtbm)
        q = (
            select(j, d)
            .join(d, and_(j.dkbm == d.dkbm))
            .where(*filters)
        )
        rows = db.execute(q).all()

        result: list[dict] = []
        for cbdkxx, dk in rows:
            scmj = float(dk.scmj) if dk and dk.scmj else 0.0
            result.append({
                "dkbm": dk.dkbm or "",
                "dkbm_prefix": (dk.dkbm or "")[:14],
                "dkbm_suffix": (dk.dkbm or "")[14:],
                "dkmc": dk.dkmc or "",
                "dklb_text": DK_LB_MAP.get(dk.dklb or "", dk.dklb or ""),
                "scmj": f"{scmj:.2f}",
                "scmj_mu": f"{scmj / 666.67:.4f}",
                "dkdz": dk.dkdz or "",
                "dkxz": dk.dkxz or "",
                "dknz": dk.dknz or "",
                "dkbz": dk.dkbz or "",
                "sfjbnt_text": SFJBNT_MAP.get(
                    dk.sfjbnt or "", dk.sfjbnt or ""
                ),
                "dldj_text": DLDJ_MAP.get(dk.dldj or "", dk.dldj or ""),
                "tdlylx_text": TDLYLX_MAP.get(
                    dk.tdlylx or "", dk.tdlylx or ""
                ),
                "htmj": _fmt_decimal(cbdkxx.htmj) if cbdkxx else "",
            })
        return result


# ── module-level utilities ─────────────────────────────

def _one(db: Session, stmt):
    return db.scalar(stmt)


def _fmt_date(val) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y年%m月%d日")
    return str(val)


def _fmt_date_cn(val) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y年%m月%d日")
    return str(val)


def _fmt_date_iso(val) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    return str(val)


def _contract_years(start, end) -> str:
    if isinstance(start, datetime) and isinstance(end, datetime):
        years = end.year - start.year
        if (end.month, end.day) >= (start.month, start.day):
            years += 1
        return str(years)
    return "30"


def _fmt_decimal(val) -> str:
    if val is None:
        return ""
    return f"{float(val):.2f}"


def _loads_geojson(value):
    """把仓储层返回的 GeoJSON 字符串转成 dict；坏数据一律降级成 None（画不出图不报错）。"""
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _load_geometry_map(db: Session, dkbms: list[str]) -> dict:
    """``{dkbm: GeoJSON}``，用于承包地块示意图的逐地块小图。"""
    codes = [code for code in dict.fromkeys(dkbms) if code]
    if not codes:
        return {}
    return {
        row.get("dkbm"): _loads_geojson(row.get("geometry"))
        for row in land_parcel_repository.get_dk_by_codes(db, codes)
        if row.get("dkbm")
    }


def _dictionary_map(db: Session, dict_type: str) -> dict[str, str]:
    """Return ``{item_value: item_name}`` for one enabled dictionary type."""
    rows = db.execute(
        select(DictionaryItem.item_value, DictionaryItem.item_name)
        .where(DictionaryItem.dict_type == dict_type, DictionaryItem.enabled.is_(True))
        .order_by(DictionaryItem.sort_order.asc(), DictionaryItem.item_value.asc())
    ).all()
    return {value: name for value, name in rows if value}


def _cadastral_survey_note(
    detail: str | None, surveyor: str | None, survey_date, *, include_change: bool,
) -> str:
    """Build the 调查记事 cell text for 承包方/发包方/地块调查表."""
    lines: list[str] = []
    if include_change:
        lines.append(f"承包方代表变更情况：{detail or '无变更'}")
        lines.append("土地承包经营权权属特殊情况：无。")
        lines.append("农户内成员分家析产、合户或家庭成员其他情况：无。")
        lines.append("其他需要说明的情况：无。")
    elif detail:
        lines.append(str(detail))
    lines.append(f"调查员：{surveyor or ''}（签字并摁手印）")
    lines.append(f"日期：{_fmt_date_cn(survey_date) or '    年    月    日'}")
    return "\n".join(lines)


contract_template_service = ContractTemplateService()
