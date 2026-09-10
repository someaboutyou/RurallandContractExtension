import json
import logging

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyBatch,
    SurveyCbfBase,
    SurveyCbfResult,
    SurveyCbdkxxResult,
    SurveyDkResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service

logger = logging.getLogger(__name__)

class SurveyServiceParcelGeometryMixin:
    def validate_parcel_geometry(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        payload: dict,
        current_user: User,
    ) -> dict:
        logger.info(
            "survey.validate_parcel_geometry start batch_id=%s contractor_uid=%s payload_geometry_type=%s local_parcel_count=%s",
            batch_id,
            contractor_uid,
            payload.get("geometry", {}).get("type") if isinstance(payload.get("geometry"), dict) else None,
            len(payload.get("localParcels") or []),
        )
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")

        geometry = self._normalize_geojson_geometry(payload.get("geometry"))
        if geometry is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parcel geometry is required")
        source_srid = int(payload.get("geometrySourceSrid") or 4326)
        area_mu = self._measure_geojson_area_mu(db, geometry, source_srid)
        if area_mu is None or area_mu <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parcel geometry is invalid")

        local_conflicts = self._find_local_geometry_conflicts(db, geometry, source_srid, payload.get("localParcels") or [])
        known_dkbms = [
            item.get("dkbm")
            for item in (payload.get("localParcels") or [])
            if isinstance(item, dict) and item.get("dkbm")
        ]
        db_conflicts = self._find_database_geometry_conflicts(
            db,
            batch.tenant_code,
            geometry,
            source_srid,
            exclude_dkbms=known_dkbms,
        )
        overlaps = local_conflicts + db_conflicts
        logger.info(
            "survey.validate_parcel_geometry result batch_id=%s contractor_uid=%s area_mu=%s local_conflicts=%s db_conflicts=%s valid=%s",
            batch_id,
            contractor_uid,
            area_mu,
            len(local_conflicts),
            len(db_conflicts),
            len(overlaps) == 0,
        )
        return {
            "valid": len(overlaps) == 0,
            "areaMu": area_mu,
            "overlaps": overlaps,
        }

    def generate_next_parcel_code(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        current_user: User,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")

        prefix = (result.group_region_code or result.cbfbm[:14] or batch.region_code or "")[:14]
        if not prefix:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parcel code prefix is unavailable")

        existing_codes = db.scalars(
            select(SurveyDkResult.dkbm)
            .where(
                SurveyDkResult.tenant_code == batch.tenant_code,
                SurveyDkResult.dkbm.like(f"{prefix}%"),
            )
            .execution_options(skip_tenant_scope=True)
        ).all()

        max_sequence = 0
        for code in existing_codes:
            text = str(code or "").strip()
            if len(text) < len(prefix) + 5:
                continue
            suffix = text[len(prefix) : len(prefix) + 5]
            if suffix.isdigit():
                max_sequence = max(max_sequence, int(suffix))

        next_sequence = max_sequence + 1
        return {
            "prefix": prefix,
            "sequence": next_sequence,
            "dkbm": f"{prefix}{next_sequence:05d}",
        }

    def preview_split_parcel(
        self,
        db: Session,
        batch_id: int,
        contractor_uid: str,
        payload: dict,
        current_user: User,
    ) -> dict:
        batch = self._ensure_batch(db, batch_id)
        if batch.status == "finished":
            raise HTTPException(400, "invalid operation")
        result = self._get_result(db, batch_id, contractor_uid)
        if result.survey_status == "confirmed":
            raise HTTPException(400, "invalid operation")
        data_access_service.ensure_code_in_scope(current_user, result.cbfbm, detail="out of scope")

        dkbm = payload["dkbm"]
        old_relation = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.dkbm == dkbm,
                SurveyCbdkxxResult.cbfbm == result.cbfbm,
                SurveyCbdkxxResult.result_status.notin_(("removed", "split_source")),
            )
        ).first()

        old_parcel = None
        pending_source_geometry = None
        if old_relation is not None:
            old_parcel = db.scalars(
                select(SurveyDkResult)
                .where(
                    SurveyDkResult.dkbm == old_relation.dkbm,
                    SurveyDkResult.result_status.notin_(("removed", "split_source")),
                )
                .order_by(SurveyDkResult.id.desc())
            ).first()
            if old_parcel is None:
                raise HTTPException(404, "parcel not found")
        else:
            # Parcel not in DB yet - may be a pending (unsaved) add_parcel.
            # The frontend must provide the source geometry in this case.
            src_geom = self._normalize_geojson_geometry(payload.get("sourceGeometry"))
            if src_geom is None:
                raise HTTPException(404, "parcel relation not found")
            pending_source_geometry = src_geom

        split_mode = str(payload.get("splitMode") or "area").strip().lower()
        if pending_source_geometry is not None:
            # Split a geometry that only exists in the frontend (not yet in DB).
            src_srid = int(payload.get("sourceGeometrySrid") or 4326)
            if split_mode == "geometry":
                split_result = self._split_geojson_by_shape(
                    db,
                    pending_source_geometry,
                    src_srid,
                    payload.get("splitGeometry"),
                    int(payload.get("geometrySourceSrid") or 4326),
                )
            else:
                new_scmj = float(payload.get("newScmj") or 0)
                if new_scmj <= 0:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split area is required")
                split_result = self._split_geojson_by_direction(
                    db,
                    pending_source_geometry,
                    src_srid,
                    payload.get("splitDirection"),
                    new_scmj,
                )
            # Build a minimal parcel-like object for _prepare_split_generated_parcels.
            class _PendingParcel:
                pass
            mock_parcel = _PendingParcel()
            mock_parcel.dkmc = payload.get("newDkmc") or dkbm
        else:
            if split_mode == "geometry":
                split_result = self._split_row_geometry_by_shape(
                    db,
                    old_parcel.id,
                    payload.get("splitGeometry"),
                    int(payload.get("geometrySourceSrid") or 4326),
                )
            else:
                new_scmj = float(payload.get("newScmj") or 0)
                if new_scmj <= 0:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split area is required")
                split_result = self._split_row_geometry_by_direction(
                    db,
                    old_parcel.id,
                    payload.get("splitDirection"),
                    new_scmj,
                )
            mock_parcel = old_parcel

        generated_parcels = self._prepare_split_generated_parcels(
            db,
            batch_id,
            contractor_uid,
            result,
            mock_parcel,
            split_mode,
            payload,
            split_result["parts"],
            current_user,
        )
        return {
            "sourceDkbm": dkbm,
            "splitMode": split_mode,
            "generatedParcels": generated_parcels,
        }

    def _normalize_geojson_geometry(self, geometry: dict | None) -> dict | None:
        if geometry is None:
            return None
        candidate = geometry
        if isinstance(candidate, dict) and candidate.get("type") == "Feature":
            candidate = candidate.get("geometry")
        if not isinstance(candidate, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid parcel geometry")
        geometry_type = str(candidate.get("type") or "")
        if geometry_type not in {"Polygon", "MultiPolygon"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parcel geometry must be Polygon or MultiPolygon")
        if not candidate.get("coordinates"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parcel geometry is empty")
        return candidate

    def _geojson_4527_sql(self, geojson_param: str = "geojson", srid_param: str = "source_srid") -> str:
        return (
            "ST_Multi(ST_CollectionExtract(ST_MakeValid("
            f"ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:{geojson_param}), :{srid_param}), 4527)"
            "), 3))"
        )

    def _measure_geojson_area_mu(self, db: Session, geometry: dict, source_srid: int) -> float | None:
        stmt = text(
            f"""
            WITH input_geom AS (
                SELECT {self._geojson_4527_sql()} AS geom
            )
            SELECT
                CASE
                    WHEN geom IS NULL OR ST_IsEmpty(geom) THEN NULL
                    ELSE ROUND(CAST(ST_Area(geom) / 666.6666667 AS numeric), 4)
                END AS area_mu
            FROM input_geom
            """
        )
        try:
            area_mu = db.scalar(
                stmt,
                {
                    "geojson": json.dumps(geometry, ensure_ascii=False),
                    "source_srid": int(source_srid or 4326),
                },
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid parcel geometry") from exc
        return float(area_mu) if area_mu is not None else None

    def _find_local_geometry_conflicts(self, db: Session, geometry: dict, source_srid: int, local_parcels: list[dict] | None) -> list[dict]:
        candidate_parcels = [
            {
                "dkbm": item.get("dkbm"),
                "dkmc": item.get("dkmc"),
                "cbfbm": item.get("cbfbm"),
                "cbfmc": item.get("cbfmc"),
                "geometry": self._normalize_geojson_geometry(item.get("geometry")),
            }
            for item in (local_parcels or [])
            if isinstance(item, dict) and item.get("resultStatus") != "removed" and item.get("geometry")
        ]
        if not candidate_parcels:
            return []
        stmt = text(
            """
            WITH input_geom AS (
                SELECT """
            + self._geojson_4527_sql()
            + """ AS geom
            ),
            local_parcels AS (
                SELECT
                    item->>'dkbm' AS dkbm,
                    item->>'dkmc' AS dkmc,
                    item->>'cbfbm' AS cbfbm,
                    item->>'cbfmc' AS cbfmc,
                    ST_Multi(
                        ST_CollectionExtract(
                            ST_MakeValid(
                                ST_Transform(
                                    ST_SetSRID(ST_GeomFromGeoJSON((item->'geometry')::text), 4326),
                                    4527
                                )
                            ),
                            3
                        )
                    ) AS geom
                FROM jsonb_array_elements(CAST(:local_parcels_json AS jsonb)) AS item
            )
            SELECT
                'local' AS source,
                dkbm,
                dkmc,
                cbfbm,
                cbfmc,
                ROUND(CAST(ST_Area(ST_Intersection(local_parcels.geom, input_geom.geom)) / 666.6666667 AS numeric), 4) AS overlap_area_mu
            FROM local_parcels
            CROSS JOIN input_geom
            WHERE input_geom.geom IS NOT NULL
              AND local_parcels.geom IS NOT NULL
              AND NOT ST_IsEmpty(local_parcels.geom)
              AND ST_Intersects(local_parcels.geom, input_geom.geom)
              AND NOT ST_Touches(local_parcels.geom, input_geom.geom)
            ORDER BY overlap_area_mu DESC NULLS LAST, dkbm
            LIMIT 20
            """
        )
        rows = db.execute(
            stmt,
            {
                "geojson": json.dumps(geometry, ensure_ascii=False),
                "source_srid": int(source_srid or 4326),
                "local_parcels_json": json.dumps(candidate_parcels, ensure_ascii=False),
            },
        ).mappings().all()
        return [
            {
                "source": row["source"],
                "dkbm": row["dkbm"],
                "dkmc": row["dkmc"],
                "cbfbm": row["cbfbm"],
                "cbfmc": row["cbfmc"],
                "overlapAreaMu": float(row["overlap_area_mu"]) if row["overlap_area_mu"] is not None else None,
            }
            for row in rows
        ]

    def _find_database_geometry_conflicts(
        self,
        db: Session,
        tenant_code: str,
        geometry: dict,
        source_srid: int,
        exclude_dkbms: list[str] | None = None,
    ) -> list[dict]:
        params = {
            "tenant_code": tenant_code,
            "geojson": json.dumps(geometry, ensure_ascii=False),
            "source_srid": int(source_srid or 4326),
        }
        exclude_codes = [str(code).strip() for code in (exclude_dkbms or []) if str(code).strip()]
        exclude_sql = ""
        if exclude_codes:
            placeholders = []
            for index, code in enumerate(exclude_codes):
                key = f"exclude_dkbm_{index}"
                params[key] = code
                placeholders.append(f":{key}")
            exclude_sql = f" AND dk.dkbm NOT IN ({', '.join(placeholders)})"
        stmt = text(
            f"""
            WITH input_geom AS (
                SELECT {self._geojson_4527_sql()} AS geom
            ),
            current_dk AS (
                SELECT DISTINCT ON (dkbm)
                    dkbm,
                    dkmc,
                    geom
                FROM public.survey_dk_result
                WHERE tenant_code = :tenant_code
                  AND result_status NOT IN ('removed', 'split_source')
                  AND geom IS NOT NULL
                ORDER BY dkbm, id DESC
            ),
            current_relation AS (
                SELECT DISTINCT ON (dkbm)
                    dkbm,
                    cbfbm
                FROM public.survey_cbdkxx_result
                WHERE tenant_code = :tenant_code
                  AND result_status NOT IN ('removed', 'split_source')
                ORDER BY dkbm, id DESC
            ),
            current_contractor AS (
                SELECT DISTINCT ON (cbfbm)
                    cbfbm,
                    cbfmc
                FROM public.survey_cbf_result
                WHERE tenant_code = :tenant_code
                ORDER BY cbfbm, id DESC
            )
            SELECT
                'database' AS source,
                dk.dkbm,
                dk.dkmc,
                relation.cbfbm,
                contractor.cbfmc,
                ROUND(CAST(ST_Area(ST_Intersection(dk.geom, input_geom.geom)) / 666.6666667 AS numeric), 4) AS overlap_area_mu
            FROM current_dk AS dk
            CROSS JOIN input_geom
            LEFT JOIN current_relation AS relation ON relation.dkbm = dk.dkbm
            LEFT JOIN current_contractor AS contractor ON contractor.cbfbm = relation.cbfbm
            WHERE input_geom.geom IS NOT NULL
              AND dk.geom IS NOT NULL
              AND NOT ST_IsEmpty(dk.geom)
              AND ST_Intersects(dk.geom, input_geom.geom)
              AND NOT ST_Touches(dk.geom, input_geom.geom)
              {exclude_sql}
            ORDER BY overlap_area_mu DESC NULLS LAST, dk.dkbm
            LIMIT 20
            """
        )
        rows = db.execute(stmt, params).mappings().all()
        return [
            {
                "source": row["source"],
                "dkbm": row["dkbm"],
                "dkmc": row["dkmc"],
                "cbfbm": row["cbfbm"],
                "cbfmc": row["cbfmc"],
                "overlapAreaMu": float(row["overlap_area_mu"]) if row["overlap_area_mu"] is not None else None,
            }
            for row in rows
        ]

    def _write_survey_dk_geometry(self, db: Session, table_name: str, row_id: int, geometry: dict, source_srid: int) -> None:
        stmt = text(
            f"""
            UPDATE {table_name}
            SET geom = {self._geojson_4527_sql()}
            WHERE id = :row_id
            """
        )
        try:
            db.execute(
                stmt,
                {
                    "row_id": row_id,
                    "geojson": json.dumps(geometry, ensure_ascii=False),
                    "source_srid": int(source_srid or 4326),
                },
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="failed to save parcel geometry") from exc

    def _normalize_split_geometry(self, geometry: dict | None) -> dict | None:
        if geometry is None:
            return None
        candidate = geometry
        if isinstance(candidate, dict) and candidate.get("type") == "Feature":
            candidate = candidate.get("geometry")
        if not isinstance(candidate, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid split geometry")
        geometry_type = str(candidate.get("type") or "")
        if geometry_type not in {"LineString", "MultiLineString", "Polygon", "MultiPolygon"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="split geometry must be line or polygon",
            )
        if not candidate.get("coordinates"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split geometry is empty")
        return candidate

    @staticmethod

    @staticmethod
    def _parse_geojson_text(value: str | None) -> dict | None:
        if not value:
            return None
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid split geometry result") from exc

    def _load_result_geometry_extent(self, db: Session, row_id: int) -> dict:
        row = db.execute(
            text(
                """
                SELECT
                    ST_XMin(geom) AS min_x,
                    ST_YMin(geom) AS min_y,
                    ST_XMax(geom) AS max_x,
                    ST_YMax(geom) AS max_y,
                    ST_Area(geom) AS area_sqm
                FROM survey_dk_result
                WHERE id = :row_id
                  AND geom IS NOT NULL
                  AND NOT ST_IsEmpty(geom)
                """
            ),
            {"row_id": row_id},
        ).mappings().first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="selected parcel does not have geometry",
            )
        return {
            "minX": float(row["min_x"]),
            "minY": float(row["min_y"]),
            "maxX": float(row["max_x"]),
            "maxY": float(row["max_y"]),
            "areaSqm": float(row["area_sqm"]),
        }

    @staticmethod

    @staticmethod
    def _direction_clip_bounds(direction: str, threshold: float, extent: dict) -> dict:
        min_x = extent["minX"]
        min_y = extent["minY"]
        max_x = extent["maxX"]
        max_y = extent["maxY"]
        padding = 1.0
        if direction == "east":
            return {"left": threshold, "bottom": min_y - padding, "right": max_x + padding, "top": max_y + padding}
        if direction == "west":
            return {"left": min_x - padding, "bottom": min_y - padding, "right": threshold, "top": max_y + padding}
        if direction == "south":
            return {"left": min_x - padding, "bottom": min_y - padding, "right": max_x + padding, "top": threshold}
        if direction == "north":
            return {"left": min_x - padding, "bottom": threshold, "right": max_x + padding, "top": max_y + padding}
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid split direction")

    def _measure_directional_split_area_sqm(self, db: Session, row_id: int, bounds: dict) -> float:
        area_sqm = db.scalar(
            text(
                """
                WITH source AS (
                    SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)) AS geom
                    FROM survey_dk_result
                    WHERE id = :row_id
                ),
                clip AS (
                    SELECT ST_MakeEnvelope(:left, :bottom, :right, :top, 4527) AS geom
                )
                SELECT COALESCE(
                    ST_Area(
                        ST_Multi(
                            ST_CollectionExtract(
                                ST_MakeValid(ST_Intersection(source.geom, clip.geom)),
                                3
                            )
                        )
                    ),
                    0
                )
                FROM source
                CROSS JOIN clip
                """
            ),
            {"row_id": row_id, **bounds},
        )
        return float(area_sqm or 0)

    def _split_rows_to_parts(self, rows: list[dict] | None) -> list[dict]:
        parts: list[dict] = []
        for row in rows or []:
            geometry = self._parse_geojson_text(row.get("geojson"))
            area_mu = float(row["area_mu"]) if row.get("area_mu") is not None else 0
            if geometry and area_mu > 0:
                parts.append({
                    "geometry": geometry,
                    "areaMu": round(area_mu, 4),
                })
        return parts

    def _split_row_geometry_by_direction(
        self,
        db: Session,
        row_id: int,
        direction: str,
        target_area_mu: float,
    ) -> dict:
        normalized_direction = str(direction or "").strip().lower()
        if normalized_direction not in {"east", "west", "south", "north"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid split direction")
        extent = self._load_result_geometry_extent(db, row_id)
        target_area_sqm = float(target_area_mu) * 666.6666667
        source_area_sqm = float(extent["areaSqm"])
        if target_area_sqm <= 0 or target_area_sqm >= source_area_sqm:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split area must be smaller than source parcel area")

        low = extent["minX"] if normalized_direction in {"east", "west"} else extent["minY"]
        high = extent["maxX"] if normalized_direction in {"east", "west"} else extent["maxY"]
        increasing = normalized_direction in {"west", "south"}
        for _ in range(32):
            middle = (low + high) / 2
            bounds = self._direction_clip_bounds(normalized_direction, middle, extent)
            current_area_sqm = self._measure_directional_split_area_sqm(db, row_id, bounds)
            if increasing:
                if current_area_sqm < target_area_sqm:
                    low = middle
                else:
                    high = middle
            else:
                if current_area_sqm > target_area_sqm:
                    low = middle
                else:
                    high = middle
        threshold = (low + high) / 2
        bounds = self._direction_clip_bounds(normalized_direction, threshold, extent)
        rows = db.execute(
            text(
                """
                WITH source AS (
                    SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)) AS geom
                    FROM survey_dk_result
                    WHERE id = :row_id
                ),
                clip AS (
                    SELECT ST_MakeEnvelope(:left, :bottom, :right, :top, 4527) AS geom
                ),
                fragments AS (
                    SELECT
                        0 AS part_group,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid((dump).geom), 3)) AS geom
                    FROM source
                    CROSS JOIN clip
                    CROSS JOIN LATERAL ST_Dump(
                        ST_CollectionExtract(ST_MakeValid(ST_Intersection(source.geom, clip.geom)), 3)
                    ) AS dump
                    UNION ALL
                    SELECT
                        1 AS part_group,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid((dump).geom), 3)) AS geom
                    FROM source
                    CROSS JOIN clip
                    CROSS JOIN LATERAL ST_Dump(
                        ST_CollectionExtract(ST_MakeValid(ST_Difference(source.geom, clip.geom)), 3)
                    ) AS dump
                )
                SELECT
                    part_group,
                    ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geojson,
                    ROUND(CAST(ST_Area(geom) / 666.6666667 AS numeric), 4) AS area_mu
                FROM fragments
                WHERE geom IS NOT NULL
                  AND NOT ST_IsEmpty(geom)
                ORDER BY part_group, ST_Area(geom) DESC, ST_XMin(geom), ST_YMin(geom)
                """
            ),
            {"row_id": row_id, **bounds},
        ).mappings().all()
        parts = self._split_rows_to_parts(rows)
        if len(parts) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="failed to split parcel by direction")
        return {"parts": parts}

    def _split_row_geometry_by_shape(
        self,
        db: Session,
        row_id: int,
        split_geometry: dict,
        source_srid: int,
    ) -> dict:
        normalized_geometry = self._normalize_split_geometry(split_geometry)
        if normalized_geometry is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split geometry is required")
        geometry_type = str(normalized_geometry.get("type") or "")
        params = {
            "row_id": row_id,
            "geojson": json.dumps(normalized_geometry, ensure_ascii=False),
            "source_srid": int(source_srid or 4326),
        }
        if geometry_type in {"Polygon", "MultiPolygon"}:
            stmt = text(
                f"""
                WITH source AS (
                    SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)) AS geom
                    FROM survey_dk_result
                    WHERE id = :row_id
                ),
                splitter AS (
                    SELECT ST_MakeValid({self._geojson_4527_sql()}) AS geom
                ),
                fragments AS (
                    SELECT
                        0 AS part_group,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid((dump).geom), 3)) AS geom
                    FROM source
                    CROSS JOIN splitter
                    CROSS JOIN LATERAL ST_Dump(
                        ST_CollectionExtract(ST_MakeValid(ST_Intersection(source.geom, splitter.geom)), 3)
                    ) AS dump
                    UNION ALL
                    SELECT
                        1 AS part_group,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid((dump).geom), 3)) AS geom
                    FROM source
                    CROSS JOIN splitter
                    CROSS JOIN LATERAL ST_Dump(
                        ST_CollectionExtract(ST_MakeValid(ST_Difference(source.geom, splitter.geom)), 3)
                    ) AS dump
                )
                SELECT
                    part_group,
                    ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geojson,
                    ROUND(CAST(ST_Area(geom) / 666.6666667 AS numeric), 4) AS area_mu
                FROM fragments
                WHERE geom IS NOT NULL
                  AND NOT ST_IsEmpty(geom)
                ORDER BY part_group, ST_Area(geom) DESC, ST_XMin(geom), ST_YMin(geom)
                """
            )
        else:
            stmt = text(
                f"""
                WITH source AS (
                    SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)) AS geom
                    FROM survey_dk_result
                    WHERE id = :row_id
                ),
                splitter AS (
                    SELECT ST_MakeValid(
                        ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), :source_srid), 4527)
                    ) AS geom
                ),
                fragments AS (
                    SELECT
                        0 AS part_group,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid((dump).geom), 3)) AS geom
                    FROM source
                    CROSS JOIN splitter
                    CROSS JOIN LATERAL ST_Dump(ST_Split(source.geom, splitter.geom)) AS dump
                )
                SELECT
                    part_group,
                    ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geojson,
                    ROUND(CAST(ST_Area(geom) / 666.6666667 AS numeric), 4) AS area_mu
                FROM fragments
                WHERE geom IS NOT NULL
                  AND NOT ST_IsEmpty(geom)
                ORDER BY ST_Area(geom) DESC, ST_XMin(geom), ST_YMin(geom)
                """
            )
        rows = db.execute(stmt, params).mappings().all()
        parts = self._split_rows_to_parts(rows)
        if geometry_type in {"LineString", "MultiLineString"} and len(parts) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split line does not divide the parcel")
        if len(parts) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split geometry is invalid")
        return {"parts": parts}

    def _load_geojson_geometry_extent(self, db: Session, geometry: dict, source_srid: int) -> dict:
        row = db.execute(
            text(
                f"""
                WITH src AS (
                    SELECT {self._geojson_4527_sql('src_geojson', 'src_srid')} AS geom
                )
                SELECT
                    ST_XMin(geom) AS min_x,
                    ST_YMin(geom) AS min_y,
                    ST_XMax(geom) AS max_x,
                    ST_YMax(geom) AS max_y,
                    ST_Area(geom) AS area_sqm
                FROM src
                WHERE geom IS NOT NULL AND NOT ST_IsEmpty(geom)
                """
            ),
            {"src_geojson": json.dumps(geometry, ensure_ascii=False), "src_srid": int(source_srid or 4326)},
        ).mappings().first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source geometry is invalid")
        return {
            "minX": float(row["min_x"]),
            "minY": float(row["min_y"]),
            "maxX": float(row["max_x"]),
            "maxY": float(row["max_y"]),
            "areaSqm": float(row["area_sqm"]),
        }

    def _measure_geojson_clip_area_sqm(self, db: Session, geometry: dict, source_srid: int, bounds: dict) -> float:
        area_sqm = db.scalar(
            text(
                f"""
                WITH source AS (
                    SELECT {self._geojson_4527_sql('src_geojson', 'src_srid')} AS geom
                ),
                clip AS (
                    SELECT ST_MakeEnvelope(:left, :bottom, :right, :top, 4527) AS geom
                )
                SELECT COALESCE(
                    ST_Area(
                        ST_Multi(
                            ST_CollectionExtract(
                                ST_MakeValid(ST_Intersection(source.geom, clip.geom)),
                                3
                            )
                        )
                    ),
                    0
                )
                FROM source
                CROSS JOIN clip
                """
            ),
            {"src_geojson": json.dumps(geometry, ensure_ascii=False), "src_srid": int(source_srid or 4326), **bounds},
        )
        return float(area_sqm or 0)

    def _split_geojson_by_shape(
        self,
        db: Session,
        source_geometry: dict,
        source_srid: int,
        split_geometry: dict,
        split_srid: int,
    ) -> dict:
        normalized_geometry = self._normalize_split_geometry(split_geometry)
        if normalized_geometry is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split geometry is required")
        geometry_type = str(normalized_geometry.get("type") or "")
        params = {
            "src_geojson": json.dumps(source_geometry, ensure_ascii=False),
            "src_srid": int(source_srid or 4326),
            "geojson": json.dumps(normalized_geometry, ensure_ascii=False),
            "source_srid": int(split_srid or 4326),
        }
        if geometry_type in {"Polygon", "MultiPolygon"}:
            stmt = text(
                f"""
                WITH source AS (
                    SELECT {self._geojson_4527_sql('src_geojson', 'src_srid')} AS geom
                ),
                splitter AS (
                    SELECT ST_MakeValid({self._geojson_4527_sql()}) AS geom
                ),
                fragments AS (
                    SELECT
                        0 AS part_group,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid((dump).geom), 3)) AS geom
                    FROM source
                    CROSS JOIN splitter
                    CROSS JOIN LATERAL ST_Dump(
                        ST_CollectionExtract(ST_MakeValid(ST_Intersection(source.geom, splitter.geom)), 3)
                    ) AS dump
                    UNION ALL
                    SELECT
                        1 AS part_group,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid((dump).geom), 3)) AS geom
                    FROM source
                    CROSS JOIN splitter
                    CROSS JOIN LATERAL ST_Dump(
                        ST_CollectionExtract(ST_MakeValid(ST_Difference(source.geom, splitter.geom)), 3)
                    ) AS dump
                )
                SELECT
                    part_group,
                    ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geojson,
                    ROUND(CAST(ST_Area(geom) / 666.6666667 AS numeric), 4) AS area_mu
                FROM fragments
                WHERE geom IS NOT NULL
                  AND NOT ST_IsEmpty(geom)
                ORDER BY part_group, ST_Area(geom) DESC, ST_XMin(geom), ST_YMin(geom)
                """
            )
        else:
            stmt = text(
                f"""
                WITH source AS (
                    SELECT {self._geojson_4527_sql('src_geojson', 'src_srid')} AS geom
                ),
                splitter AS (
                    SELECT ST_MakeValid(
                        ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), :source_srid), 4527)
                    ) AS geom
                ),
                fragments AS (
                    SELECT
                        0 AS part_group,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid((dump).geom), 3)) AS geom
                    FROM source
                    CROSS JOIN splitter
                    CROSS JOIN LATERAL ST_Dump(ST_Split(source.geom, splitter.geom)) AS dump
                )
                SELECT
                    part_group,
                    ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geojson,
                    ROUND(CAST(ST_Area(geom) / 666.6666667 AS numeric), 4) AS area_mu
                FROM fragments
                WHERE geom IS NOT NULL
                  AND NOT ST_IsEmpty(geom)
                ORDER BY ST_Area(geom) DESC, ST_XMin(geom), ST_YMin(geom)
                """
            )
        rows = db.execute(stmt, params).mappings().all()
        parts = self._split_rows_to_parts(rows)
        if geometry_type in {"LineString", "MultiLineString"} and len(parts) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split line does not divide the parcel")
        if len(parts) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split geometry is invalid")
        return {"parts": parts}

    def _split_geojson_by_direction(
        self,
        db: Session,
        source_geometry: dict,
        source_srid: int,
        direction: str,
        target_area_mu: float,
    ) -> dict:
        normalized_direction = str(direction or "").strip().lower()
        if normalized_direction not in {"east", "west", "south", "north"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid split direction")
        extent = self._load_geojson_geometry_extent(db, source_geometry, source_srid)
        target_area_sqm = float(target_area_mu) * 666.6666667
        source_area_sqm = float(extent["areaSqm"])
        if target_area_sqm <= 0 or target_area_sqm >= source_area_sqm:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="split area must be smaller than source parcel area")

        low = extent["minX"] if normalized_direction in {"east", "west"} else extent["minY"]
        high = extent["maxX"] if normalized_direction in {"east", "west"} else extent["maxY"]
        increasing = normalized_direction in {"west", "south"}
        for _ in range(32):
            middle = (low + high) / 2
            bounds = self._direction_clip_bounds(normalized_direction, middle, extent)
            current_area_sqm = self._measure_geojson_clip_area_sqm(db, source_geometry, source_srid, bounds)
            if increasing:
                if current_area_sqm < target_area_sqm:
                    low = middle
                else:
                    high = middle
            else:
                if current_area_sqm > target_area_sqm:
                    low = middle
                else:
                    high = middle
        threshold = (low + high) / 2
        bounds = self._direction_clip_bounds(normalized_direction, threshold, extent)
        rows = db.execute(
            text(
                f"""
                WITH source AS (
                    SELECT {self._geojson_4527_sql('src_geojson', 'src_srid')} AS geom
                ),
                clip AS (
                    SELECT ST_MakeEnvelope(:left, :bottom, :right, :top, 4527) AS geom
                ),
                fragments AS (
                    SELECT
                        0 AS part_group,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid((dump).geom), 3)) AS geom
                    FROM source
                    CROSS JOIN clip
                    CROSS JOIN LATERAL ST_Dump(
                        ST_CollectionExtract(ST_MakeValid(ST_Intersection(source.geom, clip.geom)), 3)
                    ) AS dump
                    UNION ALL
                    SELECT
                        1 AS part_group,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid((dump).geom), 3)) AS geom
                    FROM source
                    CROSS JOIN clip
                    CROSS JOIN LATERAL ST_Dump(
                        ST_CollectionExtract(ST_MakeValid(ST_Difference(source.geom, clip.geom)), 3)
                    ) AS dump
                )
                SELECT
                    part_group,
                    ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geojson,
                    ROUND(CAST(ST_Area(geom) / 666.6666667 AS numeric), 4) AS area_mu
                FROM fragments
                WHERE geom IS NOT NULL
                  AND NOT ST_IsEmpty(geom)
                ORDER BY part_group, ST_Area(geom) DESC, ST_XMin(geom), ST_YMin(geom)
                """
            ),
            {"src_geojson": json.dumps(source_geometry, ensure_ascii=False), "src_srid": int(source_srid or 4326), **bounds},
        ).mappings().all()
        parts = self._split_rows_to_parts(rows)
        if len(parts) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="failed to split parcel by direction")
        return {"parts": parts}