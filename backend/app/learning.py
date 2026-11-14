"""Human feedback context and exact-case extraction corrections, never rule overrides."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app import models
from app.schemas import Identifier, Record, Timestamp
from app.site_api import Database

router = APIRouter(tags=["Site Knowledge"])


def validate_correction(flag, action):
    if action.correction_event_id is None:
        return
    event = next((link.event for link in flag.sources if link.event_id == action.correction_event_id), None)
    if action.action != "false_alarm" or event is None or event.intent != "planned_work":
        raise HTTPException(422, "Only false-alarm feedback may correct a linked planned-work Event to a question")


def record_knowledge(session, flag, correction_event_id):
    session.flush()
    session.add(models.SiteKnowledge(
        id=uuid4().hex, feedback_id=flag.audit[-1].id, correction_event_id=correction_event_id,
    ))


def extraction_correction(session, source, statement, ordinal):
    entries = session.scalars(select(models.SiteKnowledge).where(
        models.SiteKnowledge.correction_event_id.is_not(None),
    ).order_by(models.SiteKnowledge.id))
    for entry in entries:
        original = entry.correction_event
        previous = original.source
        if (entry.feedback.feedback == "false_alarm"
                and previous.site_id == source.site_id
                and previous.text == source.text
                and previous.sender_role == source.sender_role
                and previous.sender_crew_id == source.sender_crew_id
                and original.ordinal == ordinal
                and original.quote == statement.quote
                and original.intent == statement.intent == "planned_work"):
            return entry
    return None


class KnowledgeView(Record):
    id: Identifier
    flag_id: Identifier
    feedback_id: int
    feedback: str
    reason: str
    recorded_at: Timestamp
    source_ids: list[str]
    correction_event_id: Identifier | None
    correction: str | None


@router.get("/site-knowledge", response_model=list[KnowledgeView])
def get_knowledge(session: Database):
    result = []
    for entry in session.scalars(select(models.SiteKnowledge).order_by(models.SiteKnowledge.feedback_id)):
        audit = entry.feedback
        flag = session.get(models.Flag, audit.flag_id)
        result.append(KnowledgeView(
            id=entry.id, flag_id=flag.id, feedback_id=audit.id, feedback=audit.feedback,
            reason=audit.reason, recorded_at=audit.recorded_at,
            source_ids=sorted({link.event.source_message_id for link in flag.sources}),
            correction_event_id=entry.correction_event_id,
            correction="planned_work → question (exact message, role and Crew only)" if entry.correction_event_id else None,
        ))
    return result


class FeedbackMetric(Record):
    date: str
    confirmed_flags: int
    reviewed_flags: int
    confirmed_share: float


@router.get("/metrics/flag-feedback", response_model=list[FeedbackMetric])
def get_feedback_metric(session: Database):
    audits = session.scalars(select(models.FlagAudit).where(
        models.FlagAudit.feedback.is_not(None),
    ).order_by(models.FlagAudit.recorded_at, models.FlagAudit.id))
    verdicts, days = {}, {}
    for audit in audits:
        verdicts[audit.flag_id] = audit.feedback != "false_alarm"
        day = audit.recorded_at.date().isoformat()
        confirmed = sum(verdicts.values())
        days[day] = FeedbackMetric(
            date=day, confirmed_flags=confirmed, reviewed_flags=len(verdicts),
            confirmed_share=confirmed / len(verdicts),
        )
    return list(days.values())
