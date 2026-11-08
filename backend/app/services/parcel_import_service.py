"""承包地块管理：地块调查表 / 摸底核实表 / 矢量图斑导入。

对齐 CS 版三个导入入口：

- 地块调查表：只导入地块属性（CS ``AccountLandBusiness.ImportData``）；
- 摸底核实表：导入发包方、承包方、家庭成员、地块（CS ``ImportLandTiesTable``）；
- 矢量图斑：按地块编码更新地块图形（CS ``ImportLandShapeData``）。

本实现按“承包方编码匹配当前批次现有承包方”导入；找不到的承包方按错误行
返回，不会凭空创建整户数据，避免导入错文件污染批次。
"""

from __future__ import annotations

import io
import logging
import tempfile
import zipfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import xlrd
from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.crs import get_target_srid
from app.models.survey import (
    SurveyBatch,
    SurveyCbfBase,
    SurveyCbfJtcyBase,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyCbdkxxBase,
    SurveyCbdkxxResult,
    SurveyDkBase,
    SurveyDkResult,
    SurveyFbfResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service
from app.services.dictionary_service import dictionary_service
from app.services.survey.excel_transfer import (
    GENDER_CODES,
    _cell,
    _parse_date_cell,
    _raw_cell,
)

logger = logging.getLogger(__name__)

SQM_PER_MU = Decimal("666.6666667")

IMPORT_PARCEL_SURVEY = "parcel_survey"
IMPORT_BASELINE_SURVEY = "baseline_survey"
IMPORT_VECTOR = "vector"

IMPORT_LABELS = {
    IMPORT_PARCEL_SURVEY: "地块调查表",
    IMPORT_BASELINE_SURVEY: "摸底核实表",
    IMPORT_VECTOR: "矢量图斑",
}

MODE_MERGE = "merge"
MODE_REPLACE = "replace"
MODE_CONTRACTOR_ONLY = "contractor_only"

DICT_TYPES = {
    "contractor_type": "nyt2539_c02_contractor_type",
    "id_type": "nyt2539_c15_id_document_type",
    "relation": "nyt2539_c20_relation_to_head",
    "ownership": "nyt2539_c06_ownership_property",
    "category": "nyt2539_c07_parcel_category",
    "grade": "nyt2539_c08_land_grade",
    "land_use": "nyt2539_c09_land_use",
}


def _decimal(value: Any) -> Decimal | None:
    text_value = str(value or "").replace(",", "").strip()
    if not text_value:
        return None
    try:
        return Decimal(text_value)
    except InvalidOperation:
        return None


def _mu_to_sqm(value: Any) -> Decimal | None:
    mu = _decimal(value)
    return (mu * SQM_PER_MU).quantize(Decimal("0.01")) if mu is not None else None


def _date_text(value: Any, datemode: int) -> str | None:
    parsed = _parse_date_cell(value, datemode)
    return parsed or None


def _yes(value: str) -> str:
    text_value = (value or "").strip()
    if text_value in {"是", "1", "Y", "y", "true", "True"}:
        return "1"
    return "0"


def _safe_code(value: Any, length: int) -> str:
    text_value = "".join(ch for ch in str(value or "") if ch.isdigit())
    return text_value[:length]


class ParcelImportService:
    # ── 字典 ────────────────────────────────────────────────────────────────

    def _dictionary_maps(self, db: Session) -> dict[str, tuple[dict[str, str], dict[str, str]]]:
        result: dict[str, tuple[dict[str, str], dict[str, str]]] = {}
        for key, dict_type in DICT_TYPES.items():
            options = dictionary_service.get_options(db, dict_type)
            label_by_code = {item["value"]: item["label"] for item in options}
            code_by_label = {item["label"]: item["value"] for item in options}
            result[key] = (label_by_code, code_by_label)
        return result

    @staticmethod
    def _relation_label(maps: dict, value: str) -> str:
        text_value = (value or "").strip()
        if not text_value:
            return ""
        label_by_code = maps.get("relation", ({}, {}))[0]
        return label_by_code.get(text_value, text_value)

    @staticmethod
    def _code(maps: dict, key: str, value: str, default: str = "") -> str:
        text_value = (value or "").strip()
        if not text_value:
            return default
        label_by_code, code_by_label = maps.get(key, ({}, {}))
        if text_value in label_by_code:
            return text_value
        return code_by_label.get(text_value, default or text_value)

    @staticmethod
    def _ensure_batch(db: Session, batch_id: int, current_user: User) -> SurveyBatch:
        batch = db.get(SurveyBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="调查批次不存在")
        data_access_service.ensure_region_filter_in_scope(
            current_user, batch.region_code, detail="当前批次区域不在可导入范围内"
        )
        return batch

    @staticmethod
    def _load_contractors(
        db: Session, batch: SurveyBatch
    ) -> tuple[dict[str, SurveyCbfResult], dict[str, SurveyCbfBase]]:
        bases = db.scalars(
            select(SurveyCbfBase)
            .where(
                SurveyCbfBase.tenant_code == batch.tenant_code,
                SurveyCbfBase.batch_id == batch.id,
            )
            .order_by(SurveyCbfBase.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        base_by_code: dict[str, SurveyCbfBase] = {}
        for base in bases:
            base_by_code.setdefault(base.cbfbm, base)
        uids = list({base.contractor_uid for base in bases})
        results: dict[str, SurveyCbfResult] = {}
        if uids:
            rows = db.scalars(
                select(SurveyCbfResult)
                .where(
                    SurveyCbfResult.tenant_code == batch.tenant_code,
                    SurveyCbfResult.contractor_uid.in_(uids),
                )
                .order_by(SurveyCbfResult.id.asc())
                .execution_options(skip_tenant_scope=True)
            ).all()
            for row in rows:
                results[row.cbfbm] = row
        return results, base_by_code

    # ── Excel 解析 ──────────────────────────────────────────────────────────

    @staticmethod
    def _open_excel(content: bytes):
        try:
            book = xlrd.open_workbook(file_contents=content)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"无法读取 Excel 文件：{exc}") from exc
        if book.nsheets == 0:
            raise HTTPException(status_code=400, detail="Excel 文件没有工作表")
        return book, book.sheet_by_index(0)

    def _parse_parcel_survey(self, content: bytes) -> tuple[list[dict], list[dict]]:
        book, sh = self._open_excel(content)
        issues: list[dict] = []
        rows: list[dict] = []
        for r in range(5, sh.nrows):
            cbfbm = _safe_code(_cell(sh, r, 0), 18)
            dkbm = _safe_code(_cell(sh, r, 21), 19)
            if not cbfbm and not dkbm:
                continue
            if not cbfbm or len(cbfbm) != 18:
                issues.append({"row": r + 1, "message": "承包方编码不是 18 位数字"})
                continue
            if not dkbm or len(dkbm) != 19:
                issues.append({"row": r + 1, "message": "地块编码不是 19 位数字"})
                continue
            rows.append({
                "rowIndex": r + 1,
                "cbfbm": cbfbm,
                "cbfmc": _cell(sh, r, 1),
                "dkbm": dkbm,
                "dkmc": _cell(sh, r, 20) or dkbm,
                "htmj": _mu_to_sqm(_cell(sh, r, 23)),
                "scmj": _mu_to_sqm(_cell(sh, r, 24)),
                "syqxz": "",
                "dklb": _cell(sh, r, 34) or "承包地块",
                "tdlylx": _cell(sh, r, 31),
                "dldj": _cell(sh, r, 30),
                "tdyt": _cell(sh, r, 29),
                "sfjbnt": _yes(_cell(sh, r, 32)),
                "dkxz": _cell(sh, r, 25),
                "dknz": _cell(sh, r, 26),
                "dkbz": _cell(sh, r, 27),
                "dkbzxx": _cell(sh, r, 28),
                "dkdz": _cell(sh, r, 35),
                "zjrxm": _cell(sh, r, 33),
            })
        return rows, issues

    def _parse_baseline_survey(self, content: bytes) -> tuple[dict, list[dict], list[dict]]:
        book, sh = self._open_excel(content)
        datemode = book.datemode
        issues: list[dict] = []
        issuer = {
            "fbfmc": _cell(sh, 2, 0),
            "fbfbm": _safe_code(_cell(sh, 2, 5), 14),
            "fbffzrxm": _cell(sh, 2, 7),
            "fzrzjlx": _cell(sh, 2, 11),
            "fzrzjhm": _cell(sh, 2, 14),
            "lxdh": _cell(sh, 2, 19),
            "fbfdz": _cell(sh, 2, 22),
            "yzbm": _cell(sh, 2, 28),
            "fbfdcy": _cell(sh, 2, 30),
            "fbfdcrq": _date_text(_raw_cell(sh, 2, 33), datemode),
        }

        households: list[dict] = []
        current: dict | None = None
        for r in range(5, sh.nrows):
            cbfbm = _safe_code(_cell(sh, r, 3), 18)
            cbfmc = _cell(sh, r, 1)
            if cbfbm:
                if len(cbfbm) != 18:
                    issues.append({"row": r + 1, "message": "承包方编码不是 18 位数字"})
                    current = None
                else:
                    current = {
                        "rowIndex": r + 1,
                        "cbfbm": cbfbm,
                        "cbfmc": cbfmc,
                        "cbflx": _cell(sh, r, 2),
                        "lxdh": _cell(sh, r, 4),
                        "cbfdz": _cell(sh, r, 5),
                        "memberCount": _cell(sh, r, 6),
                        "members": [],
                        "parcels": [],
                    }
                    households.append(current)
            if current is None:
                continue

            member_name = _cell(sh, r, 7)
            member_id = _cell(sh, r, 11)
            if member_name or member_id:
                current["members"].append({
                    "rowIndex": r + 1,
                    "name": member_name,
                    "gender": _cell(sh, r, 8),
                    "phone": _cell(sh, r, 9),
                    "idType": _cell(sh, r, 10),
                    "idNo": member_id,
                    "relation": _cell(sh, r, 12),
                    "noteCode": _cell(sh, r, 13),
                    "note": _cell(sh, r, 14),
                })

            dkbm = _safe_code(_cell(sh, r, 16), 19)
            if dkbm:
                if len(dkbm) != 19:
                    issues.append({"row": r + 1, "message": "地块编码不是 19 位数字"})
                else:
                    current["parcels"].append({
                        "rowIndex": r + 1,
                        "dkbm": dkbm,
                        "dkmc": _cell(sh, r, 15) or dkbm,
                        "syqxz": _cell(sh, r, 17),
                        "dklb": _cell(sh, r, 18),
                        "tdlylx": _cell(sh, r, 19),
                        "dldj": _cell(sh, r, 20),
                        "tdyt": _cell(sh, r, 21),
                        "sfjbnt": _yes(_cell(sh, r, 22)),
                        "htmj": _mu_to_sqm(_cell(sh, r, 23)),
                        "yhtmj": _mu_to_sqm(_cell(sh, r, 24)),
                        "scmj": _mu_to_sqm(_cell(sh, r, 26)),
                        "dkxz": _cell(sh, r, 28),
                        "dknz": _cell(sh, r, 29),
                        "dkbz": _cell(sh, r, 30),
                        "dkbzxx": _cell(sh, r, 31),
                        "dkdz": _cell(sh, r, 32),
                    })
        return issuer, households, issues

    # ── 预览 ────────────────────────────────────────────────────────────────

    def preview(
        self,
        db: Session,
        batch_id: int,
        import_type: str,
        content: bytes,
        mode: str,
        current_user: User,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id, current_user)
        if import_type == IMPORT_VECTOR:
            return self._preview_vector(db, batch, content)
        if import_type == IMPORT_PARCEL_SURVEY:
            rows, issues = self._parse_parcel_survey(content)
            results, _ = self._load_contractors(db, batch)
            valid = [row for row in rows if row["cbfbm"] in results]
            missing = [row for row in rows if row["cbfbm"] not in results]
            for row in missing:
                issues.append({
                    "row": row["rowIndex"],
                    "message": f"承包方不存在：{row['cbfbm']}",
                })
            return {
                "importType": import_type,
                "label": IMPORT_LABELS[import_type],
                "total": len(rows),
                "matched": len(valid),
                "create": len({row["dkbm"] for row in valid}),
                "update": 0,
                "skipped": len(missing),
                "error": len(issues),
                "issues": issues,
                "samples": valid[:50],
            }
        if import_type == IMPORT_BASELINE_SURVEY:
            issuer, households, issues = self._parse_baseline_survey(content)
            results, _ = self._load_contractors(db, batch)
            missing = [h for h in households if h["cbfbm"] not in results]
            for household in missing:
                issues.append({
                    "row": household["rowIndex"],
                    "message": f"承包方不存在：{household['cbfbm']}",
                })
            valid = [h for h in households if h["cbfbm"] in results]
            return {
                "importType": import_type,
                "label": IMPORT_LABELS[import_type],
                "mode": mode,
                "total": len(households),
                "matched": len(valid),
                "create": 0,
                "update": len(valid),
                "skipped": len(missing),
                "error": len(issues),
                "memberCount": sum(len(h["members"]) for h in valid),
                "parcelCount": sum(len(h["parcels"]) for h in valid),
                "issuer": issuer,
                "issues": issues,
                "samples": [
                    {
                        "rowIndex": h["rowIndex"],
                        "cbfbm": h["cbfbm"],
                        "cbfmc": h["cbfmc"],
                        "members": len(h["members"]),
                        "parcels": len(h["parcels"]),
                    }
                    for h in valid[:50]
                ],
            }
        raise HTTPException(status_code=400, detail="不支持的导入类型")

    # ── 导入 ────────────────────────────────────────────────────────────────

    def import_data(
        self,
        db: Session,
        batch_id: int,
        import_type: str,
        content: bytes,
        mode: str,
        current_user: User,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id, current_user)
        self._ensure_batch_editable(batch)
        if import_type == IMPORT_VECTOR:
            return self._import_vector(db, batch, content, current_user)
        maps = self._dictionary_maps(db)
        if import_type == IMPORT_PARCEL_SURVEY:
            rows, issues = self._parse_parcel_survey(content)
            result = self._import_parcel_rows(db, batch, rows, maps, issues)
        elif import_type == IMPORT_BASELINE_SURVEY:
            issuer, households, issues = self._parse_baseline_survey(content)
            result = self._import_baseline(db, batch, issuer, households, maps, issues, mode)
        else:
            raise HTTPException(status_code=400, detail="不支持的导入类型")
        db.commit()
        result["importType"] = import_type
        result["label"] = IMPORT_LABELS[import_type]
        logger.info(
            "地块导入完成 batch_id=%s type=%s mode=%s result=%s 操作人=%s",
            batch_id, import_type, mode, result, getattr(current_user, "username", None),
        )
        return result

    @staticmethod
    def _ensure_batch_editable(batch: SurveyBatch) -> None:
        if batch.status != "active":
            raise HTTPException(status_code=400, detail="调查批次已结束，不能导入")

    def _import_parcel_rows(
        self,
        db: Session,
        batch: SurveyBatch,
        rows: list[dict],
        maps: dict,
        issues: list[dict],
    ) -> dict:
        results, _ = self._load_contractors(db, batch)
        now = datetime.now(timezone.utc)
        created = updated = skipped = 0
        for row in rows:
            contractor = results.get(row["cbfbm"])
            if contractor is None:
                issues.append({"row": row["rowIndex"], "message": f"承包方不存在：{row['cbfbm']}"})
                skipped += 1
                continue
            try:
                applied = self._upsert_parcel(
                    db, batch, contractor, row, maps, now, replace=False
                )
                if applied == "created":
                    created += 1
                else:
                    updated += 1
            except HTTPException as exc:
                issues.append({"row": row["rowIndex"], "message": str(exc.detail)})
                skipped += 1
        return {
            "mode": "parcel",
            "total": len(rows),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "error": len(issues),
            "issues": issues,
        }

    def _import_baseline(
        self,
        db: Session,
        batch: SurveyBatch,
        issuer_data: dict,
        households: list[dict],
        maps: dict,
        issues: list[dict],
        mode: str,
    ) -> dict:
        results, _ = self._load_contractors(db, batch)
        now = datetime.now(timezone.utc)
        updated_households = updated_members = updated_parcels = skipped = 0

        self._upsert_issuer(db, batch, issuer_data, maps, now)

        for household in households:
            contractor = results.get(household["cbfbm"])
            if contractor is None:
                issues.append({
                    "row": household["rowIndex"],
                    "message": f"承包方不存在：{household['cbfbm']}",
                })
                skipped += 1
                continue
            updated_households += 1
            self._update_contractor(db, batch, contractor, household, issuer_data, maps, now)

            if mode == MODE_CONTRACTOR_ONLY:
                continue
            if mode == MODE_REPLACE:
                old_dkbms = set(
                    db.scalars(
                        select(SurveyCbdkxxResult.dkbm).where(
                            SurveyCbdkxxResult.tenant_code == batch.tenant_code,
                            SurveyCbdkxxResult.cbfbm == contractor.cbfbm,
                        )
                    ).all()
                )
                db.execute(delete(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.tenant_code == batch.tenant_code,
                    SurveyCbfJtcyResult.contractor_uid == contractor.contractor_uid,
                ))
                db.execute(delete(SurveyCbfJtcyBase).where(
                    SurveyCbfJtcyBase.tenant_code == batch.tenant_code,
                    SurveyCbfJtcyBase.batch_id == batch.id,
                    SurveyCbfJtcyBase.contractor_uid == contractor.contractor_uid,
                ))
                db.execute(delete(SurveyCbdkxxResult).where(
                    SurveyCbdkxxResult.tenant_code == batch.tenant_code,
                    SurveyCbdkxxResult.cbfbm == contractor.cbfbm,
                ))
                db.execute(delete(SurveyCbdkxxBase).where(
                    SurveyCbdkxxBase.tenant_code == batch.tenant_code,
                    SurveyCbdkxxBase.batch_id == batch.id,
                    SurveyCbdkxxBase.cbfbm == contractor.cbfbm,
                ))
                for dkbm in old_dkbms:
                    still_used = db.scalar(
                        select(func.count(SurveyCbdkxxResult.id)).where(
                            SurveyCbdkxxResult.tenant_code == batch.tenant_code,
                            SurveyCbdkxxResult.dkbm == dkbm,
                        )
                    ) or 0
                    if still_used:
                        continue
                    db.execute(delete(SurveyDkResult).where(
                        SurveyDkResult.tenant_code == batch.tenant_code,
                        SurveyDkResult.dkbm == dkbm,
                    ))
                    db.execute(delete(SurveyDkBase).where(
                        SurveyDkBase.tenant_code == batch.tenant_code,
                        SurveyDkBase.batch_id == batch.id,
                        SurveyDkBase.dkbm == dkbm,
                    ))

            for member in household["members"]:
                self._upsert_member(db, batch, contractor, member, maps, now)
                updated_members += 1
            for parcel in household["parcels"]:
                self._upsert_parcel(
                    db, batch, contractor, parcel, maps, now, replace=mode == MODE_REPLACE
                )
                updated_parcels += 1
            contractor.cbfcysl = len(household["members"]) or contractor.cbfcysl

        return {
            "mode": mode,
            "total": len(households),
            "updatedContractors": updated_households,
            "updatedMembers": updated_members,
            "updatedParcels": updated_parcels,
            "skipped": skipped,
            "error": len(issues),
            "issues": issues,
        }

    # ── 资源 upsert ─────────────────────────────────────────────────────────

    def _upsert_issuer(
        self, db: Session, batch: SurveyBatch, data: dict, maps: dict, now: datetime
    ) -> None:
        fbfbm = _safe_code(data.get("fbfbm"), 14)
        if not fbfbm:
            return
        issuer = db.scalars(
            select(SurveyFbfResult)
            .where(
                SurveyFbfResult.tenant_code == batch.tenant_code,
                SurveyFbfResult.fbfbm == fbfbm,
            )
            .execution_options(skip_tenant_scope=True)
        ).first()
        if issuer is None:
            return
        issuer.fbfmc = data.get("fbfmc") or issuer.fbfmc
        issuer.fbffzrxm = data.get("fbffzrxm") or issuer.fbffzrxm
        issuer.fzrzjlx = self._code(maps, "id_type", data.get("fzrzjlx", ""), issuer.fzrzjlx)
        issuer.fzrzjhm = data.get("fzrzjhm") or issuer.fzrzjhm
        issuer.lxdh = data.get("lxdh") or issuer.lxdh
        issuer.fbfdz = data.get("fbfdz") or issuer.fbfdz
        issuer.yzbm = data.get("yzbm") or issuer.yzbm
        issuer.fbfdcy = data.get("fbfdcy") or issuer.fbfdcy
        if data.get("fbfdcrq"):
            issuer.fbfdcrq = datetime.fromisoformat(data["fbfdcrq"])

    def _update_contractor(
        self,
        db: Session,
        batch: SurveyBatch,
        contractor: SurveyCbfResult,
        household: dict,
        issuer_data: dict,
        maps: dict,
        now: datetime,
    ) -> None:
        head = next(
            (
                m for m in household["members"]
                if self._relation_label(maps, m["relation"]) in {"户主", "本人"}
            ),
            None,
        )
        contractor.cbfmc = household["cbfmc"] or contractor.cbfmc
        contractor.cbflx = self._code(maps, "contractor_type", household["cbflx"], contractor.cbflx or "1")
        contractor.cbfdz = household["cbfdz"] or contractor.cbfdz
        contractor.lxdh = household["lxdh"] or contractor.lxdh
        if head:
            contractor.cbfzjlx = self._code(maps, "id_type", head["idType"], contractor.cbfzjlx or "1")
            contractor.cbfzjhm = head["idNo"] or contractor.cbfzjhm
        contractor.cbfcysl = len(household["members"]) or contractor.cbfcysl
        if issuer_data.get("fbfdcy"):
            contractor.cbfdcy = issuer_data["fbfdcy"]
        if issuer_data.get("fbfdcrq"):
            contractor.cbfdcrq = datetime.fromisoformat(issuer_data["fbfdcrq"])

    def _upsert_member(
        self,
        db: Session,
        batch: SurveyBatch,
        contractor: SurveyCbfResult,
        member: dict,
        maps: dict,
        now: datetime,
    ) -> None:
        id_no = member["idNo"].strip()
        existing = db.scalars(
            select(SurveyCbfJtcyResult)
            .where(
                SurveyCbfJtcyResult.tenant_code == batch.tenant_code,
                SurveyCbfJtcyResult.contractor_uid == contractor.contractor_uid,
                SurveyCbfJtcyResult.cyzjhm == id_no,
            )
            .execution_options(skip_tenant_scope=True)
        ).first() if id_no else None
        if existing is None:
            member_uid = str(uuid5(NAMESPACE_URL, f"import:{batch.id}:{contractor.cbfbm}:{id_no or member['name']}"))
            existing = SurveyCbfJtcyResult(
                tenant_code=batch.tenant_code,
                region_code=contractor.region_code or batch.region_code,
                contractor_uid=contractor.contractor_uid,
                member_uid=member_uid,
                cbfbm=contractor.cbfbm,
                cyxm=member["name"] or "",
                cyzjlx="1",
                cyzjhm=id_no,
                cyxb="1",
                yhzgx="",
                initialized_at=now,
            )
            db.add(existing)
        existing.cbfbm = contractor.cbfbm
        existing.cyxm = member["name"] or existing.cyxm
        existing.cyzjlx = self._code(maps, "id_type", member["idType"], existing.cyzjlx or "1")
        existing.cyzjhm = id_no or existing.cyzjhm
        existing.cyxb = GENDER_CODES.get(member["gender"], existing.cyxb or "1")
        existing.yhzgx = self._code(maps, "relation", member["relation"], existing.yhzgx or "")
        existing.cybzsm = member["note"] or existing.cybzsm
        existing.sfgyr = "1"

    def _upsert_parcel(
        self,
        db: Session,
        batch: SurveyBatch,
        contractor: SurveyCbfResult,
        row: dict,
        maps: dict,
        now: datetime,
        *,
        replace: bool,
    ) -> str:
        dkbm = row["dkbm"]
        parcel = db.scalars(
            select(SurveyDkResult)
            .where(
                SurveyDkResult.tenant_code == batch.tenant_code,
                SurveyDkResult.dkbm == dkbm,
            )
            .execution_options(skip_tenant_scope=True)
        ).first()
        created = parcel is None
        if parcel is None:
            parcel = SurveyDkResult(
                tenant_code=batch.tenant_code,
                region_code=contractor.region_code or batch.region_code,
                parcel_uid=str(uuid5(NAMESPACE_URL, f"survey:dk:{dkbm}")),
                ysdm=_safe_code(contractor.cbfbm[:6] or batch.region_code[:6], 6).ljust(6, "0"),
                dkbm=dkbm,
                dkmc=row.get("dkmc") or dkbm,
                dklb="10",
                dldj="01",
                tdyt="1",
                sfjbnt="0",
                scmj=Decimal("0"),
                initialized_at=now,
            )
            db.add(parcel)
            db.flush()

        parcel.region_code = contractor.region_code or batch.region_code
        parcel.dkmc = row.get("dkmc") or parcel.dkmc
        parcel.syqxz = self._code(maps, "ownership", row.get("syqxz", ""), parcel.syqxz or "31")
        parcel.dklb = self._code(maps, "category", row.get("dklb", ""), parcel.dklb or "10")
        parcel.tdlylx = row.get("tdlylx") or parcel.tdlylx
        parcel.dldj = self._code(maps, "grade", row.get("dldj", ""), parcel.dldj or "01")
        parcel.tdyt = self._code(maps, "land_use", row.get("tdyt", ""), parcel.tdyt or "1")
        parcel.sfjbnt = row.get("sfjbnt") or parcel.sfjbnt or "0"
        parcel.scmj = row.get("scmj") or parcel.scmj or Decimal("0")
        parcel.dkdz = row.get("dkdz") or parcel.dkdz
        parcel.dkxz = row.get("dkxz") or parcel.dkxz
        parcel.dknz = row.get("dknz") or parcel.dknz
        parcel.dkbz = row.get("dkbz") or parcel.dkbz
        parcel.dkbzxx = row.get("dkbzxx") or parcel.dkbzxx
        parcel.zjrxm = row.get("zjrxm") or parcel.zjrxm

        if created:
            db.add(SurveyDkBase(
                tenant_code=batch.tenant_code,
                region_code=parcel.region_code,
                batch_id=batch.id,
                parcel_uid=parcel.parcel_uid,
                source_dkbm=dkbm,
                ysdm=parcel.ysdm,
                dkbm=dkbm,
                dkmc=parcel.dkmc,
                syqxz=parcel.syqxz,
                dklb=parcel.dklb,
                tdlylx=parcel.tdlylx,
                dldj=parcel.dldj,
                tdyt=parcel.tdyt,
                sfjbnt=parcel.sfjbnt,
                scmj=parcel.scmj,
                dkdz=parcel.dkdz,
                dkxz=parcel.dkxz,
                dknz=parcel.dknz,
                dkbz=parcel.dkbz,
                dkbzxx=parcel.dkbzxx,
                zjrxm=parcel.zjrxm,
                initialized_from_table="import_parcel",
                initialized_from_key=dkbm,
                initialized_at=now,
                snapshot_at=now,
                result_id=parcel.id,
            ))

        relation = db.scalars(
            select(SurveyCbdkxxResult)
            .where(
                SurveyCbdkxxResult.tenant_code == batch.tenant_code,
                SurveyCbdkxxResult.dkbm == dkbm,
                SurveyCbdkxxResult.cbfbm == contractor.cbfbm,
            )
            .execution_options(skip_tenant_scope=True)
        ).first()
        if relation is None:
            relation = SurveyCbdkxxResult(
                tenant_code=batch.tenant_code,
                region_code=parcel.region_code,
                parcel_info_uid=str(uuid5(NAMESPACE_URL, f"survey:cbdkxx:{dkbm}:{contractor.cbfbm}")),
                dkbm=dkbm,
                fbfbm=(row.get("fbfbm") or contractor.cbfbm[:14]),
                cbfbm=contractor.cbfbm,
                cbjyqqdfs="110",
                htmj=row.get("htmj") or parcel.scmj or Decimal("0"),
                cbhtbm=f"HT{dkbm}"[:19],
                cbjyqzbm=f"QZ{dkbm}"[:19],
                initialized_at=now,
            )
            db.add(relation)
            db.flush()
            db.add(SurveyCbdkxxBase(
                tenant_code=batch.tenant_code,
                region_code=relation.region_code,
                batch_id=batch.id,
                parcel_info_uid=relation.parcel_info_uid,
                source_dkbm=dkbm,
                dkbm=dkbm,
                fbfbm=relation.fbfbm,
                cbfbm=contractor.cbfbm,
                cbjyqqdfs=relation.cbjyqqdfs,
                htmj=relation.htmj,
                cbhtbm=relation.cbhtbm,
                cbjyqzbm=relation.cbjyqzbm,
                initialized_from_table="import_parcel",
                initialized_from_key=f"{dkbm}:{contractor.cbfbm}",
                initialized_at=now,
                snapshot_at=now,
                result_id=relation.id,
            ))
        else:
            relation.htmj = row.get("htmj") or relation.htmj
            relation.yhtmj = row.get("yhtmj") or relation.yhtmj

        return "created" if created else "updated"

    # ── 矢量图斑 ────────────────────────────────────────────────────────────

    def _extract_shp(self, content: bytes) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp_dir = tempfile.TemporaryDirectory(prefix="parcel_shp_")
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            temp_dir.cleanup()
            raise HTTPException(status_code=400, detail="请上传包含 SHP 的 ZIP 压缩包") from exc
        try:
            for info in archive.infolist():
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in Path(name).parts:
                    continue
                archive.extract(info, temp_dir.name)
        finally:
            archive.close()
        shp_files = list(Path(temp_dir.name).rglob("*.shp"))
        if not shp_files:
            temp_dir.cleanup()
            raise HTTPException(status_code=400, detail="ZIP 中没有 .shp 文件")
        return temp_dir, shp_files[0]

    @staticmethod
    def _dkbm_from_props(props: dict) -> str:
        for key in ("DKBM", "dkbm", "地块编码", "地块编号", "DKBH", "dkbh"):
            value = props.get(key)
            if value:
                return _safe_code(value, 19)
        for key, value in props.items():
            if str(key).upper() == "DKBM":
                return _safe_code(value, 19)
        return ""

    def _preview_vector(self, db: Session, batch: SurveyBatch, content: bytes) -> dict:
        temp_dir, shp_path = self._extract_shp(content)
        issues: list[dict] = []
        samples: list[dict] = []
        total = matched = 0
        try:
            from app.services.data_import.gb_package import (
                _open_shp,
                make_geometry_transformer,
            )

            with _open_shp(shp_path) as source:
                transformer = make_geometry_transformer(source.crs)
                for index, feature in enumerate(source, 1):
                    total += 1
                    props = dict(feature.get("properties") or {})
                    dkbm = self._dkbm_from_props(props)
                    if not dkbm:
                        issues.append({"row": index, "message": "图斑缺少地块编码字段（DKBM）"})
                        continue
                    parcel = db.scalars(
                        select(SurveyDkResult.id)
                        .where(
                            SurveyDkResult.tenant_code == batch.tenant_code,
                            SurveyDkResult.dkbm == dkbm,
                        )
                        .execution_options(skip_tenant_scope=True)
                    ).first()
                    if parcel is None:
                        issues.append({"row": index, "message": f"地块不存在：{dkbm}"})
                        continue
                    matched += 1
                    if len(samples) < 50:
                        samples.append({"row": index, "dkbm": dkbm})
        finally:
            temp_dir.cleanup()
        return {
            "importType": IMPORT_VECTOR,
            "label": IMPORT_LABELS[IMPORT_VECTOR],
            "total": total,
            "matched": matched,
            "create": 0,
            "update": matched,
            "skipped": total - matched,
            "error": len(issues),
            "issues": issues,
            "samples": samples,
        }

    def _import_vector(
        self, db: Session, batch: SurveyBatch, content: bytes, current_user: User
    ) -> dict:
        temp_dir, shp_path = self._extract_shp(content)
        target_srid = get_target_srid()
        updated = skipped = 0
        issues: list[dict] = []
        try:
            from app.services.data_import.gb_package import (
                _open_shp,
                json_safe,
                make_geometry_transformer,
                transform_geometry,
            )
            from app.services.survey import survey_service

            with _open_shp(shp_path) as source:
                transformer = make_geometry_transformer(source.crs)
                for index, feature in enumerate(source, 1):
                    props = dict(feature.get("properties") or {})
                    dkbm = self._dkbm_from_props(props)
                    if not dkbm:
                        issues.append({"row": index, "message": "图斑缺少地块编码字段（DKBM）"})
                        skipped += 1
                        continue
                    parcel = db.scalars(
                        select(SurveyDkResult)
                        .where(
                            SurveyDkResult.tenant_code == batch.tenant_code,
                            SurveyDkResult.dkbm == dkbm,
                        )
                        .execution_options(skip_tenant_scope=True)
                    ).first()
                    if parcel is None:
                        issues.append({"row": index, "message": f"地块不存在：{dkbm}"})
                        skipped += 1
                        continue
                    geometry = transform_geometry(
                        json_safe(feature.get("geometry")), transformer
                    )
                    if not geometry or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
                        issues.append({"row": index, "message": f"地块 {dkbm} 图斑不是面"})
                        skipped += 1
                        continue
                    survey_service._write_survey_dk_geometry(
                        db, "survey_dk_result", parcel.id, geometry, target_srid
                    )
                    updated += 1
        finally:
            temp_dir.cleanup()
        db.commit()
        return {
            "importType": IMPORT_VECTOR,
            "label": IMPORT_LABELS[IMPORT_VECTOR],
            "updated": updated,
            "skipped": skipped,
            "error": len(issues),
            "issues": issues,
        }


parcel_import_service = ParcelImportService()
