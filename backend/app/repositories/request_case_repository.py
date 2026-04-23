from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.request_case import RequestCase
from app.models.request_case_participant import RequestCaseParticipant
from app.models.user import User


class RequestCaseRepository:
    def list_cases(
        self,
        db: Session,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        status: str | None = None,
        extra_filters: list | None = None,
    ) -> tuple[list[RequestCase], int]:
        filters = []
        if keyword:
            like_value = f"%{keyword.strip()}%"
            filters.append(
                or_(
                    RequestCase.serial_no.ilike(like_value),
                    RequestCase.request_title.ilike(like_value),
                    RequestCase.contractor_name.ilike(like_value),
                    RequestCase.issuer_name.ilike(like_value),
                    RequestCase.contractor_id_no.ilike(like_value),
                )
            )
        if status:
            filters.append(RequestCase.status == status)
        if extra_filters:
            filters.extend(extra_filters)

        total_stmt = select(func.count(RequestCase.id))
        if filters:
            total_stmt = total_stmt.where(*filters)
        total = db.scalar(total_stmt) or 0

        stmt = (
            select(RequestCase)
            .options(
                joinedload(RequestCase.issuer),
                joinedload(RequestCase.created_by),
                joinedload(RequestCase.workflow_version),
                selectinload(RequestCase.participants)
                .joinedload(RequestCaseParticipant.user)
                .joinedload(User.role),
            )
            .order_by(RequestCase.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        if filters:
            stmt = stmt.where(*filters)
        return list(db.scalars(stmt).unique().all()), total

    def get_case(self, db: Session, case_id: int, *, extra_filters: list | None = None) -> RequestCase | None:
        stmt = (
            select(RequestCase)
            .options(
                joinedload(RequestCase.issuer),
                joinedload(RequestCase.created_by),
                joinedload(RequestCase.workflow_version),
                selectinload(RequestCase.participants)
                .joinedload(RequestCaseParticipant.user)
                .joinedload(User.role),
            )
            .where(RequestCase.id == case_id)
        )
        if extra_filters:
            stmt = stmt.where(*extra_filters)
        return db.scalar(stmt)

    def create_case(self, db: Session, record: RequestCase) -> RequestCase:
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def update_case(self, db: Session, record: RequestCase) -> RequestCase:
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def delete_case(self, db: Session, record: RequestCase) -> None:
        db.delete(record)
        db.commit()


request_case_repository = RequestCaseRepository()
