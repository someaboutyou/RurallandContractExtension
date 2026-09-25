import logging
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException, status
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyCbfBase,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyCbdkxxResult,
    SurveyChangeDiff,
    SurveyChangeRecord,
    SurveyDkResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service
from app.services.relation_codes import (
    HEAD_RELATION_VALUE,
    head_relation_after_change,
    is_head_relation,
    normalize_non_head_relations,
    pick_household_head,
)

logger = logging.getLogger(__name__)


class SurveyServiceHouseholdMixin:
    def _find_active_swap_change(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        tenant_code: str,
    ) -> SurveyChangeRecord | None:
        return db.scalars(
            select(SurveyChangeRecord)
            .where(
                SurveyChangeRecord.tenant_code == tenant_code,
                SurveyChangeRecord.batch_id == batch_id,
                SurveyChangeRecord.contractor_uid == contractor_uid,
                SurveyChangeRecord.change_type == "swap_parcels",
                SurveyChangeRecord.change_status != "rolled_back",
            )
            .order_by(SurveyChangeRecord.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).first()

    def _ensure_can_deregister(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        result: SurveyCbfResult,
    ) -> None:
        active_swap = self._find_active_swap_change(db, batch_id, contractor_uid, result.tenant_code)
        if active_swap is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该承包方存在未撤回的地块互换，不能注销",
            )

    def change_household_head(
        self, db: Session, batch_id: int, contractor_uid: str,
        new_head_member_uid: str, reason: str | None, current_user: User,
        commit: bool = True,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        # 任务归属：只有名下有这一户的人（或批次创建人 / 管理员）能改。
        self.ensure_task_write_permission(db, batch, result, current_user)
        now = datetime.now(timezone.utc)

        old_head = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
                SurveyCbfJtcyResult.is_household_head.is_(True),
            )
        ).first()
        old_name = old_head.cyxm if old_head else None

        new_head = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
                SurveyCbfJtcyResult.member_uid == new_head_member_uid,
            )
        ).first()
        if new_head is None:
            raise HTTPException(404, "not found")
        if new_head.is_deceased:
            raise HTTPException(400, "invalid operation")

        if old_head:
            old_head.is_household_head = False
            old_head.is_changed = True
            # ⛔ 原户主若还挂着"户主类"关系码（02 户主 / 01 本人）必须一并改掉，
            # 否则一个户里会同时存在两个户主类码 —— 而本项目按「优先 02 → 次选 01」
            # 判定户主，会取回原户主（2026-09-25 修）。做法是"对调"：原户主继承
            # 新户主原先的关系码；双方都是户主类码时收敛为 10（配偶）。
            old_head.yhzgx = head_relation_after_change(new_head.yhzgx, old_head.yhzgx)
        new_head.is_household_head = True
        new_head.is_changed = True
        new_head.yhzgx = HEAD_RELATION_VALUE

        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="change_head",
            before_summary={"old_head": old_name, "old_head_uid": old_head.member_uid if old_head else None},
            after_summary={"new_head": new_head.cyxm, "new_head_uid": new_head_member_uid},
            reason=reason,
            current_user=current_user, now=now,
        )
        db.flush()

        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now

        result.investigated_at = now
        if not commit:
            db.flush()
            return {"queued": True}
        self._rebuild_contractor_diffs(db, batch_id, [contractor_uid], change_ids={contractor_uid: record.id})
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def maintain_members(
        self, db: Session, batch_id: int, contractor_uid: str,
        members_to_add: list[dict], members_to_update: list[dict],
        members_to_delete: list[str | dict], reason: str | None, current_user: User,
        commit: bool = True,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        # 任务归属：只有名下有这一户的人（或批次创建人 / 管理员）能改。
        self.ensure_task_write_permission(db, batch, result, current_user)
        now = datetime.now(timezone.utc)

        change_details = {"added": [], "updated": [], "deleted": []}
        deleted_member_reasons = {}

        delete_requests = []
        for item in members_to_delete:
            if isinstance(item, str):
                delete_requests.append({"memberUid": item, "changeReason": reason})
            else:
                delete_requests.append({
                    "memberUid": item.get("memberUid"),
                    "changeReason": item.get("changeReason") or reason,
                })

        for item in delete_requests:
            member_uid = item.get("memberUid")
            if not member_uid:
                continue
            member = db.scalars(
                select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.contractor_uid == contractor_uid,
                    SurveyCbfJtcyResult.member_uid == member_uid,
                )
            ).first()
            if member is None:
                continue
            item_reason = item.get("changeReason") or reason
            deleted_member_reasons[member_uid] = item_reason
            change_details["deleted"].append({
                "member_uid": member_uid,
                "name": member.cyxm,
                "id_no": member.cyzjhm,
                "relation": member.yhzgx,
                "change_reason": item_reason,
            })
            db.delete(member)

        for item in members_to_update:
            member_uid = item.get("memberUid")
            if not member_uid:
                continue
            member = db.scalars(
                select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.contractor_uid == contractor_uid,
                    SurveyCbfJtcyResult.member_uid == member_uid,
                )
            ).first()
            if member is None:
                continue
            item_reason = item.get("changeReason") or reason
            field_map = [
                ("cyxm", "name"),
                ("cyxb", "gender"),
                ("cyzjlx", "idType"),
                ("cyzjhm", "idNo"),
                ("yhzgx", "relationToHead"),
                ("cybz", "noteCode"),
                ("sfgyr", "isCoOwner"),
                ("cybzsm", "note"),
                ("is_household_head", "isHouseholdHead"),
            ]
            changed_fields = []
            for attr, key in field_map:
                if key not in item:
                    continue
                before_value = getattr(member, attr)
                after_value = bool(item.get(key)) if attr == "is_household_head" else item.get(key)
                if self._diff_value(before_value) == self._diff_value(after_value):
                    continue
                setattr(member, attr, after_value)
                changed_fields.append(attr)
            if changed_fields:
                change_details["updated"].append({
                    "member_uid": member_uid,
                    "name": member.cyxm,
                    "fields": changed_fields,
                    "change_reason": item_reason,
                })
                member.is_changed = True
                member.change_reason = item_reason
                member.investigator_id = current_user.id
                member.investigator_name = current_user.real_name
                member.investigated_at = now

        for item in members_to_add:
            member_uid = item.get("memberUid") or str(uuid4())
            item_reason = item.get("changeReason") or reason
            member = SurveyCbfJtcyResult(
                contractor_uid=contractor_uid,
                member_uid=member_uid,
                cbfbm=result.cbfbm,
                cyxm=item["name"],
                cyxb=item.get("gender", "1"),
                cyzjlx=item.get("idType", "1"),
                cyzjhm=item.get("idNo", ""),
                yhzgx=item.get("relationToHead", "09"),
                cybz=item.get("noteCode"),
                sfgyr=item.get("isCoOwner"),
                cybzsm=item.get("note"),
                member_result_status="added",
                survey_status="surveyed",
                is_household_head=bool(item.get("isHouseholdHead")),
                is_changed=True,
                change_reason=item_reason,
                initialized_at=now,
                investigator_id=current_user.id,
                investigator_name=current_user.real_name,
                investigated_at=now,
            )
            db.add(member)
            change_details["added"].append({
                "member_uid": member_uid,
                "name": item["name"],
                "change_reason": item_reason,
            })

        member_count = db.scalar(
            select(func.count(SurveyCbfJtcyResult.id)).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
        ) or 0
        result.cbfcysl = member_count
        result.investigated_at = now

        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="member_maintain",
            before_summary={},
            after_summary=change_details,
            reason=reason,
            current_user=current_user, now=now,
        )
        db.flush()

        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + sum(len(change_details[key]) for key in ["added", "updated", "deleted"])
            task.investigated_at = now

        if not commit:
            db.flush()
            return {"queued": True}
        self._rebuild_contractor_diffs(
            db,
            batch_id,
            [contractor_uid],
            change_ids={contractor_uid: record.id},
            deleted_member_reasons={contractor_uid: deleted_member_reasons},
        )
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def deregister_contractor(
        self, db: Session, batch_id: int, contractor_uid: str,
        reason: str, current_user: User,
        commit: bool = True,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        # 任务归属：只有名下有这一户的人（或批次创建人 / 管理员）能改。
        self.ensure_task_write_permission(db, batch, result, current_user)
        self._ensure_can_deregister(db, batch_id, contractor_uid, result)
        now = datetime.now(timezone.utc)

        members = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
        ).all()
        parcel_relations = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ).all()
        parcel_dkbms = [item.dkbm for item in parcel_relations]
        parcel_rows = db.scalars(
            select(SurveyDkResult)
            .where(
                SurveyDkResult.dkbm.in_(parcel_dkbms or [""]),
                SurveyDkResult.result_status.notin_(("removed", "split_source")),
            )
            .order_by(SurveyDkResult.dkbm.asc(), SurveyDkResult.id.desc())
        ).all() if parcel_dkbms else []
        parcel_map: dict[str, SurveyDkResult] = {}
        for item in parcel_rows:
            parcel_map.setdefault(item.dkbm, item)
        task = self._get_task(db, batch_id, contractor_uid)

        before_summary = {
            "result": {
                "surveyStatus": result.survey_status,
                "resultStatus": result.result_status,
                "isChanged": result.is_changed,
                "changeType": result.change_type,
                "changeReason": result.change_reason,
            },
            "task": {
                "taskStatus": task.task_status if task else ("not_started" if result.survey_status == "not_surveyed" else result.survey_status),
                "hasChange": task.has_change if task else result.is_changed,
                "changeCount": task.change_count if task else 0,
                "remark": task.remark if task else result.remark,
            },
            "members": [
                {"memberUid": m.member_uid, "name": m.cyxm, "idNo": m.cyzjhm}
                for m in members
            ],
            "parcel_relations": [
                {
                    "parcelInfoUid": p.parcel_info_uid,
                    "dkbm": p.dkbm,
                    "resultStatus": p.result_status,
                    "isChanged": p.is_changed,
                    "changeType": p.change_type,
                    "changeReason": p.change_reason,
                }
                for p in parcel_relations
            ],
            "parcels": [
                {
                    "parcelUid": p.parcel_uid,
                    "dkbm": p.dkbm,
                    "resultStatus": p.result_status,
                    "isChanged": p.is_changed,
                    "changeType": p.change_type,
                    "changeReason": p.change_reason,
                }
                for p in parcel_map.values()
            ],
        }

        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="deregister",
            before_summary=before_summary,
            after_summary={"action": "deregistered", "reason": reason},
            reason=reason,
            current_user=current_user, now=now,
        )
        db.flush()

        result.result_status = "cancelled"
        result.is_changed = True
        result.change_type = "deregister"
        result.change_reason = reason
        result.investigator_id = current_user.id
        result.investigator_name = current_user.real_name
        result.investigated_at = now

        # 差异行无业务编码列，显式继承承包方结果的租户/村组码，
        # 避免 before_flush 退化成当前用户的区域码（组级权限用户会 403）。
        scope_tenant = result.tenant_code
        scope_region = result.group_region_code or result.region_code or result.cbfbm

        db.add(SurveyChangeDiff(
            batch_id=batch_id,
            contractor_uid=contractor_uid,
            change_id=record.id,
            tenant_code=scope_tenant,
            region_code=scope_region,
            entity_type="contractor",
            entity_uid=contractor_uid,
            entity_name=result.cbfmc,
            field_name="result_status",
            field_label="承包方状态",
            before_value=before_summary["result"]["resultStatus"],
            after_value="cancelled",
            change_reason=reason,
        ))
        for member in members:
            db.add(SurveyChangeDiff(
                batch_id=batch_id,
                contractor_uid=contractor_uid,
                change_id=record.id,
                tenant_code=scope_tenant,
                region_code=scope_region,
                entity_type="member",
                entity_uid=member.member_uid,
                entity_name=member.cyxm,
                field_name="member",
                field_label="家庭成员",
                before_value=f"{member.cyxm} / {member.cyzjhm}",
                after_value=f"{member.cyxm} / {member.cyzjhm}",
                change_reason=reason,
            ))
        for relation in parcel_relations:
            relation.is_changed = True
            relation.change_type = "deregister"
            relation.change_reason = reason
            relation_before = next((item for item in before_summary["parcel_relations"] if item["parcelInfoUid"] == relation.parcel_info_uid), {})
            db.add(SurveyChangeDiff(
                batch_id=batch_id,
                contractor_uid=contractor_uid,
                change_id=record.id,
                tenant_code=scope_tenant,
                region_code=scope_region,
                entity_type="parcel_relation",
                entity_uid=relation.parcel_info_uid,
                entity_name=relation.dkbm,
                field_name="change_type",
                field_label="承包地块状态",
                before_value=relation_before.get("changeType"),
                after_value="deregister",
                change_reason=reason,
            ))
        for parcel in parcel_map.values():
            parcel.is_changed = True
            parcel.change_type = "deregister"
            parcel.change_reason = reason
            parcel_before = next((item for item in before_summary["parcels"] if item["dkbm"] == parcel.dkbm), {})
            db.add(SurveyChangeDiff(
                batch_id=batch_id,
                contractor_uid=contractor_uid,
                change_id=record.id,
                tenant_code=scope_tenant,
                region_code=scope_region,
                entity_type="parcel",
                entity_uid=parcel.parcel_uid,
                entity_name=parcel.dkmc,
                field_name="change_type",
                field_label="地块状态",
                before_value=parcel_before.get("changeType"),
                after_value="deregister",
                change_reason=reason,
            ))

        if task:
            task.task_status = "deregistered"
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now
            task.remark = reason

        if not commit:
            db.flush()
            return {"queued": True}
        db.commit()
        return {"contractorUid": contractor_uid, "status": "deregistered", "changeNo": record.change_no}

    def rollback_deregistered_contractor(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        current_user: User,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前批次已结束，不能撤回注销")
        result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        self.ensure_task_write_permission(db, batch, result, current_user)

        deregister_change = db.scalars(
            select(SurveyChangeRecord)
            .where(
                SurveyChangeRecord.tenant_code == batch.tenant_code,
                SurveyChangeRecord.batch_id == batch_id,
                SurveyChangeRecord.contractor_uid == contractor_uid,
                SurveyChangeRecord.change_type == "deregister",
                SurveyChangeRecord.change_status != "rolled_back",
            )
            .order_by(SurveyChangeRecord.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).first()
        if deregister_change is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未找到可撤回的注销记录")

        before_summary = deregister_change.before_summary or {}
        previous_result = before_summary.get("result") or {}
        # Older clients used to write the deregistration preview into the result
        # before the snapshot was created.  Treat that poisoned snapshot as the
        # normal active state so rollback actually unlocks the contractor.
        if previous_result.get("resultStatus") in {"cancelled", "extinct"} or previous_result.get("changeType") == "deregister":
            previous_result = {
                **previous_result,
                "resultStatus": "normal",
                "changeType": "none",
                "changeReason": None,
            }
        previous_task = before_summary.get("task") or {}
        previous_relations = {
            item.get("parcelInfoUid"): item
            for item in before_summary.get("parcel_relations") or []
            if item.get("parcelInfoUid")
        }
        previous_parcels = {
            item.get("dkbm"): item
            for item in before_summary.get("parcels") or []
            if item.get("dkbm")
        }
        now = datetime.now(timezone.utc)

        result.survey_status = previous_result.get("surveyStatus") or result.survey_status
        result.result_status = previous_result.get("resultStatus") or "normal"
        result.is_changed = bool(previous_result.get("isChanged"))
        result.change_type = previous_result.get("changeType") or "none"
        result.change_reason = previous_result.get("changeReason")
        result.investigator_id = current_user.id
        result.investigator_name = current_user.real_name
        result.investigated_at = now

        relation_rows = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.parcel_info_uid.in_(list(previous_relations) or [""]),
            )
        ).all()
        for relation in relation_rows:
            previous = previous_relations.get(relation.parcel_info_uid) or {}
            relation.result_status = previous.get("resultStatus") or "normal"
            relation.is_changed = bool(previous.get("isChanged"))
            relation.change_type = previous.get("changeType") or "none"
            relation.change_reason = previous.get("changeReason")

        parcel_rows = db.scalars(
            select(SurveyDkResult)
            .where(
                SurveyDkResult.dkbm.in_(list(previous_parcels) or [""]),
                SurveyDkResult.result_status.notin_(("removed", "split_source")),
            )
            .order_by(SurveyDkResult.dkbm.asc(), SurveyDkResult.id.desc())
        ).all() if previous_parcels else []
        latest_parcels: dict[str, SurveyDkResult] = {}
        for item in parcel_rows:
            latest_parcels.setdefault(item.dkbm, item)
        for dkbm, parcel in latest_parcels.items():
            previous = previous_parcels.get(dkbm) or {}
            parcel.result_status = previous.get("resultStatus") or "normal"
            parcel.is_changed = bool(previous.get("isChanged"))
            parcel.change_type = previous.get("changeType") or "none"
            parcel.change_reason = previous.get("changeReason")

        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.task_status = previous_task.get("taskStatus") or ("not_started" if result.survey_status == "not_surveyed" else result.survey_status)
            task.has_change = bool(previous_task.get("hasChange"))
            task.change_count = int(previous_task.get("changeCount") or 0)
            task.investigated_at = now
            task.remark = previous_task.get("remark")

        deregister_change.change_status = "rolled_back"
        rollback_reason = f"撤回注销 {deregister_change.change_no}"
        rollback_record = self._create_change_record(
            db,
            batch_id,
            contractor_uid,
            result.cbfbm,
            change_type="rollback_deregister",
            before_summary={"changeNo": deregister_change.change_no},
            after_summary={"action": "rollback_deregister"},
            reason=rollback_reason,
            current_user=current_user,
            now=now,
        )
        db.flush()
        self._rebuild_contractor_diffs(
            db,
            batch_id,
            [contractor_uid],
            change_ids={contractor_uid: rollback_record.id},
        )
        self.refresh_auto_tags(db, batch_id, contractor_uid, current_user, commit=False)
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def split_household(
        self, db: Session, batch_id: int, contractor_uid: str,
        payload: dict, current_user: User,
        commit: bool = True,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        # 任务归属：只有名下有这一户的人（或批次创建人 / 管理员）能改。
        self.ensure_task_write_permission(db, batch, result, current_user)
        now = datetime.now(timezone.utc)

        all_members = db.scalars(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
        ).all()
        targets = payload.get("newHouseholds") or []
        if len(targets) < 2 or len(all_members) < 2:
            raise HTTPException(400, "分户至少需要生成两个新承包户")
        if any(not (item.get("memberUids") or []) or not (item.get("parcelDkbms") or []) for item in targets):
            raise HTTPException(400, "每个新承包户至少需要分配一名家庭成员和一块地")
        if any(item.get("householdHeadMemberUid") not in (item.get("memberUids") or []) for item in targets):
            raise HTTPException(400, "每个新承包户必须从本户家庭成员中指定一名户主")
        source_task = self._get_task(db, batch_id, contractor_uid)
        if source_task is None:
            raise HTTPException(404, "未找到原承包户调查任务")

        codes = [str(item.get("newCbfbm") or "").strip() for item in targets]
        if len(set(codes)) != len(codes) or result.cbfbm in codes:
            raise HTTPException(400, "新承包方编码不能重复或与原户相同")
        existing_code = db.scalar(select(SurveyCbfResult.id).where(SurveyCbfResult.cbfbm.in_(codes)))
        if existing_code:
            raise HTTPException(400, "新承包方编码已存在")

        member_map = {member.member_uid: member for member in all_members}
        assigned_members = [uid for item in targets for uid in (item.get("memberUids") or [])]
        if len(assigned_members) != len(set(assigned_members)) or set(assigned_members) != set(member_map):
            raise HTTPException(400, "原户所有成员必须且只能分配到一个新户")

        active_relations = db.scalars(select(SurveyCbdkxxResult).where(
            SurveyCbdkxxResult.tenant_code == batch.tenant_code,
            SurveyCbdkxxResult.cbfbm == result.cbfbm,
            SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
        ).execution_options(skip_tenant_scope=True)).all()
        if len(active_relations) < 2:
            raise HTTPException(400, "有效地块不足两个，不能办理分户")
        parcel_map = {rel.dkbm: rel for rel in active_relations}
        assigned_parcels = [code for item in targets for code in (item.get("parcelDkbms") or [])]
        if len(assigned_parcels) != len(set(assigned_parcels)) or set(assigned_parcels) != set(parcel_map):
            raise HTTPException(400, "原户所有有效地块必须且只能分配到一个新户")

        group_id = uuid4().hex
        # 快照必须能支撑撤回：除了结果态，还要记下**任务态** —— 分户现在与合户对齐，
        # 会把原户 task_status 置 deregistered（原户已不存在，应从待办摘除），
        # 撤回时按这里还原。⛔ 只放 JSON 可序列化的值，datetime 不要放进来。
        source_before = {"result_status": result.result_status, "is_changed": result.is_changed,
            "change_type": result.change_type, "change_reason": result.change_reason,
            "task_status": source_task.task_status, "has_change": source_task.has_change,
            "change_count": source_task.change_count, "remark": source_task.remark}
        member_states_before = [{"member_uid": m.member_uid, "yhzgx": m.yhzgx,
            "is_household_head": m.is_household_head, "is_changed": m.is_changed,
            "change_reason": m.change_reason} for m in all_members]
        parcel_states_before = [{"dkbm": rel.dkbm, "is_changed": rel.is_changed,
            "change_type": rel.change_type, "change_reason": rel.change_reason} for rel in active_relations]
        created = []
        change_ids = {}
        for target in targets:
            new_cbfbm = target["newCbfbm"].strip()
            new_cbfmc = target["newCbfmc"].strip()
            target_members = [member_map[uid] for uid in target["memberUids"]]
            new_uid = str(uuid5(NAMESPACE_URL, f"survey:{batch_id}:cbf:{new_cbfbm}"))
            result_values = {c.name: getattr(result, c.name) for c in SurveyCbfResult.__table__.columns if c.name not in {"id", "created_at", "updated_at"}}
            result_values.update(contractor_uid=new_uid, cbfbm=new_cbfbm, cbfmc=new_cbfmc,
                cbfzjhm="", cbfcysl=len(target_members), survey_status="surveyed", result_status="added",
                is_changed=True, change_type="split_household", change_reason=payload.get("reason"),
                investigator_id=current_user.id, investigator_name=current_user.real_name,
                investigated_at=now, confirmed_at=None, initialized_at=now,
                remark=f"split_group:{group_id};source:{contractor_uid}")
            new_result = SurveyCbfResult(**result_values)
            db.add(new_result)
            db.flush()

            base_values = {c.name: getattr(source_task, c.name) for c in SurveyCbfBase.__table__.columns if c.name not in {"id", "created_at", "updated_at"}}
            base_values.update(contractor_uid=new_uid, source_cbfbm=new_cbfbm, cbfbm=new_cbfbm, cbfmc=new_cbfmc,
                cbfzjhm="", cbfcysl=len(target_members), result_id=new_result.id, task_status="surveyed",
                has_change=True, change_count=1, investigated_at=now, initialized_at=now, snapshot_at=now,
                initialized_from_table="split_household", initialized_from_key=group_id,
                remark=f"split_group:{group_id};source:{contractor_uid}")
            db.add(SurveyCbfBase(**base_values))

            head_uid = target["householdHeadMemberUid"]
            for member in target_members:
                member.contractor_uid = new_uid
                member.cbfbm = new_cbfbm
                member.is_changed = True
                member.change_reason = payload.get("reason")
                member.is_household_head = member.member_uid == head_uid
                if member.is_household_head:
                    # ⛔ 户主的关系码是字典里的 `02`（户主），不是 `01`（本人）。
                    # 旧实现写 `01`，与存量户的 `02` 并存 ⇒ 同一个户里出现两个"户主"。
                    member.yhzgx = HEAD_RELATION_VALUE
            # 与合户同理：源户可能不止一个户主类关系码（存量数据里确实有 228 户如此），
            # 未指定为本户户主的一律收敛为 `80`（其他），避免新户出现多个"户主"。
            normalize_non_head_relations(
                target_members,
                next((m for m in target_members if m.member_uid == head_uid), None),
            )
            for dkbm in target.get("parcelDkbms") or []:
                rel = parcel_map[dkbm]
                rel.cbfbm = new_cbfbm
                rel.is_changed = True
                rel.change_type = "split_household"
                rel.change_reason = payload.get("reason")

            child_record = self._create_change_record(db, batch_id, new_uid, new_cbfbm,
                change_type="split_household", before_summary={},
                after_summary={"action": "created", "split_group_id": group_id, "from_household": result.cbfbm,
                    "members": [m.member_uid for m in target_members], "household_head_member_uid": head_uid,
                    "parcels": target.get("parcelDkbms") or []},
                reason=payload.get("reason"), current_user=current_user, now=now)
            db.flush()
            change_ids[new_uid] = child_record.id
            created.append({"contractorUid": new_uid, "cbfbm": new_cbfbm, "cbfmc": new_cbfmc})

        result.result_status = "cancelled"
        result.cbfcysl = 0
        result.is_changed = True
        result.change_type = "split_household"
        result.change_reason = payload.get("reason")
        result.investigated_at = now

        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="split_household",
            before_summary={
                "member_count": len(all_members), "parcel_count": len(active_relations),
                **source_before, "member_states": member_states_before, "parcel_states": parcel_states_before,
            },
            after_summary={
                "action": "cancelled_after_split", "split_group_id": group_id,
                "new_households": created,
            },
            reason=payload.get("reason"),
            current_user=current_user, now=now,
        )
        db.flush()

        source_task.has_change = True
        source_task.change_count = (source_task.change_count or 0) + 1
        source_task.investigated_at = now
        # 与 merge_household 对齐：原户这个承包方已不存在，"调查这一户"已无意义，
        # 应从主待办列表摘除（list_tasks 默认过滤 task_status != "deregistered"）。
        # ⛔ 摘除之后**必须保证撤回入口可达**：主列表已看不到这个户，撤回只能走
        # 「已注销承包方」弹窗，而它按 changeType 分流到 split-household/rollback。
        # 两者必须同源，否则等于把 ISSUE-01 的同型断裂复制到分户（2026-09-25）。
        source_task.task_status = "deregistered"

        # diff 重建必须排在 commit 判断之前，与 merge_household 的收尾顺序对齐。
        # 分户是 terminal 操作，调用方 update_result 在 has_terminal_operation 时
        # 会整段跳过 diff 重建，全部依赖这里；若先走 "if not commit: return"，
        # 队列模式下（_apply_pending_operations 传 commit=False）原户与新户的
        # survey_change_diffs 就都不会被刷新，原户停在分户前的旧值、新户恒为空。
        self._rebuild_contractor_diffs(
            db,
            batch_id,
            [contractor_uid, *[item["contractorUid"] for item in created]],
            change_ids={contractor_uid: record.id, **change_ids},
        )
        # 原户分户后 result.result_status 转 cancelled。但 survey_cbf_base **没有**
        # result_status 列（只有任务态 task_status），_rebuild_diffs 的
        # contractor_fields 无从比出这一项 —— 与 deregister_contractor 一样只能手工补。
        # ⛔ 顺序必须排在 _rebuild_contractor_diffs **之后**：它开头会 DELETE 掉
        # form_diff_entity_types（含 contractor）的全部行再重算，提前插入会被清掉。
        # 撤回分户时再次重建 ⇒ 这条随之消失，净差异语义成立。
        if source_before.get("result_status") != "cancelled":
            db.add(SurveyChangeDiff(
                batch_id=batch_id,
                contractor_uid=contractor_uid,
                change_id=record.id,
                tenant_code=result.tenant_code,
                region_code=result.group_region_code or result.region_code or result.cbfbm,
                entity_type="contractor",
                entity_uid=contractor_uid,
                entity_name=result.cbfmc,
                field_name="result_status",
                field_label="承包方状态",
                before_value=source_before.get("result_status"),
                after_value="cancelled",
                change_reason=payload.get("reason"),
            ))
        if not commit:
            db.flush()
            return {"queued": True}
        db.commit()
        return {"splitGroupId": group_id, "sourceContractorUid": contractor_uid, "newHouseholds": created}

    def rollback_split_household(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "当前调查任务已结束，不能撤回分户")
        source = self._get_result(db, batch_id, contractor_uid)
        self.ensure_task_write_permission(db, batch, source, current_user)
        record = db.scalars(select(SurveyChangeRecord).where(
            SurveyChangeRecord.batch_id == batch_id, SurveyChangeRecord.contractor_uid == contractor_uid,
            SurveyChangeRecord.change_type == "split_household", SurveyChangeRecord.change_status != "rolled_back",
        ).order_by(SurveyChangeRecord.id.desc())).first()
        summary = record.after_summary if record else {}
        group_id = (summary or {}).get("split_group_id")
        children = (summary or {}).get("new_households") or []
        if not group_id or not children:
            raise HTTPException(400, "未找到可撤回的分户记录")
        child_uids = [item["contractorUid"] for item in children]
        child_results = db.scalars(select(SurveyCbfResult).where(SurveyCbfResult.contractor_uid.in_(child_uids))).all()
        if any(item.survey_status == "confirmed" or item.change_type != "split_household" for item in child_results):
            raise HTTPException(400, "分户生成的新户已确认或存在后续变更，不能撤回")

        before = record.before_summary or {}
        member_states = {item["member_uid"]: item for item in before.get("member_states") or []}
        parcel_states = {item["dkbm"]: item for item in before.get("parcel_states") or []}
        members = db.scalars(select(SurveyCbfJtcyResult).where(SurveyCbfJtcyResult.contractor_uid.in_(child_uids))).all()
        for member in members:
            state = member_states.get(member.member_uid, {})
            member.contractor_uid = contractor_uid
            member.cbfbm = source.cbfbm
            member.yhzgx = state.get("yhzgx", member.yhzgx)
            member.is_changed = bool(state.get("is_changed", False))
            member.change_reason = state.get("change_reason")
            member.is_household_head = bool(state.get("is_household_head", is_head_relation(member.yhzgx)))
        relations = db.scalars(select(SurveyCbdkxxResult).where(SurveyCbdkxxResult.cbfbm.in_([i["cbfbm"] for i in children]))).all()
        for rel in relations:
            state = parcel_states.get(rel.dkbm, {})
            rel.cbfbm = source.cbfbm
            rel.is_changed = bool(state.get("is_changed", False))
            rel.change_type = state.get("change_type") or "none"
            rel.change_reason = state.get("change_reason")
        db.query(SurveyChangeDiff).filter(SurveyChangeDiff.contractor_uid.in_(child_uids)).delete(synchronize_session=False)
        child_changes = db.scalars(select(SurveyChangeRecord).where(
            SurveyChangeRecord.batch_id == batch_id, SurveyChangeRecord.contractor_uid.in_(child_uids),
            SurveyChangeRecord.change_type == "split_household")).all()
        for item in child_changes:
            item.change_status = "rolled_back"
        db.query(SurveyCbfBase).filter(SurveyCbfBase.batch_id == batch_id, SurveyCbfBase.contractor_uid.in_(child_uids)).delete(synchronize_session=False)
        db.query(SurveyCbfResult).filter(SurveyCbfResult.contractor_uid.in_(child_uids)).delete(synchronize_session=False)
        source.result_status = before.get("result_status") or "normal"
        source.cbfcysl = len(members)
        source.is_changed = bool(before.get("is_changed", False))
        source.change_type = before.get("change_type") or "none"
        source.change_reason = before.get("change_reason")
        # 任务态还原：分户会把原户 task_status 置 deregistered（从主待办列表摘除），
        # 撤回时必须按快照还原，否则原户虽然"恢复了"却仍被 list_tasks 过滤掉，
        # 界面表现就是"撤回了但列表里没有"。
        source_task = self._get_task(db, batch_id, contractor_uid)
        if source_task is not None:
            source_task.task_status = before.get("task_status") or "not_started"
            source_task.has_change = bool(before.get("has_change", False))
            source_task.change_count = int(before.get("change_count") or 0)
            source_task.remark = before.get("remark")
        record.change_status = "rolled_back"
        rollback = self._create_change_record(db, batch_id, contractor_uid, source.cbfbm,
            change_type="rollback_split_household", before_summary={"split_group_id": group_id},
            after_summary={"action": "restored", "removed_households": children},
            reason=f"撤回分户 {record.change_no}", current_user=current_user, now=datetime.now(timezone.utc))
        db.flush()
        self._rebuild_contractor_diffs(db, batch_id, [contractor_uid], change_ids={contractor_uid: rollback.id})
        db.commit()
        return {"splitGroupId": group_id, "restoredContractorUid": contractor_uid, "removedHouseholds": children}

    def list_contractor_candidates(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        current_user: User,
        keyword: str | None = None,
        purpose: str = "merge",
    ) -> list[dict]:
        """同村组、可参与户级操作（合户 / 地块互换）的候选承包方。

        候选池按「当前批次 + 同一村组 + 状态可参与」在后端算全，供前端下拉直接消费；
        不再依赖任务列表页的数据快照（后者受关键字 / 任务状态 / page_size=100 分页影响，
        会把候选池连带收窄）。判定口径与 merge_household / swap_parcels 的校验保持一致：
        merge —— 结果状态 normal/added；swap —— 未注销且对方有可互换地块。
        """
        batch = self._ensure_batch(db, batch_id)
        source_task = self._get_task(db, batch_id, contractor_uid)
        if source_task is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="承包方不属于当前调查批次",
            )
        source_result = self._get_result(db, batch_id, contractor_uid)
        data_access_service.ensure_code_in_scope(current_user, source_result.cbfbm, detail="out of scope")
        group_key = source_result.group_region_code or source_result.region_code or source_task.cbfbm[:14]

        group_expr = func.coalesce(
            func.nullif(SurveyCbfResult.group_region_code, ""),
            SurveyCbfResult.region_code,
        )
        filters = [
            SurveyCbfBase.tenant_code == batch.tenant_code,
            SurveyCbfBase.batch_id == batch_id,
            group_expr == group_key,
            SurveyCbfBase.task_status.notin_(("deregistered", "finished")),
            SurveyCbfResult.survey_status != "confirmed",
        ]
        if purpose == "swap":
            # swap_parcels 的校验只要求目标户未被确认；再加一层"对方还有可互换地块"，
            # 免得选到没有地块的户才发现无从勾选。
            filters.append(SurveyCbfResult.result_status != "cancelled")
            filters.append(
                exists(
                    select(SurveyCbdkxxResult.id)
                    .where(
                        SurveyCbdkxxResult.tenant_code == SurveyCbfBase.tenant_code,
                        SurveyCbdkxxResult.cbfbm == SurveyCbfBase.cbfbm,
                        SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
                    )
                    .correlate(SurveyCbfBase)
                )
            )
        else:
            filters.append(SurveyCbfResult.result_status.in_(("normal", "added")))
        filters.extend(data_access_service.build_code_scope_filters(SurveyCbfBase.cbfbm, current_user))
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(or_(SurveyCbfBase.cbfbm.ilike(pattern), SurveyCbfBase.cbfmc.ilike(pattern)))

        rows = db.execute(
            select(SurveyCbfBase, SurveyCbfResult)
            .join(
                SurveyCbfResult,
                and_(
                    SurveyCbfResult.tenant_code == SurveyCbfBase.tenant_code,
                    SurveyCbfResult.contractor_uid == SurveyCbfBase.contractor_uid,
                ),
            )
            .where(*filters)
            .order_by(SurveyCbfBase.cbfbm.asc())
            .limit(2000)
            .execution_options(skip_tenant_scope=True)
        ).all()
        logger.info(
            "Survey contractor candidates: batch_id=%s contractor_uid=%s purpose=%s group_key=%s keyword=%s returned=%s",
            batch_id,
            contractor_uid,
            purpose,
            group_key,
            keyword,
            len(rows),
        )
        return [
            {
                "id": task.id,
                "batchId": task.batch_id,
                "contractorUid": task.contractor_uid,
                "cbfbm": task.cbfbm,
                "cbfmc": task.cbfmc,
                "cbfdz": task.cbfdz,
                "cbfcysl": task.cbfcysl or 0,
                "lxdh": task.lxdh,
                "regionCode": task.region_code,
                "groupRegionCode": result.group_region_code or task.cbfbm[:14],
                "groupRegionName": result.group_region_name,
                "taskStatus": task.task_status,
                "hasChange": bool(task.has_change),
                "changeCount": task.change_count or 0,
                "investigatedAt": task.investigated_at,
                "remark": task.remark,
            }
            for task, result in rows
        ]

    def list_contractor_codes(
        self,
        db: Session,
        batch_id: int,
        current_user: User,
        prefix: str | None = None,
    ) -> list[str]:
        """当前租户下已占用的承包方编码（可按前缀过滤）。

        合户 / 分户都需要为新承包户生成 18 位编码，前端原先拿任务列表页（page_size=100）
        当"已用编码集合"，批次超过 100 户时算出的编码可能与列表外的户重复，保存时才报错。
        这里直接给全量编码，与 split_household 的唯一性校验（按 survey_cbf_result.cbfbm 查重）
        保持同一张表、同一口径。
        """
        batch = self._ensure_batch(db, batch_id)
        filters = [
            SurveyCbfResult.tenant_code == batch.tenant_code,
        ]
        filters.extend(data_access_service.build_code_scope_filters(SurveyCbfResult.cbfbm, current_user))
        normalized = str(prefix or "").strip()
        if normalized:
            filters.append(SurveyCbfResult.cbfbm.like(f"{normalized}%"))
        rows = db.scalars(
            select(SurveyCbfResult.cbfbm)
            .where(*filters)
            .order_by(SurveyCbfResult.cbfbm.asc())
            .limit(20000)
            .execution_options(skip_tenant_scope=True)
        ).all()
        codes = [str(code) for code in rows if code]
        logger.info(
            "Survey contractor codes: batch_id=%s prefix=%s returned=%s",
            batch_id,
            normalized or "-",
            len(codes),
        )
        return codes

    def merge_household(
        self, db: Session, batch_id: int, source_contractor_uid: str,
        payload: dict, current_user: User,
        commit: bool = True,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        source_uids = list(dict.fromkeys(payload.get("sourceContractorUids") or []))
        if source_contractor_uid not in source_uids or len(source_uids) < 2:
            raise HTTPException(400, "合户必须包含当前户，并且至少选择两个原承包方")
        tasks = [self._get_task(db, batch_id, uid) for uid in source_uids]
        if any(task is None for task in tasks):
            raise HTTPException(400, "参与合户的承包方不属于当前调查批次")
        results = [self._get_result(db, batch_id, uid) for uid in source_uids]
        # 合户一次动多户：每一户都要过归属校验，否则「把别人家的户并进来」就是越权。
        for item in results:
            self.ensure_task_write_permission(db, batch, item, current_user)
        if any(item.survey_status == "confirmed" or item.result_status not in {"normal", "added"} for item in results):
            raise HTTPException(400, "参与合户的承包方必须为未确认的正常状态")
        region_codes = {item.group_region_code or item.region_code for item in results}
        if len(region_codes) != 1:
            raise HTTPException(400, "只能合并同一村组的承包方")
        for item in results:
            data_access_service.ensure_code_in_scope(current_user, item.cbfbm, detail="out of scope")

        new_cbfbm = str(payload.get("newCbfbm") or "").strip()
        if not new_cbfbm.isdigit() or len(new_cbfbm) != 18:
            raise HTTPException(400, "新承包方编码必须为18位数字")
        existing = db.scalar(select(SurveyCbfResult.id).where(
            SurveyCbfResult.tenant_code == batch.tenant_code,
            SurveyCbfResult.cbfbm == new_cbfbm,
        ).execution_options(skip_tenant_scope=True))
        if existing:
            raise HTTPException(400, "新承包方编码已存在")

        members = db.scalars(select(SurveyCbfJtcyResult).where(
            SurveyCbfJtcyResult.tenant_code == batch.tenant_code,
            SurveyCbfJtcyResult.contractor_uid.in_(source_uids),
        ).execution_options(skip_tenant_scope=True)).all()
        member_ids = [m.member_uid for m in members]
        if len(member_ids) != len(set(member_ids)):
            raise HTTPException(400, "参与户存在重复家庭成员，请先处理重复数据")
        head_uid = payload.get("householdHeadMemberUid")
        head = next((m for m in members if m.member_uid == head_uid), None)
        if head is None:
            raise HTTPException(400, "必须从合并后的家庭成员中指定户主")
        old_codes = [item.cbfbm for item in results]
        parcels = db.scalars(select(SurveyCbdkxxResult).where(
            SurveyCbdkxxResult.tenant_code == batch.tenant_code,
            SurveyCbdkxxResult.cbfbm.in_(old_codes),
            SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
        ).execution_options(skip_tenant_scope=True)).all()

        source_snapshots = {}
        for result, task in zip(results, tasks):
            source_snapshots[result.contractor_uid] = {
                "result": {"result_status": result.result_status, "cbfcysl": result.cbfcysl,
                    "is_changed": result.is_changed, "change_type": result.change_type,
                    "change_reason": result.change_reason},
                "task": {"task_status": task.task_status, "has_change": task.has_change,
                    "change_count": task.change_count, "remark": task.remark},
                "members": [{"member_uid": m.member_uid, "cbfbm": m.cbfbm,
                    "contractor_uid": m.contractor_uid, "yhzgx": m.yhzgx,
                    "is_household_head": m.is_household_head, "is_changed": m.is_changed,
                    "change_reason": m.change_reason}
                    for m in members if m.contractor_uid == result.contractor_uid],
                "parcels": [{"parcel_info_uid": p.parcel_info_uid, "dkbm": p.dkbm,
                    "cbfbm": p.cbfbm, "is_changed": p.is_changed,
                    "change_type": p.change_type, "change_reason": p.change_reason}
                    for p in parcels if p.cbfbm == result.cbfbm],
            }

        now = datetime.now(timezone.utc)
        group_id = uuid4().hex
        new_uid = str(uuid5(NAMESPACE_URL, f"survey:{batch_id}:cbf:{new_cbfbm}"))
        template_result, template_task = results[0], tasks[0]
        result_values = {c.name: getattr(template_result, c.name) for c in SurveyCbfResult.__table__.columns if c.name not in {"id", "created_at", "updated_at"}}
        result_values.update(contractor_uid=new_uid, cbfbm=new_cbfbm,
            cbfmc=payload["newCbfmc"].strip(), cbfzjlx=head.cyzjlx, cbfzjhm=head.cyzjhm,
            cbfdz=payload["newAddress"].strip(), cbfcysl=len(members), survey_status="surveyed",
            result_status="added", is_changed=True, change_type="merge_household",
            change_reason=payload.get("reason"), investigator_id=current_user.id,
            investigator_name=current_user.real_name, investigated_at=now, confirmed_at=None,
            initialized_at=now, remark=f"merge_group:{group_id};sources:{','.join(source_uids)}")
        new_result = SurveyCbfResult(**result_values)
        db.add(new_result)
        db.flush()
        base_values = {c.name: getattr(template_task, c.name) for c in SurveyCbfBase.__table__.columns if c.name not in {"id", "created_at", "updated_at"}}
        base_values.update(contractor_uid=new_uid, source_cbfbm=new_cbfbm, cbfbm=new_cbfbm,
            cbfmc=payload["newCbfmc"].strip(), cbfzjlx=head.cyzjlx, cbfzjhm=head.cyzjhm,
            cbfdz=payload["newAddress"].strip(), cbfcysl=len(members), result_id=new_result.id,
            task_status="surveyed", has_change=True, change_count=1, investigated_at=now,
            initialized_at=now, snapshot_at=now, initialized_from_table="merge_household",
            initialized_from_key=group_id, remark=f"merge_group:{group_id};sources:{','.join(source_uids)}")
        db.add(SurveyCbfBase(**base_values))

        for member in members:
            member.contractor_uid, member.cbfbm = new_uid, new_cbfbm
            member.is_household_head = member.member_uid == head_uid
            if member.is_household_head:
                # ⛔ 户主关系码是字典里的 `02`（户主），不是 `01`（本人）。
                member.yhzgx = HEAD_RELATION_VALUE
            member.is_changed, member.change_reason = True, payload.get("reason")
        # 合户会把 A、B 两户**各自的户主**（`yhzgx='02'`）一起带进新户，若不处理，
        # 新户里就同时存在多个"户主"（用户报的现象）。这两个人相对**新户主**的关系
        # 无从推断，写"配偶/子女"都是臆造 ⇒ 取字典里语义诚实的 `80 其他`。
        normalized = normalize_non_head_relations(members, head)
        if normalized:
            logger.info(
                "合户 %s：把 %d 名非户主成员残留的户主类关系码收敛为 80（其他）",
                new_cbfbm, normalized,
            )
        for parcel in parcels:
            parcel.cbfbm, parcel.is_changed = new_cbfbm, True
            parcel.change_type, parcel.change_reason = "merge_household", payload.get("reason")

        change_ids = {}
        for result, task in zip(results, tasks):
            record = self._create_change_record(db, batch_id, result.contractor_uid, result.cbfbm,
                change_type="merge_household",
                before_summary=source_snapshots[result.contractor_uid],
                after_summary={"action": "cancelled_after_merge", "merge_group_id": group_id,
                    "new_household": new_cbfbm, "new_contractor_uid": new_uid},
                reason=payload.get("reason"), current_user=current_user, now=now)
            change_ids[result.contractor_uid] = record.id
            result.result_status, result.cbfcysl = "cancelled", 0
            result.is_changed, result.change_type = True, "merge_household"
            result.change_reason, result.investigated_at = payload.get("reason"), now
            task.task_status, task.has_change = "deregistered", True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now
            task.remark = f"merged into new household {new_cbfbm} {payload['newCbfmc']}"
        new_record = self._create_change_record(db, batch_id, new_uid, new_cbfbm,
            change_type="merge_household", before_summary={},
            after_summary={"action": "created_after_merge", "merge_group_id": group_id,
                "source_households": old_codes, "members": member_ids,
                "household_head_member_uid": head_uid, "parcels": [p.dkbm for p in parcels]},
            reason=payload.get("reason"), current_user=current_user, now=now)
        change_ids[new_uid] = new_record.id
        self._rebuild_contractor_diffs(db, batch_id, [*source_uids, new_uid], change_ids=change_ids)
        # 参与合户的原户 result.result_status 全部转 cancelled。同分户：base 表没有
        # result_status 列，无法自动比对，只能在此手工补（⛔ 顺序必须在重建之后，
        # 否则会被 _rebuild_contractor_diffs 的 DELETE 清掉）。
        # 撤回合户时再次重建 ⇒ 这些行随之消失，净差异语义成立。
        for src_result, _src_task in zip(results, tasks):
            snapshot = source_snapshots.get(src_result.contractor_uid) or {}
            before_status = (snapshot.get("result") or {}).get("result_status")
            if before_status == "cancelled":
                continue
            db.add(SurveyChangeDiff(
                batch_id=batch_id,
                contractor_uid=src_result.contractor_uid,
                change_id=change_ids.get(src_result.contractor_uid),
                tenant_code=src_result.tenant_code,
                region_code=src_result.group_region_code or src_result.region_code or src_result.cbfbm,
                entity_type="contractor",
                entity_uid=src_result.contractor_uid,
                entity_name=src_result.cbfmc,
                field_name="result_status",
                field_label="承包方状态",
                before_value=before_status,
                after_value="cancelled",
                change_reason=payload.get("reason"),
            ))
        if not commit:
            db.flush()
            return {"queued": True}
        db.commit()
        return {"mergeGroupId": group_id, "sourceContractorUids": source_uids,
            "newHousehold": {"contractorUid": new_uid, "cbfbm": new_cbfbm, "cbfmc": payload["newCbfmc"]}}

    def rollback_merge_household(self, db: Session, batch_id: int, contractor_uid: str, current_user: User) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "当前调查批次已结束，不能撤回合户")
        source = self._get_result(db, batch_id, contractor_uid)
        self.ensure_task_write_permission(db, batch, source, current_user)
        record = db.scalars(select(SurveyChangeRecord).where(
            SurveyChangeRecord.batch_id == batch_id,
            SurveyChangeRecord.contractor_uid == contractor_uid,
            SurveyChangeRecord.change_type == "merge_household",
            SurveyChangeRecord.change_status != "rolled_back",
        ).order_by(SurveyChangeRecord.id.desc())).first()
        summary = record.after_summary if record else {}
        group_id = (summary or {}).get("merge_group_id")
        new_uid = (summary or {}).get("new_contractor_uid")
        if not group_id or not new_uid:
            raise HTTPException(400, "未找到可撤回的合户记录")
        records = db.scalars(select(SurveyChangeRecord).where(
            SurveyChangeRecord.batch_id == batch_id,
            SurveyChangeRecord.change_type == "merge_household",
            SurveyChangeRecord.change_status != "rolled_back",
        )).all()
        records = [item for item in records if (item.after_summary or {}).get("merge_group_id") == group_id]
        source_records = [item for item in records if (item.after_summary or {}).get("action") == "cancelled_after_merge"]
        new_result = self._get_result(db, batch_id, new_uid)
        if new_result.survey_status == "confirmed" or new_result.change_type != "merge_household":
            raise HTTPException(400, "合户生成的新承包方已确认或发生后续变更，不能撤回")

        restored_uids = []
        for item in source_records:
            old_result = self._get_result(db, batch_id, item.contractor_uid)
            old_task = self._get_task(db, batch_id, item.contractor_uid)
            before = item.before_summary or {}
            rs, ts = before.get("result") or {}, before.get("task") or {}
            old_result.result_status = rs.get("result_status") or "normal"
            old_result.cbfcysl = int(rs.get("cbfcysl") or 0)
            old_result.is_changed = bool(rs.get("is_changed", False))
            old_result.change_type = rs.get("change_type") or "none"
            old_result.change_reason = rs.get("change_reason")
            if old_task:
                old_task.task_status = ts.get("task_status") or "not_started"
                old_task.has_change = bool(ts.get("has_change", False))
                old_task.change_count = int(ts.get("change_count") or 0)
                old_task.remark = ts.get("remark")
            for state in before.get("members") or []:
                member = db.scalar(select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.member_uid == state["member_uid"],
                    SurveyCbfJtcyResult.contractor_uid == new_uid))
                if member:
                    member.contractor_uid, member.cbfbm = state["contractor_uid"], state["cbfbm"]
                    member.yhzgx = state.get("yhzgx") or member.yhzgx
                    member.is_household_head = bool(state.get("is_household_head", False))
                    member.is_changed = bool(state.get("is_changed", False))
                    member.change_reason = state.get("change_reason")
            for state in before.get("parcels") or []:
                rel = db.scalar(select(SurveyCbdkxxResult).where(
                    SurveyCbdkxxResult.parcel_info_uid == state["parcel_info_uid"],
                    SurveyCbdkxxResult.cbfbm == new_result.cbfbm))
                if rel:
                    rel.cbfbm = state["cbfbm"]
                    rel.is_changed = bool(state.get("is_changed", False))
                    rel.change_type = state.get("change_type") or "none"
                    rel.change_reason = state.get("change_reason")
            restored_uids.append(item.contractor_uid)
        for item in records:
            item.change_status = "rolled_back"
        db.query(SurveyChangeDiff).filter(SurveyChangeDiff.contractor_uid.in_([new_uid, *restored_uids])).delete(synchronize_session=False)
        db.query(SurveyCbfBase).filter(SurveyCbfBase.batch_id == batch_id, SurveyCbfBase.contractor_uid == new_uid).delete(synchronize_session=False)
        db.delete(new_result)
        rollback = self._create_change_record(db, batch_id, contractor_uid, source.cbfbm,
            change_type="rollback_merge_household", before_summary={"merge_group_id": group_id},
            after_summary={"action": "restored", "restored_contractor_uids": restored_uids,
                "removed_new_contractor_uid": new_uid}, reason=f"撤回合户 {record.change_no}",
            current_user=current_user, now=datetime.now(timezone.utc))
        db.flush()
        self._rebuild_contractor_diffs(db, batch_id, restored_uids,
            change_ids={uid: rollback.id for uid in restored_uids})
        db.commit()
        return {"mergeGroupId": group_id, "restoredContractorUids": restored_uids,
            "removedNewContractorUid": new_uid}
