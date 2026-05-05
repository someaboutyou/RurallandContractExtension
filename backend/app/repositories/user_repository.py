from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.user import User


class UserRepository:
    def list_users(
        self,
        db: Session,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        role_id: int | None = None,
        tenant_code: str | None = None,
        status: str | None = None,
    ) -> tuple[list[User], int]:
        stmt = select(User)
        count_stmt = select(func.count(User.id))

        if keyword:
            like_value = f"%{keyword}%"
            condition = or_(User.username.ilike(like_value), User.real_name.ilike(like_value))
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        if role_id is not None:
            stmt = stmt.where(User.role_id == role_id)
            count_stmt = count_stmt.where(User.role_id == role_id)

        if tenant_code:
            stmt = stmt.where(User.tenant_code == tenant_code)
            count_stmt = count_stmt.where(User.tenant_code == tenant_code)

        if status:
            stmt = stmt.where(User.status == status)
            count_stmt = count_stmt.where(User.status == status)

        stmt = (
            stmt.options(joinedload(User.tenant), joinedload(User.role), joinedload(User.region), selectinload(User.region_permissions))
            .order_by(User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(db.scalars(stmt).unique().all())
        total = db.scalar(count_stmt) or 0
        return items, total

    def get_user(self, db: Session, user_id: int) -> User | None:
        stmt = select(User).options(
            joinedload(User.tenant),
            joinedload(User.role),
            joinedload(User.region),
            selectinload(User.region_permissions),
        ).where(User.id == user_id)
        return db.scalars(stmt).unique().first()

    def get_user_by_username(self, db: Session, username: str) -> User | None:
        stmt = select(User).options(
            joinedload(User.tenant),
            joinedload(User.role),
            joinedload(User.region),
            selectinload(User.region_permissions),
        ).where(User.username == username)
        return db.scalars(stmt).first()

    def add_user(self, db: Session, user: User) -> User:
        db.add(user)
        db.commit()
        db.refresh(user)
        return self.get_user(db, user.id) or user

    def update_user(self, db: Session, user: User) -> User:
        db.add(user)
        db.commit()
        db.refresh(user)
        return self.get_user(db, user.id) or user

    def delete_user(self, db: Session, user: User) -> None:
        db.delete(user)
        db.commit()


user_repository = UserRepository()
