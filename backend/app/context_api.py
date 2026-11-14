"""Source-backed, read-only context for dashboards and replaceable agents."""

import json
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field
from sqlalchemy import or_, select

from app import models, schemas
from app.flag_api import FlagView, flag_view
from app.ingestion import event_views
from app.ingestion_schemas import EventView
from app.revision_rules import receipt_evidence, revision_work
from app.sequence_rules import completion_evidence
from app.rules import PRECONDITIONS, affected_work, ancestors, inspection_evidence, inspection_evidence_scope, utc
from app.site_api import Database, get_plans, zone_scope

router = APIRouter(prefix="/context", tags=["Context"])
EvaluationStatus = Literal["satisfied", "not_satisfied", "unknown", "contradictory"]
SAFETY_NOTICE = (
    "Unconfirmed statements are not proof. Missing evaluations or the absence of open Flags do not grant clearance. "
    "Evidence review, Proposal approval and Flag closure are separate human dashboard actions."
)


class PreconditionView(schemas.Record):
    name: str
    zone_id: str
    task_id: str | None
    evaluation: EvaluationStatus
    explanation: str
    inspection_id: str | None = None
    context: dict = Field(default_factory=dict)
    source_refs: list[str]


class ZoneStatus(schemas.Record):
    zone: schemas.Zone
    zones: list[schemas.Zone]
    plans: list[schemas.PlanView]
    tasks: list[schemas.Task]
    inspections: list[schemas.Inspection]
    evidence: list[schemas.EvidenceView]
    preconditions: list[PreconditionView]
    open_flags: list[FlagView]
    events: list[EventView]
    source_refs: list[str]
    safety_notice: str = SAFETY_NOTICE


def context_scope(session, zone_id):
    zones = {zone.id: zone for zone in session.scalars(select(models.Zone).order_by(models.Zone.id))}
    if zone_id is None:
        return zones, set(zones)
    descendants = zone_scope(session, zone_id, True)
    return zones, descendants | set(ancestors(zone_id, zones))


def scoped_records(session, zone_id):
    zones, scope = context_scope(session, zone_id)
    tasks = session.scalars(select(models.Task).where(models.Task.zone_id.in_(scope)).order_by(
        models.Task.starts_at, models.Task.id)).all()
    inspections = session.scalars(select(models.Inspection).where(models.Inspection.zone_id.in_(scope)).order_by(
        models.Inspection.scheduled_at, models.Inspection.id)).all()
    evidence_query = select(models.Evidence).order_by(models.Evidence.id)
    events_query = select(models.Event).join(models.SourceMessage).order_by(
        models.SourceMessage.sent_at, models.SourceMessage.id, models.Event.ordinal)
    if zone_id is not None:
        evidence_query = evidence_query.where(or_(
            models.Evidence.zone_id.in_(scope),
            models.Evidence.inspection_id.in_([item.id for item in inspections]),
            models.Evidence.task_id.in_([task.id for task in tasks]),
        ))
        events_query = events_query.where(models.Event.zones.any(models.Zone.id.in_(scope)))
    evidence = session.scalars(evidence_query).all()
    events = session.scalars(events_query).all()
    flags = session.scalars(select(models.Flag).where(models.Flag.zone_id.in_(scope)).order_by(
        models.Flag.created_at, models.Flag.id)).all()
    return zones, scope, tasks, inspections, evidence, events, flags


def preconditions(session, zones, scope, tasks):
    result = []
    statements = session.scalars(select(models.Event).order_by(models.Event.id)).all()
    for statement in statements:
        work_items = list(affected_work(session, statement, zones)) + list(revision_work(session, statement, zones))
        for work in work_items:
            if work.zone_id not in scope:
                continue
            for rule in PRECONDITIONS:
                if not rule.applies(work):
                    continue
                evaluation = rule.evaluate(session, work, zones)
                evidence = []
                if rule.type == "C":
                    evidence = [item for predecessor in work.task.predecessors
                                for item in completion_evidence(session, predecessor, zones)]
                elif evaluation.inspection_id is not None:
                    evidence = inspection_evidence(session, session.get(models.Inspection, evaluation.inspection_id),
                                                   inspection_evidence_scope(work.zone_id, zones))
                elif work.revision is not None:
                    evidence = receipt_evidence(session, work.zone_id, work.crew.id if work.crew else None,
                                                work.revision, zones)
                result.append(PreconditionView(
                    name=rule.name, zone_id=work.zone_id, task_id=work.task.id if work.task else None,
                    evaluation=evaluation.status, explanation=evaluation.explanation,
                    inspection_id=evaluation.inspection_id, context=evaluation.context,
                    source_refs=[f"source:{statement.source_message_id}", *[
                        f"event:{identifier}" for identifier in evaluation.source_event_ids],
                        *[item.source_ref for item in evidence]],
                ))
    covered = {item.task_id for item in result}
    for task in tasks:
        if task.id not in covered:
            result.append(PreconditionView(
                name="work_preconditions", zone_id=task.zone_id, task_id=task.id,
                evaluation="unknown", explanation="No applicable recorded work evaluation; the schedule alone is not clearance.",
                source_refs=[f"task:{task.id}"],
            ))
    return result


@router.get("/zones/{zone_id}", response_model=ZoneStatus)
def get_zone_status(zone_id: str, session: Database):
    """Zone/subtree plus covering ancestor records; sibling-only records are excluded. Never grants clearance."""
    zones, scope, tasks, inspections, evidence, events, flags = scoped_records(session, zone_id)
    return ZoneStatus(
        zone=schemas.Zone.model_validate(zones[zone_id]),
        zones=[schemas.Zone.model_validate(zone) for zone in zones.values()
               if zone.id in scope and (zone.id == zone_id or zone_id in ancestors(zone.id, zones))],
        plans=[plan for plan in get_plans(session) if plan.floor_id in scope],
        tasks=[schemas.Task.model_validate(task) for task in tasks],
        inspections=[schemas.Inspection.model_validate(item) for item in inspections],
        evidence=[schemas.EvidenceView.model_validate(item) for item in evidence],
        preconditions=preconditions(session, zones, scope, tasks),
        open_flags=[flag_view(session, flag) for flag in flags if flag.state not in {"resolved", "false_alarm"}],
        events=event_views(session, events), source_refs=[f"zone:{zone_id}", *[f"task:{task.id}" for task in tasks],
            *[item.source_ref for item in evidence], *[f"source:{item.source_message_id}" for item in events]],
    )


class RecordEntry(schemas.Record):
    kind: str
    record_ref: str
    source_refs: list[str]
    record: dict
    recorded_at: schemas.Timestamp | None = None


class RecordResults(schemas.Record):
    entries: list[RecordEntry]
    total_matches: int
    truncated: bool
    safety_notice: str = SAFETY_NOTICE


def entry(kind, record, *, sources=(), recorded_at=None, suffix=""):
    value = record.model_dump(mode="json")
    reference = f"{kind}:{value['id']}{suffix}"
    return RecordEntry(kind=kind, record_ref=reference, source_refs=list(sources) or [reference],
                       record=value, recorded_at=recorded_at)


def record_entries(session, zone_id):
    zones, scope, tasks, inspections, evidence, events, flags = scoped_records(session, zone_id)
    result = [entry("zone", schemas.Zone.model_validate(zones[identifier])) for identifier in sorted(scope)]
    result.extend(entry("task", schemas.Task.model_validate(item)) for item in tasks)
    result.extend(entry("inspection", schemas.Inspection.model_validate(item)) for item in inspections)
    for item in evidence:
        value = schemas.EvidenceView.model_validate(item)
        result.append(entry("evidence", value, sources=[item.source_ref]))
        for review in value.history:
            result.append(entry("evidence", value, sources=[item.source_ref], recorded_at=review.recorded_at,
                                suffix=f"/review/{review.sequence}").model_copy(update={
                                    "record": {"evidence": value.model_dump(mode="json"),
                                               "review": review.model_dump(mode="json")}}))
    for value in event_views(session, events):
        result.append(entry("event", value, sources=[f"source:{value.source_message_id}"],
                            recorded_at=value.source.sent_at))
    for item in flags:
        value = flag_view(session, item)
        result.append(entry("flag", value, sources=[audit.source_ref for audit in value.audit]))
        for index, audit in enumerate(value.audit):
            result.append(entry("flag", value, sources=[audit.source_ref], recorded_at=audit.recorded_at,
                                suffix=f"/audit/{index}").model_copy(update={
                                    "record": {"flag_id": item.id, "audit": audit.model_dump(mode="json"),
                                               "current_evaluation": value.evaluation, "evidence": [
                                                   evidence.model_dump(mode="json") for evidence in value.evidence]}}))
    plans = session.scalars(select(models.Plan).where(models.Plan.floor_id.in_(scope)).order_by(models.Plan.id)).all()
    for plan in plans:
        result.append(entry("plan", schemas.Plan.model_validate(plan)))
        revisions = session.scalars(select(models.Revision).where(models.Revision.plan_id == plan.id).order_by(
            models.Revision.sequence)).all()
        for revision in revisions:
            result.append(entry("revision", schemas.RevisionView.model_validate(revision), recorded_at=revision.issued_at))
    return result


@router.get("/timeline", response_model=RecordResults)
def get_timeline(
    session: Database, zone_id: str | None = None,
    from_time: schemas.Timestamp | None = None, to_time: schemas.Timestamp | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    """Source-time Events, review-time Evidence decisions, Flag audit and revision issue times; [from, to)."""
    if from_time is not None and to_time is not None and from_time >= to_time:
        raise HTTPException(422, "from_time must be before to_time")
    entries = [item for item in record_entries(session, zone_id) if item.recorded_at is not None
               and (from_time is None or utc(item.recorded_at) >= from_time)
               and (to_time is None or utc(item.recorded_at) < to_time)]
    entries.sort(key=lambda item: (item.recorded_at, item.record_ref))
    return RecordResults(entries=entries[:limit], total_matches=len(entries), truncated=len(entries) > limit)


@router.get("/search", response_model=RecordResults)
def search_record(
    session: Database, query: Annotated[str, Query(min_length=1, max_length=200)],
    zone_id: str | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Literal, case-insensitive record search, not an LLM answer. Evidence keeps current review status/history."""
    if not query.strip():
        raise HTTPException(422, "query must not be blank")
    entries = [item for item in record_entries(session, zone_id) if item.recorded_at is None or item.kind in {"event", "revision"}]
    matches = [item for item in entries if query.casefold() in json.dumps(item.record, ensure_ascii=False).casefold()]
    return RecordResults(entries=matches[:limit], total_matches=len(matches), truncated=len(matches) > limit)
