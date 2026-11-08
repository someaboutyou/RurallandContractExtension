# -*- coding: utf-8 -*-
"""探针：调查批次管理页「数据正确性勾稽」——HTTP 返回 vs 数据库独立直查。

不只看报错：每个数字都要两边对得上账。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
    text = line.strip()
    if not text or text.startswith("#") or "=" not in text:
        continue
    key, value = text.split("=", 1)
    os.environ.setdefault(key.strip(), value.strip())
os.environ.setdefault("SECRET_KEY", "probe-only")
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from sqlalchemy import func, select, text  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.survey import (  # noqa: E402
    SurveyBatch,
    SurveyCbdkxxBase,
    SurveyCbfBase,
    SurveyCbfJtcyBase,
    SurveyFbfBase,
)

BASE = "http://127.0.0.1:8000/api/v1"
TOKEN = create_access_token("1")
BID = 3

results: list[tuple[str, bool, str]] = []


def record(name, ok, detail):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} — {detail}")


def call(method, path, payload=None, timeout=60):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8", "replace"))


def main():
    db = SessionLocal()
    try:
        # ── 1. 批次统计卡五项 vs SQL 独立计数 ─────────────────
        code, payload = call("GET", f"/surveys/batches/{BID}/stats")
        api = payload.get("data") or {}
        sql_issuer = db.scalar(select(func.count(func.distinct(SurveyFbfBase.fbfbm))).where(SurveyFbfBase.batch_id == BID)) or 0
        sql_cbf = db.scalar(select(func.count(SurveyCbfBase.id)).where(SurveyCbfBase.batch_id == BID)) or 0
        sql_jtcy = db.scalar(select(func.count(SurveyCbfJtcyBase.id)).where(SurveyCbfJtcyBase.batch_id == BID)) or 0
        sql_dk = db.scalar(select(func.count(SurveyCbdkxxBase.id)).where(SurveyCbdkxxBase.batch_id == BID)) or 0
        sql_ht = db.scalar(
            select(func.count(func.distinct(SurveyCbdkxxBase.cbhtbm))).where(
                SurveyCbdkxxBase.batch_id == BID,
                SurveyCbdkxxBase.cbhtbm.isnot(None), SurveyCbdkxxBase.cbhtbm != "",
            )
        ) or 0
        checks = [
            ("issuerCount", api.get("issuerCount"), sql_issuer),
            ("contractorCount", api.get("contractorCount"), sql_cbf),
            ("memberCount", api.get("memberCount"), sql_jtcy),
            ("parcelCount", api.get("parcelCount"), sql_dk),
            ("contractCount", api.get("contractCount"), sql_ht),
        ]
        bad = [f"{k}: api={a} sql={s}" for k, a, s in checks if a != s]
        record("统计卡五项 vs SQL 独立计数", not bad, "全部一致 " + str({k: a for k, a, _ in checks}) if not bad else "; ".join(bad))
        # 合理性：合同数 ≤ 承包户数、地块数 ≥ 承包户数
        record("统计合理性（合同≤户、地块≥户、成员≥户）", sql_ht <= sql_cbf and sql_dk >= sql_cbf and sql_jtcy >= sql_cbf,
               f"合同{sql_ht}≤户{sql_cbf}≤成员{sql_jtcy}，地块{sql_dk}≥户")

        # ── 2. 批次列表计数 vs survey_cbf_base 状态分布 ────────
        code, payload = call("GET", "/surveys/batches?page=1&page_size=50")
        item = next((i for i in (payload.get("data") or {}).get("items", []) if i["id"] == BID), None)
        rows = db.execute(
            text("SELECT task_status, COUNT(*) FROM survey_cbf_base WHERE batch_id = :b GROUP BY task_status"),
            {"b": BID},
        ).all()
        dist = {r[0]: r[1] for r in rows}
        total = sum(dist.values())
        checked = [
            ("taskCount", item.get("taskCount"), total),
            ("surveyedCount", item.get("surveyedCount"), dist.get("surveyed", 0)),
            ("confirmedCount", item.get("confirmedCount"), dist.get("confirmed", 0)),
            ("skippedCount", item.get("skippedCount"), dist.get("skipped", 0)),
            ("notStartedCount", item.get("notStartedCount"), dist.get("not_started", 0)),
            ("unassignedCount", item.get("unassignedCount"),
             db.scalar(select(func.count(SurveyCbfBase.id)).where(
                 SurveyCbfBase.batch_id == BID,
                 (SurveyCbfBase.assigned_to.is_(None)) | (SurveyCbfBase.assigned_to == 0))) or 0),
        ]
        bad = [f"{k}: api={a} sql={s}" for k, a, s in checked if a != s]
        record("批次列表计数 vs 状态分布 SQL", not bad, f"状态分布={dist}" if not bad else "; ".join(bad))

        # ── 3. 发包方清单字段 vs survey_fbf_result（区域口径：批次区域码 14 位前缀）──
        code, payload = call("GET", f"/surveys/batches/{BID}/issuers?page=1&page_size=200")
        iitems = (payload.get("data") or {}).get("items") or []
        region14 = str(db.scalar(select(SurveyBatch.region_code).where(SurveyBatch.id == BID)) or "")[:14]
        db_rows = db.execute(
            text("SELECT fbfbm, fbfmc, fbffzrxm, lxdh, fbfdz FROM survey_fbf_result WHERE fbfbm LIKE :p"),
            {"p": f"{region14}%"},
        ).all()
        db_map = {r[0]: r for r in db_rows}
        bad = []
        for row in iitems:
            d = db_map.get(row.get("code"))
            if d is None:
                bad.append(f"{row.get('code')} 不在库内")
                continue
            if row.get("name") != d[1]:
                bad.append(f"{row.get('code')} 名称 api={row.get('name')!r} db={d[1]!r}")
            if (row.get("responsibleName") or None) != (d[2] or None):
                bad.append(f"{row.get('code')} 负责人不一致")
        record("发包方清单字段 vs survey_fbf_result", not bad, f"{len(iitems)} 行逐字段核对一致" if not bad else "; ".join(bad[:5]))

        # ── 4. active-batches vs survey_batches ───────────────
        code, payload = call("GET", "/surveys/active-batches")
        api_ids = {i["id"] for i in (payload.get("data") or [])}
        sql_ids = set(db.scalars(select(SurveyBatch.id).where(SurveyBatch.status == "active", SurveyBatch.survey_type == "household_survey")))
        record("active-batches vs survey_batches(active)", api_ids == sql_ids, f"api={sorted(api_ids)} sql={sorted(sql_ids)}")

        # ── 5. 质检结果对账：记录表分组 + 抽样核真 ──────────────
        # 5a. 最近一次运行的 error 计数与探针早前结果（69 error / 14 warn）对账
        last_run = db.execute(
            text("SELECT run_id FROM survey_quality_check_records WHERE batch_id = :b GROUP BY run_id ORDER BY max(id) DESC LIMIT 1"),
            {"b": BID},
        ).scalar()
        qdist_rows = db.execute(
            text("SELECT severity, check_item, COUNT(*) FROM survey_quality_check_records WHERE batch_id = :b AND run_id = :r AND severity != 'summary' GROUP BY severity, check_item"),
            {"b": BID, "r": last_run},
        ).all()
        qmap = {(r[0], r[1]): r[2] for r in qdist_rows}
        err_total = sum(v for (sev, _), v in qmap.items() if sev == "error")
        warn_total = sum(v for (sev, _), v in qmap.items() if sev == "warn")
        record("质检计数对账（最近 run：error=69 / warn=14）", err_total == 69 and warn_total == 14, f"error={err_total}, warn={warn_total}, 分布={qmap}")

        # 5b. 抽样核真：空证件号 error 的每条是否属实（68 条）+ 定位多出的 1 条
        blank = db.execute(
            text("SELECT message FROM survey_quality_check_records WHERE batch_id = :b AND run_id = :r AND severity = 'error' AND message LIKE '%证件号码未填写%'"),
            {"b": BID, "r": last_run},
        ).all()
        other_err = db.execute(
            text("SELECT check_item, message FROM survey_quality_check_records WHERE batch_id = :b AND run_id = :r AND severity = 'error' AND message NOT LIKE '%证件号码未填写%'"),
            {"b": BID, "r": last_run},
        ).all()
        db_blank = db.execute(
            text("""
                SELECT COUNT(*) FROM survey_cbf_jtcy_base m
                JOIN survey_cbf_base c ON c.batch_id = m.batch_id AND c.contractor_uid = m.contractor_uid
                WHERE m.batch_id = :b AND (m.cyzjhm IS NULL OR m.cyzjhm = '')
            """),
            {"b": BID},
        ).scalar() or 0
        record("质检空证件号 error 与库内勾稽", len(blank) == db_blank, f"记录 {len(blank)} 条 vs 库内空证件成员 {db_blank} 人")
        record("其余 error 归属可解释（非证件类）", len(other_err) == err_total - len(blank), f"非证件类 error {len(other_err)} 条: {[m[1][:50] for m in other_err[:3]]}")

        # ── 6. 批次号格式与创建时间合理性 ─────────────────────
        batches = db.scalars(select(SurveyBatch).order_by(SurveyBatch.id)).all()
        bad = []
        for b in batches:
            if b.batch_no and not b.batch_no.startswith("SUR"):
                bad.append(f"批次{b.id} 编号异常: {b.batch_no}")
            if b.created_at and b.created_at.year < 2020:
                bad.append(f"批次{b.id} 创建时间异常: {b.created_at}")
        record("批次号格式/创建时间合理性", not bad, f"{len(batches)} 个批次检查完" if not bad else "; ".join(bad))

    finally:
        db.close()

    fails = [r for r in results if not r[1]]
    print(f"\n共 {len(results)} 项，通过 {len(results) - len(fails)}，失败 {len(fails)}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
