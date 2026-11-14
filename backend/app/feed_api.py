"""Activity feed for the Superintendent: a read-only projection of the site record.

The feed never changes Flags, Evidence or Tasks. It reports what the record says
and labels how trustworthy each statement is (PLAN §3.2, §3.6). Entries describe
Zones, Tasks and Crews/trades; people appear only as their role (PLAN §6).
"""

import base64
import json
from datetime import UTC
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app import models
from app.schemas import Identifier, Record, Timestamp
from app.site_api import Database, zone_scope

router = APIRouter(tags=["Feed"])

Kind = Literal["event", "revision", "evidence_decision", "task_completed", "flag_change", "proposal"]
# How far the entry can be trusted: an LLM statement stays unconfirmed until a
# human confirms its Evidence; plan diffs are deterministic; seed is baseline.
Confirmation = Literal["unconfirmed", "confirmed", "rejected", "deterministic", "seed", "human", "system", "advice"]

INTENT_TITLES = {
    "planned_work": "Work announced",
    "task_completion": "Task completion reported",
    "question": "Question",
    "inspection_result": "Inspection result reported",
    "revision_acknowledgment": "Revision receipt reported",
    "observation": "Observation",
}
FLAG_ACTIONS = {
    "detected": "raised",
    "notified": "warning sent",
    "acknowledge": "acknowledged",
    "action_approved": "action approved, in progress",
    "resolved": "closed as resolved",
    "false_alarm": "closed as false alarm",
    "escalated": "escalated",
    "precondition_evaluated": "re-evaluated",
}
PRECONDITIONS = {"inspection_passed": "inspection not proven", "revision_acknowledged": "current revision not acknowledged"}
# Within one instant a cause precedes its consequences (source → Flag → warning).
ORDER = {"revision": 0, "event": 1, "evidence_decision": 2, "task_completed": 2, "flag_change": 3, "proposal": 4}


class FeedEntry(Record):
    id: str
    kind: Kind
    occurred_at: Timestamp
    recorded_at: Timestamp
    title: str
    summary: str | None = None
    quote: str | None = None
    confirmation: Confirmation
    zone_ids: list[str]
    link: str | None
    channel: str | None = None
    actor_role: str | None = None
    crew_id: str | None = None
    trade: str | None = None
    task_id: str | None = None
    flag_id: str | None = None
    flag_state: str | None = None
    revision_id: str | None = None
    evidence_id: str | None = None
    source_ref: str | None = None


class FeedPage(Record):
    entries: list[FeedEntry]
    next_cursor: str | None


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def label(value):
    return value.replace("_", " ") if value else value


def link_for(zone_ids, flag_id=None):
    if flag_id:
        return f"/flags/{flag_id}"
    return f"/zones/{zone_ids[0]}" if zone_ids else None


def zone_text(zone_ids):
    return ", ".join(zone_ids) if zone_ids else "zone unresolved"


def event_confirmation(event, evidence):
    if event.details.get("origin") == "deterministic_plan_diff":
        return "deterministic"
    statuses = {item.review_status for item in evidence}
    if statuses == {"confirmed"}:
        return "confirmed"
    if statuses == {"rejected"}:
        return "rejected"
    return "unconfirmed"


def event_entry(event, evidence, crews, tasks):
    details = event.details or {}
    crew = crews.get(event.crew_id)
    confirmation = event_confirmation(event, evidence)
    summary = None
    if event.intent == "revision":
        title = f"Rev {details.get('revision_label') or '?'} received for {details.get('plan_reference') or 'unknown plan'}"
        if details.get("diff_status") == "succeeded":
            summary = f"Plan diff: affected zones {zone_text(event.zone_ids)}. Does not confirm crew receipt."
        elif details.get("diff_status") == "failed":
            summary = f"Plan diff failed; affected zones from the unconfirmed revision note: {zone_text(event.zone_ids)}."
        else:
            summary = f"Affected zones from the unconfirmed revision note: {zone_text(event.zone_ids)}."
    elif event.intent == "inspection_result":
        kind = label(details.get("inspection_kind")) or "inspection"
        claim = details.get("claim")
        title = {
            "pending": f"Inspection {kind} postponed / pending",
            "passed": f"Inspection {kind} reported passed",
            "failed": f"Inspection {kind} reported failed",
        }.get(claim, f"Inspection {kind} update")
    elif event.intent == "task_completion":
        task = next((tasks[item.task_id] for item in evidence if item.task_id in tasks), None)
        name = task.name if task else details.get("task_reference") or "unresolved task"
        title = f"Completion of {name} reported"
        if details.get("claim") == "not_completed":
            title = f"{name} reported not completed"
    elif event.intent == "revision_acknowledgment":
        title = f"{crew.name if crew else 'Crew'} reports receipt of {details.get('plan_reference') or 'plan'} Rev {details.get('revision_label') or '?'}"
    else:
        title = INTENT_TITLES.get(event.intent, label(event.intent))
        if event.activity:
            title = f"{title}: {label(event.activity)}"
    if confirmation == "unconfirmed" and event.intent != "question":
        title = f"{title} (unconfirmed)"
    return FeedEntry(
        id=f"event:{event.id}", kind="event", occurred_at=utc(event.source.sent_at),
        recorded_at=utc(event.created_at), title=title,
        summary=summary, quote=event.quote, confirmation=confirmation, zone_ids=event.zone_ids,
        link=link_for(event.zone_ids), channel=event.source.channel, actor_role=event.source.sender_role,
        crew_id=event.crew_id, trade=crew.trade if crew else event.trade,
        task_id=next((item.task_id for item in evidence if item.task_id), None),
        revision_id=details.get("revision_id"), source_ref=f"source:{event.source_message_id}",
    )


def revision_entry(revision):
    return FeedEntry(
        id=f"revision:{revision.id}", kind="revision", occurred_at=utc(revision.issued_at),
        recorded_at=utc(revision.issued_at),
        title=f"Rev {revision.label} issued for {revision.plan_id}",
        summary=f"Changed zones: {zone_text(revision.zone_ids)}.", confirmation="seed",
        zone_ids=revision.zone_ids, link=link_for(revision.zone_ids), revision_id=revision.id,
        source_ref=f"revision:{revision.id}",
    )


def evidence_entries(evidence, review, tasks, crews):
    """One entry per human decision; seed and ingestion history are not decisions."""
    zone_ids = [evidence.zone_id] if evidence.zone_id else []
    task = tasks.get(evidence.task_id)
    crew_id = evidence.crew_id or (task.crew_id if task else None)
    crew = crews.get(crew_id)
    current = evidence.history[-1] is review
    later = None if current else evidence.review_status
    subject = {
        "inspection": f"inspection {evidence.inspection_id or 'unresolved'}",
        "task_completion": f"task {task.name if task else evidence.task_id or 'unresolved'}",
        "revision_acknowledgment": f"{crew.name if crew else 'crew'} receipt of {evidence.revision_id or 'unresolved revision'}",
    }[evidence.kind]
    completed = (
        evidence.kind == "task_completion" and evidence.claim == "completed" and review.status == "confirmed"
        and current and task is not None and task.zone_id == evidence.zone_id
    )
    if completed:
        title = f"{task.name} completed"
        summary = "Completion confirmed from source-backed evidence."
    else:
        title = f"Evidence {review.status}: {label(evidence.claim)} for {subject}"
        summary = f"Later {later}." if later and later != review.status else None
    if review.reason:
        summary = f"{summary} Reason: {review.reason}" if summary else f"Reason: {review.reason}"
    return FeedEntry(
        id=f"evidence-review:{review.id}", kind="task_completed" if completed else "evidence_decision",
        occurred_at=utc(review.decided_at or review.recorded_at), recorded_at=utc(review.recorded_at),
        title=title, summary=summary,
        quote=evidence.quote, confirmation=review.status, zone_ids=zone_ids, link=link_for(zone_ids),
        channel="dashboard", actor_role=review.reviewer_role, crew_id=crew_id,
        trade=crew.trade if crew else None, task_id=evidence.task_id, revision_id=evidence.revision_id,
        evidence_id=evidence.id, source_ref=evidence.source_ref,
    )


def flag_entry(flag, audit, sent_at, crews):
    zone_ids = [flag.zone_id]
    action = FLAG_ACTIONS.get(audit.action, label(audit.action))
    title = f"Flag {flag.type} {action}: {zone_text(zone_ids)}"
    if audit.action == "detected":
        title = f"{title}, {PRECONDITIONS.get(flag.precondition, label(flag.precondition))}"
    summary = audit.reason
    if audit.action == "detected":
        summary = flag.explanation
    if audit.action == "acknowledge":
        summary = f"Acknowledged the warning; this is not evidence of receipt or inspection. {audit.reason or ''}".strip()
    crew = crews.get((flag.context or {}).get("crew_id"))
    # A rule reaction belongs at the time of the source that caused it, so an
    # offline replay with scenario timestamps keeps cause and Flag together.
    occurred = sent_at.get(audit.source_ref) if audit.actor_role is None else None
    return FeedEntry(
        id=f"flag-audit:{audit.id}", kind="flag_change", occurred_at=utc(occurred or audit.recorded_at),
        recorded_at=utc(audit.recorded_at),
        title=title, summary=summary, confirmation="human" if audit.actor_role else "system",
        zone_ids=zone_ids, link=link_for(zone_ids, flag.id), channel=audit.channel,
        actor_role=audit.actor_role or "system", crew_id=crew.id if crew else None,
        trade=crew.trade if crew else None, task_id=flag.task_id, flag_id=flag.id,
        flag_state=audit.to_state, revision_id=(flag.context or {}).get("revision_id"),
        source_ref=audit.source_ref,
    )


def proposal_entry(proposal, flag):
    zone_ids = [flag.zone_id]
    return FeedEntry(
        id=f"proposal:{proposal.id}", kind="proposal", occurred_at=utc(proposal.created_at),
        recorded_at=utc(proposal.created_at),
        title=f"Proposal for Flag {flag.type} in {flag.zone_id}: {proposal.action}",
        summary=f"{proposal.rationale} Awaiting Superintendent approval.", confirmation="advice",
        zone_ids=zone_ids, link=link_for(zone_ids, flag.id), channel=proposal.channel,
        actor_role="agent", task_id=flag.task_id, flag_id=flag.id, source_ref=f"proposal:{proposal.id}",
    )


def build_feed(session):
    """All entries, most recently recorded first. The demo record is small, so this stays in memory.

    "Latest news" is what the record learned last. Sorting by `recorded_at`
    keeps replayed scenario timestamps (`occurred_at`) and live human actions
    in the order they actually happened.
    """
    crews = {crew.id: crew for crew in session.scalars(select(models.Crew))}
    tasks = {task.id: task for task in session.scalars(select(models.Task))}
    events = session.scalars(select(models.Event)).all()
    evidence = session.scalars(select(models.Evidence)).all()
    by_statement = {}
    for item in evidence:
        by_statement.setdefault(item.statement_ref, []).append(item)
    entries = [event_entry(event, by_statement.get(event.id, []), crews, tasks) for event in events]
    announced = {event.details.get("revision_id") for event in events if event.intent == "revision"}
    entries += [revision_entry(revision) for revision in session.scalars(select(models.Revision))
                if revision.id not in announced]
    entries += [evidence_entries(item, review, tasks, crews) for item in evidence
                for review in item.history if review.actor_type == "human"]
    sent_at = {f"source:{source.id}": source.sent_at for source in session.scalars(select(models.SourceMessage))}
    flags = {flag.id: flag for flag in session.scalars(select(models.Flag))}
    entries += [flag_entry(flag, audit, sent_at, crews) for flag in flags.values() for audit in flag.audit]
    entries += [proposal_entry(proposal, flags[proposal.flag_id])
                for proposal in session.scalars(select(models.Proposal)) if proposal.flag_id in flags]
    return sorted(entries, key=sort_key, reverse=True)


def sort_key(entry):
    return entry.recorded_at.timestamp(), ORDER[entry.kind], entry.id


def encode_cursor(entry):
    return base64.urlsafe_b64encode(json.dumps(list(sort_key(entry))).encode()).decode()


def decode_cursor(value):
    try:
        at, order, identifier = json.loads(base64.urlsafe_b64decode(value.encode()))
        return float(at), int(order), str(identifier)
    except (ValueError, TypeError) as error:
        raise HTTPException(422, "Invalid cursor") from error


@router.get("/feed", response_model=FeedPage)
def get_feed(
    session: Database,
    zone_id: Identifier | None = None,
    include_descendants: bool = True,
    from_time: Timestamp | None = None,
    to_time: Timestamp | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    kind: Annotated[list[Kind] | None, Query()] = None,
):
    """Most recently recorded first. A Zone filter includes descendants; times bound `occurred_at` as [from, to)."""
    if from_time is not None and to_time is not None and from_time >= to_time:
        raise HTTPException(422, "from_time must be before to_time")
    scope = zone_scope(session, zone_id, include_descendants) if zone_id is not None else None
    after = decode_cursor(cursor) if cursor else None
    selected = []
    for entry in build_feed(session):
        if scope is not None and not scope.intersection(entry.zone_ids):
            continue
        if from_time is not None and entry.occurred_at < from_time:
            continue
        if to_time is not None and entry.occurred_at >= to_time:
            continue
        if kind and entry.kind not in kind:
            continue
        if after is not None and sort_key(entry) >= after:
            continue
        selected.append(entry)
        if len(selected) > limit:
            break
    page = selected[:limit]
    return FeedPage(entries=page, next_cursor=encode_cursor(page[-1]) if len(selected) > limit else None)
