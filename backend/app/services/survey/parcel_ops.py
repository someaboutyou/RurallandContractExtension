import logging
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyCbfBase,
    SurveyCbfResult,
    SurveyCbdkxxResult,
    SurveyChangeRecord,
    SurveyDkResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service

logger = logging.getLogger(__name__)

class SurveyServiceParcelOpsMixin:
    _PARCEL_SNAPSHOT_FIELDS = (
        "parcel_uid", "tenant_code", "region_code", "bsm", "ysdm", "dkbm", "dkmc",
        "syqxz", "dklb", "tdlylx", "dldj", "tdyt", "sfjbnt", "scmj", "dkdz",
        "dkxz", "dknz", "dkbz", "dkbzxx", "zjrxm", "survey_status", "result_status",
        "is_changed", "change_type", "change_reason", "source_import_batch_id",
        "source_import_row_id", "last_import_batch_id", "last_import_row_id", "initialized_at",
        "remark",
    )
    _RELATION_SNAPSHOT_FIELDS = (
        "parcel_info_uid", "tenant_code", "region_code", "dkbm", "fbfbm", "cbfbm",
        "cbjyqqdfs", "htmj", "cbhtbm", "lzhtbm", "cbjyqzbm", "yhtmj", "htmjm",
        "yhtmjm", "sfqqqg", "survey_status", "result_status", "is_changed", "change_type",
        "change_reason", "source_import_batch_id", "source_import_row_id", "last_import_batch_id",
        "last_import_row_id", "initialized_at", "remark",
    )

    def _snapshot_model(self, item, fields: tuple[str, ...]) -> dict:
        snapshot = {}
        for field in fields:
            value = getattr(item, field, None)
            if field in {"scmj", "htmj", "yhtmj", "htmjm", "yhtmjm"} and value is not None:
                value = str(value)
            elif isinstance(value, datetime):
                value = value.isoformat()
            snapshot[field] = value
        return snapshot

    def _snapshot_kwargs(self, snapshot: dict, fields: tuple[str, ...]) -> dict:
        values = {field: snapshot.get(field) for field in fields}
        initialized_at = values.get("initialized_at")
        if isinstance(initialized_at, str):
            values["initialized_at"] = datetime.fromisoformat(initialized_at)
        return values

    def _snapshot_parcel_geometry(self, db: Session, parcel_id: int) -> dict | None:
        value = db.scalar(text("SELECT ST_AsGeoJSON(ST_Transform(geom, 4326)) FROM survey_dk_result WHERE id = :id"), {"id": parcel_id})
        if not value:
            return None
        import json
        return json.loads(value)

    def _restore_parcel_snapshot(self, db: Session, snapshot: dict, geometry: dict | None) -> SurveyDkResult:
        parcel = SurveyDkResult(**self._snapshot_kwargs(snapshot, self._PARCEL_SNAPSHOT_FIELDS))
        db.add(parcel)
        db.flush()
        if geometry:
            self._write_survey_dk_geometry(db, "survey_dk_result", parcel.id, geometry, 4326)
        return parcel

    def _restore_relation_snapshot(self, db: Session, snapshot: dict) -> SurveyCbdkxxResult:
        relation = SurveyCbdkxxResult(**self._snapshot_kwargs(snapshot, self._RELATION_SNAPSHOT_FIELDS))
        db.add(relation)
        db.flush()
        return relation

    def add_parcel(
        self, db: Session, batch_id: int, contractor_uid: str,
        payload: dict, current_user: User,
        commit: bool = True,
    ) -> dict:
        # repaired docstring
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

        # 閺屻儲澹橀崣鎴濆瘶閺傜櫢绱欐禒搴″嚒閺堝婀撮崸妤€鍙х化璁宠厬閼惧嘲褰囬敍灞惧灗娴犲孩澹欓崠鍛煙娴狅絿鐖滈幒銊ヮ嚤閿?
        existing_parcel = db.scalars(
            select(SurveyCbdkxxResult.fbfbm).where(
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status != "removed",
            ).limit(1)
        ).first()
        fbfbm = existing_parcel or result.cbfbm[:14]
        geometry = self._normalize_geojson_geometry(payload.get("geometry"))
        geometry_source_srid = int(payload.get("geometrySourceSrid") or 4326)
        duplicate_dkbm = db.scalar(
            select(SurveyDkResult.id).where(
                SurveyDkResult.dkbm == payload["dkbm"],
                SurveyDkResult.result_status != "removed",
            ).limit(1)
        )
        if duplicate_dkbm:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"parcel code already exists: {payload['dkbm']}")
        if geometry is not None:
            area_mu = self._measure_geojson_area_mu(db, geometry, geometry_source_srid)
            if area_mu is None or area_mu <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parcel geometry is invalid")
            overlaps = self._find_database_geometry_conflicts(
                db,
                batch.tenant_code,
                geometry,
                geometry_source_srid,
            )
            if overlaps:
                overlap_text = "、".join(item.get("dkbm") or "-" for item in overlaps[:3])
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"parcel geometry overlaps existing parcels: {overlap_text}",
                )

        parcel_uid = str(uuid4())
        parcel_info_uid = str(uuid4())
        scmj = payload["scmj"]

        # 閸掓稑缂?SurveyDkResult
        dk_result = SurveyDkResult(
            parcel_uid=parcel_uid,
            ysdm=result.cbfbm[:6] or "000000",
            dkbm=payload["dkbm"],
            dkmc=payload["dkmc"],
            syqxz=payload.get("syqxz", "10"),
            dklb=payload["dklb"],
            tdlylx=payload.get("tdlylx", "001"),
            dldj=payload["dldj"],
            tdyt=payload["tdyt"],
            sfjbnt=payload.get("sfjbnt", "1"),
            scmj=scmj,
            dkdz=payload.get("dkdz"),
            dkxz=payload.get("dkxz"),
            dknz=payload.get("dknz"),
            dkbz=payload.get("dkbz"),
            dkbzxx=payload.get("dkbzxx"),
            survey_status="surveyed",
            result_status="added",
            is_changed=True,
            change_type="add_parcel",
            change_reason=payload.get("reason"),
            initialized_at=now,
        )
        db.add(dk_result)
        db.flush()
        if geometry is not None:
            self._write_survey_dk_geometry(db, "survey_dk_result", dk_result.id, geometry, geometry_source_srid)

        # 閸掓稑缂?SurveyCbdkxxResult
        cbdkxx = SurveyCbdkxxResult(
            parcel_info_uid=parcel_info_uid,
            dkbm=payload["dkbm"],
            fbfbm=fbfbm,
            cbfbm=result.cbfbm,
            cbjyqqdfs=payload.get("cbjyqqdfs", "001"),
            htmj=payload.get("htmj") or scmj,
            cbhtbm=payload.get("cbhtbm") or "",
            lzhtbm=payload.get("lzhtbm"),
            cbjyqzbm=payload.get("cbjyqzbm") or "",
            yhtmj=payload.get("yhtmj"),
            htmjm=payload.get("htmjm"),
            yhtmjm=payload.get("yhtmjm"),
            sfqqqg=payload.get("sfqqqg"),
            survey_status="surveyed",
            result_status="added",
            is_changed=True,
            change_type="add_parcel",
            change_reason=payload.get("reason"),
            initialized_at=now,
        )
        db.add(cbdkxx)

        # 閸欐ê瀵茬拋鏉跨秿
        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="add_parcel",
            before_summary={"parcels_count": db.scalar(
                select(func.count(SurveyCbdkxxResult.id)).where(
                    SurveyCbdkxxResult.cbfbm == result.cbfbm,
                )
            ) or 0},
            after_summary={"action": "add_parcel", "dkbm": payload["dkbm"], "scmj": scmj},
            reason=payload.get("reason"),
            current_user=current_user, now=now,
        )
        db.flush()

        # 閺囧瓨鏌婃禒璇插
        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now

        result.investigated_at = now
        if not commit:
            db.flush()
            return {"queued": True}
        self._rebuild_contractor_diffs(db, batch_id, [contractor_uid], change_ids={contractor_uid: None})
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def _prepare_split_generated_parcels(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        result: SurveyCbfResult,
        source_parcel: SurveyDkResult,
        split_mode: str,
        payload: dict,
        parts: list[dict],
        current_user: User,
    ) -> list[dict]:
        definitions = payload.get("generatedParcels") or []
        part_count = len(parts)
        if part_count < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split must generate at least two parcels")

        if definitions and len(definitions) > part_count:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="generated parcel count does not match split result")

        if not definitions:
            first_code = str(payload.get('newDkbm') or '').strip()
            first_name = str(payload.get('newDkmc') or '').strip()
            if first_code and first_name:
                definitions = [{
                    'dkbm': first_code,
                    'dkmc': first_name,
                }]

        next_code_info = self.generate_next_parcel_code(db, batch_id, contractor_uid, current_user)
        prefix = str(next_code_info.get("prefix") or "").strip()
        sequence = int(next_code_info.get("sequence") or 1)
        existing_codes = set(
            db.scalars(
                select(SurveyDkResult.dkbm).where(
                    SurveyDkResult.tenant_code == result.tenant_code,
                ).execution_options(skip_tenant_scope=True)
            ).all()
        )
        used_codes: set[str] = set()

        def next_auto_code() -> str:
            nonlocal sequence
            while True:
                candidate = f"{prefix}{sequence:05d}" if prefix else str(sequence)
                sequence += 1
                if candidate not in existing_codes and candidate not in used_codes:
                    return candidate

        generated: list[dict] = []
        base_name = str((definitions[0].get("dkmc") if definitions else None) or source_parcel.dkmc or "切割地块").strip() or "切割地块"
        for index, part in enumerate(parts):
            if index < len(definitions):
                item = definitions[index] or {}
                dkbm = str(item.get("dkbm") or "").strip()
                dkmc = str(item.get("dkmc") or "").strip()
                if not dkbm or not dkmc:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="generated parcel code and name are required")
            else:
                dkbm = next_auto_code()
                dkmc = f"{base_name}{index + 1}"
            if dkbm in used_codes or dkbm in existing_codes:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"parcel code already exists: {dkbm}")
            used_codes.add(dkbm)
            generated.append({
                "dkbm": dkbm,
                "dkmc": dkmc,
                "scmj": round(float(part["areaMu"]), 2),
                "htmj": round(float(part["areaMu"]), 2),
                "geometry": part["geometry"],
            })

        if split_mode == "area" and len(generated) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="direction split must generate two current parcels")
        return generated

    def split_parcel(
        self, db: Session, batch_id: int, contractor_uid: str,
        payload: dict, current_user: User,
        commit: bool = True,
    ) -> dict:
        # repaired docstring
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

        # 閺屻儲澹橀崢鐔锋勾閸ф鍙ч懕?
        dkbm = payload["dkbm"]
        old_relation = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm == dkbm,
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ).first()
        if old_relation is None:
            raise HTTPException(404, "原地块关联不存在")

        # 閺屻儲澹橀崢鐔锋勾閸?
        old_parcel = db.scalars(
            select(SurveyDkResult)
            .where(
                SurveyDkResult.dkbm == old_relation.dkbm,
                SurveyDkResult.result_status.notin_(("removed", "split_source")),
            )
            .order_by(SurveyDkResult.id.desc())
        ).first()
        if old_parcel is None:
            raise HTTPException(404, "原地块不存在")

        split_mode = str(payload.get("splitMode") or "area").strip().lower()
        old_area = float(old_parcel.scmj or 0)
        split_preview = None
        if split_mode == "geometry":
            split_preview = self._split_row_geometry_by_shape(
                db,
                old_parcel.id,
                payload.get("splitGeometry"),
                int(payload.get("geometrySourceSrid") or 4326),
            )
        else:
            new_scmj = float(payload.get("newScmj") or 0)
            if new_scmj <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split area is required")
            if payload.get("splitDirection"):
                split_preview = self._split_row_geometry_by_direction(
                    db,
                    old_parcel.id,
                    payload.get("splitDirection"),
                    new_scmj,
                )
            else:
                if new_scmj >= old_area:
                    raise HTTPException(400, f"切割面积({new_scmj})不能大于等于原地块面积({old_area})")
        split_parts = split_preview["parts"] if split_preview else []
        generated_parcels = self._prepare_split_generated_parcels(
            db,
            batch_id,
            contractor_uid,
            result,
            old_parcel,
            split_mode,
            payload,
            split_parts,
            current_user,
        )

        # 閸戝繐鐨崢鐔锋勾閸ф娼扮粔?
        # Save original status before modifying
        original_result_status = old_parcel.result_status
        original_change_type = old_parcel.change_type
        original_change_reason = old_parcel.change_reason
        original_is_changed = old_parcel.is_changed
        source_parcel_snapshot = self._snapshot_model(old_parcel, self._PARCEL_SNAPSHOT_FIELDS)
        source_relation_snapshot = self._snapshot_model(old_relation, self._RELATION_SNAPSHOT_FIELDS)
        source_geometry = self._snapshot_parcel_geometry(db, old_parcel.id)

        for item in generated_parcels:
            new_parcel = SurveyDkResult(
                parcel_uid=str(uuid4()),
                ysdm=old_parcel.ysdm,
                dkbm=item["dkbm"],
                dkmc=item["dkmc"],
                syqxz=old_parcel.syqxz,
                dklb=old_parcel.dklb,
                tdlylx=old_parcel.tdlylx,
                dldj=old_parcel.dldj,
                tdyt=old_parcel.tdyt,
                sfjbnt=old_parcel.sfjbnt,
                scmj=item["scmj"],
                dkdz=old_parcel.dkdz,
                dkxz=old_parcel.dkxz,
                dknz=old_parcel.dknz,
                dkbz=f"由 {old_parcel.dkbm} 切割生成",
                survey_status="surveyed",
                result_status="split_generated",
                is_changed=True,
                change_type="split_parcel",
                change_reason=payload.get("reason"),
                initialized_at=now,
            )
            db.add(new_parcel)
            db.flush()
            self._write_survey_dk_geometry(
                db,
                "survey_dk_result",
                new_parcel.id,
                item["geometry"],
                4326,
            )

            new_relation = SurveyCbdkxxResult(
                parcel_info_uid=str(uuid4()),
                dkbm=item["dkbm"],
                fbfbm=old_relation.fbfbm,
                cbfbm=result.cbfbm,
                cbjyqqdfs=old_relation.cbjyqqdfs,
                htmj=item["htmj"],
                cbhtbm=old_relation.cbhtbm,
                lzhtbm=old_relation.lzhtbm,
                cbjyqzbm=old_relation.cbjyqzbm,
                sfqqqg=old_relation.sfqqqg,
                survey_status="surveyed",
                result_status="split_generated",
                is_changed=True,
                change_type="split_parcel",
                change_reason=payload.get("reason"),
                initialized_at=now,
            )
            db.add(new_relation)

        # 閸欐ê瀵茬拋鏉跨秿
        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="split_parcel",
            before_summary={
                "dkbm": old_parcel.dkbm,
                "original_area": old_area,
                "source_result_status": original_result_status,
                "source_change_type": original_change_type,
                "source_change_reason": original_change_reason,
                "source_is_changed": original_is_changed,
                "source_parcel": source_parcel_snapshot,
                "source_relation": source_relation_snapshot,
                "source_geometry": source_geometry,
            },
            after_summary={
                "action": "split_parcel",
                "split_mode": split_mode,
                "split_direction": payload.get("splitDirection"),
                "original_dkbm": old_parcel.dkbm,
                "generated_count": len(generated_parcels),
                "generated_parcels": [
                    {
                        "dkbm": item["dkbm"],
                        "dkmc": item["dkmc"],
                        "area": item["scmj"],
                    }
                    for item in generated_parcels
                ],
            },
            reason=payload.get("reason"),
            current_user=current_user, now=now,
        )
        db.flush()

        # result 表只保存当前有效数据；源地块的完整内容已经进入变更快照。
        db.delete(old_relation)
        db.delete(old_parcel)

        # 閺囧瓨鏌婃禒璇插
        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now

        result.investigated_at = now
        if not commit:
            db.flush()
            return {"queued": True}
        self._rebuild_contractor_diffs(db, batch_id, [contractor_uid], change_ids={contractor_uid: None})
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def swap_parcels(
        self, db: Session, batch_id: int, contractor_uid: str,
        payload: dict, current_user: User,
        commit: bool = True,
        change_type: str = "swap_parcels",
    ) -> dict:
        # repaired docstring
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

        target_uid = payload["targetContractorUid"]
        target_result = self._get_result(db, batch_id, target_uid)
        if target_result.survey_status == "confirmed":
            raise HTTPException(400, "目标承包方已确认")
        if target_uid == contractor_uid:
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, target_result.cbfbm, detail="out of scope")
        # 互换是**两户同时被改**：只校验本户会留下「把别人家的地块换走」的越权口子。
        self.ensure_task_write_permission(db, batch, target_result, current_user)
        source_group = result.group_region_code or (result.cbfbm[:14] if result.cbfbm else "")
        target_group = target_result.group_region_code or (target_result.cbfbm[:14] if target_result.cbfbm else "")
        if source_group and target_group and source_group != target_group:
            raise HTTPException(400, "目标承包方只能选择本组承包方")

        source_dkbms = payload["sourceDkbms"]
        target_dkbms = payload["targetDkbms"]
        reason = payload.get("reason")
        if len(source_dkbms) != len(set(source_dkbms)) or len(target_dkbms) != len(set(target_dkbms)):
            raise HTTPException(400, "互换地块不能重复选择")

        def load_active_relations(dkbms: list[str], cbfbm: str, side: str) -> list[SurveyCbdkxxResult]:
            rows = db.scalars(
                select(SurveyCbdkxxResult).where(
                    SurveyCbdkxxResult.dkbm.in_(dkbms),
                    SurveyCbdkxxResult.cbfbm == cbfbm,
                    SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
                )
            ).all()
            by_code = {row.dkbm: row for row in rows}
            missing = [dkbm for dkbm in dkbms if dkbm not in by_code]
            if missing:
                raise HTTPException(404, f"{side}地块 {missing[0]} 不属于对应承包方")
            return [by_code[dkbm] for dkbm in dkbms]

        source_relations = load_active_relations(source_dkbms, result.cbfbm, "本方")
        target_relations = load_active_relations(target_dkbms, target_result.cbfbm, "目标方")

        relation_fields = (
            ("cbfbm", "承包方代码",),
            ("fbfbm", "发包方代码",),
            ("cbjyqqdfs", "承包经营权取得方式",),
            ("cbhtbm", "承包合同编码"),
            ("lzhtbm", "流转合同编码"),
            ("cbjyqzbm", "承包经营权证编码"),
            ("sfqqqg", "是否确权确股"),
        )
        source_contract = {
            field_name: getattr(source_relations[0], field_name)
            for field_name, _ in relation_fields
        }
        target_contract = {
            field_name: getattr(target_relations[0], field_name)
            for field_name, _ in relation_fields
        }

        def transfer_relation(
            rel: SurveyCbdkxxResult,
            recipient_cbfbm: str,
            recipient_contract: dict,
        ) -> list[dict]:
            changes = []
            for field_name, field_label in relation_fields:
                before_value = getattr(rel, field_name)
                after_value = (
                    recipient_cbfbm
                    if field_name == "cbfbm"
                    else recipient_contract[field_name]
                )
                if before_value != after_value:
                    changes.append({
                        "field_name": field_name,
                        "field_label": field_label,
                        "before_value": before_value,
                        "after_value": after_value,
                    })
                    setattr(rel, field_name, after_value)
            rel.is_changed = True
            rel.change_type = change_type
            rel.change_reason = reason
            return changes

        # 閹笛嗩攽娴滄帗宕?
        swapped_source = []
        swapped_target = []
        for rel in source_relations:
            swapped_source.append({
                "dkbm": rel.dkbm,
                "changes": transfer_relation(rel, target_result.cbfbm, target_contract),
            })

        for rel in target_relations:
            swapped_target.append({
                "dkbm": rel.dkbm,
                "changes": transfer_relation(rel, result.cbfbm, source_contract),
            })

        # 閸欐ê瀵茬拋鏉跨秿閿涘牊绨弬鐧哥礆
        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type=change_type,
            before_summary={"swapped_out": source_dkbms},
            after_summary={"swapped_in": target_dkbms, "counterparty": target_result.cbfbm},
            reason=reason,
            current_user=current_user, now=now,
        )
        db.flush()

        # 閸欐ê瀵茬拋鏉跨秿閿涘牏娲伴弽鍥ㄦ煙閿?
        target_record = self._create_change_record(
            db, batch_id, target_uid, target_result.cbfbm,
            change_type=change_type,
            before_summary={"swapped_out": target_dkbms},
            after_summary={"swapped_in": source_dkbms, "counterparty": result.cbfbm},
            reason=reason,
            current_user=current_user, now=now,
        )
        db.flush()

        # 閺囧瓨鏌婇崣灞炬煙娴犺濮?
        for uid in [contractor_uid, target_uid]:
            task = self._get_task(db, batch_id, uid)
            if task:
                task.has_change = True
                task.change_count = (task.change_count or 0) + 1
                task.investigated_at = now

        result.investigated_at = now
        target_result.investigated_at = now
        if not commit:
            db.flush()
            return {"queued": True}
        self._rebuild_contractor_diffs(
            db,
            batch_id,
            [contractor_uid, target_uid],
            change_ids={contractor_uid: None, target_uid: None},
        )
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def rollback_swap_parcels(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        change_id: int,
        payload: dict,
        current_user: User,
        commit: bool = True,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        result = self._get_result(db, batch_id, contractor_uid)
        self._ensure_editable_batch_and_result(db, result, current_user)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")

        change = db.scalars(
            select(SurveyChangeRecord)
            .where(
                SurveyChangeRecord.tenant_code == batch.tenant_code,
                SurveyChangeRecord.batch_id == batch_id,
                SurveyChangeRecord.contractor_uid == contractor_uid,
                SurveyChangeRecord.id == change_id,
            )
            .execution_options(skip_tenant_scope=True)
        ).first()
        if change is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="change record not found")
        if change.change_type != "swap_parcels":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="only saved parcel swaps can be rolled back")
        if change.change_status == "rolled_back":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="this parcel swap has already been rolled back")

        before_summary = change.before_summary or {}
        after_summary = change.after_summary or {}
        source_dkbms = [str(item).strip() for item in (after_summary.get("swapped_in") or []) if str(item).strip()]
        target_dkbms = [str(item).strip() for item in (before_summary.get("swapped_out") or []) if str(item).strip()]
        if not source_dkbms or not target_dkbms:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="saved parcel swap data is incomplete and cannot be rolled back")

        source_relations = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm.in_(source_dkbms),
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ).all()
        source_relation_by_code = {row.dkbm: row for row in source_relations}
        missing_source = [dkbm for dkbm in source_dkbms if dkbm not in source_relation_by_code]
        if missing_source:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="current parcel ownership has changed and this swap cannot be rolled back")

        target_relations = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm.in_(target_dkbms),
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ).all()
        target_relation_by_code = {row.dkbm: row for row in target_relations}
        missing_target = [dkbm for dkbm in target_dkbms if dkbm not in target_relation_by_code]
        if missing_target:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="current parcel ownership has changed and this swap cannot be rolled back")

        target_owner_codes = {target_relation_by_code[dkbm].cbfbm for dkbm in target_dkbms}
        if len(target_owner_codes) != 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="the swapped parcels are no longer held by the same contractor")
        target_cbfbm = next(iter(target_owner_codes))
        if target_cbfbm == result.cbfbm:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="the parcel swap has already been restored")

        target_task = db.scalars(
            select(SurveyCbfBase)
            .where(
                SurveyCbfBase.tenant_code == batch.tenant_code,
                SurveyCbfBase.batch_id == batch_id,
                SurveyCbfBase.cbfbm == target_cbfbm,
            )
            .order_by(SurveyCbfBase.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).first()
        if target_task is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="the counterparty of this parcel swap could not be found")
        target_result = self._get_result(db, batch_id, target_task.contractor_uid)

        # 互换要动两户，所以两户都得过归属校验：只查本户会留下
        # 「把别人家的地块换回来」这个越权口子。
        self._ensure_editable_batch_and_result(db, target_result, current_user)
        data_access_service.ensure_code_in_scope(current_user, target_result.cbfbm, detail="out of scope")

        rollback_reason = (payload.get("reason") or "").strip() or f"鎾ゅ洖浜掓崲 {change.change_no}"
        self.swap_parcels(
            db,
            batch_id,
            contractor_uid,
            {
                "targetContractorUid": target_result.contractor_uid,
                "sourceDkbms": source_dkbms,
                "targetDkbms": target_dkbms,
                "reason": rollback_reason,
            },
            current_user,
            commit=False,
            change_type="rollback_swap_parcels",
        )

        change.change_status = "rolled_back"
        counterpart_change = db.scalars(
            select(SurveyChangeRecord)
            .where(
                SurveyChangeRecord.tenant_code == batch.tenant_code,
                SurveyChangeRecord.batch_id == batch_id,
                SurveyChangeRecord.contractor_uid == target_result.contractor_uid,
                SurveyChangeRecord.change_type == "swap_parcels",
                SurveyChangeRecord.change_status != "rolled_back",
            )
            .order_by(SurveyChangeRecord.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        for item in counterpart_change:
            item_before = item.before_summary or {}
            item_after = item.after_summary or {}
            item_swapped_out = [str(code).strip() for code in (item_before.get("swapped_out") or []) if str(code).strip()]
            item_swapped_in = [str(code).strip() for code in (item_after.get("swapped_in") or []) if str(code).strip()]
            item_counterparty = str(item_after.get("counterparty") or "").strip()
            if (
                item_swapped_out == source_dkbms
                and item_swapped_in == target_dkbms
                and item_counterparty == result.cbfbm
            ):
                item.change_status = "rolled_back"
                break

        if not commit:
            db.flush()
            return {"queued": True}

        self._rebuild_contractor_diffs(
            db,
            batch_id,
            [contractor_uid, target_result.contractor_uid],
            change_ids={contractor_uid: None, target_result.contractor_uid: None},
        )
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def rollback_split_parcel(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        change_id: int,
        payload: dict,
        current_user: User,
        commit: bool = True,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        result = self._get_result(db, batch_id, contractor_uid)
        self._ensure_editable_batch_and_result(db, result, current_user)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")

        change = db.scalars(
            select(SurveyChangeRecord)
            .where(
                SurveyChangeRecord.tenant_code == batch.tenant_code,
                SurveyChangeRecord.batch_id == batch_id,
                SurveyChangeRecord.contractor_uid == contractor_uid,
                SurveyChangeRecord.id == change_id,
            )
            .execution_options(skip_tenant_scope=True)
        ).first()
        if change is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="change record not found")
        if change.change_type != "split_parcel":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="only saved parcel splits can be rolled back")
        if change.change_status == "rolled_back":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="this parcel split has already been rolled back")

        before_summary = change.before_summary or {}
        after_summary = change.after_summary or {}
        source_dkbm = str(before_summary.get("dkbm") or after_summary.get("original_dkbm") or "").strip()
        generated_items = after_summary.get("generated_parcels") or []
        generated_dkbms = [str(item.get("dkbm") or "").strip() for item in generated_items if str(item.get("dkbm") or "").strip()]
        if not generated_dkbms:
            legacy_dkbm = str(after_summary.get("new_dkbm") or "").strip()
            if legacy_dkbm:
                generated_dkbms = [legacy_dkbm]
        if not source_dkbm or not generated_dkbms:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="saved parcel split data is incomplete and cannot be rolled back")

        source_parcel_snapshot = before_summary.get("source_parcel")
        source_relation_snapshot = before_summary.get("source_relation")
        if not source_parcel_snapshot or not source_relation_snapshot:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="saved parcel split does not contain a restorable source snapshot")
        source_exists = db.scalar(select(SurveyDkResult.id).where(SurveyDkResult.dkbm == source_dkbm).limit(1))
        if source_exists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="the source parcel code is already in use and cannot be restored")

        generated_relations = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm.in_(generated_dkbms),
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ).all()
        generated_relation_by_code = {item.dkbm: item for item in generated_relations}
        missing_relations = [dkbm for dkbm in generated_dkbms if dkbm not in generated_relation_by_code]
        if missing_relations:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="some generated parcels are no longer current and this split cannot be rolled back")

        generated_parcels = db.scalars(
            select(SurveyDkResult).where(
                SurveyDkResult.dkbm.in_(generated_dkbms),
                SurveyDkResult.result_status.notin_(("removed", "split_source")),
            )
        ).all()
        generated_parcel_by_code = {item.dkbm: item for item in generated_parcels}
        missing_parcels = [dkbm for dkbm in generated_dkbms if dkbm not in generated_parcel_by_code]
        if missing_parcels:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="some generated parcel geometries are no longer current and this split cannot be rolled back")

        rollback_reason = (payload.get("reason") or "").strip() or f"撤回切割 {change.change_no}"
        for dkbm in generated_dkbms:
            relation = generated_relation_by_code[dkbm]
            parcel = generated_parcel_by_code[dkbm]
            db.delete(relation)
            db.delete(parcel)

        db.flush()
        self._restore_parcel_snapshot(db, source_parcel_snapshot, before_summary.get("source_geometry"))
        self._restore_relation_snapshot(db, source_relation_snapshot)

        rollback_record = self._create_change_record(
            db,
            batch_id,
            contractor_uid,
            result.cbfbm,
            change_type="rollback_split_parcel",
            before_summary={
                "original_change_id": change.id,
                "source_dkbm": source_dkbm,
                "generated_dkbms": generated_dkbms,
            },
            after_summary={
                "action": "rollback_split_parcel",
                "source_dkbm": source_dkbm,
                "generated_dkbms": generated_dkbms,
            },
            reason=rollback_reason,
            current_user=current_user,
            now=datetime.now(timezone.utc),
        )
        db.add(rollback_record)

        change.change_status = "rolled_back"

        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = datetime.now(timezone.utc)
        result.investigated_at = datetime.now(timezone.utc)

        if not commit:
            db.flush()
            return {"queued": True}

        self._rebuild_contractor_diffs(db, batch_id, [contractor_uid], change_ids={contractor_uid: None})
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def remove_parcel(
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

        dkbm = payload["dkbm"]

        # 查找承包方-地块关联
        relation = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm == dkbm,
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ).first()
        if relation is None:
            raise HTTPException(404, "未找到对应的承包地块关联信息")

        # 查找地块
        parcel = db.scalars(
            select(SurveyDkResult).where(
                SurveyDkResult.dkbm == dkbm,
            )
        ).first()

        before_parcels_count = db.scalar(
            select(func.count(SurveyCbdkxxResult.id)).where(
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ) or 0
        previous_result_status = relation.result_status
        previous_change_type = relation.change_type
        previous_change_reason = relation.change_reason
        previous_is_changed = relation.is_changed
        relation_snapshot = self._snapshot_model(relation, self._RELATION_SNAPSHOT_FIELDS)
        parcel_snapshot = self._snapshot_model(parcel, self._PARCEL_SNAPSHOT_FIELDS) if parcel else None
        parcel_geometry = self._snapshot_parcel_geometry(db, parcel.id) if parcel else None

        db.delete(relation)
        if parcel:
            remaining_relation = db.scalar(
                select(func.count(SurveyCbdkxxResult.id)).where(
                    SurveyCbdkxxResult.dkbm == dkbm,
                    SurveyCbdkxxResult.id != relation.id,
                    SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
                )
            ) or 0
            if remaining_relation == 0:
                db.delete(parcel)

        # 创建变更记录
        record = self._create_change_record(
            db, batch_id, contractor_uid, result.cbfbm,
            change_type="remove_parcel",
            before_summary={
                "parcels_count": before_parcels_count,
                "dkbm": dkbm,
                "source_result_status": previous_result_status,
                "source_change_type": previous_change_type,
                "source_change_reason": previous_change_reason,
                "source_is_changed": previous_is_changed,
                "relation": relation_snapshot,
                "parcel": parcel_snapshot,
                "geometry": parcel_geometry,
            },
            after_summary={
                "action": "remove_parcel",
                "dkbm": dkbm,
                "parcels_count": before_parcels_count - 1,
            },
            reason=payload.get("reason"),
            current_user=current_user, now=now,
        )
        db.flush()

        # 更新任务状态
        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = now

        result.investigated_at = now
        if not commit:
            db.flush()
            return {"queued": True}
        self._rebuild_contractor_diffs(db, batch_id, [contractor_uid], change_ids={contractor_uid: None})
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)

    def rollback_remove_parcel(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        change_id: int,
        payload: dict,
        current_user: User,
        commit: bool = True,
    ) -> dict:
        """撤回已保存的地块移除操作"""
        batch = self._ensure_batch(db, batch_id)
        result = self._get_result(db, batch_id, contractor_uid)
        self._ensure_editable_batch_and_result(db, result, current_user)
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")

        change = db.scalars(
            select(SurveyChangeRecord)
            .where(
                SurveyChangeRecord.tenant_code == batch.tenant_code,
                SurveyChangeRecord.batch_id == batch_id,
                SurveyChangeRecord.contractor_uid == contractor_uid,
                SurveyChangeRecord.id == change_id,
            )
            .execution_options(skip_tenant_scope=True)
        ).first()
        if change is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="change record not found")
        if change.change_type != "remove_parcel":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="only saved parcel removals can be rolled back")
        if change.change_status == "rolled_back":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="this parcel removal has already been rolled back")

        after_summary = change.after_summary or {}
        dkbm = str(after_summary.get("dkbm") or "").strip()
        if not dkbm:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="saved removal data is incomplete and cannot be rolled back")

        before_summary = change.before_summary or {}
        # 恢复值只能取自 remove_parcel 写进 before_summary 的 source_* 快照。
        # 早期实现在下面的 before_summary / after_summary 里直接引用了
        # previous_result_status 等四个本地变量，但它们在本函数里从未赋值
        # ⇒ 每次撤销移除都 NameError ⇒ 整次保存 500 回滚，"撤销移除"100% 不可用。
        previous_result_status = str(before_summary.get("source_result_status") or "normal").strip() or "normal"
        previous_change_type = str(before_summary.get("source_change_type") or "none").strip() or "none"
        previous_change_reason = before_summary.get("source_change_reason")
        previous_is_changed = bool(before_summary.get("source_is_changed"))
        rollback_reason = (payload.get("reason") or "").strip() or f"撤回移除 {change.change_no}"
        relation_snapshot = before_summary.get("relation")
        if not relation_snapshot:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="saved parcel removal does not contain a restorable relation snapshot")
        if db.scalar(select(SurveyCbdkxxResult.id).where(
            SurveyCbdkxxResult.dkbm == dkbm,
            SurveyCbdkxxResult.cbfbm == result.cbfbm,
        ).limit(1)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="the parcel relation already exists and cannot be restored")

        parcel_snapshot = before_summary.get("parcel")
        if parcel_snapshot and not db.scalar(select(SurveyDkResult.id).where(SurveyDkResult.dkbm == dkbm).limit(1)):
            self._restore_parcel_snapshot(db, parcel_snapshot, before_summary.get("geometry"))
        relation_snapshot = {**relation_snapshot, "cbfbm": result.cbfbm}
        self._restore_relation_snapshot(db, relation_snapshot)

        # 创建撤回变更记录
        rollback_record = self._create_change_record(
            db,
            batch_id,
            contractor_uid,
            result.cbfbm,
            change_type="rollback_remove_parcel",
            before_summary={
                "original_change_id": change.id,
                "dkbm": dkbm,
                "restored_result_status": previous_result_status,
                "restored_change_type": previous_change_type,
                "restored_change_reason": previous_change_reason,
                "restored_is_changed": previous_is_changed,
            },
            after_summary={
                "action": "rollback_remove_parcel",
                "dkbm": dkbm,
                "restored_result_status": previous_result_status,
                "restored_change_type": previous_change_type,
                "restored_change_reason": previous_change_reason,
                "restored_is_changed": previous_is_changed,
            },
            reason=rollback_reason,
            current_user=current_user,
            now=datetime.now(timezone.utc),
        )
        db.add(rollback_record)

        change.change_status = "rolled_back"

        task = self._get_task(db, batch_id, contractor_uid)
        if task:
            task.has_change = True
            task.change_count = (task.change_count or 0) + 1
            task.investigated_at = datetime.now(timezone.utc)
        result.investigated_at = datetime.now(timezone.utc)

        if not commit:
            db.flush()
            return {"queued": True}

        self._rebuild_contractor_diffs(db, batch_id, [contractor_uid], change_ids={contractor_uid: None})
        db.commit()
        return self.get_result(db, batch_id, contractor_uid, current_user)
