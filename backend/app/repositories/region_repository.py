from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.region import Region


class RegionRepository:
    def list_regions(
        self,
        db: Session,
        level: str | None = None,
        tenant_code: str | None = None,
    ) -> list[Region]:
        stmt = select(Region).order_by(Region.sort_order.asc(), Region.code.asc())
        if level:
            stmt = stmt.where(Region.level == level)
        if tenant_code:
            stmt = stmt.where(Region.tenant_code == tenant_code)
        return list(db.scalars(stmt).all())

    def get_region(self, db: Session, region_id: int) -> Region | None:
        return db.get(Region, region_id)

    def get_region_by_code(self, db: Session, code: str) -> Region | None:
        return db.scalar(select(Region).where(Region.code == code))

    def list_children(
        self,
        db: Session,
        parent_id: int | None = None,
        tenant_code: str | None = None,
        include_groups: bool = False,
    ) -> list[Region]:
        stmt = select(Region).where(Region.parent_id.is_(None) if parent_id is None else Region.parent_id == parent_id)
        if tenant_code:
            stmt = stmt.where(Region.tenant_code == tenant_code)
        if not include_groups:
            stmt = stmt.where(Region.level != "group")
        return list(db.scalars(stmt.order_by(Region.sort_order.asc(), Region.code.asc())).all())

    def search_regions(
        self,
        db: Session,
        keyword: str,
        tenant_code: str | None = None,
        include_groups: bool = False,
        limit: int = 50,
    ) -> list[Region]:
        pattern = f"%{keyword.strip()}%"
        stmt = select(Region).where(
            or_(
                Region.code.ilike(pattern),
                Region.name.ilike(pattern),
                Region.full_name.ilike(pattern),
            )
        )
        if tenant_code:
            stmt = stmt.where(Region.tenant_code == tenant_code)
        if not include_groups:
            stmt = stmt.where(Region.level != "group")
        return list(db.scalars(stmt.order_by(Region.sort_order.asc(), Region.code.asc()).limit(limit)).all())


region_repository = RegionRepository()
