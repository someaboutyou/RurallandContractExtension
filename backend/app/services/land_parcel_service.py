import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.survey import SurveyCbdkxxResult, SurveyCbfResult, SurveyDkBase, SurveyFbfResult
from app.models.user import User
from app.repositories.land_parcel_repository import land_parcel_repository
from app.services.data_access_service import data_access_service


class LandParcelService:

    def get_parcels_for_contractor(
        self, db: Session, cbfbm: str, current_user: User
    ) -> list[dict]:
        data_access_service.ensure_code_in_scope(
            current_user, cbfbm, detail="鎵垮寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴"
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
            current_user, fbfbm, detail="鍙戝寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴"
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
            current_user, cbfbm, detail="鎵垮寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴"
        )

        cbdkxx_result_rows = db.scalars(
            select(SurveyCbdkxxResult).where(
                SurveyCbdkxxResult.cbfbm == cbfbm,
            ).order_by(SurveyCbdkxxResult.dkbm)
        ).all()

        if not cbdkxx_result_rows:
            return []

        dkbm_list = [row.dkbm for row in cbdkxx_result_rows]
        fbfbm_list = list(set(row.fbfbm for row in cbdkxx_result_rows if row.fbfbm))

        dk_base_rows = db.scalars(
            select(SurveyDkBase).where(
                SurveyDkBase.batch_id == batch_id,
                SurveyDkBase.dkbm.in_(dkbm_list),
            )
        ).all()
        dk_base_map = {row.dkbm: row for row in dk_base_rows}
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

        result = []
        for cbdkxx in cbdkxx_result_rows:
            dk_base = dk_base_map.get(cbdkxx.dkbm)
            fbf = fbf_map.get(cbdkxx.fbfbm)

            item = {
                "dkbm": cbdkxx.dkbm,
                "dkmc": dk_base.dkmc if dk_base else None,
                "scmj": str(dk_base.scmj) if dk_base and dk_base.scmj is not None else None,
                "htmj": str(cbdkxx.htmj) if cbdkxx.htmj is not None else None,
                "yhtmj": str(cbdkxx.yhtmj) if cbdkxx.yhtmj is not None else None,
                "htmjm": str(cbdkxx.htmjm) if cbdkxx.htmjm is not None else None,
                "yhtmjm": str(cbdkxx.yhtmjm) if cbdkxx.yhtmjm is not None else None,
                "syqxz": dk_base.syqxz if dk_base else None,
                "dklb": dk_base.dklb if dk_base else None,
                "dldj": dk_base.dldj if dk_base else None,
                "tdyt": dk_base.tdyt if dk_base else None,
                "tdlylx": dk_base.tdlylx if dk_base else None,
                "sfjbnt": dk_base.sfjbnt if dk_base else None,
                "dkdz": dk_base.dkdz if dk_base else None,
                "dkxz": dk_base.dkxz if dk_base else None,
                "dknz": dk_base.dknz if dk_base else None,
                "dkbz": dk_base.dkbz if dk_base else None,
                "dkbzxx": dk_base.dkbzxx if dk_base else None,
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
                "geometry": dk_geometry_map.get(cbdkxx.dkbm),
            }
            result.append(item)

        return result

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
            )
        ).all()
        rows = land_parcel_repository.get_nearby_dk_by_codes(db, batch_id, dkbm_list)

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
