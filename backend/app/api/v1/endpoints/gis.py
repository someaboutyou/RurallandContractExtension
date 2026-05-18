import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.cbht import Cbht
from app.models.fbf import Fbf
from app.models.request_case import RequestCase
from app.models.survey import SurveyCbdkxxResult, SurveyCbfJtcyResult, SurveyCbfResult, SurveyDkResult, SurveyFbfResult
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


def _format_date(value) -> str | None:
    if not value:
        return None
    if hasattr(value, "date"):
        return value.date().isoformat()
    return str(value)


def _first_parcel_code_by_code(
    db: Session,
    column,
    code: str | None,
    current_user: User,
) -> str | None:
    if not code:
        return None
    return db.scalar(
        select(SurveyCbdkxxResult.dkbm)
        .where(
            column == code,
            *data_access_service.build_code_scope_filters(SurveyCbdkxxResult.dkbm, current_user),
        )
        .order_by(SurveyCbdkxxResult.dkbm.asc())
        .limit(1)
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
                    "primaryParcelCode": _first_parcel_code_by_code(db, SurveyCbdkxxResult.cbfbm, item.contractor_code, current_user)
                    or _first_parcel_code_by_code(db, SurveyCbdkxxResult.cbhtbm, item.contract_code, current_user),
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
                    "primaryParcelCode": _first_parcel_code_by_code(db, SurveyCbdkxxResult.fbfbm, item.fbfbm, current_user),
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
                    "primaryParcelCode": _first_parcel_code_by_code(db, SurveyCbdkxxResult.cbfbm, item.cbfbm, current_user),
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
    family_member_filters = []
    if cbf:
        family_member_filters.append(
            (
                SurveyCbfJtcyResult.batch_id == cbf.batch_id,
                SurveyCbfJtcyResult.contractor_uid == cbf.contractor_uid,
            )
        )
    family_member_filters.append(
        (
            SurveyCbfJtcyResult.cbfbm == cbdkxx.cbfbm,
        )
    )
    family_members = []
    for filters in family_member_filters:
        family_members = db.scalars(
            select(SurveyCbfJtcyResult)
            .where(
                *filters,
                *data_access_service.build_code_scope_filters(SurveyCbfJtcyResult.cbfbm, current_user),
            )
            .order_by(SurveyCbfJtcyResult.cyxm.asc(), SurveyCbfJtcyResult.cyzjhm.asc())
        ).all()
        if family_members:
            break
    contract = None
    if cbdkxx.cbhtbm:
        contract = db.scalar(
            select(Cbht)
            .where(
                Cbht.cbhtbm == cbdkxx.cbhtbm,
                *data_access_service.build_code_scope_filters(Cbht.cbhtbm, current_user),
            )
            .limit(1)
        )

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
            "fbffzrzjlx": fbf.fzrzjlx if fbf else None,
            "fbffzrzjhm": fbf.fzrzjhm if fbf else None,
            "fbflxdh": fbf.lxdh if fbf else None,
            "fbfdz": fbf.fbfdz if fbf else None,
            "fbfyzbm": fbf.yzbm if fbf else None,
            "fbfdcy": fbf.fbfdcy if fbf else None,
            "fbfdcrq": _format_date(fbf.fbfdcrq) if fbf else None,
            "fbfdcjs": fbf.fbfdcjs if fbf else None,
            "fbfSurveyStatus": fbf.survey_status if fbf else None,
            "fbfResultStatus": fbf.result_status if fbf else None,
            "fbfIsChanged": fbf.is_changed if fbf else None,
            "fbfChangeType": fbf.change_type if fbf else None,
            "fbfChangeReason": fbf.change_reason if fbf else None,
            "fbfRegionCode": fbf.region_code if fbf else None,
            "fbfTenantCode": fbf.tenant_code if fbf else None,
            "cbfbm": cbdkxx.cbfbm,
            "cbfmc": cbf.cbfmc if cbf else None,
            "cbflx": cbf.cbflx if cbf else None,
            "cbfzjlx": cbf.cbfzjlx if cbf else None,
            "cbfzjhm": cbf.cbfzjhm if cbf else None,
            "cbflxdh": cbf.lxdh if cbf else None,
            "cbfdz": cbf.cbfdz if cbf else None,
            "cbfyzbm": cbf.yzbm if cbf else None,
            "cbfcysl": cbf.cbfcysl if cbf else None,
            "cbfdcrq": _format_date(cbf.cbfdcrq) if cbf else None,
            "cbfdcy": cbf.cbfdcy if cbf else None,
            "cbfdcjs": cbf.cbfdcjs if cbf else None,
            "gsjs": cbf.gsjs if cbf else None,
            "gsjsr": cbf.gsjsr if cbf else None,
            "gsshrq": _format_date(cbf.gsshrq) if cbf else None,
            "gsshr": cbf.gsshr if cbf else None,
            "cbfSurveyStatus": cbf.survey_status if cbf else None,
            "cbfResultStatus": cbf.result_status if cbf else None,
            "cbfIsChanged": cbf.is_changed if cbf else None,
            "cbfChangeType": cbf.change_type if cbf else None,
            "cbfChangeReason": cbf.change_reason if cbf else None,
            "cbfPolicyBasis": cbf.policy_basis if cbf else None,
            "cbfEvidenceSummary": cbf.evidence_summary if cbf else None,
            "cbfInvestigatorName": cbf.investigator_name if cbf else None,
            "cbfInvestigatedAt": _format_date(cbf.investigated_at) if cbf else None,
            "cbfReviewerName": cbf.reviewer_name if cbf else None,
            "cbfReviewedAt": _format_date(cbf.reviewed_at) if cbf else None,
            "cbfConfirmedAt": _format_date(cbf.confirmed_at) if cbf else None,
            "cbfGroupRegionCode": cbf.group_region_code if cbf else None,
            "cbfGroupRegionName": cbf.group_region_name if cbf else None,
            "cbfRemark": cbf.remark if cbf else None,
            "cbhtbm": cbdkxx.cbhtbm,
            "cbjyqzbm": cbdkxx.cbjyqzbm,
            "cbjyqqdfs": cbdkxx.cbjyqqdfs,
            "yhtmj": str(cbdkxx.yhtmj) if cbdkxx.yhtmj is not None else None,
            "htmjm": str(cbdkxx.htmjm) if cbdkxx.htmjm is not None else None,
            "yhtmjm": str(cbdkxx.yhtmjm) if cbdkxx.yhtmjm is not None else None,
            "sfqqqg": cbdkxx.sfqqqg,
            "dklb": dk.dklb if dk else None,
            "tdlylx": dk.tdlylx if dk else None,
            "dldj": dk.dldj if dk else None,
            "tdyt": dk.tdyt if dk else None,
            "sfjbnt": dk.sfjbnt if dk else None,
            "dkdz": dk.dkdz if dk else None,
            "dkxz": dk.dkxz if dk else None,
            "dknz": dk.dknz if dk else None,
            "dkbz": dk.dkbz if dk else None,
            "dkbzxx": dk.dkbzxx if dk else None,
            "familyMembers": [
                {
                    "name": item.cyxm,
                    "idType": item.cyzjlx,
                    "idNo": item.cyzjhm,
                    "gender": item.cyxb,
                    "relationToHead": item.yhzgx,
                    "isCoOwner": item.sfgyr,
                    "noteCode": item.cybz,
                    "note": item.cybzsm,
                }
                for item in family_members
            ],
            "contract": {
                "cbhtbm": contract.cbhtbm,
                "ycbhtbm": contract.ycbhtbm,
                "cbfs": contract.cbfs,
                "cbqxq": _format_date(contract.cbqxq),
                "cbqxz": _format_date(contract.cbqxz),
                "qdsj": _format_date(contract.qdsj),
                "htzmj": str(contract.htzmj) if contract.htzmj is not None else None,
                "htzmjm": str(contract.htzmjm) if contract.htzmjm is not None else None,
                "yhtzmj": str(contract.yhtzmj) if contract.yhtzmj is not None else None,
                "yhtzmjm": str(contract.yhtzmjm) if contract.yhtzmjm is not None else None,
                "cbdkzs": contract.cbdkzs,
            }
            if contract
            else None,
            "geometry": geometry,
        }
    }
