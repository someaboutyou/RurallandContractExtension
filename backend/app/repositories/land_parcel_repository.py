from sqlalchemy import text
from sqlalchemy.orm import Session


class LandParcelRepository:
    """Query survey land parcel tables for parcel data."""

    def get_dkbm_list_by_cbfbm(self, db: Session, cbfbm: str) -> list[str]:
        stmt = text(
            """
            SELECT dkbm
            FROM public.survey_cbdkxx_result
            WHERE cbfbm = :cbfbm
              AND result_status NOT IN ('removed', 'split_source')
            """
        )
        rows = db.execute(stmt, {"cbfbm": cbfbm}).all()
        return [row[0] for row in rows]

    def get_cbdkxx_by_cbfbm(self, db: Session, cbfbm: str) -> list[dict]:
        stmt = text(
            """
            SELECT dkbm, htmj
            FROM public.survey_cbdkxx_result
            WHERE cbfbm = :cbfbm
              AND result_status NOT IN ('removed', 'split_source')
            """
        )
        rows = db.execute(stmt, {"cbfbm": cbfbm}).all()
        return [{"dkbm": row[0], "htmj": row[1]} for row in rows]

    def get_cbdkxx_by_fbfbm(self, db: Session, fbfbm: str) -> list[dict]:
        stmt = text(
            """
            SELECT dkbm, cbfbm, htmj
            FROM public.survey_cbdkxx_result
            WHERE fbfbm = :fbfbm
              AND result_status NOT IN ('removed', 'split_source')
            """
        )
        rows = db.execute(stmt, {"fbfbm": fbfbm}).all()
        return [{"dkbm": row[0], "cbfbm": row[1], "htmj": row[2]} for row in rows]

    def get_dk_by_codes(self, db: Session, dkbm_list: list[str]) -> list[dict]:
        if not dkbm_list:
            return []

        placeholders = ",".join(f":dkbm_{i}" for i in range(len(dkbm_list)))
        params = {f"dkbm_{i}": value for i, value in enumerate(dkbm_list)}
        stmt = text(
            f"""
            SELECT DISTINCT ON (dkbm)
                dkbm,
                dkmc,
                syqxz,
                dklb,
                scmj,
                dkdz,
                ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geometry
            FROM public.survey_dk_result
            WHERE dkbm IN ({placeholders})
              AND result_status <> 'removed'
            ORDER BY dkbm, id DESC
            """
        )
        rows = db.execute(stmt, params).all()
        return [
            {
                "dkbm": row[0],
                "dkmc": row[1],
                "syqxz": row[2],
                "dklb": row[3],
                "scmj": row[4],
                "dkdz": row[5],
                "geometry": row[6],
            }
            for row in rows
        ]

    def get_nearby_dk_by_codes(
        self,
        db: Session,
        dkbm_list: list[str],
        buffer_meters: int = 500,
        limit: int = 800,
    ) -> list[dict]:
        if not dkbm_list:
            return []

        placeholders = ",".join(f":dkbm_{i}" for i in range(len(dkbm_list)))
        params = {
            **{f"dkbm_{i}": value for i, value in enumerate(dkbm_list)},
            "buffer_meters": buffer_meters,
            "limit": limit,
        }
        stmt = text(
            f"""
            WITH current_dk AS (
                SELECT DISTINCT ON (dkbm) *
                FROM public.survey_dk_result
                WHERE result_status NOT IN ('removed', 'split_source')
                ORDER BY dkbm, id DESC
            ),
            selected AS (
                SELECT ST_Collect(geom) AS geom
                FROM current_dk
                WHERE dkbm IN ({placeholders})
                  AND geom IS NOT NULL
            ),
            extent AS (
                SELECT ST_Expand(ST_Envelope(geom), :buffer_meters) AS geom
                FROM selected
                WHERE geom IS NOT NULL
            ),
            spatial_candidates AS (
                SELECT dk.dkbm, dk.dkmc, dk.geom
                FROM current_dk AS dk, selected, extent
                WHERE dk.geom IS NOT NULL
                  AND (
                    ST_Intersects(dk.geom, extent.geom)
                    OR ST_DWithin(dk.geom, selected.geom, :buffer_meters)
                  )
            ),
            nearest_candidates AS (
                SELECT dk.dkbm, dk.dkmc, dk.geom
                FROM current_dk AS dk, selected
                WHERE dk.geom IS NOT NULL
                ORDER BY dk.geom <-> selected.geom
                LIMIT 200
            ),
            candidates AS (
                SELECT * FROM spatial_candidates
                UNION
                SELECT * FROM nearest_candidates
            )
            SELECT
                candidates.dkbm,
                candidates.dkmc,
                ST_AsGeoJSON(ST_Transform(candidates.geom, 4326)) AS geometry
            FROM candidates
            ORDER BY
              CASE WHEN candidates.dkbm IN ({placeholders}) THEN 0 ELSE 1 END,
              candidates.dkbm
            LIMIT :limit
            """
        )
        rows = db.execute(stmt, params).all()
        return [
            {
                "dkbm": row[0],
                "dkmc": row[1],
                "geometry": row[2],
            }
            for row in rows
        ]


land_parcel_repository = LandParcelRepository()
