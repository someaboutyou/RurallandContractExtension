import json
import logging
import logging
import math
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyCbfBase,
    SurveyCbfResult,
    SurveyCbdkxxResult,
    SurveyChangeRecord,
    SurveyDkResult,
    SurveyJzdResult,
    SurveyJzxResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service
from app.services.survey.parcel_geometry import SQM_PER_MU

logger = logging.getLogger(__name__)

class SurveyServiceParcelOpsMixin:
    _PARCEL_SNAPSHOT_FIELDS = (
        "parcel_uid", "tenant_code", "region_code", "bsm", "ysdm", "dkbm", "dkmc",
        "image_number", "syqxz", "dklb", "tdlylx", "dldj", "tdyt", "sfjbnt", "scmj", "dkdz",
        "dkxz", "dknz", "dkbz", "dkbzxx", "zjrxm", "survey_person", "survey_date",
        "survey_note", "check_person", "check_date", "check_opinion", "survey_status", "result_status",
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
            elif isinstance(value, (datetime, date)):
                value = value.isoformat()
            snapshot[field] = value
        return snapshot

    def _snapshot_kwargs(self, snapshot: dict, fields: tuple[str, ...]) -> dict:
        values = {field: snapshot.get(field) for field in fields}
        initialized_at = values.get("initialized_at")
        if isinstance(initialized_at, str):
            values["initialized_at"] = datetime.fromisoformat(initialized_at)
        for field in ("survey_date", "check_date"):
            value = values.get(field)
            if isinstance(value, str) and value:
                values[field] = date.fromisoformat(value)
        return values

    def update_parcel_attributes(self, db: Session, contractor_uid: str, cbfbm: str, updates: list[dict]) -> bool:
        """把「地块信息」面板上的属性编辑写回结果表。

        只改属性（名称/面积/地类/四至/指界人/备注等），不动图形与结构；
        随「保存调查结果」一起提交，由差异重建逻辑负责生成地块级变更明细。
        返回本次是否有字段实际发生变化。
        """
        optional_fields = (
            "syqxz", "tdlylx", "dkdz", "dkxz", "dknz", "dkbz", "dkbzxx", "zjrxm",
        )
        changed_any = False
        for item in updates or []:
            dkbm = str(item.get("dkbm") or "").strip()
            if not dkbm:
                continue
            relation = db.scalars(
                select(SurveyCbdkxxResult)
                .where(
                    SurveyCbdkxxResult.cbfbm == cbfbm,
                    SurveyCbdkxxResult.dkbm == dkbm,
                    SurveyCbdkxxResult.result_status != "removed",
                )
                .order_by(SurveyCbdkxxResult.id.desc())
            ).first()
            parcel = db.scalars(
                select(SurveyDkResult)
                .where(
                    SurveyDkResult.dkbm == dkbm,
                    SurveyDkResult.result_status != "removed",
                )
                .order_by(SurveyDkResult.id.desc())
            ).first()
            if parcel is None and relation is None:
                continue
            changed = False
            if parcel is not None:
                for field in ("dkmc", "dklb", "dldj", "tdyt", "sfjbnt"):
                    if field not in item:
                        continue
                    raw = item.get(field)
                    new_value = str(raw).strip() if raw not in (None, "") else ""
                    if not new_value:
                        # 非空列：空值不覆盖，避免把必填项写坏。
                        continue
                    if getattr(parcel, field) != new_value:
                        setattr(parcel, field, new_value)
                        changed = True
                for field in optional_fields:
                    if field not in item:
                        continue
                    raw = item.get(field)
                    new_value = str(raw).strip() if raw not in (None, "") else None
                    if getattr(parcel, field) != new_value:
                        setattr(parcel, field, new_value)
                        changed = True
                if item.get("scmj") is not None:
                    new_area = Decimal(str(item["scmj"]))
                    if parcel.scmj != new_area:
                        parcel.scmj = new_area
                        changed = True
                if changed:
                    parcel.is_changed = True
            if relation is not None and item.get("htmj") is not None:
                new_contract = Decimal(str(item["htmj"]))
                new_mu = (new_contract / Decimal(str(SQM_PER_MU))).quantize(Decimal("0.01"))
                if relation.htmj != new_contract or relation.htmjm != new_mu:
                    relation.htmj = new_contract
                    relation.htmjm = new_mu
                    relation.is_changed = True
                    changed = True
            changed_any = changed_any or changed
        return changed_any

    def initialize_parcel_attributes(self, db: Session, payload: dict, current_user: User) -> dict:
        """承包地块「数据初始化」（对齐 CS 版承包台账-初始数据）。

        支持初始化的子项：所有权性质、地块类别、土地利用类型、地力等级、土地用途、
        是否基本农田、确权面积（按实测/合同面积）、指界人（固定值/按户主）、地块备注；
        并可选择「仅初始化空值」与「仅处理承包地块（类别 10）」。
        """
        values = {
            field: payload.get(field)
            for field in ("syqxz", "dklb", "tdlylx", "dldj", "tdyt", "sfjbnt")
            if payload.get(field) not in (None, "")
        }
        aware_mode = payload.get("awareAreaMode")
        refer_person = str(payload.get("referPerson") or "").strip()
        refer_by_owner = bool(payload.get("referPersonByOwner"))
        init_refer = bool(refer_person or refer_by_owner)
        comment = payload.get("comment")
        init_comment = comment is not None
        initialize_null = bool(payload.get("initializeNull"))
        only_contract = bool(payload.get("onlyContractParcels"))
        if not (values or aware_mode or init_refer or init_comment):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少选择一个初始化项")

        def empty(value, empty_code: str | None = None) -> bool:
            if value is None:
                return True
            text = str(value).strip()
            return not text or (empty_code is not None and text == empty_code)

        def area_mu(value) -> Decimal | None:
            if value is None:
                return None
            return (Decimal(str(value)) / Decimal(str(SQM_PER_MU))).quantize(Decimal("0.01"))

        owner_names: dict[str, str] = {}
        processed = 0
        updated = 0
        skipped = 0
        affected_contractors: set[str] = set()
        seen: set[tuple[str, str]] = set()
        for item in payload.get("items") or []:
            cbfbm = str(item.get("cbfbm") or "").strip()
            dkbm = str(item.get("dkbm") or "").strip()
            if not cbfbm or not dkbm or (cbfbm, dkbm) in seen:
                continue
            seen.add((cbfbm, dkbm))
            data_access_service.ensure_code_in_scope(
                current_user, cbfbm, detail="承包方不在当前数据权限范围内"
            )
            relation = db.scalars(
                select(SurveyCbdkxxResult)
                .where(
                    SurveyCbdkxxResult.cbfbm == cbfbm,
                    SurveyCbdkxxResult.dkbm == dkbm,
                    SurveyCbdkxxResult.result_status != "removed",
                )
                .order_by(SurveyCbdkxxResult.id.desc())
            ).first()
            if relation is None:
                skipped += 1
                continue
            parcel = db.scalars(
                select(SurveyDkResult)
                .where(
                    SurveyDkResult.dkbm == dkbm,
                    SurveyDkResult.result_status != "removed",
                )
                .order_by(SurveyDkResult.id.desc())
            ).first()
            if parcel is None:
                skipped += 1
                continue
            if only_contract and not empty(parcel.dklb) and str(parcel.dklb) != "10":
                skipped += 1
                continue
            processed += 1
            changed = False
            for field, value in values.items():
                current = getattr(parcel, field)
                if initialize_null and not empty(current, "900" if field == "dldj" else None):
                    continue
                if current != value:
                    setattr(parcel, field, value)
                    changed = True
            if aware_mode:
                current_mu = relation.htmjm
                if not initialize_null or current_mu is None or float(current_mu) == 0:
                    if aware_mode == "actual":
                        target_mu = area_mu(parcel.scmj)
                    else:
                        target_mu = area_mu(relation.htmj)
                    if target_mu is not None and relation.htmjm != target_mu:
                        relation.htmjm = target_mu
                        relation.is_changed = True
                        changed = True
            if init_refer:
                if not initialize_null or empty(parcel.zjrxm):
                    if refer_by_owner:
                        if cbfbm not in owner_names:
                            owner_names[cbfbm] = db.scalar(
                                select(SurveyCbfResult.cbfmc)
                                .where(SurveyCbfResult.cbfbm == cbfbm)
                                .order_by(SurveyCbfResult.id.desc())
                            ) or ""
                        target_refer = owner_names[cbfbm]
                    else:
                        target_refer = refer_person
                    if target_refer and parcel.zjrxm != target_refer:
                        parcel.zjrxm = target_refer
                        changed = True
            if init_comment:
                if not initialize_null or empty(parcel.dkbzxx):
                    target_comment = (comment or "").strip() or None
                    if parcel.dkbzxx != target_comment:
                        parcel.dkbzxx = target_comment
                        changed = True
            if changed:
                parcel.is_changed = True
                relation.is_changed = True
                updated += 1
                affected_contractors.add(cbfbm)

        db.commit()
        return {
            "processed": processed,
            "updated": updated,
            "skipped": skipped,
            "contractors": len(affected_contractors),
        }

    def initialize_image_numbers(self, db: Session, payload: dict, current_user: User) -> dict:
        """图幅编号初始化（对齐 CS 版承包台账-初始数据-图幅编号）。

        按地块图形的投影坐标计算公里格网编号：
        - 1:2000 → 1km 格网；1:1000 → 500m；1:500 → 250m；
        - 默认 Y-X 顺序（CS `IsUseYX=false`），可切换 X-Y；
        - 默认取顶点 + 外接矩形角点，勾选「初始化全部图幅编号」时对长边加密取点。
        """
        scale = payload.get("scale") or "1:2000"
        scale_index, step_m, decimals = {
            "1:2000": (0, 1000.0, 1),
            "1:1000": (1, 500.0, 1),
            "1:500": (2, 250.0, 2),
        }[scale]
        use_yx = bool(payload.get("useYX"))
        initial_all = bool(payload.get("initialAll"))

        def normalize_x(value: float) -> float:
            # 数据采用带带号的高斯投影（如 39,610,254），CS 口径不含带号，先去掉百万位带号。
            if value >= 1_000_000:
                return value - math.floor(value / 1_000_000) * 1_000_000
            return value

        def grid_value(km: float) -> float:
            integer = math.floor(km)
            frac = km - integer
            if scale_index == 2:
                if frac <= 0.25:
                    frac = 0.0
                elif frac <= 0.5:
                    frac = 0.25
                elif frac <= 0.75:
                    frac = 0.5
                else:
                    frac = 0.75
            elif scale_index == 1:
                frac = 0.0 if frac <= 0.5 else 0.5
            else:
                frac = 0.0
            return integer + frac

        def sheet_code(point: tuple[float, float]) -> str:
            x_km = normalize_x(point[0]) / 1000.0
            y_km = point[1] / 1000.0
            x_text = f"{grid_value(x_km):.{decimals}f}"
            y_text = f"{grid_value(y_km):.{decimals}f}"
            return f"{x_text}-{y_text}" if use_yx else f"{y_text}-{x_text}"

        def densify(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
            result: list[tuple[float, float]] = []
            count = len(points)
            for index, point in enumerate(points):
                result.append(point)
                nxt = points[(index + 1) % count]
                dx = nxt[0] - point[0]
                dy = nxt[1] - point[1]
                length = math.hypot(dx, dy)
                if length <= step_m:
                    continue
                steps = int(length // step_m)
                for step_index in range(1, steps + 1):
                    ratio = step_index * step_m / length
                    if ratio < 1:
                        result.append((point[0] + dx * ratio, point[1] + dy * ratio))
            return result

        def geometry_points(raw: str) -> list[tuple[float, float]]:
            try:
                data = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                return []
            geometry_type = data.get("type")
            coordinates = data.get("coordinates") or []
            rings: list[list] = []
            if geometry_type == "Polygon":
                rings = coordinates
            elif geometry_type == "MultiPolygon":
                rings = [ring for polygon in coordinates for ring in polygon]
            elif geometry_type == "Point":
                return [(float(coordinates[0]), float(coordinates[1]))] if coordinates else []
            points: list[tuple[float, float]] = []
            for ring in rings:
                for coordinate in ring:
                    if isinstance(coordinate, (list, tuple)) and len(coordinate) >= 2:
                        points.append((float(coordinate[0]), float(coordinate[1])))
            return points

        processed = 0
        updated = 0
        skipped = 0
        affected_contractors: set[str] = set()
        seen: set[tuple[str, str]] = set()
        for item in payload.get("items") or []:
            cbfbm = str(item.get("cbfbm") or "").strip()
            dkbm = str(item.get("dkbm") or "").strip()
            if not cbfbm or not dkbm or (cbfbm, dkbm) in seen:
                continue
            seen.add((cbfbm, dkbm))
            data_access_service.ensure_code_in_scope(
                current_user, cbfbm, detail="承包方不在当前数据权限范围内"
            )
            relation = db.scalars(
                select(SurveyCbdkxxResult)
                .where(
                    SurveyCbdkxxResult.cbfbm == cbfbm,
                    SurveyCbdkxxResult.dkbm == dkbm,
                    SurveyCbdkxxResult.result_status != "removed",
                )
                .order_by(SurveyCbdkxxResult.id.desc())
            ).first()
            if relation is None:
                skipped += 1
                continue
            parcel = db.scalars(
                select(SurveyDkResult)
                .where(
                    SurveyDkResult.dkbm == dkbm,
                    SurveyDkResult.result_status != "removed",
                )
                .order_by(SurveyDkResult.id.desc())
            ).first()
            if parcel is None:
                skipped += 1
                continue
            raw_geometry = db.scalar(
                text("SELECT ST_AsGeoJSON(geom, 15, 0) FROM survey_dk_result WHERE id = :id"),
                {"id": parcel.id},
            )
            points = geometry_points(raw_geometry) if raw_geometry else []
            if not points:
                skipped += 1
                continue
            processed += 1
            sample = densify(points) if initial_all else list(points)
            if not initial_all:
                xs = [point[0] for point in points]
                ys = [point[1] for point in points]
                sample.extend(
                    [
                        (min(xs), min(ys)),
                        (max(xs), min(ys)),
                        (max(xs), max(ys)),
                        (min(xs), max(ys)),
                    ]
                )
            codes: list[str] = []
            for point in sample:
                code = sheet_code(point)
                if code not in codes:
                    codes.append(code)
            value = "、".join(codes)
            if value and parcel.image_number != value:
                parcel.image_number = value
                parcel.is_changed = True
                updated += 1
                affected_contractors.add(cbfbm)

        db.commit()
        return {
            "processed": processed,
            "updated": updated,
            "skipped": skipped,
            "contractors": len(affected_contractors),
        }

    def initialize_parcel_survey_info(self, db: Session, payload: dict, current_user: User) -> dict:
        """地块调查信息初始化（对齐 CS 版初始数据-调查信息）。

        支持：调查员/调查日期/调查记事、审核员/审核日期/审核意见、指界人
        （固定值或按户主），并支持「仅初始化空值」「仅处理承包地块」。
        """
        survey_date = payload.get("surveyDate")
        check_date = payload.get("checkDate")
        if survey_date and check_date and survey_date > check_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="调查日期必须小于审核日期",
            )
        text_values = {
            "survey_person": payload.get("surveyPerson"),
            "survey_note": payload.get("surveyNote"),
            "check_person": payload.get("checkPerson"),
            "check_opinion": payload.get("checkOpinion"),
        }
        text_values = {key: value for key, value in text_values.items() if value is not None}
        refer_person = str(payload.get("referPerson") or "").strip()
        refer_by_owner = bool(payload.get("referPersonByOwner"))
        init_refer = bool(refer_person or refer_by_owner)
        initialize_null = bool(payload.get("initializeNull"))
        only_contract = bool(payload.get("onlyContractParcels"))
        if not (text_values or survey_date or check_date or init_refer):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少选择一个初始化项")

        def empty(value) -> bool:
            return value is None or not str(value).strip()

        owner_names: dict[str, str] = {}
        processed = 0
        updated = 0
        skipped = 0
        affected_contractors: set[str] = set()
        seen: set[tuple[str, str]] = set()
        for item in payload.get("items") or []:
            cbfbm = str(item.get("cbfbm") or "").strip()
            dkbm = str(item.get("dkbm") or "").strip()
            if not cbfbm or not dkbm or (cbfbm, dkbm) in seen:
                continue
            seen.add((cbfbm, dkbm))
            data_access_service.ensure_code_in_scope(
                current_user, cbfbm, detail="承包方不在当前数据权限范围内"
            )
            relation = db.scalars(
                select(SurveyCbdkxxResult)
                .where(
                    SurveyCbdkxxResult.cbfbm == cbfbm,
                    SurveyCbdkxxResult.dkbm == dkbm,
                    SurveyCbdkxxResult.result_status != "removed",
                )
                .order_by(SurveyCbdkxxResult.id.desc())
            ).first()
            if relation is None:
                skipped += 1
                continue
            parcel = db.scalars(
                select(SurveyDkResult)
                .where(
                    SurveyDkResult.dkbm == dkbm,
                    SurveyDkResult.result_status != "removed",
                )
                .order_by(SurveyDkResult.id.desc())
            ).first()
            if parcel is None:
                skipped += 1
                continue
            if only_contract and not empty(parcel.dklb) and str(parcel.dklb) != "10":
                skipped += 1
                continue
            processed += 1
            changed = False
            for field, value in text_values.items():
                current = getattr(parcel, field)
                if initialize_null and not empty(current):
                    continue
                target = str(value).strip() or None
                if current != target:
                    setattr(parcel, field, target)
                    changed = True
            if survey_date is not None:
                if not initialize_null or parcel.survey_date is None:
                    if parcel.survey_date != survey_date:
                        parcel.survey_date = survey_date
                        changed = True
            if check_date is not None:
                if not initialize_null or parcel.check_date is None:
                    if parcel.check_date != check_date:
                        parcel.check_date = check_date
                        changed = True
            if init_refer:
                if not initialize_null or empty(parcel.zjrxm):
                    if refer_by_owner:
                        if cbfbm not in owner_names:
                            owner_names[cbfbm] = db.scalar(
                                select(SurveyCbfResult.cbfmc)
                                .where(SurveyCbfResult.cbfbm == cbfbm)
                                .order_by(SurveyCbfResult.id.desc())
                            ) or ""
                        target_refer = owner_names[cbfbm]
                    else:
                        target_refer = refer_person
                    if target_refer and parcel.zjrxm != target_refer:
                        parcel.zjrxm = target_refer
                        changed = True
            if changed:
                parcel.is_changed = True
                updated += 1
                affected_contractors.add(cbfbm)

        db.commit()
        return {
            "processed": processed,
            "updated": updated,
            "skipped": skipped,
            "contractors": len(affected_contractors),
        }

    def initialize_parcel_code_boundary(self, db: Session, payload: dict, current_user: User) -> dict:
        """地块编码与四至获取（对齐 CS 版初始数据）。

        - 地块编码：全部重新生成 / 重编合并部分，可从上往下从左往右排序，
          可保留原 5 位调查编码（发包方编码 + 调查编码）；
        - 四至：取括号前内容；按空间相邻关系获取周边地块并写入四至。
        """
        mode = payload.get("landCodeMode") or "none"
        sort_by_position = bool(payload.get("sortByPosition"))
        keep_survey_number = bool(payload.get("keepSurveyNumber"))
        trim_neighbor = bool(payload.get("trimNeighborNote"))
        fill_neighbors = bool(payload.get("fillNeighbors"))
        if mode not in ("all", "merge") and not trim_neighbor and not fill_neighbors:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少选择一个初始化项")

        targets: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for item in payload.get("items") or []:
            cbfbm = str(item.get("cbfbm") or "").strip()
            dkbm = str(item.get("dkbm") or "").strip()
            if not cbfbm or not dkbm or (cbfbm, dkbm) in seen:
                continue
            seen.add((cbfbm, dkbm))
            data_access_service.ensure_code_in_scope(
                current_user, cbfbm, detail="承包方不在当前数据权限范围内"
            )
            relation = db.scalars(
                select(SurveyCbdkxxResult)
                .where(
                    SurveyCbdkxxResult.cbfbm == cbfbm,
                    SurveyCbdkxxResult.dkbm == dkbm,
                    SurveyCbdkxxResult.result_status != "removed",
                )
                .order_by(SurveyCbdkxxResult.id.desc())
            ).first()
            if relation is None:
                continue
            parcel = db.scalars(
                select(SurveyDkResult)
                .where(
                    SurveyDkResult.dkbm == dkbm,
                    SurveyDkResult.result_status != "removed",
                )
                .order_by(SurveyDkResult.id.desc())
            ).first()
            if parcel is None:
                continue
            targets.append(
                {
                    "parcel": parcel,
                    "relation": relation,
                    "zone": (relation.fbfbm or dkbm[:14] or "").strip(),
                }
            )

        if not targets:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到可初始化的地块")

        def envelope(parcel: SurveyDkResult) -> tuple[float, float, float, float] | None:
            row = db.execute(
                text(
                    "SELECT ST_XMin(geom), ST_YMin(geom), ST_XMax(geom), ST_YMax(geom) "
                    "FROM survey_dk_result WHERE id = :id"
                ),
                {"id": parcel.id},
            ).first()
            if row is None or row[0] is None:
                return None
            return (float(row[0]), float(row[1]), float(row[2]), float(row[3]))

        def order_targets(items: list[dict]) -> list[dict]:
            if not sort_by_position:
                return sorted(items, key=lambda item: item["parcel"].dkbm or "")
            envs = {id(item["parcel"]): envelope(item["parcel"]) for item in items}
            with_shape = [item for item in items if envs.get(id(item["parcel"]))]
            if not with_shape:
                return sorted(items, key=lambda item: item["parcel"].dkbm or "")
            min_height = min(env[3] - env[1] for env in (envs[id(item["parcel"])] for item in with_shape))
            if min_height <= 0:
                min_height = 5.0
            min_x = min(env[0] for env in (envs[id(item["parcel"])] for item in with_shape))
            max_x = max(env[2] for env in (envs[id(item["parcel"])] for item in with_shape))
            min_y = min(env[1] for env in (envs[id(item["parcel"])] for item in with_shape))
            max_y = max(env[3] for env in (envs[id(item["parcel"])] for item in with_shape))
            row_count = max(1, int(math.ceil((max_y - min_y) / min_height)))
            ordered: list[dict] = []
            used: set[int] = set()
            for row_index in range(row_count + 1):
                band_top = max_y - row_index * min_height
                band_bottom = band_top - min_height
                candidates = []
                for item in with_shape:
                    env = envs[id(item["parcel"])]
                    key = id(item["parcel"])
                    if key in used:
                        continue
                    if env[3] >= band_bottom and env[1] <= band_top:
                        candidates.append(item)
                candidates.sort(key=lambda item: envs[id(item["parcel"])][0])
                for item in candidates:
                    ordered.append(item)
                    used.add(id(item["parcel"]))
            ordered.extend(item for item in items if id(item["parcel"]) not in used)
            _ = (min_x, max_x)
            return ordered

        zones: dict[str, list[dict]] = {}
        for item in targets:
            if item["zone"]:
                zones.setdefault(item["zone"], []).append(item)

        renumbered = 0
        renumbered_parcel_ids: set[int] = set()
        for zone, zone_items in zones.items():
            if mode not in ("all", "merge"):
                continue
            # CS 口径：地块编码按**发包方（村组）全部地块**统一处理，勾选记录只用于确定范围。
            zone_relations = db.scalars(
                select(SurveyCbdkxxResult).where(
                    SurveyCbdkxxResult.fbfbm == zone,
                    SurveyCbdkxxResult.result_status != "removed",
                )
            ).all()
            zone_dkbms = [rel.dkbm for rel in zone_relations if rel.dkbm]
            zone_dk_rows = db.scalars(
                select(SurveyDkResult)
                .where(
                    SurveyDkResult.dkbm.in_(zone_dkbms or [""]),
                    SurveyDkResult.result_status != "removed",
                )
                .order_by(SurveyDkResult.dkbm.asc(), SurveyDkResult.id.desc())
            ).all()
            dk_map: dict[str, SurveyDkResult] = {}
            for row in zone_dk_rows:
                dk_map.setdefault(row.dkbm, row)
            zone_work = [
                {"parcel": dk_map[rel.dkbm], "relation": rel, "zone": zone}
                for rel in zone_relations
                if rel.dkbm in dk_map
            ]
            if not zone_work:
                continue
            ordered = order_targets(zone_work)
            if mode == "merge":
                renovate = [
                    item for item in ordered
                    if not (item["parcel"].dkbm or "").startswith(zone)
                ]
            else:
                renovate = list(ordered)
            if not renovate:
                continue

            existing_codes = {item["parcel"].dkbm for item in zone_work if item["parcel"].dkbm}
            target_old_codes = {item["parcel"].dkbm for item in renovate}
            suffixes: set[int] = set()
            for code in existing_codes:
                if code and len(code) == 19 and code[:14] == zone and code[14:].isdigit():
                    suffixes.add(int(code[14:]))
            non_target_suffixes = {
                int(code[14:])
                for code in existing_codes
                if code not in target_old_codes
                and len(code) == 19
                and code[:14] == zone
                and code[14:].isdigit()
            }
            next_index = 1 if mode == "all" else (max(suffixes) + 1 if suffixes else 1)
            assignments: list[tuple[dict, str, str]] = []
            assigned: set[int] = set()
            for item in renovate:
                old_code = item["parcel"].dkbm or ""
                if keep_survey_number:
                    tail = old_code[14:] if len(old_code) == 19 else old_code
                    candidate = int(tail) if tail.isdigit() else next_index
                else:
                    candidate = next_index
                while candidate in non_target_suffixes or candidate in assigned:
                    candidate += 1
                new_code = f"{zone}{candidate:05d}"
                assigned.add(candidate)
                if not keep_survey_number:
                    next_index = candidate + 1
                if new_code != old_code:
                    assignments.append((item, old_code, new_code))

            if not assignments:
                continue
            # 两阶段更新，避免 (tenant_code, dkbm) 唯一约束在互换编码时瞬时冲突。
            for index, (item, _, _) in enumerate(assignments, start=1):
                # 临时编码必须保留 14 位区域前缀，否则会话钩子会按“区域越权”拒绝写入。
                temp_code = f"{zone}T{index:04d}"
                item["parcel"].dkbm = temp_code
                item["relation"].dkbm = temp_code
            db.flush()
            for item, _, new_code in assignments:
                item["parcel"].dkbm = new_code
                item["relation"].dkbm = new_code
                item["parcel"].is_changed = True
                item["relation"].is_changed = True
                item["_renumbered"] = True
                renumbered_parcel_ids.add(item["parcel"].id)
            db.flush()
            for _, old_code, new_code in assignments:
                renumbered += 1
                db.execute(
                    update(SurveyJzdResult)
                    .where(SurveyJzdResult.source_dkbm == old_code)
                    .values(source_dkbm=new_code)
                )
                db.execute(
                    update(SurveyJzxResult)
                    .where(SurveyJzxResult.source_dkbm == old_code)
                    .values(source_dkbm=new_code)
                )

        processed = 0
        updated = 0
        skipped = 0
        affected_contractors: set[str] = set()
        for item in targets:
            parcel = item["parcel"]
            relation = item["relation"]
            processed += 1
            changed = parcel.id in renumbered_parcel_ids
            if trim_neighbor:
                for field in ("dkdz", "dknz", "dkxz", "dkbz"):
                    value = getattr(parcel, field)
                    if not value:
                        continue
                    text_value = str(value)
                    for separator in ("(", "（"):
                        if separator in text_value:
                            text_value = text_value.split(separator, 1)[0].strip()
                    if text_value != value:
                        setattr(parcel, field, text_value or None)
                        changed = True
            if fill_neighbors:
                center = db.execute(
                    text(
                        "SELECT ST_X(ST_Centroid(geom)), ST_Y(ST_Centroid(geom)) "
                        "FROM survey_dk_result WHERE id = :id"
                    ),
                    {"id": parcel.id},
                ).first()
                if center is not None and center[0] is not None:
                    neighbors = db.execute(
                        text(
                            "SELECT c.cbfmc, "
                            "ST_X(ST_Centroid(d.geom)) - :tx AS dx, "
                            "ST_Y(ST_Centroid(d.geom)) - :ty AS dy "
                            "FROM survey_dk_result d "
                            "JOIN survey_cbdkxx_result r ON r.dkbm = d.dkbm AND r.tenant_code = d.tenant_code "
                            "JOIN survey_cbf_result c ON c.cbfbm = r.cbfbm AND c.tenant_code = r.tenant_code "
                            "WHERE d.tenant_code = :tenant AND d.id <> :pid "
                            "AND d.result_status <> 'removed' "
                            "AND ST_Intersects(d.geom, ST_Buffer((SELECT geom FROM survey_dk_result WHERE id = :pid), 0.5))"
                        ),
                        {
                            "tenant": parcel.tenant_code,
                            "pid": parcel.id,
                            "tx": center[0],
                            "ty": center[1],
                        },
                    ).all()
                    direction_names: dict[str, list[str]] = {
                        "dkdz": [], "dknz": [], "dkxz": [], "dkbz": []
                    }
                    for name, dx, dy in neighbors:
                        label = (name or "").strip()
                        if not label:
                            continue
                        if abs(float(dx)) >= abs(float(dy)):
                            field = "dkdz" if float(dx) > 0 else "dkxz"
                        else:
                            field = "dkbz" if float(dy) > 0 else "dknz"
                        if label not in direction_names[field]:
                            direction_names[field].append(label)
                    for field, names in direction_names.items():
                        if not names:
                            continue
                        target_value = "、".join(names)
                        if getattr(parcel, field) != target_value:
                            setattr(parcel, field, target_value)
                            changed = True
            if changed:
                parcel.is_changed = True
                relation.is_changed = True
                updated += 1
                affected_contractors.add(relation.cbfbm)

        db.commit()
        return {
            "processed": processed,
            "updated": updated,
            "renumbered": renumbered,
            "skipped": skipped,
            "contractors": len(affected_contractors),
        }

    @staticmethod
    def _format_area(value, decimals: int, round_mode: str):
        if value is None:
            return None
        if round_mode == "cut":
            factor = 10**decimals
            return math.trunc(float(value) * factor) / factor
        quantum = Decimal(1).scaleb(-decimals)
        return float(
            Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
        )

    def calculate_parcel_areas(self, db: Session, payload: dict, current_user: User) -> dict:
        """面积量算（CS 初始数据-面积量算）：平面面积 × 0.0015 → 亩。"""
        decimals = int(payload.get("decimals", 2))
        round_mode = payload.get("roundMode") or "round"
        to_actual = bool(payload.get("toActualArea"))
        to_aware = bool(payload.get("toAwareArea"))
        if not (to_actual or to_aware):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择面积量算方式")

        processed = 0
        updated = 0
        skipped = 0
        affected_contractors: set[str] = set()
        seen: set[tuple[str, str]] = set()
        for item in payload.get("items") or []:
            cbfbm = str(item.get("cbfbm") or "").strip()
            dkbm = str(item.get("dkbm") or "").strip()
            if not cbfbm or not dkbm or (cbfbm, dkbm) in seen:
                continue
            seen.add((cbfbm, dkbm))
            data_access_service.ensure_code_in_scope(
                current_user, cbfbm, detail="承包方不在当前数据权限范围内"
            )
            relation = db.scalars(
                select(SurveyCbdkxxResult)
                .where(
                    SurveyCbdkxxResult.cbfbm == cbfbm,
                    SurveyCbdkxxResult.dkbm == dkbm,
                    SurveyCbdkxxResult.result_status != "removed",
                )
                .order_by(SurveyCbdkxxResult.id.desc())
            ).first()
            if relation is None:
                skipped += 1
                continue
            parcel = db.scalars(
                select(SurveyDkResult)
                .where(
                    SurveyDkResult.dkbm == dkbm,
                    SurveyDkResult.result_status != "removed",
                )
                .order_by(SurveyDkResult.id.desc())
            ).first()
            if parcel is None:
                skipped += 1
                continue
            area_m2 = db.scalar(
                text("SELECT ST_Area(geom) FROM survey_dk_result WHERE id = :id"),
                {"id": parcel.id},
            )
            if area_m2 is None:
                skipped += 1
                continue
            processed += 1
            area_mu = self._format_area(float(area_m2) * 0.0015, decimals, round_mode)
            changed = False
            if to_actual and area_mu is not None:
                new_scmj = Decimal(str(area_mu * 666.6666667)).quantize(Decimal("0.01"))
                if parcel.scmj != new_scmj:
                    parcel.scmj = new_scmj
                    parcel.is_changed = True
                    changed = True
            if to_aware and area_mu is not None:
                new_mu = Decimal(str(area_mu)).quantize(Decimal("0.01"))
                if relation.htmjm != new_mu:
                    relation.htmjm = new_mu
                    relation.is_changed = True
                    changed = True
            if changed:
                updated += 1
                affected_contractors.add(cbfbm)

        db.commit()
        return {
            "processed": processed,
            "updated": updated,
            "skipped": skipped,
            "contractors": len(affected_contractors),
        }

    def truncate_parcel_areas(self, db: Session, payload: dict, current_user: User) -> dict:
        """面积截取（CS 初始数据-面积截取）：按小数位整理实测/确权/二轮合同面积。"""
        decimals = int(payload.get("decimals", 2))
        round_mode = payload.get("roundMode") or "round"
        to_actual = bool(payload.get("actualArea"))
        to_aware = bool(payload.get("awareArea"))
        to_table = bool(payload.get("tableArea"))
        if not (to_actual or to_aware or to_table):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择面积截取项")

        divisor = Decimal(str(SQM_PER_MU))
        processed = 0
        updated = 0
        skipped = 0
        affected_contractors: set[str] = set()
        seen: set[tuple[str, str]] = set()
        for item in payload.get("items") or []:
            cbfbm = str(item.get("cbfbm") or "").strip()
            dkbm = str(item.get("dkbm") or "").strip()
            if not cbfbm or not dkbm or (cbfbm, dkbm) in seen:
                continue
            seen.add((cbfbm, dkbm))
            data_access_service.ensure_code_in_scope(
                current_user, cbfbm, detail="承包方不在当前数据权限范围内"
            )
            relation = db.scalars(
                select(SurveyCbdkxxResult)
                .where(
                    SurveyCbdkxxResult.cbfbm == cbfbm,
                    SurveyCbdkxxResult.dkbm == dkbm,
                    SurveyCbdkxxResult.result_status != "removed",
                )
                .order_by(SurveyCbdkxxResult.id.desc())
            ).first()
            if relation is None:
                skipped += 1
                continue
            parcel = db.scalars(
                select(SurveyDkResult)
                .where(
                    SurveyDkResult.dkbm == dkbm,
                    SurveyDkResult.result_status != "removed",
                )
                .order_by(SurveyDkResult.id.desc())
            ).first()
            if parcel is None:
                skipped += 1
                continue
            processed += 1
            changed = False
            if to_actual and parcel.scmj is not None:
                current_mu = float(Decimal(str(parcel.scmj)) / divisor)
                new_mu = self._format_area(current_mu, decimals, round_mode)
                new_scmj = Decimal(str(new_mu * 666.6666667)).quantize(Decimal("0.01"))
                if parcel.scmj != new_scmj:
                    parcel.scmj = new_scmj
                    parcel.is_changed = True
                    changed = True
            if to_aware and relation.htmjm is not None:
                new_mu = self._format_area(float(relation.htmjm), decimals, round_mode)
                new_value = Decimal(str(new_mu)).quantize(Decimal(1).scaleb(-decimals))
                if relation.htmjm != new_value:
                    relation.htmjm = new_value
                    relation.is_changed = True
                    changed = True
            if to_table and relation.yhtmjm is not None:
                new_mu = self._format_area(float(relation.yhtmjm), decimals, round_mode)
                new_value = Decimal(str(new_mu)).quantize(Decimal(1).scaleb(-decimals))
                if relation.yhtmjm != new_value:
                    relation.yhtmjm = new_value
                    relation.is_changed = True
                    changed = True
            if changed:
                updated += 1
                affected_contractors.add(cbfbm)

        db.commit()
        return {
            "processed": processed,
            "updated": updated,
            "skipped": skipped,
            "contractors": len(affected_contractors),
        }

    def analyze_basic_farmland(self, db: Session, payload: dict, current_user: User) -> dict:
        """基本农田分析（对齐 CS 版初始数据-基本农田）。

        以勾选地块与永久基本农田保护图斑（``yjjbntbhtb``）做空间相交分析：
        相交 → 是否基本农田 = 是（1），否则 = 否（0）。
        """
        layer_total = db.scalar(text('SELECT count(*) FROM public.yjjbntbhtb')) or 0
        layer_srid = db.scalar(
            text('SELECT ST_SRID("Shape") FROM public.yjjbntbhtb WHERE "Shape" IS NOT NULL LIMIT 1')
        )
        if not layer_total or layer_srid is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="未获得基本农田保护图斑数据",
            )

        processed = 0
        updated = 0
        yes_count = 0
        no_count = 0
        skipped = 0
        affected_contractors: set[str] = set()
        seen: set[tuple[str, str]] = set()
        for item in payload.get("items") or []:
            cbfbm = str(item.get("cbfbm") or "").strip()
            dkbm = str(item.get("dkbm") or "").strip()
            if not cbfbm or not dkbm or (cbfbm, dkbm) in seen:
                continue
            seen.add((cbfbm, dkbm))
            data_access_service.ensure_code_in_scope(
                current_user, cbfbm, detail="承包方不在当前数据权限范围内"
            )
            relation = db.scalars(
                select(SurveyCbdkxxResult)
                .where(
                    SurveyCbdkxxResult.cbfbm == cbfbm,
                    SurveyCbdkxxResult.dkbm == dkbm,
                    SurveyCbdkxxResult.result_status != "removed",
                )
                .order_by(SurveyCbdkxxResult.id.desc())
            ).first()
            parcel = db.scalars(
                select(SurveyDkResult)
                .where(
                    SurveyDkResult.dkbm == dkbm,
                    SurveyDkResult.result_status != "removed",
                )
                .order_by(SurveyDkResult.id.desc())
            ).first()
            if relation is None or parcel is None:
                skipped += 1
                continue
            target_srid = db.scalar(
                text("SELECT ST_SRID(geom) FROM survey_dk_result WHERE id = :id"),
                {"id": parcel.id},
            )
            if not target_srid:
                skipped += 1
                continue
            intersects = db.scalar(
                text(
                    'SELECT EXISTS ('
                    '  SELECT 1 FROM public.yjjbntbhtb b '
                    '  WHERE b."Shape" IS NOT NULL AND ST_Intersects('
                    '    CASE '
                    '      WHEN :layer_srid = 0 THEN ST_SetSRID(b."Shape", :target_srid) '
                    '      WHEN :layer_srid = :target_srid THEN b."Shape" '
                    '      ELSE ST_Transform(b."Shape", :target_srid) '
                    '    END, '
                    '    (SELECT geom FROM survey_dk_result WHERE id = :pid)'
                    '  )'
                    ')'
                ),
                {
                    "layer_srid": int(layer_srid),
                    "target_srid": int(target_srid),
                    "pid": parcel.id,
                },
            )
            processed += 1
            new_value = "1" if intersects else "0"
            if new_value == "1":
                yes_count += 1
            else:
                no_count += 1
            if parcel.sfjbnt != new_value:
                parcel.sfjbnt = new_value
                parcel.is_changed = True
                relation.is_changed = True
                updated += 1
                affected_contractors.add(cbfbm)

        db.commit()
        return {
            "processed": processed,
            "updated": updated,
            "yes": yes_count,
            "no": no_count,
            "skipped": skipped,
            "contractors": len(affected_contractors),
        }

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
        if result.survey_status == "confirmed" or getattr(result, "is_locked", False):
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

    # ── 单条待保存操作的即时落库 ──────────────────────────────
    #
    # 背景：前端把「新增地块 / 切割生成 / 互换换入」这类操作先攒在 `pendingOperations`
    # 里，列表上只显示"预览行"，点「保存调查结果」才统一落库。
    # 问题是**界址点 / 界址线是从库里的地块图形（`survey_dk_result.geom`）推导的**，
    # 地块不落库就没有宿体，预览行点「界址点 / 界址线维护」必然被拒。
    #
    # 这个入口让用户在**地块列表的操作列**上把某一行单独落库，不必为了它把整份
    # 调查结果提交一遍（那会连带触发承包方必填校验、推进调查状态、关闭弹窗）。
    #
    # ⛔ 与 `update_result` 的边界必须守住：
    #   - 完全不写承包方主体字段（名称 / 证件 / 成员 / 发包方…）；
    #   - 不碰 `survey_status`，也就是**不推进业务状态**；
    #   - 只处理传入的这一条操作，其余待保存操作留在前端。
    # 所以它只接受 `add_parcel`：切割会连带改源地块状态、互换会动到对手方，
    # 「保存一行」对它们不是准确语义，仍应走「保存调查结果」统一提交。
    def persist_pending_operation(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        operation: dict,
        current_user: User,
        commit: bool = True,
    ) -> dict:
        op_type = (operation or {}).get("type")
        payload = (operation or {}).get("payload") or {}
        if op_type != "add_parcel":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该操作不支持单独保存，请点击「保存调查结果」统一提交",
            )
        dkbm = str(payload.get("dkbm") or "").strip()
        if not dkbm:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="地块编码不能为空，无法保存"
            )
        # ⛔ 归属判据以**库里的关联行**为准，不看 payload 里前端填的 cbfbm。
        result = self._get_result(db, batch_id, contractor_uid)
        owner = db.scalars(
            select(SurveyCbdkxxResult.cbfbm).where(
                SurveyCbdkxxResult.dkbm == dkbm,
                SurveyCbdkxxResult.result_status != "removed",
            )
        ).first()
        if owner is not None:
            if owner == result.cbfbm:
                # 幂等：同一条重复提交（前端漏移 / 用户连点两次）按成功返回。
                # 否则整体保存时会撞 `add_parcel` 里的 duplicate 校验，把整次保存打回。
                return {"dkbm": dkbm, "alreadyPersisted": True}
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"地块编码 {dkbm} 已被其他承包方占用，请更换编码后再保存",
            )
        self.add_parcel(db, batch_id, contractor_uid, payload, current_user, commit=commit)
        return {"dkbm": dkbm, "alreadyPersisted": False}

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
            # 面积单位口径（2026-11-04 统一）：库里 scmj/htmj 一律 ㎡。
            # part["areaMu"] 是几何面积（亩），落库/预览返回前换算成 ㎡。
            # 切割设置里人工改过的合同面积（definitions[index].htmj，前端已按 ㎡ 提交）优先采用。
            area_sqm = round(float(part["areaMu"]) * SQM_PER_MU, 2)
            definition_htmj = None
            if index < len(definitions):
                definition_htmj = (definitions[index] or {}).get("htmj")
            generated.append({
                "dkbm": dkbm,
                "dkmc": dkmc,
                "scmj": area_sqm,
                "htmj": round(float(definition_htmj), 2) if definition_htmj else area_sqm,
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
        if result.survey_status == "confirmed" or getattr(result, "is_locked", False):
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
            # newScmj 口径为 ㎡（2026-11-04 统一）；old_area（scmj 列）同为 ㎡，比较口径一致。
            new_scmj = float(payload.get("newScmj") or 0)
            if new_scmj <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split area is required")
            if payload.get("splitDirection") or self._parse_edge_index(payload.get("edgeIndex")) is not None:
                split_preview = self._split_row_geometry_by_direction(
                    db,
                    old_parcel.id,
                    payload.get("splitDirection"),
                    new_scmj / SQM_PER_MU,
                    edge_index=self._parse_edge_index(payload.get("edgeIndex")),
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
                "split_edge_index": self._parse_edge_index(payload.get("edgeIndex")),
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
        if result.survey_status == "confirmed" or getattr(result, "is_locked", False):
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")
        # 任务归属：只有名下有这一户的人（或批次创建人 / 管理员）能改。
        self.ensure_task_write_permission(db, batch, result, current_user)
        now = datetime.now(timezone.utc)

        target_uid = payload["targetContractorUid"]
        target_result = self._get_result(db, batch_id, target_uid)
        if target_result.survey_status == "confirmed" or getattr(target_result, "is_locked", False):
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

        # 互换会**覆盖**地块原有的变更态（is_changed / change_type / change_reason）。
        # 撤回互换时必须按原值还原，否则净未变的地块撤回后仍挂着 swap 系的 change_type，
        # 界面上 parcelStatusLabel() 就会落到 `isChanged → "变更"`，把「已撤回」显示成「变更」。
        # 与 remove/split 的 source_* 快照是同一套约定，区别只在于互换一次动多块地，
        # 所以按 dkbm 存成 map；且两户各存一份**完整**快照 —— 撤回可能由任意一侧发起，
        # 各存一份就不必再去对手方那条记录里拼原值。
        pre_swap_states: dict[str, dict] = {}

        def capture_relation_state(rel: SurveyCbdkxxResult) -> None:
            pre_swap_states[rel.dkbm] = {
                "is_changed": bool(rel.is_changed),
                "change_type": rel.change_type,
                "change_reason": rel.change_reason,
            }

        def transfer_relation(
            rel: SurveyCbdkxxResult,
            recipient_cbfbm: str,
            recipient_contract: dict,
        ) -> list[dict]:
            capture_relation_state(rel)
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
            before_summary={"swapped_out": source_dkbms, "source_relation_states": pre_swap_states},
            after_summary={"swapped_in": target_dkbms, "counterparty": target_result.cbfbm},
            reason=reason,
            current_user=current_user, now=now,
        )
        db.flush()

        # 閸欐ê瀵茬拋鏉跨秿閿涘牏娲伴弽鍥ㄦ煙閿?
        target_record = self._create_change_record(
            db, batch_id, target_uid, target_result.cbfbm,
            change_type=change_type,
            before_summary={"swapped_out": target_dkbms, "source_relation_states": pre_swap_states},
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

        rollback_reason = (payload.get("reason") or "").strip() or f"撤回互换 {change.change_no}"
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

        # 互换已经退回去了 ⇒ 地块上的变更态也要还原成互换前的样子，否则「撤回互换」
        # 会把两块净未变的地显示成「变更」（change_type 仍是 rollback_swap_parcels）。
        # 原值取自**本户这条互换记录**的快照（swap_parcels 写入时两户各存一份完整快照）。
        restore_states = (change.before_summary or {}).get("source_relation_states") or {}
        touched_dkbms = [*source_dkbms, *target_dkbms]
        # 注意：互换退回去之后，source_dkbms 已归属对手方、target_dkbms 已归属本户，
        # 所以这里只能按 dkbm 定位，不能再用 cbfbm 过滤。
        touched_relations = db.scalars(
            select(SurveyCbdkxxResult).where(SurveyCbdkxxResult.dkbm.in_(touched_dkbms))
        ).all()
        touched_relation_by_code = {row.dkbm: row for row in touched_relations}
        for dkbm in touched_dkbms:
            relation = touched_relation_by_code.get(dkbm)
            if relation is None:
                continue
            state = restore_states.get(dkbm) if isinstance(restore_states, dict) else None
            if not isinstance(state, dict):
                # 老数据兼容：本次修复之前写入的互换记录没有快照（线上只有 873/874 一类）。
                # 只有当地块现在的变更态**就是互换本身留下的**，才敢断定互换前是「未变更」；
                # 若它挂着别的变更类型（说明互换之外还有动作），保持现状不动，避免抹掉别人的变更。
                if relation.change_type not in {"swap_parcels", "rollback_swap_parcels"}:
                    continue
                logger.warning(
                    "撤回互换 %s：地块 %s 缺少互换前快照，按未变更还原（原 change_type=%s）",
                    change.change_no, dkbm, relation.change_type,
                )
                state = {"is_changed": False, "change_type": "none", "change_reason": None}
            relation.is_changed = bool(state.get("is_changed"))
            relation.change_type = state.get("change_type") or "none"
            relation.change_reason = state.get("change_reason")

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
        if result.survey_status == "confirmed" or getattr(result, "is_locked", False):
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
