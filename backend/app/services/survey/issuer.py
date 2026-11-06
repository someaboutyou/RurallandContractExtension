import logging
from datetime import date, datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.models.cbht import Cbht
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
            data_access_service.ensure_region_filter_in_scope(current_user, normalized_region_code)

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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调查批次已结束，不能新增")
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
        # ⛔ 落库顺序：`survey_fbf_base.result_id` 是**非空**列，此刻 result 还没有行号，
        #   所以必须先落 result 拿到 id → 回填 base.result_id → 再落 base
        #   （与 `result.py` 人工新增承包户的顺序完全一致）。
        #   2026-09-27 修：本方法原先**连 `result` 对象都没构造**，下面就写
        #   `result.result_status = ...` ⇒ 任何「新增发包方」请求都以 NameError 收场（HTTP 500），
        #   即该功能此前完全不可用。
        result = SurveyFbfResult(
            tenant_code=batch.tenant_code,
            region_code=code,
            issuer_uid=issuer_uid,
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
            initialized_at=now,
        )
        # 新建本身就是一条变化。状态由**服务端**裁定 —— 「新增并保存」的语义就是
        # 这一户已经调查过了，不能把起点值（not_surveyed）原样落库。
        result.result_status = "added"
        result.is_changed = True
        result.change_type = "add_issuer"
        result.remark = payload.get("remark")
        result.survey_status = self.resolve_saved_survey_status(None, payload.get("surveyStatus"))
        db.add(result)
        db.flush()
        # result 已拿到 id，此时才把快照行补上 result_id 并落库。
        base.result_id = result.id
        db.add(base)
        db.commit()
        return self._serialize_issuer_row(result, batch_id, 0)


    def _ensure_issuer_code_in_batch_region(self, batch, code: str) -> None:
        """发包方编码与批次区域的隶属校验 —— 从 create/update 里提炼的同一口径。"""
        region_code = batch.region_code
        if not region_code:
            return
        if len(region_code) >= 14 and code != region_code[:14]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="issuer code must equal the 14-digit batch region code")
        if len(region_code) < 14 and not code.startswith(region_code):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="issuer code is outside the batch region")


    def _issuer_contractor_codes(self, db: Session, tenant_code: str, fbfbm: str) -> set[str]:
        """该发包方名下的承包方编码全集（删除闸门口径）。

        两条关联链取并集：
          ① 地块关联 —— survey_cbdkxx_result.fbfbm（与 list_issuers 的展示计数同源）；
          ② 合同关联 —— cbht.fbfbm（地块关联可能已被 remove_parcel 移走，
             但合同还挂在这个发包方编码上；漏查会删出孤儿合同）。
        """
        parcel_codes = set(
            db.scalars(
                select(SurveyCbdkxxResult.cbfbm)
                .where(
                    SurveyCbdkxxResult.tenant_code == tenant_code,
                    SurveyCbdkxxResult.fbfbm == fbfbm,
                )
                .execution_options(skip_tenant_scope=True)
            ).all()
        )
        contract_codes = set(
            db.scalars(
                select(Cbht.cbfbm)
                .where(
                    Cbht.tenant_code == tenant_code,
                    Cbht.fbfbm == fbfbm,
                    Cbht.cbfbm.is_not(None),
                )
                .execution_options(skip_tenant_scope=True)
            ).all()
        )
        return parcel_codes | contract_codes


    def _delete_issuer_rows(self, db: Session, issuer: SurveyFbfResult) -> None:
        """删除一个发包方的快照行（survey_fbf_base）+ 成果行（survey_fbf_result）。"""
        bases = db.scalars(
            select(SurveyFbfBase)
            .where(
                SurveyFbfBase.tenant_code == issuer.tenant_code,
                SurveyFbfBase.result_id == issuer.id,
            )
            .execution_options(skip_tenant_scope=True)
        ).all()
        for base_row in bases:
            db.delete(base_row)
        db.delete(issuer)


    def delete_issuer(self, db: Session, batch_id: int, issuer_uid: str, current_user: User) -> None:
        """删除发包方调查成果。

        ⛔ 闸门在**服务端**：名下还有承包方（cbdkxx 里有挂在该 fbfbm 下的记录）就不许删 ——
        前端的 relatedContractorCount 预检只是 UX，接口必须自己拦（与权限同源原则一致）。
        """
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调查批次已结束，不能删除发包方")
        issuer = self._get_issuer(db, batch_id, issuer_uid)
        data_access_service.ensure_code_in_scope(current_user, issuer.fbfbm, detail="发包方不在当前数据权限范围内")
        # ⛔ 闸门用承包方**全集**（地块关联 ∪ 合同关联），不只看地块：
        #    地块全被移走但合同（cbht.fbfbm）还挂着的发包方，删了会留下孤儿合同。
        contractor_codes = self._issuer_contractor_codes(db, issuer.tenant_code, issuer.fbfbm)
        if contractor_codes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"该发包方下存在 {len(contractor_codes)} 个承包方，不允许删除",
            )
        self._delete_issuer_rows(db, issuer)
        db.commit()


    def merge_issuers(self, db: Session, batch_id: int, payload: dict, current_user: User) -> dict:
        """合并发包方：把被合并方的地块/承包方等关联信息刷成保留方的编码，随后删除被合并方。

        刷写范围（按「承包方编码 + 发包方」关联逐表收口）：
          ① survey_cbdkxx_result.fbfbm —— 地块/承包方关联（GIS、地块列表、导出、出表都读这里）；
          ② cbht.fbfbm —— 合同表。⛔ 必须刷：延包合同生成时 `_contract_issuer_code`
             **优先取原合同行的 fbfbm**，漏刷会让后续生成的合同写回已删除的发包方编码；
          ③ survey_cbdkxx_base.fbfbm —— **不动**（导入快照代表原貌，与 update_issuer 改码口径一致）；
          ④ fbf / issuer 主表 —— **不动**（调查域不写主数据）。

        被合并方的快照行（survey_fbf_base）与成果行（survey_fbf_result）删除。
        """
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调查批次已结束，不能合并发包方")
        keep_uid = str(payload.get("keepIssuerUid") or "").strip()
        merge_uids = [str(u).strip() for u in (payload.get("mergeIssuerUids") or []) if str(u).strip()]
        if not keep_uid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择要保留的发包方")
        if not merge_uids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择要合并的发包方")
        if keep_uid in merge_uids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="保留的发包方不能同时出现在合并列表中")
        if len(set(merge_uids)) != len(merge_uids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="合并列表中存在重复的发包方")

        keep = self._get_issuer(db, batch_id, keep_uid)
        merged_rows = [self._get_issuer(db, batch_id, uid) for uid in merge_uids]
        for item in [keep, *merged_rows]:
            data_access_service.ensure_code_in_scope(current_user, item.fbfbm, detail="发包方不在当前数据权限范围内")
            self._ensure_issuer_code_in_batch_region(batch, item.fbfbm)

        moved_parcel_count = 0
        moved_contract_count = 0
        moved_contractor_codes: set[str] = set()
        for merged in merged_rows:
            relations = db.scalars(
                select(SurveyCbdkxxResult)
                .where(
                    SurveyCbdkxxResult.tenant_code == keep.tenant_code,
                    SurveyCbdkxxResult.fbfbm == merged.fbfbm,
                )
                .execution_options(skip_tenant_scope=True)
            ).all()
            moved_parcel_count += len(relations)
            moved_contractor_codes.update(rel.cbfbm for rel in relations)
            if relations:
                db.execute(
                    update(SurveyCbdkxxResult)
                    .where(
                        SurveyCbdkxxResult.tenant_code == keep.tenant_code,
                        SurveyCbdkxxResult.fbfbm == merged.fbfbm,
                    )
                    .values(fbfbm=keep.fbfbm)
                    .execution_options(skip_tenant_scope=True, synchronize_session=False)
                )
            # 合同关联一并划转（合同可能是导入的原始合同，也可能带 survey_batch_id；
            # 发包方编码租户内唯一，这里按租户全量刷，与调查成果行的租户级唯一口径一致）
            contract_result = db.execute(
                update(Cbht)
                .where(
                    Cbht.tenant_code == keep.tenant_code,
                    Cbht.fbfbm == merged.fbfbm,
                )
                .values(fbfbm=keep.fbfbm)
                .execution_options(skip_tenant_scope=True, synchronize_session=False)
            )
            moved_contract_count += contract_result.rowcount or 0
            self._delete_issuer_rows(db, merged)
        db.commit()

        keep_contractor_count = len(self._issuer_contractor_codes(db, keep.tenant_code, keep.fbfbm))
        return {
            "keepIssuer": self._serialize_issuer_row(keep, batch_id, keep_contractor_count),
            "mergedIssuers": [
                {"issuerUid": merged.issuer_uid, "code": merged.fbfbm, "name": merged.fbfmc}
                for merged in merged_rows
            ],
            "movedParcelCount": moved_parcel_count,
            "movedContractorCount": len(moved_contractor_codes),
            "movedContractCount": moved_contract_count,
        }


    def get_issuer(self, db: Session, batch_id: int, issuer_uid: str, current_user: User) -> dict:
        issuer = self._get_issuer(db, batch_id, issuer_uid)
        data_access_service.ensure_code_in_scope(current_user, issuer.fbfbm, detail="发包方不在当前数据权限范围内")
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调查批次已结束，不能继续编辑")
        issuer = self._get_issuer(db, batch_id, issuer_uid)
        if issuer.survey_status in self.locked_survey_statuses:
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
        # ⛔ 状态由**服务端**裁定，不能写成 `payload.get("surveyStatus") or "surveyed"`：
        #   前端表单把 `surveyStatus` 当普通字段整体回传，而界面上根本没有能改它的控件
        #   ⇒ 照单全收等于把打开弹窗时读到的**起点值**（not_surveyed）原样写回，
        #   发包方成果永远停在"未调查"。判据见 `base.py::resolve_saved_survey_status`。
        issuer.survey_status = self.resolve_saved_survey_status(
            issuer.survey_status, payload.get("surveyStatus")
        )
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发包方调查成果不存在")
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

