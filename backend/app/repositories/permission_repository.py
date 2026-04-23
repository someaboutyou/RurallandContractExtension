from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.permission import Permission


class PermissionRepository:
    def list_permissions(self, db: Session) -> list[Permission]:
        stmt = select(Permission).order_by(Permission.group_name, Permission.category, Permission.id)
        return list(db.scalars(stmt).all())

    def list_by_codes(self, db: Session, codes: list[str]) -> list[Permission]:
        if not codes:
            return []
        stmt = select(Permission).where(Permission.code.in_(codes))
        return list(db.scalars(stmt).all())

    def get_permission_by_code(self, db: Session, code: str) -> Permission | None:
        stmt = select(Permission).where(Permission.code == code)
        return db.scalars(stmt).first()


permission_repository = PermissionRepository()
