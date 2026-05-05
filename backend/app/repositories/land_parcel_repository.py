from sqlalchemy import text
from sqlalchemy.orm import Session


class LandParcelRepository:
    """Query external PostGIS tables for land parcel data."""

    def get_dkbm_list_by_cbfbm(self, db: Session, cbfbm: str) -> list[str]:
        stmt = text("SELECT dkbm FROM public.cbdkxx WHERE cbfbm = :cbfbm")
        rows = db.execute(stmt, {"cbfbm": cbfbm}).all()
        return [row[0] for row in rows]

    def get_cbdkxx_by_cbfbm(self, db: Session, cbfbm: str) -> list[dict]:
        stmt = text("SELECT dkbm, htmj FROM public.cbdkxx WHERE cbfbm = :cbfbm")
        rows = db.execute(stmt, {"cbfbm": cbfbm}).all()
        return [{"dkbm": row[0], "htmj": row[1]} for row in rows]

    def get_dk_by_codes(self, db: Session, dkbm_list: list[str]) -> list[dict]:
        if not dkbm_list:
            return []
        placeholders = ",".join(f":dkbm_{i}" for i in range(len(dkbm_list)))
        params = {f"dkbm_{i}": v for i, v in enumerate(dkbm_list)}
        stmt = text(
            f"""
            SELECT
                "DKBM",
                "DKMC",
                "SYQXZ",
                "DKLB",
                "SCMJ",
                "DKDZ",
                ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geometry
            FROM public."DK3213242017"
            WHERE "DKBM" IN ({placeholders})
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


land_parcel_repository = LandParcelRepository()
