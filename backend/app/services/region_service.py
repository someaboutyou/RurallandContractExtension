from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.region_repository import region_repository


class RegionService:
    def list_regions(self, db: Session, current_user: User, level: str | None = None) -> list[dict]:
        tenant_code = None if current_user.role.data_scope == "all" else current_user.tenant_code
        records = region_repository.list_regions(db, level=level, tenant_code=tenant_code)
        return [
            {
                "id": item.id,
                "name": item.name,
                "code": item.code,
                "level": item.level,
                "tenantCode": item.tenant_code,
                "fullName": item.full_name,
            }
            for item in records
        ]


region_service = RegionService()
