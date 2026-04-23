from sqlalchemy.orm import Session

from app.repositories.tenant_repository import tenant_repository


class TenantService:
    def list_tenants(self, db: Session) -> list[dict]:
        return [
            {
                "code": item.code,
                "name": item.name,
                "regionCode": item.region_code,
                "status": item.status,
                "description": item.description,
            }
            for item in tenant_repository.list_tenants(db)
        ]


tenant_service = TenantService()
