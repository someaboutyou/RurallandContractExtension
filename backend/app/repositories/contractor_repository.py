from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.survey import SurveyCbfBase, SurveyCbfJtcyBase, SurveyCbfJtcyResult, SurveyCbfResult


class ContractorRepository:
    def list_contractors(
        self,
        db: Session,
        page: int,
        page_size: int,
        *,
        extra_filters: list | None = None,
        keyword: str | None = None,
        type_code: str | None = None,
        name: str | None = None,
        member_name: str | None = None,
        id_no: str | None = None,
        address: str | None = None,
        region_code: str | None = None,
    ) -> tuple[list[SurveyCbfResult], int]:
        total_stmt = select(func.count(SurveyCbfResult.id))
        stmt = select(SurveyCbfResult).order_by(SurveyCbfResult.id.desc()).offset((page - 1) * page_size).limit(page_size)
        if extra_filters:
            total_stmt = total_stmt.where(*extra_filters)
            stmt = stmt.where(*extra_filters)
        if region_code:
            condition = SurveyCbfResult.region_code.like(f"{region_code}%")
            total_stmt = total_stmt.where(condition)
            stmt = stmt.where(condition)
        if keyword:
            pattern = f"%{keyword}%"
            keyword_filter = or_(
                SurveyCbfResult.cbfbm.ilike(pattern),
                SurveyCbfResult.cbfmc.ilike(pattern),
                SurveyCbfResult.cbfzjhm.ilike(pattern),
                SurveyCbfResult.lxdh.ilike(pattern),
                SurveyCbfResult.cbfdz.ilike(pattern),
            )
            total_stmt = total_stmt.where(keyword_filter)
            stmt = stmt.where(keyword_filter)
        if type_code:
            total_stmt = total_stmt.where(SurveyCbfResult.cbflx == type_code)
            stmt = stmt.where(SurveyCbfResult.cbflx == type_code)
        if name:
            condition = SurveyCbfResult.cbfmc.ilike(f"%{name}%")
            total_stmt = total_stmt.where(condition)
            stmt = stmt.where(condition)
        if member_name:
            condition = exists(
                select(SurveyCbfJtcyResult.id).where(
                    SurveyCbfJtcyResult.batch_id == SurveyCbfResult.batch_id,
                    SurveyCbfJtcyResult.contractor_uid == SurveyCbfResult.contractor_uid,
                    SurveyCbfJtcyResult.cyxm.ilike(f"%{member_name}%"),
                )
            )
            total_stmt = total_stmt.where(condition)
            stmt = stmt.where(condition)
        if id_no:
            pattern = f"%{id_no}%"
            condition = or_(
                SurveyCbfResult.cbfzjhm.ilike(pattern),
                exists(
                    select(SurveyCbfJtcyResult.id).where(
                        SurveyCbfJtcyResult.batch_id == SurveyCbfResult.batch_id,
                        SurveyCbfJtcyResult.contractor_uid == SurveyCbfResult.contractor_uid,
                        SurveyCbfJtcyResult.cyzjhm.ilike(pattern),
                    )
                ),
            )
            total_stmt = total_stmt.where(condition)
            stmt = stmt.where(condition)
        if address:
            condition = SurveyCbfResult.cbfdz.ilike(f"%{address}%")
            total_stmt = total_stmt.where(condition)
            stmt = stmt.where(condition)
        total = db.scalar(total_stmt) or 0
        return list(db.scalars(stmt).all()), total

    def get_contractor(self, db: Session, code: str) -> SurveyCbfResult | None:
        return db.scalar(
            select(SurveyCbfResult).where(SurveyCbfResult.cbfbm == code).order_by(SurveyCbfResult.id.desc()).limit(1)
        )

    def get_contractor_in_batch(self, db: Session, batch_id: int, code: str) -> SurveyCbfResult | None:
        return db.scalar(
            select(SurveyCbfResult)
            .where(SurveyCbfResult.batch_id == batch_id, SurveyCbfResult.cbfbm == code)
            .order_by(SurveyCbfResult.id.desc())
            .limit(1)
        )

    def list_family_members(self, db: Session, contractor: SurveyCbfResult) -> list[SurveyCbfJtcyResult]:
        stmt = (
            select(SurveyCbfJtcyResult)
            .where(
                SurveyCbfJtcyResult.batch_id == contractor.batch_id,
                SurveyCbfJtcyResult.contractor_uid == contractor.contractor_uid,
            )
            .order_by(SurveyCbfJtcyResult.cyxm, SurveyCbfJtcyResult.cyzjhm)
        )
        return list(db.scalars(stmt).all())

    def delete_contractor(self, db: Session, contractor: SurveyCbfResult) -> None:
        db.execute(
            delete(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.batch_id == contractor.batch_id,
                SurveyCbfJtcyResult.contractor_uid == contractor.contractor_uid,
            )
        )
        db.execute(
            delete(SurveyCbfJtcyBase).where(
                SurveyCbfJtcyBase.batch_id == contractor.batch_id,
                SurveyCbfJtcyBase.contractor_uid == contractor.contractor_uid,
            )
        )
        if contractor.base_id:
            base = db.get(SurveyCbfBase, contractor.base_id)
            if base is not None:
                db.delete(base)
        db.delete(contractor)
        db.commit()


contractor_repository = ContractorRepository()
