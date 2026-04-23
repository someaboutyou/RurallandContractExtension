from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.region import Region


class RegionRepository:
    def list_regions(
        self,
        db: Session,
        level: str | None = None,
        tenant_code: str | None = None,
    ) -> list[Region]:
        stmt = select(Region).order_by(Region.code)
        if level:
            stmt = stmt.where(Region.level == level)
        if tenant_code:
            stmt = stmt.where(Region.tenant_code == tenant_code)
        return list(db.scalars(stmt).all())

    def get_region(self, db: Session, region_id: int) -> Region | None:
        return db.get(Region, region_id)


region_repository = RegionRepository()
