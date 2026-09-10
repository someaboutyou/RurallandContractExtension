import logging
from datetime import date, datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyCbfBase,
    SurveyCbdkxxResult,
    SurveyFbfBase,
    SurveyFbfResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service

logger = logging.getLogger(__name__)

class SurveyServiceIssuerMixin:
    def list_issuers(
        self,
        db: Session,
        batch_id: int,
        page: int,
        page_size: int,
        keyword: str | None,
        region_code: str | None,
        current_user: User,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        normalized_region_code = data_access_service.normalize_region_code(region_code) or data_access_service.normalize_region_code(batch.region_code)
        if normalized_region_code:
            data_access_service.ensure_region_in_scope(current_user, normalized_region_code)

        filters = self._tenant_filters(SurveyFbfResult, current_user)
        if normalized_region_code:
            if len(normalized_region_code) >= 14:
                filters.append(SurveyFbfResult.fbfbm == normalized_region_code[:14])
            else:
                filters.append(SurveyFbfResult.fbfbm.like(f"{normalized_region_code}%"))
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(or_(SurveyFbfResult.fbfbm.ilike(pattern), SurveyFbfResult.fbfmc.ilike(pattern), SurveyFbfResult.fbffzrxm.ilike(pattern)))

        total = db.scalar(
            select(func.count(SurveyFbfResult.id))
            .where(*filters)
            .execution_options(skip_tenant_scope=True)
        ) or 0
        rows = db.scalars(
            select(SurveyFbfResult)
            .where(*filters)
            .order_by(SurveyFbfResult.fbfbm.asc(), SurveyFbfResult.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .execution_options(skip_tenant_scope=True)
        ).all()

        issuer_codes = {item.fbfbm for item in rows}
        relation_counts = {code: 0 for code in issuer_codes}
        first_contractors: dict[str, str] = {}
        if issuer_codes:
            relation_rows = db.execute(
                select(
                    SurveyCbdkxxResult.fbfbm,
                    func.count(func.distinct(SurveyCbdkxxResult.cbfbm)),
                    func.min(SurveyCbdkxxResult.cbfbm),
                )
                .where(
                    SurveyCbdkxxResult.tenant_code == batch.tenant_code,
                    SurveyCbdkxxResult.fbfbm.in_(issuer_codes),
                )
                .group_by(SurveyCbdkxxResult.fbfbm)
                .execution_options(skip_tenant_scope=True)
            ).all()
            relation_counts.update({code: count for code, count, _cbfbm in relation_rows})
            first_contractors.update({code: cbfbm for code, _count, cbfbm in relation_rows if cbfbm})

        source_tasks = {}
        if first_contractors:
            task_rows = db.scalars(
                select(SurveyCbfBase)
                .where(
                    SurveyCbfBase.tenant_code == batch.tenant_code,
                    SurveyCbfBase.batch_id == batch_id,
                    SurveyCbfBase.cbfbm.in_(set(first_contractors.values())),
                )
                .execution_options(skip_tenant_scope=True)
            ).all()
            tasks_by_cbfbm = {task.cbfbm: task for task in task_rows}
            source_tasks = {
                issuer_code: tasks_by_cbfbm.get(cbfbm)
                for issuer_code, cbfbm in first_contractors.items()
            }

        items = [
            self._serialize_issuer_row(item, batch_id, relation_counts.get(item.fbfbm, 0), source_tasks.get(item.fbfbm))
            for item in rows
        ]
        return {"items": items, "total": total, "page": page, "pageSize": page_size}


    def create_issuer(self, db: Session, batch_id: int, payload: dict, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幍瑙勵偧瀹歌尙绮ㄩ弶鐕傜礉娑撳秷鍏橀弬鏉款杻")
        code = payload["code"].strip()
        data_access_service.ensure_code_in_scope(current_user, code, detail="issuer is out of scope")
        if batch.region_code:
            expected = batch.region_code[:14]
            if len(batch.region_code) >= 14 and code != expected:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="issuer code must equal the 14-digit batch region code")
            if len(batch.region_code) < 14 and not code.startswith(batch.region_code):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="issuer code is outside the batch region")
        exists = db.scalars(
            select(SurveyFbfResult).where(
                SurveyFbfResult.tenant_code == batch.tenant_code,
                SurveyFbfResult.fbfbm == code,
            ).execution_options(skip_tenant_scope=True)
        ).first()
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="issuer survey result already exists")

        now = datetime.now(timezone.utc)
        survey_date = self._parse_datetime(payload.get("surveyDate")) or datetime.combine(date.today(), datetime.min.time())
        issuer_uid = str(uuid5(NAMESPACE_URL, f"survey:{batch_id}:fbf:{code}"))
        base = SurveyFbfBase(
            tenant_code=batch.tenant_code,
            region_code=code,
            batch_id=batch_id,
            issuer_uid=issuer_uid,
            source_fbfbm=code,
            fbfbm=code,
            fbfmc=payload["name"],
            fbffzrxm=payload["responsibleName"],
            fzrzjlx=payload.get("responsibleIdType") or "1",
            fzrzjhm=payload["responsibleIdNo"],
            lxdh=payload.get("phone"),
            fbfdz=payload["address"],
            yzbm=payload.get("postcode") or "000000",
            fbfdcy=payload.get("surveyorName") or current_user.real_name,
            fbfdcrq=survey_date,
            fbfdcjs=payload.get("surveyNote"),
            initialized_from_table="manual_add",
            initialized_from_key=code,
            initialized_at=now,
            snapshot_at=now,
        )
        db.add(base)
        db.flush()
        result.result_status = "added"
        result.is_changed = True
        result.change_type = "add_issuer"
        result.remark = payload.get("remark")
        db.add(result)
        db.commit()
        return self._serialize_issuer_row(result, batch_id, 0)


    def get_issuer(self, db: Session, batch_id: int, issuer_uid: str, current_user: User) -> dict:
        issuer = self._get_issuer(db, batch_id, issuer_uid)
        data_access_service.ensure_code_in_scope(current_user, issuer.fbfbm, detail="閸欐垵瀵橀弬閫涚瑝閸︺劌缍嬮崜宥嗘殶閹诡喗娼堥梽鎰瘱閸ユ潙鍞?")
        base = db.scalars(
            select(SurveyFbfBase)
            .where(SurveyFbfBase.tenant_code == issuer.tenant_code, SurveyFbfBase.result_id == issuer.id)
            .execution_options(skip_tenant_scope=True)
        ).first()
        data = self._serialize_issuer(issuer)
        data["baseIssuer"] = self._serialize_base_issuer(base) if base else None
        return data


    def update_issuer(self, db: Session, batch_id: int, issuer_uid: str, payload: dict, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鐠嬪啯鐓￠幍瑙勵偧瀹歌尙绮ㄩ弶鐕傜礉娑撳秷鍏樼紒褏鐢荤紓鏍帆")
        issuer = self._get_issuer(db, batch_id, issuer_uid)
        if issuer.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="issuer survey result already confirmed")
        data_access_service.ensure_code_in_scope(current_user, issuer.fbfbm, detail="issuer is out of scope")
        data_access_service.ensure_code_in_scope(current_user, payload["code"], detail="issuer is out of scope")
        if batch.region_code:
            if len(batch.region_code) >= 14 and payload["code"] != batch.region_code[:14]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="issuer code must equal the 14-digit batch region code")
            if len(batch.region_code) < 14 and not payload["code"].startswith(batch.region_code):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="issuer code is outside the batch region")

        base = db.scalars(
            select(SurveyFbfBase)
            .where(SurveyFbfBase.tenant_code == issuer.tenant_code, SurveyFbfBase.result_id == issuer.id)
            .execution_options(skip_tenant_scope=True)
        ).first()
        old_fbfbm = issuer.fbfbm
        issuer.fbfbm = payload["code"]
        issuer.fbfmc = payload["name"]
        issuer.fbffzrxm = payload["responsibleName"]
        issuer.fzrzjlx = payload["responsibleIdType"]
        issuer.fzrzjhm = payload["responsibleIdNo"]
        issuer.lxdh = payload.get("phone")
        issuer.fbfdz = payload["address"]
        issuer.yzbm = payload["postcode"]
        issuer.fbfdcy = payload.get("surveyorName") or current_user.real_name
        issuer.fbfdcrq = self._parse_datetime(payload.get("surveyDate")) or issuer.fbfdcrq
        issuer.fbfdcjs = payload.get("surveyNote")
        issuer.survey_status = payload.get("surveyStatus") or "surveyed"
        issuer.result_status = payload.get("resultStatus") or "normal"
        issuer.change_type = payload.get("changeType") or "none"
        issuer.change_reason = payload.get("changeReason")
        issuer.remark = payload.get("remark")
        issuer.is_changed = self._issuer_changed(issuer, base)
        if old_fbfbm != issuer.fbfbm:
            db.execute(
                update(SurveyCbdkxxResult)
                .where(
                    SurveyCbdkxxResult.tenant_code == issuer.tenant_code,
                    SurveyCbdkxxResult.fbfbm == old_fbfbm,
                )
                .values(fbfbm=issuer.fbfbm)
                .execution_options(skip_tenant_scope=True)
            )
        db.commit()
        return self.get_issuer(db, batch_id, issuer_uid, current_user)


    def _serialize_issuer_row(self, item: SurveyFbfResult, survey_batch_id: int, related_count: int = 0, source_task: SurveyCbfBase | None = None) -> dict:
        return {
            "id": item.id,
            "batchId": survey_batch_id,
            "issuerUid": item.issuer_uid,
            "code": item.fbfbm,
            "name": item.fbfmc,
            "responsibleName": item.fbffzrxm,
            "surveyStatus": item.survey_status,
            "relatedContractorCount": related_count,
            "surveyDate": item.fbfdcrq.date().isoformat() if item.fbfdcrq else None,
            "surveyorName": item.fbfdcy,
            "sourceTask": self._serialize_task(source_task) if source_task else None,
        }


    def _get_issuer(self, db: Session, batch_id: int, issuer_uid: str) -> SurveyFbfResult:
        batch = self._ensure_batch(db, batch_id)
        issuer = db.scalars(
            select(SurveyFbfResult)
            .where(
                SurveyFbfResult.tenant_code == batch.tenant_code,
                SurveyFbfResult.issuer_uid == issuer_uid,
            )
            .execution_options(skip_tenant_scope=True)
        ).first()
        if issuer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="閸欐垵瀵橀弬纭呯殶閺屻儲鍨氶弸婊€绗夌€涙ê婀?")
        return issuer


    def _serialize_issuer(self, item: SurveyFbfResult) -> dict:
        return {
            "id": item.id,
            "issuerUid": item.issuer_uid,
            "baseId": None,  # TODO: lookup from base
            "code": item.fbfbm,
            "name": item.fbfmc,
            "responsibleName": item.fbffzrxm,
            "responsibleIdType": item.fzrzjlx,
            "responsibleIdNo": item.fzrzjhm,
            "phone": item.lxdh,
            "address": item.fbfdz,
            "postcode": item.yzbm,
            "surveyorName": item.fbfdcy,
            "surveyDate": item.fbfdcrq.date().isoformat() if item.fbfdcrq else None,
            "surveyNote": item.fbfdcjs,
            "surveyStatus": item.survey_status,
            "resultStatus": item.result_status,
            "isChanged": item.is_changed,
            "changeType": item.change_type,
            "changeReason": item.change_reason,
            "policyBasis": getattr(item, "policy_basis", None),
            "remark": item.remark,
        }


    def _serialize_base_issuer(self, item: SurveyFbfBase) -> dict:
        return {
            "code": item.fbfbm,
            "name": item.fbfmc,
            "responsibleName": item.fbffzrxm,
            "responsibleIdType": item.fzrzjlx,
            "responsibleIdNo": item.fzrzjhm,
            "phone": item.lxdh,
            "address": item.fbfdz,
            "postcode": item.yzbm,
            "surveyorName": item.fbfdcy,
            "surveyDate": item.fbfdcrq.date().isoformat() if item.fbfdcrq else None,
            "surveyNote": item.fbfdcjs,
        }

