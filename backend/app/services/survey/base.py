import logging
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyBatch,
    SurveyCbfBase,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service

logger = logging.getLogger(__name__)

class SurveyServiceBase:
    attachment_root = Path(__file__).resolve().parents[3] / "storage" / "survey_attachments"
    authorization_root = Path(__file__).resolve().parents[3] / "storage" / "survey_authorizations"
    operation_change_types = {
        "change_head",
        "member_maintain",
        "deregister",
        "add_parcel",
        "split_parcel",
        "rollback_split_parcel",
        "swap_parcels",
        "rollback_swap_parcels",
        "remove_parcel",
        "rollback_remove_parcel",
        "split_household",
        "merge_household",
    }
    terminal_operation_types = {"deregister", "merge_household", "split_household"}
    form_diff_entity_types = {"contractor", "issuer", "member"}
    parcel_diff_entity_types = {"parcel", "parcel_relation"}
    tag_names = {
        "whole_family_urbanized": "鍏ㄥ杩涘煄钀芥埛",
        "household_extinct": "鏁存埛娑堜骸",
        "five_guarantees": "浜斾繚鎴?",
        "little_or_no_land": "鏃犲湴灏戝湴",
    }
    def _ensure_batch(self, db: Session, batch_id: int) -> SurveyBatch:
        batch = db.get(SurveyBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request failed")
        return batch

    @staticmethod

    @staticmethod
    def _short_region_name(region_name: str | None, region_code: str) -> str:
        if not region_name:
            return region_code
        parts = [part.strip() for part in region_name.replace("、", "/").split("/") if part.strip()]
        return parts[-1] if parts else region_name.strip()

    def _get_result(self, db: Session, batch_id: int, contractor_uid: str) -> SurveyCbfResult:
        batch = self._ensure_batch(db, batch_id)
        result = db.scalars(
            select(SurveyCbfResult)
            .where(SurveyCbfResult.tenant_code == batch.tenant_code, SurveyCbfResult.contractor_uid == contractor_uid)
            .order_by(SurveyCbfResult.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).first()
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request failed")
        result_scope_code = result.group_region_code or result.region_code
        if batch.survey_type == "household_survey" and batch.region_code and not (result_scope_code or "").startswith(batch.region_code):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request failed")
        return result

    def _ensure_editable_batch_and_result(self, db: Session, result: SurveyCbfResult) -> None:
        base = db.scalar(select(SurveyCbfBase).where(SurveyCbfBase.contractor_uid == result.contractor_uid).order_by(SurveyCbfBase.id.desc())) if result else None
        batch = self._ensure_batch(db, base.batch_id) if base else None
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幍瑙勵偧瀹歌尙绮ㄩ弶鐕傜礉娑撳秷鍏樼紒褏鐢荤紓鏍帆")
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幋鎰亯瀹歌尙鈥樼拋銈忕礉娑撳秷鍏樼紒褏鐢荤紓鏍帆")

    def _validate_confirmable(self, db: Session, result: SurveyCbfResult) -> None:
        members = db.scalars(
            select(SurveyCbfJtcyResult)
            .where(
                SurveyCbfJtcyResult.contractor_uid == result.contractor_uid,
            )
            .order_by(SurveyCbfJtcyResult.id.asc())
        ).all()
        errors: list[str] = []
        if result.cbflx == "1":
            if not members:
                errors.append("validation error")
            household_heads = [member for member in members if member.is_household_head or member.yhzgx == "01"]
            if len(household_heads) != 1:
                errors.append("validation error")

        seen_id_nos: set[str] = set()
        for member in members:
            id_no = (member.cyzjhm or "").strip()
            if id_no:
                if id_no in seen_id_nos:
                    errors.append(f"duplicate member id number: {id_no}")
                    break
                seen_id_nos.add(id_no)

        if result.is_changed or result.change_type != "none":
            if not self._has_text(result.change_reason):
                errors.append("閹靛灝瀵橀弬鐟扮摠閸︺劌褰夐崠鏍ㄦ韫囧懘銆忔繅顐㈠晸閸欐ê瀵查崢鐔锋礈")
            if not self._has_text(result.policy_basis):
                errors.append("閹靛灝瀵橀弬鐟扮摠閸︺劌褰夐崠鏍ㄦ韫囧懘銆忔繅顐㈠晸閺€璺ㄧ摜娓氭繃宓?")

        for member in members:
            has_member_survey_change = member.is_changed or member.member_result_status != "normal" or any(
                [
                    member.is_urban_settled,
                    member.is_married_out_woman,
                    member.is_deceased,
                    member.is_five_guarantees,
                    self._has_text(member.rights_disposition),
                ]
            )
            if has_member_survey_change and not self._has_text(member.change_reason):
                errors.append("validation error")

        if errors:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request failed")

    async def _store_upload(self, directory: Path, upload_file: UploadFile) -> tuple[Path, int]:
        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="娑撳﹣绱堕弬鍥︽娑撹櫣鈹?")
        directory.mkdir(parents=True, exist_ok=True)
        suffix = Path(upload_file.filename or "").suffix
        storage_path = directory / f"{uuid4().hex}{suffix}"
        with storage_path.open("wb") as target:
            target.write(content)
        return storage_path, len(content)

    def _tenant_filters(self, model, current_user: User) -> list:
        tenant_code = data_access_service.get_tenant_code(current_user)
        if tenant_code and hasattr(model, "tenant_code"):
            return [model.tenant_code == tenant_code]
        tenant_filter = data_access_service.build_tenant_filter(model, current_user)
        return [] if tenant_filter is None else [tenant_filter]

    @staticmethod

    def _build_task_scope_filters(self, current_user: User, region_code: str | None = None) -> list:
        filters = self._tenant_filters(SurveyCbfBase, current_user)
        filters.extend(data_access_service.build_code_scope_filters(SurveyCbfBase.region_code, current_user))
        if region_code:
            filters.append(SurveyCbfBase.region_code.like(f"{region_code}%"))
        return filters

    @staticmethod
    def _append_group_region_filter(filters: list, column, region_code: str | None) -> None:
        if not region_code:
            return
        if len(region_code) >= 14:
            filters.append(column == region_code)
        else:
            filters.append(column.like(f"{region_code}%"))

    @staticmethod

    @staticmethod
    def _log_sql(db: Session, label: str, stmt) -> None:
        try:
            compiled = stmt.compile(bind=db.get_bind(), compile_kwargs={"literal_binds": True})
            logger.info("SQL[%s]: %s", label, compiled)
        except Exception:
            logger.exception("Failed to compile SQL[%s]", label)
            logger.info("SQL[%s]: %s", label, stmt)

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.combine(datetime.strptime(value, fmt).date(), datetime.min.time())
            except ValueError:
                pass
        return datetime.combine(date.fromisoformat(value), datetime.min.time())

    # 閳光偓閳光偓 鐠嬪啯鐓￠幙宥勭稊 閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓

    def _has_text(self, value: str | None) -> bool:
        return bool(str(value or "").strip())

    def _next_no(self, db: Session, prefix: str, id_column) -> str:
        next_id = (db.scalar(select(func.max(id_column))) or 0) + 1
        return f"{prefix}{datetime.now():%Y%m%d}{next_id:04d}"

    def _get_task(self, db: Session, batch_id: int, contractor_uid: str) -> SurveyCbfBase | None:
        return db.scalars(
            select(SurveyCbfBase).where(
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.contractor_uid == contractor_uid,
            )
        ).first()
