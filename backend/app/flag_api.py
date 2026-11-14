"""Flag inbox, history and authorized human lifecycle actions."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from sqlalchemy import case, select

from app import models
from app.outbox import OutboxView
from app.ingestion_schemas import EventView
from app.ingestion import event_views
from app.schemas import EvidenceView, Identifier, Record, Timestamp
from app.site_api import Database
from app.rules import flag_evidence
from app.proposal_api import AdviceView, advice_view
from app.lifecycle import InvalidTransition, transition_flag
from app.review_api import HumanAction, Reason, validate_person
from app.learning import record_knowledge, validate_correction

router = APIRouter(tags=["Flags"])


class Responsible(Record):
    id: Identifier
    name: str


class AuditView(Record):
    actor_role: str | None
    from_state: str | None
    to_state: str | None
    feedback: Literal["confirmed", "resolved", "false_alarm"] | None
    reason: str | None
    action: str
    actor: str
    channel: str
    source_ref: str
    recorded_at: Timestamp


class FlagView(Record):
    id: Identifier
    type: str
    zone_id: Identifier
    task_id: Identifier | None
    activity: str
    precondition: str
    inspection_id: Identifier | None
    severity: Literal["high", "medium", "low"]
    responsible: Responsible | None
    state: Literal["detected", "notified", "acknowledged", "in_progress", "resolved", "false_alarm"]
    evaluation: Literal["satisfied", "not_satisfied", "unknown", "contradictory"]
    explanation: str
    context: dict
    created_at: Timestamp
    updated_at: Timestamp
    sources: list[EventView]
    evidence: list[EvidenceView]
    audit: list[AuditView]
    awaiting_human_closure: bool
    notifications: list[OutboxView]
    advice: AdviceView | None


def flag_view(session, flag):
    return FlagView.model_validate({
        **{key: getattr(flag, key) for key in FlagView.model_fields if key not in {"sources", "evidence", "awaiting_human_closure", "notifications", "advice"}},
        "advice": advice_view(session, flag),
        "awaiting_human_closure": flag.evaluation == "satisfied" and flag.state not in {"resolved", "false_alarm"},
        "notifications": session.scalars(select(models.OutboxMessage).where(models.OutboxMessage.flag_id == flag.id)).all(),
        "sources": event_views(session, [link.event for link in flag.sources]),
        "evidence": flag_evidence(session, flag),
    })


@router.get("/flags", response_model=list[FlagView])
def get_flags(session: Database, status: Literal["open", "closed", "all"] = "open"):
    """Open by default, or closed/all; schedule filters never hide Flags."""
    statement = select(models.Flag)
    if status == "open":
        statement = statement.where(models.Flag.state.not_in(["resolved", "false_alarm"]))
    elif status == "closed":
        statement = statement.where(models.Flag.state.in_(["resolved", "false_alarm"]))
    flags = session.scalars(statement.order_by(case({"high": 0, "medium": 1, "low": 2}, value=models.Flag.severity),
               models.Flag.created_at, models.Flag.id)).all()
    return [flag_view(session, flag) for flag in flags]


@router.get("/flags/{flag_id}", response_model=FlagView)
def get_flag(flag_id: str, session: Database):
    flag = session.get(models.Flag, flag_id)
    if flag is None:
        raise HTTPException(404, "Flag not found")
    return flag_view(session, flag)


class FlagAction(HumanAction):
    correction_event_id: Identifier | None = None
    action: Literal["acknowledge", "resolved", "false_alarm"]
    feedback: Literal["confirmed", "resolved", "false_alarm"]
    reason: Reason
    expected_state: Literal["detected", "notified", "acknowledged", "in_progress", "resolved", "false_alarm"]


@router.post("/flags/{flag_id}/actions", response_model=FlagView)
def act_on_flag(flag_id: str, action: FlagAction, session: Database):
    session.scalar(select(models.Site).with_for_update())
    flag = session.get(models.Flag, flag_id)
    if flag is None:
        raise HTTPException(404, "Flag not found")
    validate_person(session, action)
    if action.role == "crew_lead" and flag.responsible_id != action.actor:
        raise HTTPException(403, "Only the responsible Crew Lead may act on this Flag")
    if flag.state != action.expected_state:
        raise HTTPException(409, "Flag changed; inspect its current state")
    validate_correction(flag, action)
    try:
        transition_flag(session, flag, action=action.action, actor=action.actor,
                        actor_type="human", role=action.role, channel=action.channel,
                        source_ref=f"flag:{flag.id}", feedback=action.feedback, reason=action.reason)
    except InvalidTransition as error:
        raise HTTPException(409, str(error)) from error
    record_knowledge(session, flag, action.correction_event_id)
    session.commit()
    return flag_view(session, flag)
