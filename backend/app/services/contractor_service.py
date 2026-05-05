from datetime import date, datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.region import Region
from app.models.survey import SurveyBatch, SurveyCbfBase, SurveyCbfJtcyBase, SurveyCbfJtcyResult, SurveyCbfResult
from app.models.user import User
from app.repositories.contractor_repository import contractor_repository
from app.services.data_access_service import data_access_service


class ContractorService:
    def list_contractors(
        self,
        db: Session,
        page: int,
        page_size: int,
        current_user: User,
        keyword: str | None = None,
        type_code: str | None = None,
        name: str | None = None,
        member_name: str | None = None,
        id_no: str | None = None,
        address: str | None = None,
        region_code: str | None = None,
    ) -> dict:
        if region_code:
            data_access_service.ensure_region_in_scope(current_user, region_code, detail="区域不在当前数据权限范围内")
        contractors, total = contractor_repository.list_contractors(
            db,
            page=page,
            page_size=page_size,
            extra_filters=data_access_service.build_code_scope_filters(SurveyCbfResult.cbfbm, current_user),
            keyword=keyword.strip() if keyword else None,
            type_code=type_code or None,
            name=name.strip() if name else None,
            member_name=member_name.strip() if member_name else None,
            id_no=id_no.strip() if id_no else None,
            address=address.strip() if address else None,
            region_code=region_code.strip() if region_code else None,
        )
        return {
            "items": [self._serialize_summary(item) for item in contractors],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def get_contractor(self, db: Session, code: str, current_user: User) -> dict:
        contractor = contractor_repository.get_contractor(db, code)
        if contractor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="承包方调查成果不存在")
        data_access_service.ensure_code_in_scope(current_user, contractor.cbfbm, detail="承包方不在当前数据权限范围内")
        return self._serialize_detail(db, contractor)

    def create_contractor(self, db: Session, payload: dict, current_user: User) -> dict:
        data_access_service.ensure_code_in_scope(current_user, payload["code"], detail="承包方不在当前数据权限范围内")
        group_region_code, group_region_name = self._resolve_group_region(db, payload, current_user)
        batch = self._ensure_edit_batch(db, payload, current_user)
        if contractor_repository.get_contractor_in_batch(db, batch.id, payload["code"]) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前调查批次内承包方代码已存在")

        now = datetime.now(timezone.utc)
        contractor_uid = str(uuid5(NAMESPACE_URL, f"survey:{batch.id}:cbf:{payload['code']}"))
        base = SurveyCbfBase(
            batch_id=batch.id,
            contractor_uid=contractor_uid,
            source_cbfbm=payload["code"],
            initialized_from_key=payload["code"],
            initialized_at=now,
            snapshot_at=now,
        )
        self._apply_contractor_payload(base, payload, current_user, group_region_code, group_region_name)
        db.add(base)
        db.flush()

        result = SurveyCbfResult(
            batch_id=batch.id,
            contractor_uid=contractor_uid,
            base_id=base.id,
            initialized_from_base_id=base.id,
            initialized_at=now,
            survey_status="surveyed",
            result_status="normal",
        )
        self._copy_base_to_result(result, base)
        db.add(result)
        db.flush()
        self._replace_family_members(db, result, payload.get("familyMembers", []), now, sync_base=True)
        db.commit()
        db.refresh(result)
        return self._serialize_detail(db, result)

    def update_contractor(self, db: Session, code: str, payload: dict, current_user: User) -> dict:
        contractor = contractor_repository.get_contractor(db, code)
        if contractor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="承包方调查成果不存在")
        data_access_service.ensure_code_in_scope(current_user, contractor.cbfbm, detail="承包方不在当前数据权限范围内")
        data_access_service.ensure_code_in_scope(current_user, payload["code"], detail="承包方不在当前数据权限范围内")
        group_region_code, group_region_name = self._resolve_group_region(db, payload, current_user)
        existed = contractor_repository.get_contractor_in_batch(db, contractor.batch_id, payload["code"])
        if payload["code"] != code and existed is not None and existed.id != contractor.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前调查批次内承包方代码已存在")

        self._apply_contractor_payload(contractor, payload, current_user, group_region_code, group_region_name)
        base = db.get(SurveyCbfBase, contractor.base_id)
        if base is not None:
            self._apply_contractor_payload(base, payload, current_user, group_region_code, group_region_name)
            base.source_cbfbm = payload["code"]
            base.snapshot_at = datetime.now(timezone.utc)
        self._replace_family_members(db, contractor, payload.get("familyMembers", []), datetime.now(timezone.utc), sync_base=True)
        db.commit()
        db.refresh(contractor)
        return self._serialize_detail(db, contractor)

    def delete_contractor(self, db: Session, code: str, current_user: User) -> None:
        contractor = contractor_repository.get_contractor(db, code)
        if contractor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="承包方调查成果不存在")
        data_access_service.ensure_code_in_scope(current_user, contractor.cbfbm, detail="承包方不在当前数据权限范围内")
        contractor_repository.delete_contractor(db, contractor)

    def _serialize_summary(self, contractor: SurveyCbfResult) -> dict:
        return {
            "code": contractor.cbfbm,
            "typeCode": contractor.cbflx,
            "name": contractor.cbfmc,
            "idType": contractor.cbfzjlx,
            "idNo": contractor.cbfzjhm,
            "address": contractor.cbfdz,
            "postcode": contractor.yzbm,
            "mobile": contractor.lxdh,
            "memberCount": contractor.cbfcysl,
            "surveyDate": contractor.cbfdcrq.date().isoformat() if contractor.cbfdcrq else None,
            "surveyorName": contractor.cbfdcy or "",
            "surveyNote": contractor.cbfdcjs,
            "publicNoticeNote": contractor.gsjs,
            "publicNoticeRecorder": contractor.gsjsr,
            "publicNoticeReviewDate": contractor.gsshrq.date().isoformat() if contractor.gsshrq else None,
            "publicNoticeReviewer": contractor.gsshr,
            "groupRegionCode": contractor.group_region_code,
            "groupRegionName": contractor.group_region_name,
            "batchId": contractor.batch_id,
            "contractorUid": contractor.contractor_uid,
            "familyMembers": [],
        }

    def _serialize_detail(self, db: Session, contractor: SurveyCbfResult) -> dict:
        family_members = contractor_repository.list_family_members(db, contractor)
        summary = self._serialize_summary(contractor)
        summary["familyMembers"] = [
            {
                "name": item.cyxm,
                "gender": item.cyxb,
                "idType": item.cyzjlx,
                "idNo": item.cyzjhm,
                "relationToHead": item.yhzgx,
                "noteCode": item.cybz,
                "isCoOwner": item.sfgyr,
                "note": item.cybzsm,
            }
            for item in family_members
        ]
        return summary

    def _ensure_edit_batch(self, db: Session, payload: dict, current_user: User) -> SurveyBatch:
        batch = db.scalar(select(SurveyBatch).where(SurveyBatch.status == "active").order_by(SurveyBatch.id.desc()).limit(1))
        if batch is not None:
            return batch
        now = datetime.now(timezone.utc)
        batch = SurveyBatch(
            batch_no=self._next_no(db, "SUR", SurveyBatch.id),
            batch_name="承包方管理调查成果",
            region_code=payload.get("groupRegionCode") or payload["code"][:14],
            region_name=payload.get("groupRegionName"),
            survey_type="contractor_management",
            status="active",
            started_at=now,
            created_by=current_user.id,
            remark="由承包方管理新增承包方时自动创建",
        )
        db.add(batch)
        db.flush()
        return batch

    def _apply_contractor_payload(
        self,
        target,
        payload: dict,
        current_user: User,
        group_region_code: str | None,
        group_region_name: str | None,
    ) -> None:
        target.cbfbm = payload["code"]
        target.cbflx = payload["typeCode"]
        target.cbfmc = payload["name"]
        target.cbfzjlx = payload["idType"]
        target.cbfzjhm = payload["idNo"]
        target.cbfdz = payload["address"]
        target.yzbm = payload["postcode"]
        target.lxdh = payload.get("mobile")
        target.cbfcysl = len(payload.get("familyMembers", [])) if payload["typeCode"] == "1" else 0
        target.cbfdcrq = self._parse_datetime(payload.get("surveyDate")) or getattr(target, "cbfdcrq", None) or datetime.now()
        target.cbfdcy = payload.get("surveyorName") or current_user.real_name
        target.cbfdcjs = payload.get("surveyNote")
        target.gsjs = payload.get("publicNoticeNote")
        target.gsjsr = payload.get("publicNoticeRecorder")
        target.gsshrq = self._parse_datetime(payload.get("publicNoticeReviewDate"))
        target.gsshr = payload.get("publicNoticeReviewer")
        target.group_region_code = group_region_code
        target.group_region_name = group_region_name

    def _copy_base_to_result(self, result: SurveyCbfResult, base: SurveyCbfBase) -> None:
        result.cbfbm = base.cbfbm
        result.cbflx = base.cbflx
        result.cbfmc = base.cbfmc
        result.cbfzjlx = base.cbfzjlx
        result.cbfzjhm = base.cbfzjhm
        result.cbfdz = base.cbfdz
        result.yzbm = base.yzbm
        result.lxdh = base.lxdh
        result.cbfcysl = base.cbfcysl
        result.cbfdcrq = base.cbfdcrq
        result.cbfdcy = base.cbfdcy
        result.cbfdcjs = base.cbfdcjs
        result.gsjs = base.gsjs
        result.gsjsr = base.gsjsr
        result.gsshrq = base.gsshrq
        result.gsshr = base.gsshr
        result.group_region_code = base.group_region_code
        result.group_region_name = base.group_region_name

    def _replace_family_members(self, db: Session, contractor: SurveyCbfResult, family_members: list[dict], now: datetime, sync_base: bool) -> None:
        db.execute(
            delete(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.batch_id == contractor.batch_id,
                SurveyCbfJtcyResult.contractor_uid == contractor.contractor_uid,
            )
        )
        if sync_base:
            db.execute(
                delete(SurveyCbfJtcyBase).where(
                    SurveyCbfJtcyBase.batch_id == contractor.batch_id,
                    SurveyCbfJtcyBase.contractor_uid == contractor.contractor_uid,
                )
            )
        seen_ids: set[str] = set()
        for item in family_members:
            member_id = item["idNo"]
            if member_id in seen_ids:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="家庭成员证件号不能重复")
            seen_ids.add(member_id)
            member_uid = str(uuid5(NAMESPACE_URL, f"survey:{contractor.batch_id}:member:{contractor.cbfbm}:{member_id}"))
            base = None
            if sync_base:
                base = SurveyCbfJtcyBase(
                    batch_id=contractor.batch_id,
                    contractor_uid=contractor.contractor_uid,
                    member_uid=member_uid,
                    base_contractor_code=contractor.cbfbm,
                    base_member_id_no=member_id,
                    initialized_from_key=f"{contractor.cbfbm}:{member_id}",
                    initialized_at=now,
                    snapshot_at=now,
                )
                self._apply_member_payload(base, contractor, item)
                db.add(base)
                db.flush()
            result = SurveyCbfJtcyResult(
                batch_id=contractor.batch_id,
                contractor_uid=contractor.contractor_uid,
                member_uid=member_uid,
                base_id=base.id if base else None,
                initialized_from_base_id=base.id if base else None,
                initialized_at=now,
                survey_status="surveyed",
                member_result_status="normal",
                is_household_head=item.get("relationToHead") == "01",
            )
            self._apply_member_payload(result, contractor, item)
            db.add(result)

    def _apply_member_payload(self, target, contractor: SurveyCbfResult, item: dict) -> None:
        target.cbfbm = contractor.cbfbm
        target.cyxm = item["name"]
        target.cyzjlx = item["idType"]
        target.cyzjhm = item["idNo"]
        target.cyxb = item["gender"]
        target.yhzgx = item["relationToHead"]
        target.cybz = item.get("noteCode")
        target.sfgyr = item.get("isCoOwner")
        target.cybzsm = item.get("note")

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.combine(date.fromisoformat(value), datetime.min.time())

    def _resolve_group_region(self, db: Session, payload: dict, current_user: User) -> tuple[str | None, str | None]:
        code = (payload.get("groupRegionCode") or "").strip()
        if not code:
            return None, None
        data_access_service.ensure_region_in_scope(current_user, code, detail="所属组不在当前数据权限范围内")
        region = db.scalar(select(Region).where(Region.code == code).execution_options(skip_tenant_scope=True))
        name = region.full_name if region else (payload.get("groupRegionName") or "")
        return code, name.strip() or None

    def _next_no(self, db: Session, prefix: str, id_column) -> str:
        next_id = (db.scalar(select(func.max(id_column))) or 0) + 1
        return f"{prefix}{datetime.now():%Y%m%d}{next_id:04d}"


contractor_service = ContractorService()
