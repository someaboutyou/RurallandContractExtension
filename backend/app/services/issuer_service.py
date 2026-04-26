from datetime import date, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.fbf import Fbf
from app.models.user import User
from app.repositories.issuer_repository import issuer_repository
from app.services.data_access_service import data_access_service


class IssuerService:
    def list_issuers(self, db: Session, page: int, page_size: int, current_user: User, keyword: str | None = None) -> dict:
        records, total = issuer_repository.list_issuers(
            db,
            page=page,
            page_size=page_size,
            extra_filters=data_access_service.build_code_scope_filters(Fbf.fbfbm, current_user),
            keyword=keyword.strip() if keyword else None,
        )
        return {
            "items": [self._serialize(item) for item in records],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def create_issuer(self, db: Session, payload: dict, current_user: User) -> dict:
        data_access_service.ensure_code_in_scope(current_user, payload["code"], detail="发包方不在当前数据权限范围内")
        if issuer_repository.get_issuer(db, payload["code"]) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="发包方代码已存在")
        issuer = Fbf(
            fbfbm=payload["code"],
            fbfmc=payload["name"],
            fbffzrxm=payload["ownerName"],
            fzrzjlx=payload["ownerIdType"],
            fzrzjhm=payload["ownerIdNo"],
            lxdh=payload.get("mobile"),
            fbfdz=payload["address"],
            yzbm=payload["postcode"],
            fbfdcy=payload["surveyorName"] or current_user.real_name,
            fbfdcrq=self._parse_datetime(payload.get("surveyDate")) or datetime.now(),
            fbfdcjs=payload.get("notes"),
        )
        issuer = issuer_repository.create_issuer(db, issuer)
        return self._serialize(issuer)

    def update_issuer(self, db: Session, issuer_code: str, payload: dict, current_user: User) -> dict:
        issuer = issuer_repository.get_issuer(db, issuer_code)
        if issuer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发包方不存在")
        data_access_service.ensure_code_in_scope(current_user, issuer.fbfbm, detail="发包方不在当前数据权限范围内")
        data_access_service.ensure_code_in_scope(current_user, payload["code"], detail="发包方不在当前数据权限范围内")
        if payload["code"] != issuer_code and issuer_repository.get_issuer(db, payload["code"]) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="发包方代码已存在")
        issuer.fbfbm = payload["code"]
        issuer.fbfmc = payload["name"]
        issuer.fbffzrxm = payload["ownerName"]
        issuer.fzrzjlx = payload["ownerIdType"]
        issuer.fzrzjhm = payload["ownerIdNo"]
        issuer.lxdh = payload.get("mobile")
        issuer.fbfdz = payload["address"]
        issuer.yzbm = payload["postcode"]
        issuer.fbfdcy = payload["surveyorName"]
        issuer.fbfdcrq = self._parse_datetime(payload.get("surveyDate")) or issuer.fbfdcrq
        issuer.fbfdcjs = payload.get("notes")
        issuer = issuer_repository.update_issuer(db, issuer)
        return self._serialize(issuer)

    def delete_issuer(self, db: Session, issuer_code: str, current_user: User) -> None:
        issuer = issuer_repository.get_issuer(db, issuer_code)
        if issuer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发包方不存在")
        data_access_service.ensure_code_in_scope(current_user, issuer.fbfbm, detail="发包方不在当前数据权限范围内")
        issuer_repository.delete_issuer(db, issuer)

    def _serialize(self, item: Fbf) -> dict:
        return {
            "code": item.fbfbm,
            "name": item.fbfmc,
            "ownerName": item.fbffzrxm,
            "ownerIdType": item.fzrzjlx,
            "ownerIdNo": item.fzrzjhm,
            "mobile": item.lxdh,
            "address": item.fbfdz,
            "postcode": item.yzbm,
            "surveyorName": item.fbfdcy,
            "surveyDate": item.fbfdcrq.date().isoformat() if item.fbfdcrq else None,
            "notes": item.fbfdcjs,
            "regionId": None,
            "region": None,
            "status": None,
        }

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.combine(date.fromisoformat(value), datetime.min.time())


issuer_service = IssuerService()
