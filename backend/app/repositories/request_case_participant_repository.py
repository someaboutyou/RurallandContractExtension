from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.request_case_participant import RequestCaseParticipant


class RequestCaseParticipantRepository:
    def create_participant(self, db: Session, participant: RequestCaseParticipant) -> RequestCaseParticipant:
        db.add(participant)
        db.commit()
        db.refresh(participant)
        return participant

    def list_case_participants(self, db: Session, case_id: int) -> list[RequestCaseParticipant]:
        stmt = (
            select(RequestCaseParticipant)
            .where(RequestCaseParticipant.case_id == case_id)
            .order_by(RequestCaseParticipant.created_at.asc(), RequestCaseParticipant.id.asc())
        )
        return list(db.scalars(stmt).all())


request_case_participant_repository = RequestCaseParticipantRepository()
