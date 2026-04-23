from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.role import Role
from app.models.user import User


class RoleRepository:
    def list_roles(self, db: Session) -> list[tuple[Role, int]]:
        stmt = (
            select(Role, func.count(User.id))
            .options(selectinload(Role.permissions))
            .outerjoin(User, User.role_id == Role.id)
            .group_by(Role.id)
            .order_by(Role.id)
        )
        return list(db.execute(stmt).all())

    def get_role(self, db: Session, role_id: int) -> Role | None:
        stmt = select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
        return db.scalars(stmt).first()

    def get_role_by_code(self, db: Session, code: str) -> Role | None:
        stmt = select(Role).options(selectinload(Role.permissions)).where(Role.code == code)
        return db.scalars(stmt).first()

    def count_users(self, db: Session, role_id: int) -> int:
        stmt = select(func.count(User.id)).where(User.role_id == role_id)
        return db.scalar(stmt) or 0

    def add_role(self, db: Session, role: Role) -> Role:
        db.add(role)
        db.commit()
        db.refresh(role)
        return role

    def update_role(self, db: Session, role: Role) -> Role:
        db.add(role)
        db.commit()
        db.refresh(role)
        return role

    def delete_role(self, db: Session, role: Role) -> None:
        db.delete(role)
        db.commit()


role_repository = RoleRepository()
