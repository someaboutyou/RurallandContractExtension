from datetime import date, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.cbf import Cbf
from app.models.cbf_jtcy import CbfJtcy
from app.models.user import User
from app.repositories.contractor_repository import contractor_repository
from app.services.data_access_service import data_access_service


class ContractorService:
    def list_contractors(
        self,
        db: Session,
        page: int,
        page_size: int,
        current_user: User,
        keyword: str | None = None,
        type_code: str | None = None,
    ) -> dict:
        contractors, total = contractor_repository.list_contractors(
            db,
            page=page,
            page_size=page_size,
            extra_filters=data_access_service.build_code_scope_filters(Cbf.cbfbm, current_user),
            keyword=keyword.strip() if keyword else None,
            type_code=type_code or None,
        )
        return {
            "items": [self._serialize_summary(item) for item in contractors],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def get_contractor(self, db: Session, code: str, current_user: User) -> dict:
        contractor = contractor_repository.get_contractor(db, code)
        if contractor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="承包方不存在")
        data_access_service.ensure_code_in_scope(current_user, contractor.cbfbm, detail="承包方不在当前数据权限范围内")
        return self._serialize_detail(db, contractor)

    def create_contractor(self, db: Session, payload: dict, current_user: User) -> dict:
        data_access_service.ensure_code_in_scope(current_user, payload["code"], detail="承包方不在当前数据权限范围内")
        if contractor_repository.get_contractor(db, payload["code"]) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="承包方代码已存在")
        contractor = Cbf(
            cbfbm=payload["code"],
            cbflx=payload["typeCode"],
            cbfmc=payload["name"],
            cbfzjlx=payload["idType"],
            cbfzjhm=payload["idNo"],
            cbfdz=payload["address"],
            yzbm=payload["postcode"],
            lxdh=payload.get("mobile"),
            cbfcysl=len(payload.get("familyMembers", [])) if payload["typeCode"] == "1" else 0,
            cbfdcrq=self._parse_datetime(payload.get("surveyDate")) or datetime.now(),
            cbfdcy=payload["surveyorName"] or current_user.real_name,
            cbfdcjs=payload.get("surveyNote"),
            gsjs=payload.get("publicNoticeNote"),
            gsjsr=payload.get("publicNoticeRecorder"),
            gsshrq=self._parse_datetime(payload.get("publicNoticeReviewDate")),
            gsshr=payload.get("publicNoticeReviewer"),
        )
        family_members = self._build_family_members(payload["code"], payload.get("familyMembers", []))
        contractor = contractor_repository.create_contractor(db, contractor, family_members)
        return self._serialize_detail(db, contractor)

    def update_contractor(self, db: Session, code: str, payload: dict, current_user: User) -> dict:
        contractor = contractor_repository.get_contractor(db, code)
        if contractor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="承包方不存在")
        data_access_service.ensure_code_in_scope(current_user, contractor.cbfbm, detail="承包方不在当前数据权限范围内")
        data_access_service.ensure_code_in_scope(current_user, payload["code"], detail="承包方不在当前数据权限范围内")
        if payload["code"] != code and contractor_repository.get_contractor(db, payload["code"]) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="承包方代码已存在")

        original_code = contractor.cbfbm
        contractor.cbfbm = payload["code"]
        contractor.cbflx = payload["typeCode"]
        contractor.cbfmc = payload["name"]
        contractor.cbfzjlx = payload["idType"]
        contractor.cbfzjhm = payload["idNo"]
        contractor.cbfdz = payload["address"]
        contractor.yzbm = payload["postcode"]
        contractor.lxdh = payload.get("mobile")
        contractor.cbfcysl = len(payload.get("familyMembers", [])) if payload["typeCode"] == "1" else 0
        contractor.cbfdcrq = self._parse_datetime(payload.get("surveyDate")) or contractor.cbfdcrq
        contractor.cbfdcy = payload["surveyorName"] or current_user.real_name
        contractor.cbfdcjs = payload.get("surveyNote")
        contractor.gsjs = payload.get("publicNoticeNote")
        contractor.gsjsr = payload.get("publicNoticeRecorder")
        contractor.gsshrq = self._parse_datetime(payload.get("publicNoticeReviewDate"))
        contractor.gsshr = payload.get("publicNoticeReviewer")

        family_members = self._build_family_members(contractor.cbfbm, payload.get("familyMembers", []))
        updated = contractor_repository.update_contractor(db, contractor, family_members)

        if original_code != contractor.cbfbm:
            contractor_repository.delete_contractor(db, original_code)

        return self._serialize_detail(db, updated)

    def delete_contractor(self, db: Session, code: str, current_user: User) -> None:
        contractor = contractor_repository.get_contractor(db, code)
        if contractor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="承包方不存在")
        data_access_service.ensure_code_in_scope(current_user, contractor.cbfbm, detail="承包方不在当前数据权限范围内")
        contractor_repository.delete_contractor(db, code)

    def _serialize_summary(self, contractor: Cbf) -> dict:
        return {
            "code": contractor.cbfbm,
            "typeCode": contractor.cbflx,
            "name": contractor.cbfmc,
            "idType": contractor.cbfzjlx,
            "idNo": contractor.cbfzjhm,
            "address": contractor.cbfdz,
            "postcode": contractor.yzbm,
            "mobile": contractor.lxdh,
            "memberCount": contractor.cbfcysl,
            "surveyDate": contractor.cbfdcrq.date().isoformat() if contractor.cbfdcrq else None,
            "surveyorName": contractor.cbfdcy,
            "surveyNote": contractor.cbfdcjs,
            "publicNoticeNote": contractor.gsjs,
            "publicNoticeRecorder": contractor.gsjsr,
            "publicNoticeReviewDate": contractor.gsshrq.date().isoformat() if contractor.gsshrq else None,
            "publicNoticeReviewer": contractor.gsshr,
            "familyMembers": [],
        }

    def _serialize_detail(self, db: Session, contractor: Cbf) -> dict:
        family_members = contractor_repository.list_family_members(db, contractor.cbfbm)
        summary = self._serialize_summary(contractor)
        summary["familyMembers"] = [
            {
                "name": item.cyxm,
                "gender": item.cyxb,
                "idType": item.cyzjlx,
                "idNo": item.cyzjhm,
                "relationToHead": item.yhzgx,
                "noteCode": item.cybz,
                "isCoOwner": item.sfgyr,
                "note": item.cybzsm,
            }
            for item in family_members
        ]
        return summary

    def _build_family_members(self, code: str, family_members: list[dict]) -> list[CbfJtcy]:
        members = []
        seen_ids: set[str] = set()
        for item in family_members:
            member_id = item["idNo"]
            if member_id in seen_ids:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="家庭成员证件号不能重复")
            seen_ids.add(member_id)
            members.append(
                CbfJtcy(
                    cbfbm=code,
                    cyxm=item["name"],
                    cyzjlx=item["idType"],
                    cyzjhm=member_id,
                    cyxb=item["gender"],
                    yhzgx=item["relationToHead"],
                    cybz=item.get("noteCode"),
                    sfgyr=item.get("isCoOwner"),
                    cybzsm=item.get("note"),
                )
            )
        return members

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.combine(date.fromisoformat(value), datetime.min.time())


contractor_service = ContractorService()
