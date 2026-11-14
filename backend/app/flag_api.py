"""Read-only Flag inbox. Lifecycle and human review actions belong to #9."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from sqlalchemy import case, select

from app import models
from app.outbox import OutboxView
from app.ingestion_schemas import EventView
from app.ingestion import event_views
from app.schemas import EvidenceView, Identifier, Record, Timestamp
from app.site_api import Database
from app.rules import inspection_evidence, inspection_evidence_scope

router = APIRouter(tags=["Flags"])


class Responsible(Record):
    id: Identifier
    name: str


class AuditView(Record):
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
    created_at: Timestamp
    updated_at: Timestamp
    sources: list[EventView]
    evidence: list[EvidenceView]
    audit: list[AuditView]
    notifications: list[OutboxView]


def flag_view(session, flag):
    inspection = session.get(models.Inspection, flag.inspection_id) if flag.inspection_id else None
    zones = {zone.id: zone for zone in session.scalars(select(models.Zone))} if inspection else {}
    return FlagView.model_validate({
        **{key: getattr(flag, key) for key in FlagView.model_fields if key not in {"sources", "evidence", "notifications"}},
        "notifications": session.scalars(select(models.OutboxMessage).where(models.OutboxMessage.flag_id == flag.id)).all(),
        "sources": event_views(session, [link.event for link in flag.sources]),
        "evidence": inspection_evidence(session, inspection, inspection_evidence_scope(flag.zone_id, zones)) if inspection else [],
    })


@router.get("/flags", response_model=list[FlagView])
def get_flags(session: Database):
    """All open Flags, highest severity first; unrelated schedule filters do not hide them."""
    flags = session.scalars(select(models.Flag).where(
        models.Flag.state.not_in(["resolved", "false_alarm"]),
    ).order_by(case({"high": 0, "medium": 1, "low": 2}, value=models.Flag.severity),
               models.Flag.created_at, models.Flag.id)).all()
    return [flag_view(session, flag) for flag in flags]


@router.get("/flags/{flag_id}", response_model=FlagView)
def get_flag(flag_id: str, session: Database):
    flag = session.get(models.Flag, flag_id)
    if flag is None:
        raise HTTPException(404, "Flag not found")
    return flag_view(session, flag)
