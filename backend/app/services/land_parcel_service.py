import json
from types import SimpleNamespace

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyCbdkxxBase,
    SurveyCbdkxxResult,
    SurveyCbfResult,
    SurveyChangeRecord,
    SurveyDkBase,
    SurveyDkResult,
    SurveyFbfResult,
)
from app.models.user import User
from app.repositories.land_parcel_repository import land_parcel_repository
from app.services.contractor_service import contractor_service
from app.services.data_access_service import data_access_service


def _format_optional_date(value) -> str | None:
    """把 date/datetime/已序列化字符串统一成 ISO 字符串。

    ⛔ 地块来源可能是 SurveyDkResult、SurveyDkBase（无调查/审核日期列）或变更快照
    （日期已经是字符串）。直接 ``.isoformat()`` 会在 base 行上 AttributeError、
    在快照字符串上再次失败，导致分割后该户地块清单接口 500。
    """
    if not value:
        return None
    if isinstance(value, str):
        return value
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else None


class LandParcelService:

    def _build_removed_parcel_change_map(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str | None,
    ) -> dict[str, dict]:
        if not contractor_uid:
            return {}
        rows = db.scalars(
            select(SurveyChangeRecord)
            .where(
                SurveyChangeRecord.batch_id == batch_id,
                SurveyChangeRecord.contractor_uid == contractor_uid,
                SurveyChangeRecord.change_status != "rolled_back",
            )
            .order_by(SurveyChangeRecord.id.desc())
        ).all()
        change_map: dict[str, dict] = {}
        for item in rows:
            before_summary = item.before_summary or {}
            after_summary = item.after_summary or {}
            if item.change_type == "swap_parcels":
                dkbms = [str(code).strip() for code in (before_summary.get("swapped_out") or []) if str(code).strip()]
            elif item.change_type == "remove_parcel":
                dkbm = str(after_summary.get("dkbm") or "").strip()
                dkbms = [dkbm] if dkbm else []
            elif item.change_type == "split_parcel":
                dkbm = str(before_summary.get("dkbm") or after_summary.get("original_dkbm") or "").strip()
                dkbms = [dkbm] if dkbm else []
            elif item.change_type == "split_household":
                dkbms = [str(code).strip() for code in (after_summary.get("moved_parcels") or []) if str(code).strip()]
            else:
                dkbms = []
            for dkbm in dkbms:
                change_map.setdefault(
                    dkbm,
                    {
                        "changeType": item.change_type,
                        "changeReason": item.change_reason,
                        # P1-5：带上原始快照。当源关联行/地块行已被物理删除时，
                        # 兜底分支需要靠它还原出 split_source 条目。
                        "beforeSummary": before_summary,
                    },
                )
        return change_map

    def get_parcels_for_contractor(
        self, db: Session, cbfbm: str, current_user: User
    ) -> list[dict]:
        data_access_service.ensure_code_in_scope(
            current_user, cbfbm, detail="承包方不在当前数据权限范围内"
        )

        cbdkxx_rows = land_parcel_repository.get_cbdkxx_by_cbfbm(db, cbfbm)
        if not cbdkxx_rows:
            return []

        cbdkxx_map = {row["dkbm"]: row for row in cbdkxx_rows}
        dkbm_list = list(cbdkxx_map.keys())

        dk_rows = land_parcel_repository.get_dk_by_codes(db, dkbm_list)

        result = []
        for dk in dk_rows:
            cbdkxx = cbdkxx_map.get(dk["dkbm"])
            geometry = None
            if dk["geometry"]:
                try:
                    geometry = json.loads(dk["geometry"])
                except (json.JSONDecodeError, TypeError):
                    pass

            result.append({
                "dkbm": dk["dkbm"],
                "dkmc": dk["dkmc"],
                "htmj": str(cbdkxx["htmj"]) if cbdkxx and cbdkxx["htmj"] is not None else None,
                "syqxz": dk["syqxz"],
                "dklb": dk["dklb"],
                "scmj": str(dk["scmj"]) if dk["scmj"] is not None else None,
                "dkdz": dk["dkdz"],
                "geometry": geometry,
            })
        return result

    def get_parcels_for_issuer(
        self, db: Session, fbfbm: str, current_user: User
    ) -> list[dict]:
        data_access_service.ensure_code_in_scope(
            current_user, fbfbm, detail="发包方不在当前数据权限范围内"
        )

        cbdkxx_rows = land_parcel_repository.get_cbdkxx_by_fbfbm(db, fbfbm)
        if not cbdkxx_rows:
            return []

        cbdkxx_map = {row["dkbm"]: row for row in cbdkxx_rows}
        dkbm_list = list(cbdkxx_map.keys())
        dk_rows = land_parcel_repository.get_dk_by_codes(db, dkbm_list)

        result = []
        for dk in dk_rows:
            cbdkxx = cbdkxx_map.get(dk["dkbm"])
            geometry = None
            if dk["geometry"]:
                try:
                    geometry = json.loads(dk["geometry"])
                except (json.JSONDecodeError, TypeError):
                    pass

            result.append({
                "dkbm": dk["dkbm"],
                "dkmc": dk["dkmc"],
                "htmj": str(cbdkxx["htmj"]) if cbdkxx and cbdkxx["htmj"] is not None else None,
                "syqxz": dk["syqxz"],
                "dklb": dk["dklb"],
                "scmj": str(dk["scmj"]) if dk["scmj"] is not None else None,
                "dkdz": dk["dkdz"],
                "fbfbm": fbfbm,
                "cbfbm": cbdkxx["cbfbm"] if cbdkxx else None,
                "geometry": geometry,
            })
        return result

    def get_survey_parcels(
        self, db: Session, batch_id: int, cbfbm: str, current_user: User
    ) -> list[dict]:
        data_access_service.ensure_code_in_scope(
            current_user, cbfbm, detail="承包方不在当前数据权限范围内"
        )

        cbdkxx_result_rows = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.cbfbm == cbfbm,
            ).order_by(SurveyCbdkxxResult.dkbm)
        ).all()
        cbdkxx_base_rows = db.scalars(
            select(SurveyCbdkxxBase).where(
                SurveyCbdkxxBase.batch_id == batch_id,
                SurveyCbdkxxBase.cbfbm == cbfbm,
            ).order_by(SurveyCbdkxxBase.dkbm)
        ).all()

        if not cbdkxx_result_rows and not cbdkxx_base_rows:
            return []

        dkbm_list = sorted({row.dkbm for row in cbdkxx_result_rows} | {row.dkbm for row in cbdkxx_base_rows})
        fbfbm_list = sorted({row.fbfbm for row in cbdkxx_result_rows if row.fbfbm} | {row.fbfbm for row in cbdkxx_base_rows if row.fbfbm})

        dk_base_rows = db.scalars(
            select(SurveyDkBase).where(
                SurveyDkBase.batch_id == batch_id,
                SurveyDkBase.dkbm.in_(dkbm_list),
            )
        ).all()
        dk_base_map = {row.dkbm: row for row in dk_base_rows}
        dk_result_rows = db.scalars(
            select(SurveyDkResult)
            .where(
                SurveyDkResult.dkbm.in_(dkbm_list),
                SurveyDkResult.result_status != "removed",
            )
            .order_by(SurveyDkResult.dkbm.asc(), SurveyDkResult.id.desc())
        ).all()
        dk_result_map = {}
        for row in dk_result_rows:
            dk_result_map.setdefault(row.dkbm, row)
        dk_geometry_map = {}
        for row in land_parcel_repository.get_dk_by_codes(db, dkbm_list):
            geometry = None
            if row["geometry"]:
                try:
                    geometry = json.loads(row["geometry"])
                except (json.JSONDecodeError, TypeError):
                    pass
            dk_geometry_map[row["dkbm"]] = geometry

        fbf_result_rows = db.scalars(
            select(SurveyFbfResult).where(
                SurveyFbfResult.fbfbm.in_(fbfbm_list),
            )
        ).all()
        fbf_map = {row.fbfbm: row for row in fbf_result_rows}

        cbf_result_row = db.scalars(
            select(SurveyCbfResult).where(
                SurveyCbfResult.cbfbm == cbfbm,
            ).order_by(SurveyCbfResult.id.desc())
        ).first()
        change_map = self._build_removed_parcel_change_map(
            db,
            batch_id,
            cbf_result_row.contractor_uid if cbf_result_row else None,
        )
        active_relation_rows = [row for row in cbdkxx_result_rows if row.result_status != "split_source"]
        historical_split_rows = [row for row in cbdkxx_result_rows if row.result_status == "split_source"]
        active_relations_by_dkbm = {row.dkbm: row for row in active_relation_rows}
        historical_relations_by_dkbm = {row.dkbm: row for row in historical_split_rows}
        base_relations_by_dkbm = {row.dkbm: row for row in cbdkxx_base_rows}
        removed_candidate_dkbms = (
            set(base_relations_by_dkbm)
            | set(change_map)
        ) - set(active_relations_by_dkbm) - set(historical_relations_by_dkbm)
        fallback_relation_rows = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm.in_(removed_candidate_dkbms or {""}),
                SurveyCbdkxxResult.result_status != "removed",
            ).order_by(SurveyCbdkxxResult.dkbm.asc(), SurveyCbdkxxResult.id.desc())
        ).all() if removed_candidate_dkbms else []
        fallback_relations_by_dkbm = {}
        for row in fallback_relation_rows:
            fallback_relations_by_dkbm.setdefault(row.dkbm, row)

        def build_item(cbdkxx, dk_source, fbf, result_status=None, is_changed=None, change_type=None, change_reason=None):
            return {
                "dkbm": cbdkxx.dkbm,
                "dkmc": dk_source.dkmc if dk_source else None,
                "image_number": getattr(dk_source, "image_number", None) if dk_source else None,
                "scmj": str(dk_source.scmj) if dk_source and dk_source.scmj is not None else None,
                "htmj": str(cbdkxx.htmj) if cbdkxx.htmj is not None else None,
                "yhtmj": str(cbdkxx.yhtmj) if cbdkxx.yhtmj is not None else None,
                "htmjm": str(cbdkxx.htmjm) if cbdkxx.htmjm is not None else None,
                "yhtmjm": str(cbdkxx.yhtmjm) if cbdkxx.yhtmjm is not None else None,
                "syqxz": dk_source.syqxz if dk_source else None,
                "dklb": dk_source.dklb if dk_source else None,
                "dldj": dk_source.dldj if dk_source else None,
                "tdyt": dk_source.tdyt if dk_source else None,
                "tdlylx": dk_source.tdlylx if dk_source else None,
                "sfjbnt": dk_source.sfjbnt if dk_source else None,
                "dkdz": dk_source.dkdz if dk_source else None,
                "dkxz": dk_source.dkxz if dk_source else None,
                "dknz": dk_source.dknz if dk_source else None,
                "dkbz": dk_source.dkbz if dk_source else None,
                "dkbzxx": dk_source.dkbzxx if dk_source else None,
                "zjrxm": dk_source.zjrxm if dk_source else None,
                "survey_person": getattr(dk_source, "survey_person", None) if dk_source else None,
                "survey_date": _format_optional_date(getattr(dk_source, "survey_date", None)) if dk_source else None,
                "survey_note": getattr(dk_source, "survey_note", None) if dk_source else None,
                "check_person": getattr(dk_source, "check_person", None) if dk_source else None,
                "check_date": _format_optional_date(getattr(dk_source, "check_date", None)) if dk_source else None,
                "check_opinion": getattr(dk_source, "check_opinion", None) if dk_source else None,
                "fbfbm": cbdkxx.fbfbm,
                "fbfmc": fbf.fbfmc if fbf else None,
                "cbjyqqdfs": cbdkxx.cbjyqqdfs,
                "cbhtbm": cbdkxx.cbhtbm,
                "cbjyqzbm": cbdkxx.cbjyqzbm,
                "lzhtbm": cbdkxx.lzhtbm,
                "sfqqqg": cbdkxx.sfqqqg,
                "cbfbm": cbdkxx.cbfbm,
                "cbfmc": cbf_result_row.cbfmc if cbf_result_row else None,
                "cbflx": cbf_result_row.cbflx if cbf_result_row else None,
                "resultStatus": result_status or cbdkxx.result_status,
                "isChanged": cbdkxx.is_changed if is_changed is None else is_changed,
                "changeType": cbdkxx.change_type if change_type is None else change_type,
                "changeReason": cbdkxx.change_reason if change_reason is None else change_reason,
                "geometry": dk_geometry_map.get(cbdkxx.dkbm),
            }

        result = []
        for cbdkxx in active_relation_rows:
            dk_result = dk_result_map.get(cbdkxx.dkbm)
            dk_base = dk_base_map.get(cbdkxx.dkbm)
            dk_source = dk_result or dk_base
            fbf = fbf_map.get(cbdkxx.fbfbm)
            result.append(build_item(cbdkxx, dk_source, fbf))

        for cbdkxx in historical_split_rows:
            dk_result = dk_result_map.get(cbdkxx.dkbm)
            dk_base = dk_base_map.get(cbdkxx.dkbm)
            dk_source = dk_result or dk_base
            fbf = fbf_map.get(cbdkxx.fbfbm)
            result.append(build_item(cbdkxx, dk_source, fbf, result_status="split_source"))

        for dkbm in sorted(removed_candidate_dkbms):
            base_relation = base_relations_by_dkbm.get(dkbm)
            fallback_relation = fallback_relations_by_dkbm.get(dkbm)
            change_meta = change_map.get(dkbm, {})
            relation_source = base_relation or fallback_relation
            dk_result = dk_result_map.get(dkbm)
            dk_base = dk_base_map.get(dkbm)
            dk_source = dk_result or dk_base
            geometry = dk_geometry_map.get(dkbm)
            if relation_source is None:
                # P1-5：切割“本批次新增的地块”时，源关联行与源地块行都被 split_parcel 收尾
                # 物理删除，基线里也没有它 ⇒ 只剩变更快照。此处用快照补出 split_source 条目，
                # 否则前端 find(resultStatus === "split_source") 落空，撤回已保存切割失效。
                # 其余场景（如移除新增地块）保持原有 continue 行为，不改变列表语义。
                if change_meta.get("changeType") != "split_parcel":
                    continue
                snapshot = change_meta.get("beforeSummary") or {}
                snapshot_relation = snapshot.get("source_relation")
                if not snapshot_relation:
                    continue
                relation_source = SimpleNamespace(**snapshot_relation)
                snapshot_parcel = snapshot.get("source_parcel")
                if dk_source is None and snapshot_parcel:
                    dk_source = SimpleNamespace(**snapshot_parcel)
                if geometry is None:
                    geometry = snapshot.get("source_geometry")
            fbf = fbf_map.get(relation_source.fbfbm)
            result.append({
                "dkbm": relation_source.dkbm,
                "dkmc": dk_source.dkmc if dk_source else None,
                "image_number": getattr(dk_source, "image_number", None) if dk_source else None,
                "scmj": str(dk_source.scmj) if dk_source and dk_source.scmj is not None else None,
                "htmj": str(relation_source.htmj) if relation_source.htmj is not None else None,
                "yhtmj": str(relation_source.yhtmj) if relation_source.yhtmj is not None else None,
                "htmjm": str(relation_source.htmjm) if relation_source.htmjm is not None else None,
                "yhtmjm": str(relation_source.yhtmjm) if relation_source.yhtmjm is not None else None,
                "syqxz": dk_source.syqxz if dk_source else None,
                "dklb": dk_source.dklb if dk_source else None,
                "dldj": dk_source.dldj if dk_source else None,
                "tdyt": dk_source.tdyt if dk_source else None,
                "tdlylx": dk_source.tdlylx if dk_source else None,
                "sfjbnt": dk_source.sfjbnt if dk_source else None,
                "dkdz": dk_source.dkdz if dk_source else None,
                "dkxz": dk_source.dkxz if dk_source else None,
                "dknz": dk_source.dknz if dk_source else None,
                "dkbz": dk_source.dkbz if dk_source else None,
                "dkbzxx": dk_source.dkbzxx if dk_source else None,
                "zjrxm": dk_source.zjrxm if dk_source else None,
                "survey_person": getattr(dk_source, "survey_person", None) if dk_source else None,
                "survey_date": _format_optional_date(getattr(dk_source, "survey_date", None)) if dk_source else None,
                "survey_note": getattr(dk_source, "survey_note", None) if dk_source else None,
                "check_person": getattr(dk_source, "check_person", None) if dk_source else None,
                "check_date": _format_optional_date(getattr(dk_source, "check_date", None)) if dk_source else None,
                "check_opinion": getattr(dk_source, "check_opinion", None) if dk_source else None,
                "fbfbm": relation_source.fbfbm,
                "fbfmc": fbf.fbfmc if fbf else None,
                "cbjyqqdfs": relation_source.cbjyqqdfs,
                "cbhtbm": relation_source.cbhtbm,
                "cbjyqzbm": relation_source.cbjyqzbm,
                "lzhtbm": relation_source.lzhtbm,
                "sfqqqg": relation_source.sfqqqg,
                "cbfbm": cbfbm,
                "cbfmc": cbf_result_row.cbfmc if cbf_result_row else None,
                "cbflx": cbf_result_row.cbflx if cbf_result_row else None,
                "resultStatus": "split_source" if change_meta.get("changeType") == "split_parcel" else "removed",
                "isChanged": True,
                "changeType": change_meta.get("changeType") or "remove_parcel",
                "changeReason": change_meta.get("changeReason"),
                "geometry": geometry,
            })

        result.sort(key=lambda item: (item.get("dkbm") or "", 1 if item.get("resultStatus") in {"removed", "split_source"} else 0))
        return result

    def get_parcels_overview(
        self,
        db: Session,
        page: int,
        page_size: int,
        keyword: str | None,
        current_user: User,
        batch_id: int | None = None,
    ) -> dict:
        """以承包方为单位汇总承包地块（当前结果态）。

        供「建库中心 > 承包地块」树形清单使用：父行为承包方，子行为其地块。
        面积字段沿用 NY/T 2539 口径：htmj/scmj 为平方米，htmjm/yhtmjm 为亩。
        """
        stmt = select(SurveyCbfResult)
        count_stmt = select(func.count(SurveyCbfResult.id))
        if batch_id is not None:
            # 批次口径：只显示该批次快照（survey_cbf_base）里的承包户。
            # ⛔ 先取成 Python 列表再 in_()，不要写 in_(select(...)) 子查询：
            # 全局 with_loader_criteria（区域/租户 scope）会二次注入到子查询里，
            # 命中集合被静默缩小。见 skill sqlalchemy-loader-criteria-subquery。
            uids = contractor_service.batch_contractor_uids(db, batch_id)
            if not uids:
                return {"items": [], "total": 0, "page": page, "pageSize": page_size}
            condition = SurveyCbfResult.contractor_uid.in_(uids)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            # 发包方命中：先由「承包地块关系 + 发包方结果表」找出对应的承包方编码。
            issuer_cbfbm = (
                select(SurveyCbdkxxResult.cbfbm)
                .join(
                    SurveyFbfResult,
                    SurveyFbfResult.fbfbm == SurveyCbdkxxResult.fbfbm,
                )
                .where(
                    or_(
                        SurveyFbfResult.fbfbm.ilike(pattern),
                        SurveyFbfResult.fbfmc.ilike(pattern),
                    )
                )
            )
            condition = or_(
                SurveyCbfResult.cbfbm.ilike(pattern),
                SurveyCbfResult.cbfmc.ilike(pattern),
                SurveyCbfResult.cbfbm.in_(issuer_cbfbm),
            )
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        total = db.scalar(count_stmt) or 0
        contractors = db.scalars(
            stmt.order_by(SurveyCbfResult.cbfbm.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        if not contractors:
            return {"items": [], "total": total, "page": page, "pageSize": page_size}

        cbfbm_list = [contractor.cbfbm for contractor in contractors]

        relation_rows = db.scalars(
            select(SurveyCbdkxxResult)
            .where(
                SurveyCbdkxxResult.cbfbm.in_(cbfbm_list),
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
            .order_by(SurveyCbdkxxResult.cbfbm.asc(), SurveyCbdkxxResult.dkbm.asc())
        ).all()
        relations_by_cbfbm: dict[str, list] = {}
        for relation in relation_rows:
            relations_by_cbfbm.setdefault(relation.cbfbm, []).append(relation)

        dkbm_list = sorted({relation.dkbm for relation in relation_rows})
        dk_map: dict[str, object] = {}
        if dkbm_list:
            dk_rows = db.scalars(
                select(SurveyDkResult)
                .where(
                    SurveyDkResult.dkbm.in_(dkbm_list),
                    SurveyDkResult.result_status != "removed",
                )
                .order_by(SurveyDkResult.dkbm.asc(), SurveyDkResult.id.desc())
            ).all()
            for row in dk_rows:
                dk_map.setdefault(row.dkbm, row)

        fbfbm_list = sorted({relation.fbfbm for relation in relation_rows if relation.fbfbm})
        fbf_map: dict[str, object] = {}
        if fbfbm_list:
            for row in db.scalars(
                select(SurveyFbfResult).where(SurveyFbfResult.fbfbm.in_(fbfbm_list))
            ).all():
                fbf_map[row.fbfbm] = row

        items = []
        for index, contractor in enumerate(contractors, start=(page - 1) * page_size + 1):
            parcels = []
            for relation in relations_by_cbfbm.get(contractor.cbfbm, []):
                dk = dk_map.get(relation.dkbm)
                if dk is None:
                    continue
                fbf = fbf_map.get(relation.fbfbm)
                parcels.append(
                    {
                        "dkbm": relation.dkbm,
                        "dkmc": dk.dkmc,
                        "image_number": getattr(dk, "image_number", None),
                        "htmj": str(relation.htmj) if relation.htmj is not None else None,
                        "yhtmj": str(relation.yhtmj) if relation.yhtmj is not None else None,
                        "htmjm": str(relation.htmjm) if relation.htmjm is not None else None,
                        "yhtmjm": str(relation.yhtmjm) if relation.yhtmjm is not None else None,
                        "scmj": str(dk.scmj) if dk.scmj is not None else None,
                        "dklb": dk.dklb,
                        "tdlylx": dk.tdlylx,
                        "sfjbnt": dk.sfjbnt,
                        "dkdz": dk.dkdz,
                        "dknz": dk.dknz,
                        "dkxz": dk.dkxz,
                        "dkbz": dk.dkbz,
                        "dkbzxx": dk.dkbzxx,
                        "zjrxm": dk.zjrxm,
                        "survey_person": dk.survey_person,
                        "survey_date": dk.survey_date.isoformat() if dk.survey_date else None,
                        "survey_note": dk.survey_note,
                        "check_person": dk.check_person,
                        "check_date": dk.check_date.isoformat() if dk.check_date else None,
                        "check_opinion": dk.check_opinion,
                        "sfqqqg": relation.sfqqqg,
                        "fbfbm": relation.fbfbm,
                        "fbfmc": fbf.fbfmc if fbf else None,
                        "cbfbm": contractor.cbfbm,
                        "cbfmc": contractor.cbfmc,
                        "resultStatus": relation.result_status,
                        "isChanged": relation.is_changed,
                        "changeType": relation.change_type,
                        "changeReason": relation.change_reason,
                    }
                )
            items.append(
                {
                    "cbfbm": contractor.cbfbm,
                    "cbfmc": contractor.cbfmc,
                    "contractorUid": contractor.contractor_uid,
                    "householdNo": f"{index:04d}",
                    "parcelCount": len(parcels),
                    "parcels": parcels,
                }
            )
        return {"items": items, "total": total, "page": page, "pageSize": page_size}

    def get_nearby_survey_parcels(
        self,
        db: Session,
        batch_id: int,
        cbfbm: str,
        current_user: User,
    ) -> list[dict]:
        data_access_service.ensure_code_in_scope(
            current_user, cbfbm, detail="承包方不在当前数据权限范围内"
        )

        dkbm_list = db.scalars(
            select(SurveyCbdkxxResult.dkbm).where(
                SurveyCbdkxxResult.cbfbm == cbfbm,
                SurveyCbdkxxResult.result_status != "removed",
            )
        ).all()
        rows = land_parcel_repository.get_nearby_dk_by_codes(db, dkbm_list)

        result = []
        for row in rows:
            geometry = None
            if row["geometry"]:
                try:
                    geometry = json.loads(row["geometry"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append({
                "dkbm": row["dkbm"],
                "dkmc": row["dkmc"],
                "geometry": geometry,
            })
        return result


land_parcel_service = LandParcelService()
