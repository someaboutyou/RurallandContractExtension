import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.fbf import Fbf
from app.models.request_case import RequestCase
from app.models.survey import SurveyCbdkxxResult, SurveyCbfResult, SurveyDkResult, SurveyFbfResult
from app.models.user import User
from app.schemas.response import ApiResponse
from app.repositories.land_parcel_repository import land_parcel_repository
from app.services.data_access_service import data_access_service

router = APIRouter()


def _count_parcels_by_code(
    db: Session,
    column,
    code: str | None,
    current_user: User,
) -> int:
    if not code:
        return 0
    return (
        db.scalar(
            select(func.count(func.distinct(SurveyCbdkxxResult.dkbm))).where(
                column == code,
                *data_access_service.build_code_scope_filters(SurveyCbdkxxResult.dkbm, current_user),
            )
        )
        or 0
    )


@router.get("/search", response_model=ApiResponse[dict])
def gis_search(
    keyword: str = Query(min_length=1),
    limit: int = Query(default=8, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    like_keyword = f"%{keyword.strip()}%"

    request_stmt = (
        select(RequestCase)
        .where(
            or_(
                RequestCase.serial_no.ilike(like_keyword),
                RequestCase.request_title.ilike(like_keyword),
                RequestCase.request_type.ilike(like_keyword),
                RequestCase.issuer_name.ilike(like_keyword),
                RequestCase.contractor_name.ilike(like_keyword),
                RequestCase.contractor_id_no.ilike(like_keyword),
                RequestCase.issuer_code.ilike(like_keyword),
                RequestCase.contractor_code.ilike(like_keyword),
            ),
            *data_access_service.build_request_case_filters(current_user),
        )
        .order_by(RequestCase.updated_at.desc())
        .limit(limit)
    )
    request_rows = db.scalars(request_stmt).all()

    issuer_stmt = (
        select(Fbf)
        .where(
            or_(
                Fbf.fbfbm.ilike(like_keyword),
                Fbf.fbfmc.ilike(like_keyword),
                Fbf.fbffzrxm.ilike(like_keyword),
                Fbf.fzrzjhm.ilike(like_keyword),
            ),
            *data_access_service.build_code_scope_filters(Fbf.fbfbm, current_user),
        )
        .order_by(Fbf.fbfbm.asc())
        .limit(limit)
    )
    issuer_rows = db.scalars(issuer_stmt).all()

    contractor_stmt = (
        select(SurveyCbfResult)
        .where(
            or_(
                SurveyCbfResult.cbfbm.ilike(like_keyword),
                SurveyCbfResult.cbfmc.ilike(like_keyword),
                SurveyCbfResult.cbfzjhm.ilike(like_keyword),
                SurveyCbfResult.lxdh.ilike(like_keyword),
            ),
            *data_access_service.build_code_scope_filters(SurveyCbfResult.cbfbm, current_user),
        )
        .order_by(SurveyCbfResult.cbfbm.asc(), SurveyCbfResult.id.desc())
        .limit(limit)
    )
    contractor_rows = db.scalars(contractor_stmt).all()

    return {
        "data": {
            "requests": [
                {
                    "id": item.id,
                    "serialNo": item.serial_no,
                    "requestTitle": item.request_title,
                    "requestType": item.request_type,
                    "issuerName": item.issuer_name,
                    "contractorName": item.contractor_name,
                    "contractorIdNo": item.contractor_id_no,
                    "contractorCode": item.contractor_code,
                    "mobile": item.mobile,
                    "status": item.status,
                    "currentStep": item.current_step,
                    "resultType": "request",
                }
                for item in request_rows
            ],
            "issuers": [
                {
                    "code": item.fbfbm,
                    "name": item.fbfmc,
                    "ownerName": item.fbffzrxm,
                    "ownerIdNo": item.fzrzjhm,
                    "mobile": item.lxdh,
                    "address": item.fbfdz,
                    "parcelCount": _count_parcels_by_code(db, SurveyCbdkxxResult.fbfbm, item.fbfbm, current_user),
                    "resultType": "issuer",
                }
                for item in issuer_rows
            ],
            "contractors": [
                {
                    "code": item.cbfbm,
                    "name": item.cbfmc,
                    "idNo": item.cbfzjhm,
                    "mobile": item.lxdh,
                    "address": item.cbfdz,
                    "type": item.cbflx,
                    "parcelCount": _count_parcels_by_code(db, SurveyCbdkxxResult.cbfbm, item.cbfbm, current_user),
                    "resultType": "contractor",
                }
                for item in contractor_rows
            ],
        }
    }


@router.get("/parcels/{dkbm}", response_model=ApiResponse[dict | None])
def gis_parcel_detail(
    dkbm: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data_access_service.ensure_code_in_scope(current_user, dkbm, detail="地块不在当前数据权限范围内")

    cbdkxx = db.scalars(
        select(SurveyCbdkxxResult)
        .where(
            SurveyCbdkxxResult.dkbm == dkbm,
            *data_access_service.build_code_scope_filters(SurveyCbdkxxResult.dkbm, current_user),
        )
        .order_by(SurveyCbdkxxResult.id.desc())
        .limit(1)
    ).first()
    if cbdkxx is None:
        return {"data": None}

    dk = db.scalars(
        select(SurveyDkResult)
        .where(
            SurveyDkResult.dkbm == dkbm,
            *data_access_service.build_code_scope_filters(SurveyDkResult.dkbm, current_user),
        )
        .order_by(SurveyDkResult.id.desc())
        .limit(1)
    ).first()
    fbf = db.scalars(
        select(SurveyFbfResult)
        .where(
            SurveyFbfResult.fbfbm == cbdkxx.fbfbm,
            *data_access_service.build_code_scope_filters(SurveyFbfResult.fbfbm, current_user),
        )
        .order_by(SurveyFbfResult.id.desc())
        .limit(1)
    ).first()
    cbf = db.scalars(
        select(SurveyCbfResult)
        .where(
            SurveyCbfResult.cbfbm == cbdkxx.cbfbm,
            *data_access_service.build_code_scope_filters(SurveyCbfResult.cbfbm, current_user),
        )
        .order_by(SurveyCbfResult.id.desc())
        .limit(1)
    ).first()

    geometry = None
    dk_rows = land_parcel_repository.get_dk_by_codes(db, [dkbm])
    if dk_rows and dk_rows[0].get("geometry"):
        try:
            geometry = json.loads(dk_rows[0]["geometry"])
        except (TypeError, json.JSONDecodeError):
            geometry = None

    return {
        "data": {
            "dkbm": cbdkxx.dkbm,
            "dkmc": dk.dkmc if dk else None,
            "htmj": str(cbdkxx.htmj) if cbdkxx.htmj is not None else None,
            "scmj": str(dk.scmj) if dk and dk.scmj is not None else None,
            "fbfbm": cbdkxx.fbfbm,
            "fbfmc": fbf.fbfmc if fbf else None,
            "fbffzrxm": fbf.fbffzrxm if fbf else None,
            "fbflxdh": fbf.lxdh if fbf else None,
            "fbfdz": fbf.fbfdz if fbf else None,
            "cbfbm": cbdkxx.cbfbm,
            "cbfmc": cbf.cbfmc if cbf else None,
            "cbfzjhm": cbf.cbfzjhm if cbf else None,
            "cbflxdh": cbf.lxdh if cbf else None,
            "cbfdz": cbf.cbfdz if cbf else None,
            "cbhtbm": cbdkxx.cbhtbm,
            "cbjyqzbm": cbdkxx.cbjyqzbm,
            "geometry": geometry,
        }
    }
