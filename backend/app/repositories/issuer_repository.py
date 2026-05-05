from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.fbf import Fbf


class IssuerRepository:
    def list_issuers(
        self,
        db: Session,
        page: int,
        page_size: int,
        *,
        extra_filters: list | None = None,
        keyword: str | None = None,
        region_code: str | None = None,
    ) -> tuple[list[Fbf], int]:
        total_stmt = select(func.count(Fbf.fbfbm))
        stmt = select(Fbf).order_by(Fbf.fbfbm.desc()).offset((page - 1) * page_size).limit(page_size)
        if extra_filters:
            total_stmt = total_stmt.where(*extra_filters)
            stmt = stmt.where(*extra_filters)
        if region_code:
            condition = Fbf.region_code.like(f"{region_code}%")
            total_stmt = total_stmt.where(condition)
            stmt = stmt.where(condition)
        if keyword:
            pattern = f"%{keyword}%"
            keyword_filter = or_(
                Fbf.fbfbm.ilike(pattern),
                Fbf.fbfmc.ilike(pattern),
                Fbf.fbffzrxm.ilike(pattern),
                Fbf.fzrzjhm.ilike(pattern),
                Fbf.lxdh.ilike(pattern),
            )
            total_stmt = total_stmt.where(keyword_filter)
            stmt = stmt.where(keyword_filter)
        total = db.scalar(total_stmt) or 0
        return list(db.scalars(stmt).all()), total

    def get_issuer(self, db: Session, issuer_code: str) -> Fbf | None:
        return db.get(Fbf, issuer_code)

    def create_issuer(self, db: Session, issuer: Fbf) -> Fbf:
        db.add(issuer)
        db.commit()
        db.refresh(issuer)
        return issuer

    def update_issuer(self, db: Session, issuer: Fbf) -> Fbf:
        db.add(issuer)
        db.commit()
        db.refresh(issuer)
        return issuer

    def delete_issuer(self, db: Session, issuer: Fbf) -> None:
        db.delete(issuer)
        db.commit()


issuer_repository = IssuerRepository()
