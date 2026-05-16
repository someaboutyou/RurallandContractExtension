"""
Contract template rendering service.

Renders the 农村土地承包合同 HTML template with live contract data,
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
)

# ── 枚举值映射 ──────────────────────────────────────────

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
YHZGX_MAP = {
    "01": "本人", "02": "配偶", "03": "子女", "04": "父母",
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
            )
            if batch_id is not None:
                cbf_query = cbf_query.where(
                    SurveyCbfResult.batch_id == batch_id
                )
            contractor = _one(db, cbf_query)

        # ── 发包方（从合同或承包方获取 fbfbm） ──
        issuer_fbfbm = contract.fbfbm
        if not issuer_fbfbm and contractor:
            issuer_fbfbm = getattr(contractor, "fbfbm", None)
        issuer = None
        if issuer_fbfbm:
            issuer = _one(db, select(Fbf).where(Fbf.fbfbm == issuer_fbfbm))

        # ── 家庭成员 ──
        members = []
        if contractor:
            mq = select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.cbfbm == contract.cbfbm
            )
            if batch_id is not None:
                mq = mq.where(SurveyCbfJtcyResult.batch_id == batch_id)
            members = db.scalars(mq).all()

        household_head = [
            {"cyxm": m.cyxm, "cyzjhm": m.cyzjhm}
            for m in members if m.yhzgx == "01"
        ]

        # ── 地块 ──
        parcels = self._load_parcels(db, contract.cbhtbm, batch_id)

        # ── 模板上下文 ──
        ctx = {
            # 合同
            "cbhtbm": contract.cbhtbm or "",
            "qdsj": _fmt_date(contract.qdsj),
            "cbqxq": _fmt_date(contract.cbqxq),
            "cbqxz": _fmt_date(contract.cbqxz),
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
            "fbf_dz": issuer.fbfdz if issuer else "",

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
        }
        template = self._env.get_template("contract.html")
        return template.render(**ctx)

    # ── helpers ─────────────────────────────────────────

    def _load_parcels(
        self, db: Session, cbhtbm: str, batch_id: int | None,
    ) -> list[dict]:
        """Load parcel list for one contract from survey result tables."""
        j = SurveyCbdkxxResult
        d = SurveyDkResult
        q = (
            select(j, d)
            .join(d, and_(j.dkbm == d.dkbm))
            .where(j.cbhtbm == cbhtbm)
        )
        if batch_id is not None:
            q = q.where(j.batch_id == batch_id).where(d.batch_id == batch_id)
        rows = db.execute(q).all()

        result: list[dict] = []
        for cbdkxx, dk in rows:
            scmj = float(dk.scmj) if dk and dk.scmj else 0.0
            result.append({
                "dkbm": dk.dkbm or "",
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


def _fmt_decimal(val) -> str:
    if val is None:
        return ""
    return f"{float(val):.2f}"


contract_template_service = ContractTemplateService()
