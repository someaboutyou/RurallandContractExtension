from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.cbf import Cbf
from app.models.cbf_jtcy import CbfJtcy


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
    ) -> tuple[list[Cbf], int]:
        total_stmt = select(func.count(Cbf.cbfbm))
        stmt = select(Cbf).order_by(Cbf.cbfbm.desc()).offset((page - 1) * page_size).limit(page_size)
        if extra_filters:
            total_stmt = total_stmt.where(*extra_filters)
            stmt = stmt.where(*extra_filters)
        if keyword:
            pattern = f"%{keyword}%"
            keyword_filter = or_(
                Cbf.cbfbm.ilike(pattern),
                Cbf.cbfmc.ilike(pattern),
                Cbf.cbfzjhm.ilike(pattern),
                Cbf.lxdh.ilike(pattern),
                Cbf.cbfdz.ilike(pattern),
            )
            total_stmt = total_stmt.where(keyword_filter)
            stmt = stmt.where(keyword_filter)
        if type_code:
            total_stmt = total_stmt.where(Cbf.cbflx == type_code)
            stmt = stmt.where(Cbf.cbflx == type_code)
        total = db.scalar(total_stmt) or 0
        return list(db.scalars(stmt).all()), total

    def get_contractor(self, db: Session, code: str) -> Cbf | None:
        return db.get(Cbf, code)

    def list_family_members(self, db: Session, code: str) -> list[CbfJtcy]:
        stmt = select(CbfJtcy).where(CbfJtcy.cbfbm == code).order_by(CbfJtcy.cyxm, CbfJtcy.cyzjhm)
        return list(db.scalars(stmt).all())

    def create_contractor(self, db: Session, contractor: Cbf, family_members: list[CbfJtcy]) -> Cbf:
        db.add(contractor)
        for member in family_members:
            db.add(member)
        db.commit()
        db.refresh(contractor)
        return contractor

    def update_contractor(self, db: Session, contractor: Cbf, family_members: list[CbfJtcy]) -> Cbf:
        db.add(contractor)
        db.execute(delete(CbfJtcy).where(CbfJtcy.cbfbm == contractor.cbfbm))
        for member in family_members:
            db.add(member)
        db.commit()
        db.refresh(contractor)
        return contractor

    def delete_contractor(self, db: Session, code: str) -> None:
        db.execute(delete(CbfJtcy).where(CbfJtcy.cbfbm == code))
        contractor = db.get(Cbf, code)
        if contractor is not None:
            db.delete(contractor)
        db.commit()


contractor_repository = ContractorRepository()
