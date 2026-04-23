from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant import Tenant


class TenantRepository:
    def list_tenants(self, db: Session) -> list[Tenant]:
        stmt = select(Tenant).order_by(Tenant.code)
        return list(db.scalars(stmt).all())

    def get_tenant(self, db: Session, code: str) -> Tenant | None:
        return db.get(Tenant, code)


tenant_repository = TenantRepository()
