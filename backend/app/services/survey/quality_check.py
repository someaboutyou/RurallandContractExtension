# -*- coding: utf-8 -*-
"""批次数据质检（后台任务版）。

参照原延包桌面工具「检查农村土地调查数据库数据」（YuLinTu.Component.DataCheckerTask）
的质检项目迁移而来，规则口径与原工具一致，检查对象改为本系统的批次调查成果表
（survey_cbf_result / survey_cbf_jtcy_result / survey_dk_result / survey_cbdkxx_result /
survey_fbf_result / cbht）。

质检项（与原工具 DataCheckerSetDefine 的五个勾选项一一对应）：
- ``card_no``   证件号码重复（全体家庭成员 + 户主证件号全批次查重）
- ``fbf``       发包方信息（负责人姓名/证件号/电话/地址/邮编/调查员/调查日期）
- ``cbf``       承包方信息（编码与类型匹配、证件号、地址、邮编、电话、调查员、
                公示记事人/审核人/日期；成员性别、证件号、身份证校验、与户主关系）
- ``land``      承包地块（名称、19 位地块编码、土地利用类型、地力等级、是否基本农田、
                实测面积、四至、指界人、空间图形有无）
- ``contract``  合同与权证（户名下必须有承包地块、地块必须能挂到合同台账）

实现方式与 ``xls_jobs.py`` 相同：单进程内存注册表 + daemon 线程 + 独立 DB 会话，
前端每秒轮询进度；逐条问题写入 ``survey_quality_check_records``（每次运行一条
``summary`` 汇总行 + N 条问题行），历史记录与明细都从该表查。
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import traceback
import uuid
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── 质检项定义 ────────────────────────────────────────────────

CHECK_ITEMS: list[dict] = [
    {"key": "card_no", "label": "证件号码重复", "description": "全批次家庭成员证件号码查重"},
    {"key": "fbf", "label": "发包方信息", "description": "发包方负责人、调查员、调查日期等完整性"},
    {"key": "cbf", "label": "承包方信息", "description": "承包方编码、证件、联系方式、家庭成员关系"},
    {"key": "land", "label": "承包地块信息", "description": "地块编码、面积、四至、指界人、空间图形"},
    {"key": "contract", "label": "合同与权证", "description": "承包地块与承包合同台账的勾稽关系"},
]

CHECK_ITEM_LABELS = {item["key"]: item["label"] for item in CHECK_ITEMS}
DEFAULT_ENABLED_ITEMS = {item["key"]: True for item in CHECK_ITEMS}

# ── 身份证校验（与前端 validators.js 的 diagnoseId18 同口径）──

_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK_CODES = "10X98765432"
_PHONE_RE = re.compile(r"^\+?\d[\d-]*\d$|^\+?\d$")


def check_id_number(value: str | None) -> bool:
    """18 位身份证算法校验（校验位）；15 位老号只要求纯数字。"""
    value = str(value or "").strip().upper()
    if not value:
        return False
    if len(value) == 15:
        return value.isdigit()
    if len(value) != 18:
        return False
    if not value[:17].isdigit():
        return False
    total = sum(_ID_WEIGHTS[i] * int(value[i]) for i in range(17))
    return _ID_CHECK_CODES[total % 11] == value[17]


def _is_blank(value: str | None) -> bool:
    return str(value or "").strip() == ""


def _is_phone_ok(value: str | None) -> bool:
    """联系电话：允许数字与 + -，与原工具 ToolMath.MatchAllNumber 口径一致。"""
    value = str(value or "").strip()
    if value == "":
        return True
    return bool(_PHONE_RE.match(value)) and bool(re.fullmatch(r"[+\-]?\d[\d\-]*", value.replace(" ", "")))


def _postal_problem(value: str | None) -> str:
    """返回邮编问题文案；None 表示通过。"""
    value = str(value or "").strip()
    if value == "":
        return "邮政编码未填写"
    if len(value) != 6 or not value.isdigit():
        return f"邮政编码{value}不符合 6 位数字要求"
    return None


# ── 后台任务注册表（同 xls_jobs：单进程内存 + daemon 线程）────

_MAX_JOBS = 40
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _cleanup_locked() -> None:
    if len(_JOBS) <= _MAX_JOBS:
        return
    ordered = sorted(_JOBS.items(), key=lambda kv: kv[1]["createdAt"])
    for key, _ in ordered[:-_MAX_JOBS]:
        _JOBS.pop(key, None)


def _create_job(batch_id: int, user_id: int, items: dict[str, bool]) -> dict:
    run_id = uuid.uuid4().hex
    job = {
        "id": uuid.uuid4().hex,
        "runId": run_id,
        "batchId": batch_id,
        "userId": user_id,
        "items": {k: bool(items.get(k, DEFAULT_ENABLED_ITEMS.get(k, True))) for k in DEFAULT_ENABLED_ITEMS},
        "status": "running",  # running / done / error
        "phase": "准备中",
        "done": 0,
        "total": 0,
        "current": "",
        "counts": {"error": 0, "warn": 0, "info": 0},
        "error": "",
        "createdAt": time.time(),
    }
    with _LOCK:
        _JOBS[job["id"]] = job
        _cleanup_locked()
    return job


def get_job(job_id: str) -> dict | None:
    with _LOCK:
        return _JOBS.get(job_id)


def _update_job(job_id: str, **fields) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job.update(fields)


def job_public_view(job: dict | None) -> dict | None:
    if job is None:
        return None
    return {
        "jobId": job["id"],
        "runId": job["runId"],
        "batchId": job["batchId"],
        "items": job["items"],
        "status": job["status"],
        "phase": job["phase"],
        "done": job["done"],
        "total": job["total"],
        "current": job["current"],
        "counts": job["counts"],
        "error": job["error"],
    }


class _RecordWriter:
    """问题日志写入器：批量缓冲落库 + 计数。"""

    FLUSH_SIZE = 500

    def __init__(self, db: Session, run_id: str, batch, user_id: int | None) -> None:
        from app.models.survey import SurveyQualityCheckRecord

        self._model = SurveyQualityCheckRecord
        self._db = db
        self._buffer: list = []
        self.run_id = run_id
        self.batch = batch
        self.user_id = user_id
        self.counts = {"error": 0, "warn": 0, "info": 0}
        self.per_item: dict[str, dict[str, int]] = {}

    def add(self, check_item: str, severity: str, message: str, *,
            cbfbm: str | None = None, cbfmc: str | None = None, dkbm: str | None = None) -> None:
        self.counts[severity] = self.counts.get(severity, 0) + 1
        item_counts = self.per_item.setdefault(check_item, {"error": 0, "warn": 0, "info": 0})
        item_counts[severity] = item_counts.get(severity, 0) + 1
        self._buffer.append(self._model(
            run_id=self.run_id,
            batch_id=self.batch.id,
            batch_no=self.batch.batch_no,
            tenant_code=self.batch.tenant_code,
            region_code=self.batch.region_code,
            check_item=check_item,
            severity=severity,
            cbfbm=cbfbm or None,
            cbfmc=cbfmc or None,
            dkbm=dkbm or None,
            message=message,
            created_by=self.user_id,
        ))
        if len(self._buffer) >= self.FLUSH_SIZE:
            self.flush()

    def flush(self) -> None:
        if self._buffer:
            self._db.add_all(self._buffer)
            self._db.commit()
            self._buffer.clear()


# ── 数据装载 ─────────────────────────────────────────────────

def _load_run_context(db: Session, batch) -> dict:
    """装载批次全部调查成果；一律显式按 tenant_code 过滤，跳过 ORM 全局租户 scope。"""
    from app.models.cbht import Cbht
    from app.models.dictionary import DictionaryItem
    from app.models.survey import (
        SurveyCbfBase,
        SurveyCbfJtcyResult,
        SurveyCbfResult,
        SurveyCbdkxxBase,
        SurveyCbdkxxResult,
        SurveyDkBase,
        SurveyDkResult,
        SurveyFbfBase,
        SurveyFbfResult,
    )

    tenant = batch.tenant_code
    opts = {"skip_tenant_scope": True}

    bases = db.scalars(
        select(SurveyCbfBase).where(SurveyCbfBase.tenant_code == tenant, SurveyCbfBase.batch_id == batch.id)
        .execution_options(**opts)
    ).all()
    uids = [b.contractor_uid for b in bases]
    results_by_uid: dict[str, SurveyCbfResult] = {}
    if uids:
        rows = db.scalars(
            select(SurveyCbfResult).where(
                SurveyCbfResult.tenant_code == tenant, SurveyCbfResult.contractor_uid.in_(uids)
            ).execution_options(**opts)
        ).all()
        for row in rows:  # 同 uid 多条时取最新
            results_by_uid[row.contractor_uid] = row

    members: list[SurveyCbfJtcyResult] = []
    if uids:
        members = list(db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.tenant_code == tenant, SurveyCbfJtcyResult.contractor_uid.in_(uids)
            ).execution_options(**opts)
        ).all())

    fbf_pairs: list[tuple] = []
    fbf_bases = db.scalars(
        select(SurveyFbfBase).where(SurveyFbfBase.tenant_code == tenant, SurveyFbfBase.batch_id == batch.id)
        .execution_options(**opts)
    ).all()
    if fbf_bases:
        fbf_results = db.scalars(
            select(SurveyFbfResult).where(
                SurveyFbfResult.tenant_code == tenant,
                SurveyFbfResult.id.in_([b.result_id for b in fbf_bases if b.result_id]),
            ).execution_options(**opts)
        ).all()
        by_id = {r.id: r for r in fbf_results}
        fbf_pairs = [(b, by_id.get(b.result_id)) for b in fbf_bases]

    dk_pairs: list[tuple] = []
    dk_bases = db.scalars(
        select(SurveyDkBase).where(SurveyDkBase.tenant_code == tenant, SurveyDkBase.batch_id == batch.id)
        .execution_options(**opts)
    ).all()
    if dk_bases:
        dk_results = db.scalars(
            select(SurveyDkResult).where(
                SurveyDkResult.tenant_code == tenant,
                SurveyDkResult.id.in_([b.result_id for b in dk_bases if b.result_id]),
            ).execution_options(**opts)
        ).all()
        by_id = {r.id: r for r in dk_results}
        dk_pairs = [(b, by_id.get(b.result_id)) for b in dk_bases]

    cbdk_pairs: list[tuple] = []
    cbdk_bases = db.scalars(
        select(SurveyCbdkxxBase).where(SurveyCbdkxxBase.tenant_code == tenant, SurveyCbdkxxBase.batch_id == batch.id)
        .execution_options(**opts)
    ).all()
    if cbdk_bases:
        cbdk_results = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.tenant_code == tenant,
                SurveyCbdkxxResult.id.in_([b.result_id for b in cbdk_bases if b.result_id]),
            ).execution_options(**opts)
        ).all()
        by_id = {r.id: r for r in cbdk_results}
        cbdk_pairs = [(b, by_id.get(b.result_id)) for b in cbdk_bases]

    # 合同台账：按承包方编码前缀（批次区域码）圈定，避免逐块 IN 查询
    contract_numbers: set[str] = set()
    try:
        contract_numbers = set(db.scalars(
            select(Cbht.cbhtbm).where(
                Cbht.tenant_code == tenant,
                Cbht.cbhtbm.like(f"{batch.region_code}%") if batch.region_code else Cbht.cbhtbm.isnot(None),
            ).execution_options(**opts)
        ).all())
    except Exception:  # noqa: BLE001
        logger.exception("质检装载合同台账失败，合同勾稽检查降级为跳过")

    # 与户主关系字典（缺字典时降级为只查空值，不误报）
    relation_codes: set[str] = set(db.scalars(
        select(DictionaryItem.item_value).where(
            DictionaryItem.dict_type == "nyt2539_c20_relation_to_head",
            DictionaryItem.enabled.is_(True),
        )
    ).all())

    # 空间图形缺失的地块（geom 由 PostGIS 迁移补在 survey_dk_result 上）
    geom_missing_ids: set[int] = set()
    dk_result_ids = [r.id for _, r in dk_pairs if r is not None]
    if dk_result_ids:
        try:
            for start in range(0, len(dk_result_ids), 1000):
                chunk = dk_result_ids[start:start + 1000]
                rows = db.execute(
                    text("SELECT id FROM survey_dk_result WHERE tenant_code = :tc AND geom IS NULL AND id = ANY(:ids)"),
                    {"tc": tenant, "ids": chunk},
                )
                geom_missing_ids.update(int(r[0]) for r in rows)
        except Exception:  # noqa: BLE001
            logger.exception("质检检查空间图形失败，该项降级为跳过")

    return {
        "bases": bases,
        "results_by_uid": results_by_uid,
        "members": members,
        "fbf_pairs": fbf_pairs,
        "dk_pairs": dk_pairs,
        "cbdk_pairs": cbdk_pairs,
        "contract_numbers": contract_numbers,
        "relation_codes": relation_codes,
        "geom_missing_ids": geom_missing_ids,
    }


# ── 各质检项（规则口径与原工具 TaskDataChecker 对应）──────────


def _check_card_no(ctx: dict, writer: _RecordWriter, tick) -> None:
    """证件号码重复：户主 + 全体成员，全批次按证件号分组。

    误报剔除：户主本人既在成果行有证件号、又会在成员表里有一行同名同号，
    这两行是**同一个人**——成员行证件号等于本户户主证件号的不参与查重
    （姓名不同但证件号相同的成员行仍参与，那才是真问题）。
    """
    members_by_uid: dict[str, list] = {}
    for member in ctx["members"]:
        members_by_uid.setdefault(member.contractor_uid, []).append(member)

    seen: dict[str, list[tuple[str, str, str]]] = {}  # number -> [(cbfbm, name, role)]
    for base, result in _households(ctx):
        head_number = str((result.cbfzjhm if result else base.cbfzjhm) or "").strip()
        if head_number:
            seen.setdefault(head_number, []).append((base.cbfbm, base.cbfmc, "户主"))
        for member in members_by_uid.get(base.contractor_uid, []):
            m_number = str(member.cyzjhm or "").strip()
            if m_number and m_number != head_number:
                seen.setdefault(m_number, []).append((base.cbfbm, member.cyxm, "家庭成员"))
    for number, entries in seen.items():
        if len(entries) > 1:
            descs = [f"{cbfbm} {name}({role})" for cbfbm, name, role in entries]
            # 定位字段取第一个出现户（完整出现清单在 message 里）
            writer.add("card_no", "warn",
                       f"证件号码:{number}重复,存在于{'、'.join(dict.fromkeys(descs))}!",
                       cbfbm=entries[0][0], cbfmc=entries[0][1])
    tick()


def _households(ctx: dict):
    """[(base, result)]，跳过被合户/注销终结的原户（result_status=cancelled）。"""
    for base in ctx["bases"]:
        result = ctx["results_by_uid"].get(base.contractor_uid)
        if result is not None and result.result_status == "cancelled":
            continue
        yield base, result


def _check_fbf(ctx: dict, writer: _RecordWriter, tick) -> None:
    for base, result in ctx["fbf_pairs"]:
        target = result or base
        # 定位字段：fbf 行的 cbfbm/cbfmc 列存发包方编码/名称（列复用，见模型 docstring）
        common = {"cbfbm": base.fbfbm, "cbfmc": target.fbfmc}
        where = f"发包方:{target.fbfmc}({base.fbfbm})"
        if _is_blank(target.fbffzrxm):
            writer.add("fbf", "error", f"{where}发包方负责人姓名未填写!", **common)
        if _is_blank(target.fzrzjhm):
            writer.add("fbf", "error", f"{where}发包方负责人证件号码未填写!", **common)
        elif str(target.fzrzjlx or "") == "1" and not check_id_number(target.fzrzjhm):
            writer.add("fbf", "warn", f"{where}发包方负责人证件号码{target.fzrzjhm}不符合身份证算法验证规范!", **common)
        if not _is_phone_ok(target.lxdh):
            writer.add("fbf", "error", f"{where}发包方负责人联系电话{target.lxdh}不符合数字要求!", **common)
        if _is_blank(target.fbfdz):
            writer.add("fbf", "error", f"{where}发包方地址未填写!", **common)
        postal = _postal_problem(target.yzbm)
        if postal:
            writer.add("fbf", "error", f"{where}{postal}!", **common)
        if _is_blank(target.fbfdcy):
            writer.add("fbf", "error", f"{where}发包方调查员未填写!", **common)
        if target.fbfdcrq is None:
            writer.add("fbf", "error", f"{where}发包方调查日期未填写!", **common)
        tick()


def _cbflx_range(cbflx: str) -> tuple[int, int] | None:
    """承包方编码（户号后 4 位）与承包方类型的匹配区间，同原工具。"""
    return {"1": (1, 8000), "2": (8001, 9000), "3": (9001, 9999)}.get(str(cbflx or "").strip())


def _check_cbf(ctx: dict, writer: _RecordWriter, tick) -> None:
    members_by_uid: dict[str, list] = {}
    for member in ctx["members"]:
        members_by_uid.setdefault(member.contractor_uid, []).append(member)
    relation_codes = ctx["relation_codes"]

    for base, result in _households(ctx):
        target = result or base
        common = {"cbfbm": base.cbfbm, "cbfmc": base.cbfmc}
        where = f"承包方:{base.cbfmc}({base.cbfbm})"

        # 编码与类型匹配（原工具：1≤n≤8000 / 8001-9000 / 9001-9999）
        rng = _cbflx_range(target.cbflx)
        if rng:
            tail = re.fullmatch(r"\d{4}", str(base.cbfbm or "")[-4:])
            household_no = int(base.cbfbm[-4:]) if tail else None
            if household_no is None:
                writer.add("cbf", "error", f"{where}承包方编码不符合 18 位编码规则(末 4 位户号非数字)!", **common)
            elif not (rng[0] <= household_no <= rng[1]):
                writer.add("cbf", "error", f"{where}承包方编码:{household_no:04d}与承包方类型不匹配,其值应在{rng[0]}-{rng[1]}间!", **common)

        if _is_blank(target.cbfzjhm):
            writer.add("cbf", "error", f"{where}承包方证件号码未填写!", **common)
        elif str(target.cbfzjlx or "") == "1" and not check_id_number(target.cbfzjhm):
            writer.add("cbf", "warn", f"{where}承包方证件号码{target.cbfzjhm}不符合身份证算法验证规范!", **common)
        if _is_blank(target.cbfdz):
            writer.add("cbf", "error", f"{where}承包方地址未填写!", **common)
        postal = _postal_problem(target.yzbm)
        if postal:
            writer.add("cbf", "error", f"{where}承包方{postal}!", **common)
        if not _is_phone_ok(target.lxdh):
            writer.add("cbf", "error", f"{where}承包方联系电话{target.lxdh}不符合数字要求!", **common)
        if _is_blank(target.cbfdcy):
            writer.add("cbf", "error", f"{where}承包方调查员未填写!", **common)
        if target.cbfdcrq is None:
            writer.add("cbf", "error", f"{where}承包方调查日期未填写!", **common)
        if _is_blank(target.gsjsr):
            writer.add("cbf", "error", f"{where}承包方公示记事人未填写!", **common)
        if _is_blank(target.gsshr):
            writer.add("cbf", "error", f"{where}承包方公示审核人未填写!", **common)
        if target.gsshrq is None:
            writer.add("cbf", "error", f"{where}承包方公示审核日期未填写!", **common)

        for member in members_by_uid.get(base.contractor_uid, []):
            mwhere = f"{where}家庭成员:{member.cyxm}"
            if str(member.cyxb or "") not in ("1", "2"):
                writer.add("cbf", "error", f"{mwhere}性别未知!", cbfbm=base.cbfbm, cbfmc=base.cbfmc)
            if _is_blank(member.cyzjhm):
                writer.add("cbf", "error", f"{mwhere}证件号码未填写!", cbfbm=base.cbfbm, cbfmc=base.cbfmc)
            elif str(member.cyzjlx or "") == "1" and not check_id_number(member.cyzjhm):
                writer.add("cbf", "warn", f"{mwhere}证件号码{member.cyzjhm}不符合身份证算法验证规范!",
                           cbfbm=base.cbfbm, cbfmc=base.cbfmc)
            is_head = member.cyxm == base.cbfmc and str(member.cyzjhm or "").strip() == str(base.cbfzjhm or "").strip()
            if is_head:
                continue  # 与户主同名同号的成员视同户主，免查关系
            relation = str(member.yhzgx or "").strip()
            if relation == "":
                writer.add("cbf", "error", f"{mwhere}与户主关系未填写!", cbfbm=base.cbfbm, cbfmc=base.cbfmc)
            elif relation_codes and relation not in relation_codes:
                writer.add("cbf", "error", f"{mwhere}与户主关系{relation}不符合农业部家庭关系代码要求!",
                           cbfbm=base.cbfbm, cbfmc=base.cbfmc)
        tick()


def _check_land(ctx: dict, writer: _RecordWriter, tick) -> None:
    # 地块台账(survey_dk_result)不带户，用承包地块信息(survey_cbdkxx_result)反查归属户
    cbfmc_by_cbfbm = {b.cbfbm: b.cbfmc for b, _ in _households(ctx)}
    owner_by_dkbm: dict[str, tuple[str, str]] = {}
    for cb_base, cb_result in ctx["cbdk_pairs"]:
        dkbm = str((cb_result.dkbm if cb_result else cb_base.dkbm) or "")
        if dkbm:
            owner_by_dkbm.setdefault(dkbm, (cb_base.cbfbm, cbfmc_by_cbfbm.get(cb_base.cbfbm, "")))

    for base, result in ctx["dk_pairs"]:
        target = result or base
        where = f"地块:{target.dkmc or ''}({target.dkbm})"
        owner = owner_by_dkbm.get(str(target.dkbm or ""), ("", ""))
        common = {"dkbm": target.dkbm, "cbfbm": owner[0], "cbfmc": owner[1]}
        if _is_blank(target.dkmc):
            writer.add("land", "warn", f"地块编码为:{target.dkbm}的地块名称未填写!", **common)
        if len(str(target.dkbm or "")) != 19:
            writer.add("land", "warn", f"{where}地块编码不符合农业部 19 位数字要求!", **common)
        land_type = str(target.tdlylx or "").strip()
        if land_type:
            if len(land_type) != 3:
                reason = "土地利用类型未知不符合农业部二级类型要求" if "XX" in land_type else "土地利用类型填写不符合农业部二级类型要求"
                writer.add("land", "error", f"{where}{reason}!", **common)
        # 原工具口径：地力等级为哨兵值 900 视同未填写
        if _is_blank(target.dldj) or str(target.dldj).strip() == "900":
            writer.add("land", "error", f"{where}地力等级未填写!", **common)
        # NYT 2539：1=是 / 2=否，这里只查"未填写"，取值合法性交给字典闸门
        if _is_blank(target.sfjbnt):
            writer.add("land", "error", f"{where}是否基本农田未填写!", **common)
        if not (target.scmj or Decimal("0")) > Decimal("0"):
            writer.add("land", "error", f"{where}实测面积未填写!", **common)
        for label, field in (("四至东", "dkdz"), ("四至南", "dknz"), ("四至西", "dkxz"), ("四至北", "dkbz")):
            if _is_blank(getattr(target, field, None)):
                writer.add("land", "error", f"{where}{label}未填写!", **common)
        if _is_blank(target.zjrxm):
            writer.add("land", "error", f"{where}指界人未填写!", **common)
        if target.id in ctx["geom_missing_ids"]:
            writer.add("land", "error", f"{where}无空间信息!", **common)
        tick()


def _check_contract(ctx: dict, writer: _RecordWriter, tick) -> None:
    parcels_by_uid: dict[str, list] = {}
    for base, result in ctx["cbdk_pairs"]:
        if result is not None:
            parcels_by_uid.setdefault(base.cbfbm, []).append(result)
    contract_numbers = ctx["contract_numbers"]

    for base, _result in _households(ctx):
        parcels = parcels_by_uid.get(base.cbfbm, [])
        if not parcels:
            writer.add("contract", "error", f"承包方:{base.cbfmc}({base.cbfbm})名下无承包地块信息!",
                       cbfbm=base.cbfbm, cbfmc=base.cbfmc)
            tick()
            continue
        for parcel in parcels:
            cbhtbm = str(parcel.cbhtbm or "").strip()
            if cbhtbm == "":
                writer.add("contract", "error",
                           f"承包方:{base.cbfmc}({base.cbfbm})地块:{parcel.dkbm}的承包合同编号未填写!",
                           cbfbm=base.cbfbm, cbfmc=base.cbfmc, dkbm=parcel.dkbm)
            elif contract_numbers and cbhtbm not in contract_numbers:
                writer.add("contract", "error",
                           f"承包方:{base.cbfmc}({base.cbfbm})地块:{parcel.dkbm}的承包合同{cbhtbm}不在合同台账中!",
                           cbfbm=base.cbfbm, cbfmc=base.cbfmc, dkbm=parcel.dkbm)
        tick()


# ── 运行器 ───────────────────────────────────────────────────

def start_quality_check_job(batch_id: int, user_id: int, items: dict[str, bool] | None = None) -> dict:
    job = _create_job(batch_id, user_id, items or {})

    def target():
        from app.db.session import SessionLocal
        from app.models.survey import SurveyBatch

        db = SessionLocal()
        try:
            batch = db.get(SurveyBatch, batch_id)
            if batch is None:
                raise ValueError("调查批次不存在")
            enabled = job["items"]
            _update_job(job["id"], phase="装载数据…")
            ctx = _load_run_context(db, batch)

            total = 1  # card_no 记一个单位
            if enabled.get("fbf"):
                total += len(ctx["fbf_pairs"])
            if enabled.get("cbf"):
                total += len(ctx["bases"])
            if enabled.get("land"):
                total += len(ctx["dk_pairs"])
            if enabled.get("contract"):
                total += len(ctx["bases"]) + len(ctx["cbdk_pairs"])
            total = max(total, 1)
            state = {"done": 0}

            def tick():
                state["done"] += 1
                _update_job(job["id"], done=state["done"], total=total)

            writer = _RecordWriter(db, job["runId"], batch, user_id)
            started_at = time.time()

            _update_job(job["id"], phase="检查证件号码重复")
            if enabled.get("card_no", True):
                _check_card_no(ctx, writer, tick)
            if enabled.get("fbf", True):
                _update_job(job["id"], phase="检查发包方信息")
                _check_fbf(ctx, writer, tick)
            if enabled.get("cbf", True):
                _update_job(job["id"], phase="检查承包方信息")
                _check_cbf(ctx, writer, tick)
            if enabled.get("land", True):
                _update_job(job["id"], phase="检查承包地块信息")
                _check_land(ctx, writer, tick)
            if enabled.get("contract", True):
                _update_job(job["id"], phase="检查合同与权证")
                _check_contract(ctx, writer, tick)

            _update_job(job["id"], phase="写入质检记录")
            duration_ms = int((time.time() - started_at) * 1000)
            summary = {
                "items": {k: v for k, v in enabled.items() if v},
                "counts": writer.counts,
                "perItem": writer.per_item,
                "durationMs": duration_ms,
                "notes": ["权证台账本系统未建表，权证检查以合同台账勾稽替代"] if enabled.get("contract") else [],
            }
            writer.add("summary", "summary", json.dumps(summary, ensure_ascii=False))
            writer.flush()

            counts = dict(writer.counts)
            _update_job(job["id"], status="done", phase="质检完成", done=total, total=total,
                        counts=counts, current="")
        except Exception as exc:  # noqa: BLE001
            logger.exception("数据质检任务失败 job=%s", job["id"])
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
            _update_job(job["id"], status="error", error=str(exc) or exc.__class__.__name__,
                        detail=traceback.format_exc(limit=5))
        finally:
            db.close()

    thread = threading.Thread(target=target, name=f"qc-job-{job['id'][:8]}", daemon=True)
    thread.start()
    return job


# ── 历史记录查询（供端点使用）────────────────────────────────

def list_runs(db: Session, batch_id: int, page: int = 1, page_size: int = 20) -> dict:
    from app.models.survey import SurveyQualityCheckRecord

    query = db.query(SurveyQualityCheckRecord).filter(
        SurveyQualityCheckRecord.batch_id == batch_id,
        SurveyQualityCheckRecord.check_item == "summary",
    )
    total = query.count()
    rows = (
        query.order_by(SurveyQualityCheckRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = []
    for row in rows:
        try:
            summary = json.loads(row.message)
        except (TypeError, ValueError):
            summary = None
        items.append({
            "runId": row.run_id,
            "batchId": row.batch_id,
            "batchNo": row.batch_no,
            "counts": (summary or {}).get("counts") or {},
            "perItem": (summary or {}).get("perItem") or {},
            "items": (summary or {}).get("items") or {},
            "notes": (summary or {}).get("notes") or [],
            "durationMs": (summary or {}).get("durationMs"),
            "createdAt": row.created_at.isoformat() if row.created_at else None,
            "createdByName": "",
        })
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


def list_records(
    db: Session,
    batch_id: int,
    run_id: str,
    severity: str | None = None,
    check_item: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    from app.models.survey import SurveyQualityCheckRecord

    query = db.query(SurveyQualityCheckRecord).filter(
        SurveyQualityCheckRecord.batch_id == batch_id,
        SurveyQualityCheckRecord.run_id == run_id,
        SurveyQualityCheckRecord.check_item != "summary",
    )
    if severity:
        query = query.filter(SurveyQualityCheckRecord.severity == severity)
    if check_item:
        query = query.filter(SurveyQualityCheckRecord.check_item == check_item)
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.filter(SurveyQualityCheckRecord.message.like(like))
    total = query.count()
    rows = (
        query.order_by(SurveyQualityCheckRecord.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        {
            "id": row.id,
            "runId": row.run_id,
            "checkItem": row.check_item,
            "checkItemLabel": CHECK_ITEM_LABELS.get(row.check_item, row.check_item),
            "severity": row.severity,
            "cbfbm": row.cbfbm,
            "cbfmc": row.cbfmc,
            "dkbm": row.dkbm,
            "message": row.message,
            "createdAt": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


# ── 明细导出（Excel .xls，xlwt 与 excel_transfer 同依赖）──────

_EXPORT_MAX_ROWS = 65000  # .xls 单表上限 65536，留表头与截断提示行
_SEVERITY_LABELS = {"error": "错误", "warn": "警告", "info": "提示"}


def build_records_export(
    db: Session,
    batch_id: int,
    run_id: str,
    severity: str | None = None,
    check_item: str | None = None,
    keyword: str | None = None,
) -> tuple[str, bytes]:
    """把一次质检运行的问题明细导出为 .xls，返回 (文件名, 字节)。"""
    import io

    import xlwt

    from app.models.survey import SurveyBatch, SurveyQualityCheckRecord

    batch = db.get(SurveyBatch, batch_id)
    batch_no = batch.batch_no if batch else str(batch_id)

    query = db.query(SurveyQualityCheckRecord).filter(
        SurveyQualityCheckRecord.batch_id == batch_id,
        SurveyQualityCheckRecord.run_id == run_id,
        SurveyQualityCheckRecord.check_item != "summary",
    )
    if severity:
        query = query.filter(SurveyQualityCheckRecord.severity == severity)
    if check_item:
        query = query.filter(SurveyQualityCheckRecord.check_item == check_item)
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.filter(SurveyQualityCheckRecord.message.like(like))
    rows = query.order_by(SurveyQualityCheckRecord.id.asc()).limit(_EXPORT_MAX_ROWS + 1).all()

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("质检记录")

    header_style = xlwt.easyxf(
        "font: bold on; align: horiz center, vert center; borders: left thin, right thin, top thin, bottom thin"
    )
    columns = ["序号", "质检项", "级别", "承包方编码", "承包方名称", "地块编码", "问题描述", "检查时间"]
    widths = [8, 16, 8, 20, 16, 20, 80, 20]
    for col, (title, width) in enumerate(zip(columns, widths)):
        ws.write(0, col, title, header_style)
        ws.col(col).width = width * 256

    truncated = False
    if len(rows) > _EXPORT_MAX_ROWS:
        rows = rows[:_EXPORT_MAX_ROWS]
        truncated = True

    body_style = xlwt.easyxf("align: vert center, wrap on")
    center_style = xlwt.easyxf("align: horiz center, vert center")
    for idx, row in enumerate(rows, start=1):
        ws.write(idx, 0, idx, center_style)
        ws.write(idx, 1, CHECK_ITEM_LABELS.get(row.check_item, row.check_item), center_style)
        ws.write(idx, 2, _SEVERITY_LABELS.get(row.severity, row.severity), center_style)
        ws.write(idx, 3, row.cbfbm or "", body_style)
        ws.write(idx, 4, row.cbfmc or "", body_style)
        ws.write(idx, 5, row.dkbm or "", body_style)
        ws.write(idx, 6, row.message or "", body_style)
        ws.write(idx, 7, row.created_at.strftime("%Y-%m-%d %H:%M:%S") if row.created_at else "", center_style)

    total = len(rows) + (1 if truncated else 0)
    if truncated:
        note = wb.add_sheet("说明")
        note.write(0, 0, f"记录超过 {_EXPORT_MAX_ROWS} 条，本文件仅导出前 {_EXPORT_MAX_ROWS} 条，请缩小筛选范围后分批导出。")
    elif total == 0:
        ws.write(1, 0, "当前筛选条件下没有质检问题记录。", body_style)

    buffer = io.BytesIO()
    wb.save(buffer)
    filename = f"数据质检记录_{batch_no}_{run_id[:8]}.xls"
    return filename, buffer.getvalue()
