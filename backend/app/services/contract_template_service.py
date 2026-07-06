"""
Contract template rendering service.

Renders the 鍐滄潙鍦熷湴鎵垮寘鍚堝悓 HTML template with live contract data,
supporting both screen preview and print-ready output.
"""

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.cbht import Cbht
from app.models.fbf import Fbf
from app.models.survey import (
    SurveyCbdkxxResult,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyDkResult,
    SurveyFbfResult,
)

# 鈹€鈹€ 鏋氫妇鍊兼槧灏?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

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
YHZGX_MAP = {
    "01": "户主", "02": "配偶", "03": "子女", "04": "父母",
    "05": "兄弟姐妹", "06": "祖父母", "07": "孙子女",
    "08": "儿媳/女婿", "09": "公婆/岳父母", "99": "其他",
}


class ContractTemplateService:
    """Render the contract HTML template with live data."""

    def __init__(self):
        template_dir = Path(__file__).resolve().parent.parent / "templates"
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=False,
        )

    # 鈹€鈹€ public 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

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

        # 鈹€鈹€ 鎵垮寘鏂?鈹€鈹€
        contractor = None
        if contract.cbfbm:
            cbf_query = select(SurveyCbfResult).where(
                SurveyCbfResult.cbfbm == contract.cbfbm
            ).order_by(SurveyCbfResult.id.desc())
            contractor = _one(db, cbf_query)

        # 鈹€鈹€ 鍙戝寘鏂癸紙浠庡悎鍚屾垨鎵垮寘鏂硅幏鍙?fbfbm锛?鈹€鈹€
        issuer_fbfbm = contract.fbfbm
        if not issuer_fbfbm and contractor:
            issuer_fbfbm = getattr(contractor, "fbfbm", None)
        issuer = None
        if issuer_fbfbm:
            issuer = _one(db, select(Fbf).where(Fbf.fbfbm == issuer_fbfbm))

        # 鈹€鈹€ 瀹跺涵鎴愬憳 鈹€鈹€
        members = []
        if contractor:
            mq = select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.cbfbm == contract.cbfbm
            )
            members = db.scalars(mq).all()

        household_head = [
            {"cyxm": m.cyxm, "cyzjhm": m.cyzjhm}
            for m in members if m.yhzgx == "01"
        ]
        family_members = [
            {
                "cyxm": m.cyxm or "",
                "relation_text": YHZGX_MAP.get(m.yhzgx or "", m.yhzgx or ""),
                "cyzjhm": m.cyzjhm or "",
                "remark": getattr(m, "remark", "") or "",
            }
            for m in members
        ]

        # 鈹€鈹€ 鍦板潡 鈹€鈹€
        parcels = self._load_parcels(db, contract.cbhtbm, batch_id)

        # 鈹€鈹€ 妯℃澘涓婁笅鏂?鈹€鈹€
        ctx = {
            # 鍚堝悓
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

            # 鍙戝寘鏂?
            "fbfbm": issuer.fbfbm if issuer else "",
            "fbfmc": issuer.fbfmc if issuer else "",
            "fbf_fzr": issuer.fbffzrxm if issuer else "",
            "fbf_fzr_zjhm": issuer.fzrzjhm if issuer else "",
            "fbf_dz": issuer.fbfdz if issuer else "",
            "fbf_lxdh": issuer.lxdh if issuer else "",
            "fbf_social_credit_code": getattr(issuer, "tyshxydm", "") if issuer else "",

            # 鎵垮寘鏂?
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

            # 鍦板潡
            "parcels": parcels,

            # 鎴蜂富
            "household_head": household_head,
            "family_members": family_members,
        }
        template = self._env.get_template("contract.html")
        return template.render(**ctx)

    def render_survey_contract(
        self, db: Session, *, cbhtbm: str, batch_id: int, cbfbm: str,
    ) -> str:
        """Render a contract preview from survey result data.

        This path is used by the survey screen where parcel results may already
        carry a contract code, even when the source ``cbht`` row was not imported.
        """
        contract = _one(db, select(Cbht).where(Cbht.cbhtbm == cbhtbm))

        contractor = _one(
            db,
            select(SurveyCbfResult).where(
                SurveyCbfResult.cbfbm == cbfbm,
            ).order_by(SurveyCbfResult.id.desc()),
        )

        relations = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.cbfbm == cbfbm,
                SurveyCbdkxxResult.cbhtbm == cbhtbm,
                SurveyCbdkxxResult.result_status != "removed",
            )
        ).all()
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

        household_head = [
            {"cyxm": m.cyxm, "cyzjhm": m.cyzjhm}
            for m in members if m.yhzgx == "01"
        ]
        family_members = [
            {
                "cyxm": m.cyxm or "",
                "relation_text": YHZGX_MAP.get(m.yhzgx or "", m.yhzgx or ""),
                "cyzjhm": m.cyzjhm or "",
                "remark": getattr(m, "remark", "") or "",
            }
            for m in members
        ]
        parcels = self._load_parcels(db, cbhtbm, batch_id)
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
        }
        template = self._env.get_template("contract.html")
        return template.render(**ctx)

    def render_plot_sketch_map(self, **ctx) -> str:
        """Render the contracted parcel sketch map HTML."""
        template = self._env.get_template("poltsketchmap.html")
        return template.render(**ctx)


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

        family_members = []
        for m in members:
            family_members.append({
                "name": m.cyxm or "",
                "id_type": ZJLX_MAP.get(m.cyzjlx or "", m.cyzjlx or ""),
                "id_number": m.cyzjhm or "",
                "relation": YHZGX_MAP.get(m.yhzgx or "", m.yhzgx or ""),
                "phone": "",
            })

        # Parcels
        parcels_raw = self._load_parcels(db, cbhtbm or "", batch_id) if cbhtbm else []
        total_area_mu = sum(float(p.get("scmj_mu", 0) or 0) for p in parcels_raw)

        parcels = []
        for p in parcels_raw:
            boundaries = "涓?" + (p.get("dkdz", "") or "") + " 瑗?" + (p.get("dkxz", "") or "") + " 鍗?" + (p.get("dknz", "") or "") + " 鍖?" + (p.get("dkbz", "") or "")
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

    # 鈹€鈹€ helpers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _load_parcels(
        self, db: Session, cbhtbm: str, batch_id: int | None,
    ) -> list[dict]:
        """Load parcel list for one contract from survey result tables."""
        j = SurveyCbdkxxResult
        d = SurveyDkResult
        q = (
            select(j, d)
            .join(d, and_(j.dkbm == d.dkbm))
            .where(
                j.cbhtbm == cbhtbm,
                j.result_status != "removed",
            )
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


# 鈹€鈹€ module-level utilities 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

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


contract_template_service = ContractTemplateService()
