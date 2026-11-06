from datetime import date, datetime

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.cbht import Cbht
from app.models.fbf import Fbf
from app.models.survey import (
    SurveyCbfResult,
    SurveyCbdkxxResult,
    SurveyFbfBase,
    SurveyFbfResult,
)
from app.models.user import User
from app.repositories.issuer_repository import issuer_repository
from app.services.data_access_service import data_access_service


class IssuerService:
    def list_issuers(
        self,
        db: Session,
        page: int,
        page_size: int,
        current_user: User,
        keyword: str | None = None,
        region_code: str | None = None,
    ) -> dict:
        records, total = issuer_repository.list_issuers(
            db,
            page=page,
            page_size=page_size,
            extra_filters=data_access_service.build_code_scope_filters(Fbf.fbfbm, current_user),
            keyword=keyword.strip() if keyword else None,
            region_code=region_code.strip() if region_code else None,
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

        # 有承包方时禁止删除：承包方通过承包地块关系（survey_cbdkxx_result）
        # 或承包合同（cbht）挂在发包方下，直接删发包方会产生孤儿数据。
        contractor_count = self.count_related_contractors(db, issuer_code)
        if contractor_count:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"该发包方下存在 {contractor_count} 个承包方，不能删除；请先处理这些承包方后再删除。",
            )

        issuer_repository.delete_issuer(db, issuer)

    @staticmethod
    def count_related_contractors(db: Session, issuer_code: str) -> int:
        """挂在发包方名下的承包方数量（删除闸门，导入预览共用）。"""
        survey_contractor_codes = set(
            db.scalars(
                select(SurveyCbdkxxResult.cbfbm)
                .where(
                    SurveyCbdkxxResult.fbfbm == issuer_code,
                    SurveyCbdkxxResult.cbfbm.is_not(None),
                    SurveyCbdkxxResult.result_status != "removed",
                )
                .distinct()
            ).all()
        )
        contract_contractor_codes = set(
            db.scalars(
                select(Cbht.cbfbm)
                .where(
                    Cbht.fbfbm == issuer_code,
                    Cbht.cbfbm.is_not(None),
                )
                .distinct()
            ).all()
        )
        return len(survey_contractor_codes | contract_contractor_codes)

    def merge_issuers(
        self,
        db: Session,
        keep_code: str,
        merge_codes: list[str],
        current_user: User,
    ) -> dict:
        """合并发包方：把被合并方的承包方/地块/合同划转到保留方，删除被合并方。

        口径参照 CS 版与批次内合并：
          - survey_cbdkxx_result.fbfbm → 保留方（地块/承包方关系、GIS、出表都读这里）
          - cbht.fbfbm → 保留方（避免合同挂到已删除的发包方上）
          - survey_fbf_result / survey_fbf_base：被合并方的调查成果与快照删除
            （保留方的调查成果不动；与批次内合并保持一致）
          - fbf 主表：删除被合并方，保留保留方
          - survey_cbdkxx_base 快照不动（保留导入原貌）
        """
        keep_code = (keep_code or "").strip()
        merge_codes = [str(code).strip() for code in (merge_codes or []) if str(code).strip()]
        if not keep_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择要保留的发包方")
        if not merge_codes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择要合并的发包方")
        if keep_code in merge_codes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="保留的发包方不能同时出现在合并列表中",
            )
        if len(set(merge_codes)) != len(merge_codes):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="合并列表中存在重复的发包方",
            )

        keep = issuer_repository.get_issuer(db, keep_code)
        if keep is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="保留的发包方不存在")
        merged: list[Fbf] = []
        for code in merge_codes:
            item = issuer_repository.get_issuer(db, code)
            if item is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"发包方不存在：{code}",
                )
            merged.append(item)

        for item in [keep, *merged]:
            data_access_service.ensure_code_in_scope(
                current_user, item.fbfbm, detail="发包方不在当前数据权限范围内"
            )

        tenant_code = keep.tenant_code
        moved_parcel_count = 0
        moved_contract_count = 0
        moved_contractor_codes: set[str] = set()

        for item in merged:
            # 1) 地块/承包方关联
            relations = db.scalars(
                select(SurveyCbdkxxResult)
                .where(
                    SurveyCbdkxxResult.tenant_code == tenant_code,
                    SurveyCbdkxxResult.fbfbm == item.fbfbm,
                )
                .execution_options(skip_tenant_scope=True)
            ).all()
            moved_parcel_count += len(relations)
            moved_contractor_codes.update(rel.cbfbm for rel in relations if rel.cbfbm)
            if relations:
                db.execute(
                    update(SurveyCbdkxxResult)
                    .where(
                        SurveyCbdkxxResult.tenant_code == tenant_code,
                        SurveyCbdkxxResult.fbfbm == item.fbfbm,
                    )
                    .values(fbfbm=keep.fbfbm)
                    .execution_options(skip_tenant_scope=True, synchronize_session=False)
                )

            # 2) 承包合同
            contract_result = db.execute(
                update(Cbht)
                .where(
                    Cbht.tenant_code == tenant_code,
                    Cbht.fbfbm == item.fbfbm,
                )
                .values(fbfbm=keep.fbfbm)
                .execution_options(skip_tenant_scope=True, synchronize_session=False)
            )
            moved_contract_count += contract_result.rowcount or 0

            # 3) 被合并方的调查成果与快照：删除（保留方成果保留）
            result_rows = db.scalars(
                select(SurveyFbfResult)
                .where(
                    SurveyFbfResult.tenant_code == tenant_code,
                    SurveyFbfResult.fbfbm == item.fbfbm,
                )
                .execution_options(skip_tenant_scope=True)
            ).all()
            for result_row in result_rows:
                base_rows = db.scalars(
                    select(SurveyFbfBase)
                    .where(
                        SurveyFbfBase.tenant_code == tenant_code,
                        SurveyFbfBase.result_id == result_row.id,
                    )
                    .execution_options(skip_tenant_scope=True)
                ).all()
                for base_row in base_rows:
                    db.delete(base_row)
                db.delete(result_row)

            # 4) 删除被合并的发包方主数据
            db.delete(item)

        db.commit()
        return {
            "keepIssuer": self._serialize(keep),
            "mergedIssuers": [
                {"code": item.fbfbm, "name": item.fbfmc} for item in merged
            ],
            "movedParcelCount": moved_parcel_count,
            "movedContractorCount": len(moved_contractor_codes),
            "movedContractCount": moved_contract_count,
        }

    def list_contractors(self, db: Session, issuer_code: str, current_user: User) -> list[dict]:
        issuer = issuer_repository.get_issuer(db, issuer_code)
        if issuer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发包方不存在")
        data_access_service.ensure_code_in_scope(current_user, issuer.fbfbm, detail="发包方不在当前数据权限范围内")

        contractor_codes = db.scalars(
            select(SurveyCbdkxxResult.cbfbm)
            .where(
                SurveyCbdkxxResult.fbfbm == issuer_code,
                SurveyCbdkxxResult.cbfbm.is_not(None),
                SurveyCbdkxxResult.result_status != "removed",
            )
            .distinct()
        ).all()
        if not contractor_codes:
            return []

        rows = db.scalars(
            select(SurveyCbfResult)
            .where(
                SurveyCbfResult.cbfbm.in_(contractor_codes),
                *data_access_service.build_code_scope_filters(SurveyCbfResult.cbfbm, current_user),
            )
            .order_by(SurveyCbfResult.cbfbm.asc(), SurveyCbfResult.id.desc())
        ).all()
        latest_by_code = {}
        for row in rows:
            latest_by_code.setdefault(row.cbfbm, row)
        return [self._serialize_contractor(item) for item in latest_by_code.values()]

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

    def _serialize_contractor(self, item: SurveyCbfResult) -> dict:
        return {
            "code": item.cbfbm,
            "typeCode": item.cbflx,
            "name": item.cbfmc,
            "idType": item.cbfzjlx,
            "idNo": item.cbfzjhm,
            "mobile": item.lxdh,
            "address": item.cbfdz,
            "memberCount": item.cbfcysl,
            "surveyDate": item.cbfdcrq.date().isoformat() if item.cbfdcrq else None,
            "surveyorName": item.cbfdcy,
            "groupRegionName": item.group_region_name,
        }

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.combine(date.fromisoformat(value), datetime.min.time())


issuer_service = IssuerService()
