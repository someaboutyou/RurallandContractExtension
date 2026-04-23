from sqlalchemy.orm import Session

from app.repositories.permission_repository import permission_repository


class PermissionService:
    def list_permissions(self, db: Session) -> list[dict]:
        records = permission_repository.list_permissions(db)
        return [
            {
                "id": item.id,
                "name": item.name,
                "code": item.code,
                "groupName": item.group_name,
                "category": item.category,
                "description": item.description,
            }
            for item in records
        ]


permission_service = PermissionService()
