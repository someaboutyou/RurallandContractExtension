"""Query survey land parcel tables for parcel data.

这些查询走原生 SQL，不经过 ORM 的 `with_loader_criteria` 全局钩子，
因此必须自己带上区域过滤，否则会绕过「授权区域 + 用户数据权限」的限制。
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.license import license_validator
from app.services.data_access_service import data_access_service


class LandParcelRepository:
    """Query survey land parcel tables for parcel data."""

    def _scope_conditions(self, current_user=None, alias: str = "") -> tuple[str, dict]:
        """构造区域过滤 SQL 片段与绑定参数。

        第一层是系统授权区域（授权文件里的 region_code），任何情况都必须生效；
        第二层在调用方传入 current_user 时叠加其数据权限。

        `alias` 用于多表查询时限定列归属（例如 "dk" 生成 dk.region_code）。
        返回的片段以 " AND " 开头，可直接拼在 WHERE 之后。
        """
        authorized = data_access_service.normalize_region_code(
            license_validator.get_authorized_region_code()
        )
        if not authorized:
            return " AND 1=0", {}

        prefix = f"{alias}." if alias else ""
        clauses = [
            f"{prefix}tenant_code = :scope_tenant_code",
            f"{prefix}region_code LIKE :scope_region_pattern",
        ]
        params: dict = {
            "scope_tenant_code": authorized[:6],
            "scope_region_pattern": f"{authorized}%",
        }

        if current_user is not None and getattr(current_user.role, "data_scope", None) != "all":
            permissions = data_access_service.get_region_permissions(current_user)
            if not permissions:
                return " AND 1=0", {}
            patterns = []
            for index, permission in enumerate(permissions):
                key = f"scope_user_region_{index}"
                params[key] = f"{permission.region_code}%"
                patterns.append(f"{prefix}region_code LIKE :{key}")
            clauses.append("(" + " OR ".join(patterns) + ")")

        return " AND " + " AND ".join(clauses), params

    def get_dkbm_list_by_cbfbm(self, db: Session, cbfbm: str, current_user=None) -> list[str]:
        scope_sql, scope_params = self._scope_conditions(current_user)
        stmt = text(
            f"""
            SELECT dkbm
            FROM public.survey_cbdkxx_result
            WHERE cbfbm = :cbfbm
              AND result_status NOT IN ('removed', 'split_source')
              {scope_sql}
            """
        )
        rows = db.execute(stmt, {"cbfbm": cbfbm, **scope_params}).all()
        return [row[0] for row in rows]

    def get_cbdkxx_by_cbfbm(self, db: Session, cbfbm: str, current_user=None) -> list[dict]:
        scope_sql, scope_params = self._scope_conditions(current_user)
        stmt = text(
            f"""
            SELECT dkbm, htmj
            FROM public.survey_cbdkxx_result
            WHERE cbfbm = :cbfbm
              AND result_status NOT IN ('removed', 'split_source')
              {scope_sql}
            """
        )
        rows = db.execute(stmt, {"cbfbm": cbfbm, **scope_params}).all()
        return [{"dkbm": row[0], "htmj": row[1]} for row in rows]

    def get_cbdkxx_by_fbfbm(self, db: Session, fbfbm: str, current_user=None) -> list[dict]:
        scope_sql, scope_params = self._scope_conditions(current_user)
        stmt = text(
            f"""
            SELECT dkbm, cbfbm, htmj
            FROM public.survey_cbdkxx_result
            WHERE fbfbm = :fbfbm
              AND result_status NOT IN ('removed', 'split_source')
              {scope_sql}
            """
        )
        rows = db.execute(stmt, {"fbfbm": fbfbm, **scope_params}).all()
        return [{"dkbm": row[0], "cbfbm": row[1], "htmj": row[2]} for row in rows]

    def get_dk_by_codes(self, db: Session, dkbm_list: list[str], current_user=None) -> list[dict]:
        if not dkbm_list:
            return []

        scope_sql, scope_params = self._scope_conditions(current_user)
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
              {scope_sql}
            ORDER BY dkbm, id DESC
            """
        )
        rows = db.execute(stmt, {**params, **scope_params}).all()
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
        current_user=None,
    ) -> list[dict]:
        if not dkbm_list:
            return []

        scope_sql, scope_params = self._scope_conditions(current_user)
        scope_sql_dk, _ = self._scope_conditions(current_user, alias="dk")
        placeholders = ",".join(f":dkbm_{i}" for i in range(len(dkbm_list)))
        params = {
            **{f"dkbm_{i}": value for i, value in enumerate(dkbm_list)},
            "buffer_meters": buffer_meters,
            "limit": limit,
            **scope_params,
        }
        stmt = text(
            f"""
            WITH selected AS (
                SELECT ST_Collect(geom) AS geom
                FROM public.survey_dk_result
                WHERE dkbm IN ({placeholders})
                  AND result_status NOT IN ('removed', 'split_source')
                  AND geom IS NOT NULL
                  {scope_sql}
            ),
            extent AS (
                SELECT ST_Expand(ST_Envelope(geom), :buffer_meters) AS geom
                FROM selected
                WHERE geom IS NOT NULL
            ),
            spatial_candidates AS (
                SELECT dk.dkbm, dk.dkmc, dk.geom
                FROM public.survey_dk_result AS dk, selected, extent
                WHERE dk.geom IS NOT NULL
                  AND dk.result_status NOT IN ('removed', 'split_source')
                  AND dk.geom && extent.geom
                  AND ST_DWithin(dk.geom, selected.geom, :buffer_meters)
                  {scope_sql_dk}
            )
            SELECT
                candidates.dkbm,
                candidates.dkmc,
                ST_AsGeoJSON(ST_Transform(candidates.geom, 4326)) AS geometry
            FROM spatial_candidates AS candidates
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
