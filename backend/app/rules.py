"""Deterministic Preconditions; advisory Events can trigger checks, never grant approval."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, event, or_, select
from sqlalchemy.orm import Session

from app import models
from app.revision_rules import RevisionAcknowledged, revision_work


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass(frozen=True)
class Evaluation:
    status: str
    explanation: str
    inspection_id: str | None = None
    context: dict = field(default_factory=dict)
    conflict_key: str | None = None
    source_event_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Work:
    event: models.Event
    zone_id: str
    task: models.Task | None
    crew: models.Crew | None
    revision: models.Revision | None = None


def ancestors(zone_id, zones):
    result = []
    while zone_id is not None:
        result.append(zone_id)
        zone_id = zones[zone_id].parent_id
    return result


def inspection_evidence_scope(zone_id, zones):
    """Overlapping work scope: ancestors and descendants, never sibling zones."""
    return set(ancestors(zone_id, zones)) | {
        candidate for candidate in zones if zone_id in ancestors(candidate, zones)
    }


def inspection_evidence(session, inspection, zone_ids):
    """Exact proof plus relevant unresolved claims to expose for human review."""
    records = session.scalars(select(models.Evidence).where(
        models.Evidence.kind == "inspection",
        or_(models.Evidence.inspection_id == inspection.id, and_(
            models.Evidence.inspection_id.is_(None), models.Evidence.zone_id.in_(zone_ids),
        )),
    ).order_by(models.Evidence.id).execution_options(populate_existing=True)).all()
    result = []
    for item in records:
        if item.inspection_id is not None:
            result.append(item)
        elif item.origin == "llm_statement":
            statement = session.get(models.Event, item.statement_ref)
            if statement and statement.details.get("inspection_kind") == inspection.kind:
                result.append(item)
    return result


class InspectionPassed:
    type = "A"
    name = "inspection_passed"
    kind = "rough_in"

    def applies(self, work):
        return work.revision is None and work.event.intent == "planned_work" and work.event.activity in {
            "closing_work", "drywall", "insulation",
        }

    def evaluate(self, session, work, zones):
        scope = ancestors(work.zone_id, zones)
        inspections = session.scalars(select(models.Inspection).where(
            models.Inspection.kind == self.kind, models.Inspection.zone_id.in_(scope),
        )).all()
        if not inspections:
            return Evaluation("unknown", "Required rough-in inspection is missing; no valid confirmed proof.")
        nearest = min(scope.index(item.zone_id) for item in inspections)
        matches = [item for item in inspections if scope.index(item.zone_id) == nearest]
        if len(matches) != 1:
            return Evaluation("unknown", "Required rough-in inspection is ambiguous; review its scope.")
        inspection = matches[0]
        # Exact Evidence scope must match the selected inspection, whose zone
        # may cover the work's descendant zone. Sibling evidence never applies.
        records = inspection_evidence(session, inspection, inspection_evidence_scope(work.zone_id, zones))
        relevant, confirmed, statement_times = [], [], {}
        for item in records:
            if item.review_status == "rejected":
                continue
            exact_scope = item.inspection_id == inspection.id and item.zone_id == inspection.zone_id
            if item.inspection_id is not None and not exact_scope:
                continue
            if item.origin == "llm_statement":
                statement = session.get(models.Event, item.statement_ref)
                if statement is None or item.source_ref != f"source:{statement.source_message_id}":
                    continue
                statement_times[item.id] = utc(statement.source.sent_at)
                # An old success claim cannot certify a later inspection cycle.
                if item.claim == "passed" and utc(statement.source.sent_at) < utc(inspection.scheduled_at):
                    continue
            relevant.append(item)
            review = item.history[-1] if item.history else None
            if exact_scope and review and review.status == "confirmed" and (
                review.actor_type == "human" or
                (item.origin == "seed_baseline" and review.actor_type == "seed_import")
            ):
                confirmed.append(item)
        positives = [item for item in confirmed if item.claim == "passed"]
        latest_pass_at = max((statement_times[item.id] for item in positives
                              if item.id in statement_times), default=None)

        def superseded_pending(item):
            if item.claim != "pending" or not positives:
                return False
            if item.origin == "seed_baseline":
                return True
            # Compare source times for the exact same Inspection, not review
            # times. A late confirmation cannot erase a newer counterclaim.
            return (item.inspection_id == inspection.id and latest_pass_at is not None
                    and item.id in statement_times and statement_times[item.id] < latest_pass_at)

        # Normal earlier pending states remain in Evidence/history. Failed,
        # newer, simultaneous or unresolved-scope counterclaims need review.
        claims = {item.claim for item in relevant if not superseded_pending(item)}
        if "passed" in claims and claims & {"failed", "pending"}:
            return Evaluation("contradictory", "Inspection statements conflict; review unresolved counterclaims. Unconfirmed claims are not proof.", inspection.id)
        if positives:
            return Evaluation("satisfied", "Valid confirmed proof that the rough-in inspection passed.", inspection.id)
        if any(item.claim == "failed" for item in confirmed):
            return Evaluation("not_satisfied", "Confirmed evidence reports that the rough-in inspection failed.", inspection.id)
        if any(item.claim == "pending" for item in confirmed):
            return Evaluation("not_satisfied", "Confirmed evidence reports a pending rough-in inspection; no confirmed pass.", inspection.id)
        return Evaluation("unknown", "Inspection proof is missing, unconfirmed, stale or outside the required scope.", inspection.id)


# New types implement applies/evaluate; persistence, dedup and audit are shared.
PRECONDITIONS = (InspectionPassed(), RevisionAcknowledged())


def affected_work(session, statement, zones):
    crews = {crew.id: crew for crew in session.scalars(select(models.Crew))}
    for zone_id in statement.zone_ids:
        scope = ancestors(zone_id, zones)
        tasks = session.scalars(select(models.Task).where(models.Task.zone_id.in_(scope))).all()
        crew = crews.get(statement.crew_id)
        trade = statement.trade or (crew.trade if crew else None)
        candidates = [task for task in tasks if
            (crew is not None and task.crew_id == crew.id or
             crew is None and trade is not None and crews[task.crew_id].trade == trade)
            and (statement.starts_at is None or
                 utc(task.ends_at) > utc(statement.starts_at) and
                 utc(task.starts_at) < utc(statement.ends_at or statement.starts_at))]
        task = None
        if candidates:
            nearest = min(scope.index(item.zone_id) for item in candidates)
            matches = [item for item in candidates if scope.index(item.zone_id) == nearest]
            task = matches[0] if len(matches) == 1 else None
        if crew is None and task is not None:
            crew = crews[task.crew_id]
        if crew is None and trade:
            matches = [item for item in crews.values() if item.trade == trade]
            crew = matches[0] if len(matches) == 1 else None
        yield Work(statement, zone_id, task, crew)


def evaluate_site(session, *, source_ref="rules:scan", actor="rule_engine", channel="system"):
    """Recheck persisted work Events in the caller's transaction; never close a Flag.

    Also reusable by the later morning scan. Serializing on the Site row keeps
    concurrent detections consistent; the unique open_key is a second boundary.
    """
    session.scalar(select(models.Site).with_for_update())
    zones = {zone.id: zone for zone in session.scalars(select(models.Zone))}
    existing_flags = session.scalars(select(models.Flag)).all()
    flags = {flag.open_key: flag for flag in existing_flags if flag.open_key}
    closed_sources = {
        (source.event_id, flag.type, flag.zone_id, flag.precondition,
         (flag.context or {}).get("revision_id"),
         (flag.context or {}).get("crew_id"))
        for flag in existing_flags if flag.state in {"resolved", "false_alarm"}
        for source in flag.sources
    }
    statements = session.scalars(select(models.Event).order_by(models.Event.created_at, models.Event.id)).all()
    now = datetime.now(UTC)
    for statement in statements:
        candidates = [*affected_work(session, statement, zones), *revision_work(session, statement, zones)]
        for work in candidates:
            for rule in PRECONDITIONS:
                if not rule.applies(work):
                    continue
                # A human closure settles these work sources for this conflict.
                # Rechecks must not replay them into a new Flag. New work Events
                # remain eligible, including another announcement in this Zone.
                if (statement.id, rule.type, work.zone_id, rule.name,
                    work.revision.id if work.revision else None,
                    work.crew.id if work.revision and work.crew else None) in closed_sources:
                    continue
                result = rule.evaluate(session, work, zones)
                key = result.conflict_key or ":".join((rule.type, work.zone_id,
                    work.task.id if work.task else work.crew.id if work.crew else "unassigned",
                    rule.name))
                flag = flags.get(key)
                if flag is None and result.status == "satisfied":
                    continue
                if flag is None:
                    flag = models.Flag(
                        id=uuid4().hex, type=rule.type, zone_id=work.zone_id,
                        task_id=work.task.id if work.task else None, activity=statement.activity or rule.name,
                        precondition=rule.name, inspection_id=result.inspection_id,
                        severity="high", responsible_id=work.crew.lead_id if work.crew else None,
                        state="detected", evaluation=result.status, explanation=result.explanation,
                        context=result.context, open_key=key, created_at=now, updated_at=now, sources=[],
                        audit=[models.FlagAudit(action="detected", actor="rule_engine", to_state="detected",
                            channel=statement.source.channel, source_ref=f"source:{statement.source_message_id}", recorded_at=now)],
                    )
                    session.add(flag)
                    flags[key] = flag
                    from app.outbox import enqueue_flag_warning
                    enqueue_flag_warning(session, flag, statement, work.crew, now)
                elif (flag.evaluation != result.status or flag.explanation != result.explanation
                      or flag.inspection_id != result.inspection_id or flag.context != result.context):
                    flag.evaluation, flag.explanation = result.status, result.explanation
                    flag.updated_at = now
                    flag.audit.append(models.FlagAudit(action="precondition_evaluated", actor=actor,
                        channel=channel, source_ref=source_ref, recorded_at=now))
                flag.inspection_id = result.inspection_id
                flag.context = result.context
                for event_id in dict.fromkeys((statement.id, *result.source_event_ids)):
                    if event_id not in {item.event_id for item in flag.sources}:
                        flag.sources.append(models.FlagSource(event_id=event_id, attached_at=now))
                        flag.updated_at = now


@event.listens_for(Session, "before_flush")
def queue_rule_evaluation(session, _context, _instances):
    if session.info.get("defer_rules"):
        return
    triggers = [item for item in session.new if isinstance(item, models.Event) or
                isinstance(item, models.EvidenceReview) and item.actor_type == "human"]
    if triggers:
        # Lock before inserting Events/reviews so competing ingestion/review
        # transactions observe each other's decisions after the lock releases.
        session.scalar(select(models.Site).with_for_update())
        trigger = triggers[-1]
        session.info["rule_trigger"] = (
            {"source_ref": f"evidence:{trigger.evidence_id or trigger.evidence.id}", "actor": trigger.reviewer_id, "channel": "dashboard"}
            if isinstance(trigger, models.EvidenceReview) else
            {"source_ref": f"source:{trigger.source_message_id}"}
        )


@event.listens_for(Session, "after_flush_postexec")
def evaluate_after_event_or_review(session, _context):
    trigger = session.info.pop("rule_trigger", None)
    if trigger is not None:
        evaluate_site(session, **trigger)


@event.listens_for(Session, "after_soft_rollback")
def clear_rule_trigger(session, _transaction):
    session.info.pop("rule_trigger", None)
