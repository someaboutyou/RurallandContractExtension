from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.cbf import Cbf
from app.models.fbf import Fbf
from app.models.request_case import RequestCase
from app.models.user import User
from app.schemas.response import ApiResponse
from app.services.data_access_service import data_access_service

router = APIRouter()


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
        select(Cbf)
        .where(
            or_(
                Cbf.cbfbm.ilike(like_keyword),
                Cbf.cbfmc.ilike(like_keyword),
                Cbf.cbfzjhm.ilike(like_keyword),
                Cbf.lxdh.ilike(like_keyword),
            ),
            *data_access_service.build_code_scope_filters(Cbf.cbfbm, current_user),
        )
        .order_by(Cbf.cbfbm.asc())
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
                    "resultType": "contractor",
                }
                for item in contractor_rows
            ],
        }
    }
