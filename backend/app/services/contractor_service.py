from datetime import date, datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.sequences import next_no as generate_business_no
from app.models.region import Region
from app.models.survey import SurveyBatch, SurveyCbfBase, SurveyCbfJtcyBase, SurveyCbfJtcyResult, SurveyCbfResult
from app.models.user import User
from app.repositories.contractor_repository import contractor_repository
from app.services.data_access_service import data_access_service
from app.services.relation_codes import sync_household_head_flags


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
            data_access_service.ensure_region_filter_in_scope(current_user, region_code, detail="区域不在当前数据权限范围内")
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
        # 先建结果行：survey_cbf_base.result_id 是 NOT NULL，快照行必须挂在结果行之后。
        result = SurveyCbfResult(
            contractor_uid=contractor_uid,
            initialized_at=now,
            survey_status="surveyed",
            result_status="normal",
        )
        self._apply_contractor_payload(result, payload, current_user, group_region_code, group_region_name)
        db.add(result)
        db.flush()

        base = SurveyCbfBase(
            batch_id=batch.id,
            contractor_uid=contractor_uid,
            result_id=result.id,
            source_cbfbm=payload["code"],
            initialized_from_key=payload["code"],
            initialized_at=now,
            snapshot_at=now,
        )
        self._apply_contractor_payload(base, payload, current_user, group_region_code, group_region_name)
        db.add(base)
        db.flush()

        self._replace_family_members(db, result, payload.get("familyMembers", []), now, base=base)
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
        base = contractor_repository.get_base_for_result(db, contractor)
        existed = contractor_repository.get_contractor_in_batch(db, base.batch_id, payload["code"]) if base else None
        if payload["code"] != code and existed is not None and existed.id != contractor.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前调查批次内承包方代码已存在")

        self._apply_contractor_payload(contractor, payload, current_user, group_region_code, group_region_name)
        if base is not None:
            self._apply_contractor_payload(base, payload, current_user, group_region_code, group_region_name)
            base.source_cbfbm = payload["code"]
            base.snapshot_at = datetime.now(timezone.utc)
        self._replace_family_members(db, contractor, payload.get("familyMembers", []), datetime.now(timezone.utc), base=base)
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
            "batchId": contractor.source_import_batch_id,
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
        target.region_code = data_access_service.normalize_region_code(group_region_code or payload["code"])
        target.tenant_code = data_access_service.derive_tenant_code(target.region_code)

    def _replace_family_members(
        self,
        db: Session,
        contractor: SurveyCbfResult,
        family_members: list[dict],
        now: datetime,
        base: SurveyCbfBase | None = None,
    ) -> None:
        """整体替换某户的家庭成员（结果表全删重建，快照表随之同步）。

        ``base`` 为该户的批次快照行；为 ``None`` 表示这户只有结果行
        （数据导入直写的户），此时只维护结果表——``survey_cbf_jtcy_base.batch_id``
        是 NOT NULL，没有批次就无从写快照。

        ``member_uid`` 优先沿用该成员原有值（证件号为键），否则退回与数据导入
        一致的推导式 ``survey:member:{cbfbm}:{idNo}``，避免同一个人在库里
        因编辑一次就换一个身份标识。
        """
        existing_uids = {
            item.cyzjhm: item.member_uid
            for item in db.scalars(
                select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.contractor_uid == contractor.contractor_uid,
                )
            ).all()
            if item.cyzjhm and item.member_uid
        }
        db.execute(
            delete(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == contractor.contractor_uid,
            )
        )
        if base is not None:
            db.execute(
                delete(SurveyCbfJtcyBase).where(
                    SurveyCbfJtcyBase.batch_id == base.batch_id,
                    SurveyCbfJtcyBase.contractor_uid == contractor.contractor_uid,
                )
            )
        seen_ids: set[str] = set()
        pending: list[tuple[SurveyCbfJtcyBase | None, SurveyCbfJtcyResult]] = []
        for item in family_members:
            member_id = item["idNo"]
            if member_id in seen_ids:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="家庭成员证件号不能重复")
            seen_ids.add(member_id)
            member_uid = existing_uids.get(member_id) or str(
                uuid5(NAMESPACE_URL, f"survey:member:{contractor.cbfbm}:{member_id}")
            )
            member_base = None
            if base is not None:
                member_base = SurveyCbfJtcyBase(
                    batch_id=base.batch_id,
                    contractor_uid=contractor.contractor_uid,
                    member_uid=member_uid,
                    base_contractor_code=contractor.cbfbm,
                    base_member_id_no=member_id,
                    initialized_from_table="survey_cbf_jtcy_result",
                    initialized_from_key=f"{contractor.cbfbm}:{member_id}",
                    initialized_at=now,
                    snapshot_at=now,
                )
                self._apply_member_payload(member_base, contractor, item)
                db.add(member_base)
            result = SurveyCbfJtcyResult(
                contractor_uid=contractor.contractor_uid,
                member_uid=member_uid,
                initialized_at=now,
                survey_status="surveyed",
                member_result_status="normal",
                is_household_head=False,  # 由下方 sync_household_head_flags 按统一口径收敛
            )
            self._apply_member_payload(result, contractor, item)
            db.add(result)
            pending.append((member_base, result))
        db.flush()
        for member_base, result in pending:
            if member_base is not None:
                member_base.result_id = result.id
        # 户主标记必须按统一口径收敛（优先 户主 02 → 本人 01 → 兜底第一条）。
        # ⛔ 旧实现是 `is_household_head = (relationToHead == "01")`，而字典与真实数据里
        # 户主是 "02" ⇒ 这个标记几乎恒为 False，「确认调查结果」的户主校验随之失败
        # （2026-09-25 修）。只标定 result 侧：base 是批次基线快照，不该被就地推进。
        sync_household_head_flags([row for _base_row, row in pending if row is not None])

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
        data_access_service.ensure_region_in_scope(current_user, code, detail="group region out of scope")
        region = db.scalar(select(Region).where(Region.code == code).execution_options(skip_tenant_scope=True))
        name = region.full_name if region else (payload.get("groupRegionName") or "")
        return code, name.strip() or None

    def _next_no(self, db: Session, prefix: str, id_column=None) -> str:
        # 走 PostgreSQL 序列（app.db.sequences），不再用 max(id)+1：
        # 后者在"删掉最大 id 的行"之后会回退，导致编号被重复使用（撞唯一约束）。
        return generate_business_no(db, prefix, id_column)


contractor_service = ContractorService()

