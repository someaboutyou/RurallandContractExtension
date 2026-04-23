from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.user import User
from app.models.role import Role


class AuthRepository:
    def get_user_by_username(self, db: Session, username: str) -> User | None:
        stmt = (
            select(User)
            .options(joinedload(User.tenant), joinedload(User.role).joinedload(Role.permissions), joinedload(User.region))
            .where(User.username == username)
        )
        return db.scalar(stmt)

    def get_user_by_id(self, db: Session, user_id: int) -> User | None:
        stmt = (
            select(User)
            .options(joinedload(User.tenant), joinedload(User.role).joinedload(Role.permissions), joinedload(User.region))
            .where(User.id == user_id)
        )
        return db.scalar(stmt)


auth_repository = AuthRepository()
