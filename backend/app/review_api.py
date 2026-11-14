"""Explicit dashboard Evidence decisions, independent of any Flag."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field, StringConstraints
from sqlalchemy import select

from app import models
from app.schemas import EvidenceView, Identifier, Record
from app.site_api import Database

router = APIRouter(tags=["Evidence"])
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class HumanAction(Record):
    actor: Identifier
    role: Literal["superintendent", "crew_lead"]
    channel: Literal["dashboard"]


def validate_person(session, action):
    # Deliberately a demo role switcher, not authentication. Agent channels and
    # system actors cannot use these human-only request schemas.
    if action.role == "crew_lead" and session.get(models.CrewLead, action.actor) is None:
        raise HTTPException(403, "Unknown Crew Lead")


class EvidenceDecision(HumanAction):
    decision: Literal["confirmed", "rejected"]
    expected_sequence: Annotated[int, Field(ge=0)]
    reason: Reason


def validate_scope(session, evidence):
    if evidence.zone_id is None or session.get(models.Zone, evidence.zone_id) is None:
        raise HTTPException(422, "Evidence needs a resolved Zone before confirmation")
    if evidence.kind == "inspection":
        subject = session.get(models.Inspection, evidence.inspection_id) if evidence.inspection_id else None
        valid = subject is not None and subject.zone_id == evidence.zone_id
    elif evidence.kind == "task_completion":
        subject = session.get(models.Task, evidence.task_id) if evidence.task_id else None
        valid = subject is not None and subject.zone_id == evidence.zone_id
    else:
        revision = session.get(models.Revision, evidence.revision_id) if evidence.revision_id else None
        crew = session.get(models.Crew, evidence.crew_id) if evidence.crew_id else None
        plan = session.get(models.Plan, revision.plan_id) if revision else None
        valid = revision is not None and crew is not None and (
            evidence.zone_id in revision.zone_ids or evidence.zone_id == plan.floor_id
        )
    if not valid:
        raise HTTPException(422, "Evidence scope is incomplete or does not match its subject")


def validate_evidence_reviewer(session, evidence, action):
    validate_person(session, action)
    if action.role == "superintendent":
        return
    # Inspection decisions are reserved for the Superintendent. Crew Leads may
    # review only their own Crew's exact revision or Task completion statements.
    crew_id = evidence.crew_id
    if evidence.kind == "task_completion" and evidence.task_id:
        task = session.get(models.Task, evidence.task_id)
        crew_id = task.crew_id if task else None
    crew = session.get(models.Crew, crew_id) if crew_id else None
    if evidence.kind == "inspection" or crew is None or crew.lead_id != action.actor:
        raise HTTPException(403, "Evidence review requires the responsible role/person")


@router.post("/evidence/{evidence_id}/reviews", response_model=EvidenceView)
def review_evidence(evidence_id: str, action: EvidenceDecision, session: Database):
    # Same lock order as ingestion/rules: Site first, then the reviewed record.
    session.scalar(select(models.Site).with_for_update())
    evidence = session.get(models.Evidence, evidence_id)
    if evidence is None:
        raise HTTPException(404, "Evidence not found")
    validate_evidence_reviewer(session, evidence, action)
    sequence = evidence.history[-1].sequence if evidence.history else 0
    if action.expected_sequence != sequence:
        raise HTTPException(409, "Evidence changed; inspect the current review history")
    if action.decision == evidence.review_status:
        raise HTTPException(409, "Evidence already has this review status")
    if action.decision == "confirmed":
        validate_scope(session, evidence)
        if not evidence.quote.strip() or not evidence.source_ref.strip():
            raise HTTPException(422, "Source-backed Evidence is required")
        if evidence.origin == "llm_statement":
            statement = session.get(models.Event, evidence.statement_ref) if evidence.statement_ref else None
            if (statement is None or evidence.source_ref != f"source:{statement.source_message_id}"
                    or evidence.quote != statement.quote):
                raise HTTPException(422, "Evidence source does not match the original statement")
    now = datetime.now(UTC)
    evidence.history.append(models.EvidenceReview(
        sequence=sequence + 1, status=action.decision, actor_type="human",
        reviewer_id=action.actor, reviewer_role=action.role,
        decided_at=now, recorded_at=now, reason=action.reason,
    ))
    # ORM hook re-evaluates rules inside this commit; any failure rolls back all.
    session.commit()
    return evidence
