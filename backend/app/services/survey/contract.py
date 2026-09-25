"""延包合同（承包方调查录入 →「合同信息」页）服务。

业务要点：

- **「上册」合同不变**：导入的地块关联表（``survey_cbdkxx_result.cbhtbm``）
  保留上次承包合同的编码，本模块**不改写导入数据**；
  查看上次合同就按该编码渲染。
- **生成延包合同**：按新的调查信息新发一个合同编码（沿用原合同前 14 位地区码 +
  新的 4 位流水 + ``J``），把上次合同置为 **history**（仍可查看/打印），
  新合同为 **active**。新合同与上次合同用 ``ycbhtbm`` 串起来。
- **承包期限**：默认「起 = 上次合同到期时间」（没有上次合同则为空，由人工填），
  「止 = 起 + 年限 − 1 天」（默认 30 年 ⇒ 打印件上「承包期限」正好是 30 年，
  与 ``contract_template_service._contract_years`` 的口径一致）。
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cbht import (
    CONTRACT_SOURCE_GENERATED,
    CONTRACT_SOURCE_IMPORTED,
    CONTRACT_STATUS_ACTIVE,
    CONTRACT_STATUS_HISTORY,
    Cbht,
)
from app.models.survey import SurveyCbdkxxBase, SurveyCbdkxxResult, SurveyCbfResult
from app.models.user import User
from app.services.data_access_service import data_access_service

logger = logging.getLogger(__name__)

# 延包后的承包期默认年限（二轮延包统一再延 30 年）
EXTENSION_YEARS_DEFAULT = 30
# 合同编码尾位（J = 家庭承包，与甲方导入数据的口径一致）
CONTRACT_CODE_SUFFIX = "J"
CONTRACT_CODE_REGION_LEN = 14


class SurveyServiceContractMixin:
    # ── 查询 ──────────────────────────────────────────

    def list_survey_contracts(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> dict:
        """该承包方在本批次下的全部合同（现行 + 历史 + 上次承包合同）。"""
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
        return self._build_contract_catalog(db, batch_id, result)

    def get_survey_contract_detail(
        self, db: Session, batch_id: int, contractor_uid: str, cbhtbm: str, current_user: User,
    ) -> dict:
        """指定合同的明细 + 渲染好的 HTML（历史合同也能渲染，只读）。"""
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")

        code = (cbhtbm or "").strip()
        row = db.get(Cbht, code) if code else None
        is_generated = bool(row and row.contract_source == CONTRACT_SOURCE_GENERATED)
        # 惰性导入：contract_template_service 反向依赖 app.services.survey 包，
        # 模块级导入会形成循环导入（启动即失败）。
        from app.services.contract_template_service import contract_template_service

        rendered = contract_template_service.render_survey_contract(
            db, cbhtbm=code, batch_id=batch_id, cbfbm=result.cbfbm,
            parcels_by_contractor=is_generated,
        )
        catalog = self._build_contract_catalog(db, batch_id, result)
        entry = next((item for item in catalog["contracts"] if item["cbhtbm"] == code), None)
        if entry is None:
            entry = self._serialize_contract_row(row, code=code, db=db, batch_id=batch_id, result=result)
        return {**entry, "renderedHtml": rendered, "cbfbm": result.cbfbm, "defaultTermStart": catalog["defaultTermStart"]}

    # ── 生成 ──────────────────────────────────────────

    def generate_extension_contract(
        self, db: Session, batch_id: int, contractor_uid: str, payload: dict, current_user: User,
    ) -> dict:
        """按当前调查信息生成延包合同，并把上次合同置为历史状态。"""
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调查批次已结束，不能生成合同")
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="survey result out of scope")
        if result.result_status == "cancelled":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="承包方已注销，不能生成合同")

        current_summary = self._contract_relation_summary(db, result.cbfbm)
        original_code, original_row = self._resolve_original_contract(db, result.cbfbm, batch_id)
        generated_rows = self._generated_contracts(db, batch_id, contractor_uid)
        previous_row = next((row for row in generated_rows if row.contract_status == CONTRACT_STATUS_ACTIVE), None)
        if previous_row is None and original_row is not None:
            previous_row = original_row

        term_start = self._parse_datetime(payload.get("cbqxq"))
        term_end = self._parse_datetime(payload.get("cbqxz"))
        if term_start and term_end is None:
            term_end = self._contract_term_end(term_start, self._contract_term_years(payload))
        if term_start and term_end and term_end < term_start:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="承包期限终止日期不能早于起始日期")

        # 1) 上次合同置为历史（导入的合同若库里还没有行，就地落一条历史记录，保证可查看）
        for row in generated_rows:
            if row.contract_status == CONTRACT_STATUS_ACTIVE:
                row.contract_status = CONTRACT_STATUS_HISTORY
        original_history = self._ensure_original_contract_row(
            db, result=result, batch_id=batch_id, code=original_code, row=original_row,
        )

        # 2) 新发延包合同
        prefix = self._contract_code_prefix(result, original_code)
        new_code = self._next_contract_code(db, prefix)
        htzmj = current_summary["htzmj"]
        imported_summary = self._contract_relation_summary(db, result.cbfbm, batch_id, base=True)
        contract = Cbht(
            cbhtbm=new_code,
            ycbhtbm=original_code or None,
            fbfbm=self._contract_issuer_code(db, result, original_code) or None,
            cbfbm=result.cbfbm,
            cbfs=payload.get("cbfs") or self._contract_default_cbfs(db, result.cbfbm),
            cbqxq=term_start,
            cbqxz=term_end,
            qdsj=self._parse_datetime(payload.get("qdsj")) or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
            htzmj=Decimal(f"{htzmj:.2f}") if htzmj is not None else None,
            cbdkzs=current_summary["cbdkzs"],
            htzmjm=Decimal(f"{htzmj / 666.67:.2f}") if htzmj else None,
            yhtzmj=Decimal(f"{imported_summary['htzmj']:.2f}") if imported_summary["htzmj"] else None,
            yhtzmjm=Decimal(f"{imported_summary['htzmj'] / 666.67:.2f}") if imported_summary["htzmj"] else None,
            contract_status=CONTRACT_STATUS_ACTIVE,
            contract_source=CONTRACT_SOURCE_GENERATED,
            survey_batch_id=batch_id,
            contractor_uid=contractor_uid,
            generated_at=datetime.now(timezone.utc),
            generated_by=current_user.real_name,
            tenant_code=result.tenant_code,
            region_code=result.region_code,
        )
        db.add(contract)
        db.commit()
        db.refresh(contract)

        logger.info(
            "survey.extension_contract generated batch_id=%s contractor_uid=%s cbhtbm=%s previous=%s",
            batch_id, contractor_uid, new_code, previous_row.cbhtbm if previous_row else None,
        )
        catalog = self._build_contract_catalog(db, batch_id, result)
        entry = next((item for item in catalog["contracts"] if item["cbhtbm"] == new_code), None)
        if entry is None:  # 理论上不会发生
            entry = self._serialize_contract_row(contract, code=new_code, db=db, batch_id=batch_id, result=result)
            entry["isCurrent"] = True
        return {**entry, "originalCode": original_code, "originalHistoryCode": getattr(original_history, "cbhtbm", None)}

    # ── 内部：合同清单 ────────────────────────────────

    def _build_contract_catalog(self, db: Session, batch_id: int, result: SurveyCbfResult) -> dict:
        """现行合同在最前，其余历史合同按生成时间倒序。"""
        imported_rows = db.scalars(
            select(Cbht).where(
                Cbht.cbfbm == result.cbfbm,
                Cbht.contract_source == CONTRACT_SOURCE_IMPORTED,
            )
        ).all()
        generated_rows = self._generated_contracts(db, batch_id, result.contractor_uid)

        rows: list[Cbht] = []
        seen: set[str] = set()
        for row in generated_rows + list(imported_rows):
            if row.cbhtbm in seen:
                continue
            seen.add(row.cbhtbm)
            rows.append(row)

        entries = [
            self._serialize_contract_row(row, code=row.cbhtbm, db=db, batch_id=batch_id, result=result)
            for row in rows
        ]

        original_code = self._resolve_original_contract_code(db, result.cbfbm)
        if original_code and original_code not in seen:
            # 上次承包合同尚未落地为库内记录：补一条虚拟条目（面积取导入快照），页面上照样能看
            entries.append(
                self._serialize_contract_row(None, code=original_code, db=db, batch_id=batch_id, result=result)
            )

        entries.sort(key=lambda item: (not item["isCurrent"], item["isOriginal"], item["cbhtbm"]))
        current = next((item for item in entries if item["isCurrent"]), None)
        previous = current or self._serialize_prev_term_source(db, result, batch_id)
        return {
            "currentCode": current["cbhtbm"] if current else None,
            "originalCode": original_code,
            "contracts": entries,
            # 生成合同的「承包期限起」默认值：上次合同的到期时间，没有则为空
            "defaultTermStart": previous["cbqxz"] if previous else None,
            "defaultYears": EXTENSION_YEARS_DEFAULT,
        }

    def _serialize_prev_term_source(self, db: Session, result: SurveyCbfResult, batch_id: int) -> dict | None:
        """没有现行合同时，用上次承包合同的到期时间当默认起算日。"""
        original_code, original_row = self._resolve_original_contract(db, result.cbfbm, batch_id)
        if original_row is not None:
            return self._serialize_contract_row(
                original_row, code=original_row.cbhtbm, db=db, batch_id=batch_id, result=result,
            )
        if original_code:
            return {"cbhtbm": original_code, "cbqxz": None}
        return None

    def _serialize_contract_row(
        self, row: Cbht | None, *, code: str, db: Session, batch_id: int, result: SurveyCbfResult,
    ) -> dict:
        generated = bool(row and row.contract_source == CONTRACT_SOURCE_GENERATED)
        status_value = (row.contract_status if row else CONTRACT_STATUS_ACTIVE) or CONTRACT_STATUS_ACTIVE
        source_value = (row.contract_source if row else CONTRACT_SOURCE_IMPORTED) or CONTRACT_SOURCE_IMPORTED
        # 虚拟条目（上次承包合同还没落地为库内记录）用导入快照兜底面积与地块数
        summary = self._contract_relation_summary(db, result.cbfbm, batch_id, base=True) if row is None else {}
        return {
            "cbhtbm": code,
            "ycbhtbm": row.ycbhtbm if row else None,
            "contractStatus": status_value,
            "contractStatusText": "现行" if status_value == CONTRACT_STATUS_ACTIVE else "历史",
            "contractSource": source_value,
            "contractSourceText": "延包合同" if generated else "上次承包合同",
            "isCurrent": status_value == CONTRACT_STATUS_ACTIVE and generated,
            "isOriginal": source_value == CONTRACT_SOURCE_IMPORTED,
            "isVirtual": row is None,
            "cbfs": row.cbfs if row else None,
            "cbqxq": self._contract_iso(row.cbqxq) if row else None,
            "cbqxz": self._contract_iso(row.cbqxz) if row else None,
            "qdsj": self._contract_iso(row.qdsj) if row else None,
            "cbdkzs": row.cbdkzs if row else summary.get("cbdkzs"),
            "htzmj": float(row.htzmj) if row and row.htzmj is not None else summary.get("htzmj"),
            "htzmjm": float(row.htzmjm) if row and row.htzmjm is not None else summary.get("htzmjm"),
            "yhtzmj": float(row.yhtzmj) if row and row.yhtzmj is not None else None,
            "generatedAt": self._contract_iso_datetime(row.generated_at) if row and row.generated_at else None,
            "generatedBy": row.generated_by if row else None,
        }

    # ── 内部：数据解析 ────────────────────────────────

    def _generated_contracts(self, db: Session, batch_id: int, contractor_uid: str) -> list[Cbht]:
        rows = db.scalars(
            select(Cbht)
            .where(
                Cbht.survey_batch_id == batch_id,
                Cbht.contractor_uid == contractor_uid,
                Cbht.contract_source == CONTRACT_SOURCE_GENERATED,
            )
        ).all()
        # 按生成时间倒序；generated_at 带时区，统一转字符串排序避免 aware/naive 混比
        return sorted(
            rows,
            key=lambda item: (
                item.generated_at.isoformat() if item.generated_at else "",
                item.cbhtbm,
            ),
            reverse=True,
        )

    def _resolve_original_contract_code(self, db: Session, cbfbm: str) -> str | None:
        """上次承包合同编码：取该承包方地块关联里的合同编码（导入值，未被本模块改写）。"""
        code = db.scalar(
            select(SurveyCbdkxxResult.cbhtbm)
            .where(
                SurveyCbdkxxResult.cbfbm == cbfbm,
                SurveyCbdkxxResult.result_status != "removed",
            )
            .limit(1)
        )
        if not code:
            code = db.scalar(select(SurveyCbdkxxResult.cbhtbm).where(SurveyCbdkxxResult.cbfbm == cbfbm).limit(1))
        if not code:
            code = db.scalar(
                select(Cbht.cbhtbm)
                .where(Cbht.cbfbm == cbfbm, Cbht.contract_source == CONTRACT_SOURCE_IMPORTED)
                .limit(1)
            )
        return (code or "").strip() or None

    def _resolve_original_contract(self, db: Session, cbfbm: str, batch_id: int) -> tuple[str | None, Cbht | None]:
        code = self._resolve_original_contract_code(db, cbfbm)
        row = db.get(Cbht, code) if code else None
        if row is not None and row.cbfbm and row.cbfbm != cbfbm:
            row = None
        return code, row

    def _ensure_original_contract_row(
        self, db: Session, *, result: SurveyCbfResult, batch_id: int, code: str | None, row: Cbht | None,
    ) -> Cbht | None:
        """把上次承包合同落成一条历史记录（库里已有则只改状态）。

        导入数据里 cbht 常常是空的（合同表未导入），但「历史合同仍要能查看」，
        所以这里用导入快照（``survey_cbdkxx_base``）补面积与地块数，期限留空。
        """
        if not code:
            return None
        if row is None:
            summary = self._contract_relation_summary(db, result.cbfbm, batch_id, base=True)
            row = Cbht(
                cbhtbm=code,
                fbfbm=self._contract_issuer_code(db, result, None) or None,
                cbfbm=result.cbfbm,
                cbfs=self._resolve_contract_way(db, result.cbfbm),
                htzmj=Decimal(f"{summary['htzmj']:.2f}") if summary["htzmj"] else None,
                cbdkzs=summary["cbdkzs"],
                htzmjm=Decimal(f"{summary['htzmj'] / 666.67:.2f}") if summary["htzmj"] else None,
                contract_status=CONTRACT_STATUS_HISTORY,
                contract_source=CONTRACT_SOURCE_IMPORTED,
                survey_batch_id=batch_id,
                contractor_uid=result.contractor_uid,
                tenant_code=result.tenant_code,
                region_code=result.region_code,
            )
            db.add(row)
            return row
        row.contract_status = CONTRACT_STATUS_HISTORY
        return row

    def _contract_relation_summary(self, db: Session, cbfbm: str, batch_id: int | None = None, *, base: bool = False) -> dict:
        """当前有效关联（base=True 时取导入快照）的地块数与合同面积。"""
        model = SurveyCbdkxxBase if base else SurveyCbdkxxResult
        filters = [model.cbfbm == cbfbm]
        if base:
            if batch_id is not None:
                filters.append(model.batch_id == batch_id)
        else:
            filters.append(model.result_status != "removed")
        rows = db.scalars(select(model).where(*filters)).all()
        area = sum(float(item.htmj or 0) for item in rows)
        return {
            "cbdkzs": len(rows),
            "htzmj": area if rows else None,
            "htzmjm": (area / 666.67) if rows and area else None,
        }

    def _resolve_contract_way(self, db: Session, cbfbm: str) -> str | None:
        value = db.scalar(
            select(SurveyCbdkxxResult.cbjyqqdfs)
            .where(
                SurveyCbdkxxResult.cbfbm == cbfbm,
                SurveyCbdkxxResult.result_status != "removed",
            )
            .limit(1)
        )
        return (value or "").strip() or None

    def _contract_default_cbfs(self, db: Session, cbfbm: str) -> str:
        """延包合同的承包方式默认值。

        地块关联里的 ``cbjyqqdfs`` 是「承包经营权取得方式」码值，与合同表的
        ``cbfs``（承包方式）**不是同一套编码**（导入数据里普遍是 ``110``）。
        取到合同表口径内的码值就直接用，否则按二轮延包的实际情况默认「家庭承包」。
        """
        value = self._resolve_contract_way(db, cbfbm)
        return value if value in {"001", "002", "003", "004", "005"} else "001"

    def _contract_issuer_code(self, db: Session, result: SurveyCbfResult, original_code: str | None) -> str | None:
        if original_code:
            row = db.get(Cbht, original_code)
            if row is not None and row.fbfbm:
                return row.fbfbm
        value = db.scalar(
            select(SurveyCbdkxxResult.fbfbm)
            .where(
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status != "removed",
            )
            .limit(1)
        )
        if value:
            return (value or "").strip() or None
        value = db.scalar(select(SurveyCbdkxxBase.fbfbm).where(SurveyCbdkxxBase.cbfbm == result.cbfbm).limit(1))
        return (value or "").strip() or None

    # ── 内部：编码与日期 ──────────────────────────────

    def _contract_code_prefix(self, result: SurveyCbfResult, original_code: str | None) -> str:
        candidates = [
            (original_code or "")[:CONTRACT_CODE_REGION_LEN],
            (result.group_region_code or "")[:CONTRACT_CODE_REGION_LEN],
            (result.cbfbm or "")[:CONTRACT_CODE_REGION_LEN],
            (result.region_code or "")[:CONTRACT_CODE_REGION_LEN],
        ]
        for candidate in candidates:
            if len(candidate) == CONTRACT_CODE_REGION_LEN and candidate.isdigit():
                return candidate
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法确定合同编码地区码，请先维护地块或承包方编码")

    def _next_contract_code(self, db: Session, prefix: str) -> str:
        """沿用地区码，取全库最大流水 +1（cbhtbm 是主键，必须全局唯一）。"""
        pattern = f"{prefix}%"
        codes: set[str] = set()
        for column in (Cbht.cbhtbm, SurveyCbdkxxResult.cbhtbm, SurveyCbdkxxBase.cbhtbm):
            values = db.scalars(
                select(column).where(column.like(pattern)).execution_options(skip_tenant_scope=True)
            ).all()
            codes.update(str(value or "").strip() for value in values)
        sequence = 0
        for code in codes:
            if len(code) < CONTRACT_CODE_REGION_LEN + 4:
                continue
            segment = code[CONTRACT_CODE_REGION_LEN:CONTRACT_CODE_REGION_LEN + 4]
            if segment.isdigit():
                sequence = max(sequence, int(segment))
        candidate = f"{prefix}{sequence + 1:04d}{CONTRACT_CODE_SUFFIX}"
        while candidate in codes:
            sequence += 1
            candidate = f"{prefix}{sequence + 1:04d}{CONTRACT_CODE_SUFFIX}"
        return candidate

    @staticmethod
    def _contract_term_years(payload: dict) -> int:
        try:
            years = int(payload.get("years") or EXTENSION_YEARS_DEFAULT)
        except (TypeError, ValueError):
            years = EXTENSION_YEARS_DEFAULT
        return years if years > 0 else EXTENSION_YEARS_DEFAULT

    @staticmethod
    def _contract_term_end(start: datetime, years: int) -> datetime:
        """止期 = 起期 + years 年 − 1 天（使打印件上的「承包期限」正好等于 years）。"""
        try:
            end = start.replace(year=start.year + years)
        except ValueError:  # 2 月 29 日
            end = start.replace(year=start.year + years, day=28)
        return end - timedelta(days=1)

    @staticmethod
    def _contract_iso(value: datetime | None) -> str | None:
        return value.date().isoformat() if value else None

    @staticmethod
    def _contract_iso_datetime(value: datetime | None) -> str | None:
        return value.isoformat() if value else None
