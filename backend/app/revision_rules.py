"""Source-backed revision notes and crew receipt Evidence; no geometric inference."""

import re
from uuid import uuid4

from sqlalchemy import select

from app import models


def register_note(session, event, source, revisions, zones):
    """Register a provisional revision without inventing a drawing or approval."""
    from app.rules import ancestors, utc

    if event.intent != "revision":
        return
    plan = session.get(models.Plan, event.details.get("plan_reference")) if event.details.get("plan_reference") else None
    label = event.details.get("revision_label")
    if plan is None or not label or not event.zone_ids or event.unresolved_zones:
        return
    if any(plan.floor_id not in ancestors(zone_id, zones) for zone_id in event.zone_ids):
        return
    history = [item for item in revisions if item.plan_id == plan.id]
    revision = next((item for item in history if item.label == label), None)
    latest = max(history, key=lambda item: item.sequence, default=None)
    if revision is None:
        # Arrival order and label spelling cannot establish historical sequence.
        if latest and utc(source.sent_at) <= utc(latest.issued_at):
            return
        identifier = f"{plan.id}-{label}"
        revision = models.Revision(
            id=identifier if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", identifier) else uuid4().hex,
            plan_id=plan.id, label=label, sequence=latest.sequence + 1 if latest else 1,
            issued_at=source.sent_at, file_name=None,
            zones=[zones[zone_id] for zone_id in event.zone_ids],
        )
        session.add(revision)
        revisions.append(revision)
    # Keep extracted scope on its Event, separate from authoritative CAD data.
    event.details = {**event.details, "revision_id": revision.id,
                     "affected_zones_origin": "unconfirmed_revision_note"}


def revision_work(session, statement, zones):
    """Intersect note scope with scheduled work, and later work with that scope."""
    from app.rules import Work, affected_work, ancestors, utc

    notes = session.scalars(select(models.Event).where(models.Event.intent == "revision")).all()
    notes = [note for note in notes if note.details.get("revision_id")]
    revisions = session.scalars(select(models.Revision)).all()
    latest = {}
    for revision in revisions:
        if revision.plan_id not in latest or revision.sequence > latest[revision.plan_id].sequence:
            latest[revision.plan_id] = revision
    if statement.intent == "revision" and statement in notes:
        reference = session.get(models.Revision, statement.details["revision_id"])
        current = latest[reference.plan_id]
        for task in session.scalars(select(models.Task)):
            if utc(task.ends_at) <= max(utc(statement.source.sent_at), utc(current.issued_at)):
                continue
            for zone_id in statement.zone_ids:
                if task.zone_id in ancestors(zone_id, zones):
                    target = zone_id
                elif zone_id in ancestors(task.zone_id, zones):
                    target = task.zone_id
                else:
                    continue
                yield Work(statement, target, task, session.get(models.Crew, task.crew_id), current)
    elif statement.intent == "planned_work":
        for work in affected_work(session, statement, zones):
            targets = set()
            for note in notes:
                revision = session.get(models.Revision, note.details["revision_id"])
                current = latest[revision.plan_id]
                if statement.ends_at and utc(statement.ends_at) <= utc(current.issued_at):
                    continue
                for zone_id in note.zone_ids:
                    if zone_id in ancestors(work.zone_id, zones):
                        targets.add((work.zone_id, revision.plan_id))
                    elif work.zone_id in ancestors(zone_id, zones):
                        targets.add((zone_id, revision.plan_id))
            for zone_id, plan_id in sorted(targets):
                yield Work(statement, zone_id, work.task, work.crew, latest[plan_id])


def receipt_evidence(session, zone_id, crew_id, revision, zones):
    """Include exact proof and unresolved counterclaims, never another crew/plan."""
    from app.rules import inspection_evidence_scope

    scope = inspection_evidence_scope(zone_id, zones)
    records = session.scalars(select(models.Evidence).where(
        models.Evidence.kind == "revision_acknowledgment",
        models.Evidence.zone_id.in_(scope),
    ).order_by(models.Evidence.id).execution_options(populate_existing=True)).all()
    result = []
    for item in records:
        if item.crew_id != crew_id and not (item.crew_id is None and item.origin == "llm_statement"):
            continue
        target = session.get(models.Revision, item.revision_id) if item.revision_id else None
        if target and target.plan_id == revision.plan_id:
            result.append(item)
        elif target is None and item.origin == "llm_statement":
            statement = session.get(models.Event, item.statement_ref)
            if statement and statement.details.get("plan_reference") == revision.plan_id:
                result.append(item)
    return result


class RevisionAcknowledged:
    type = "B"
    name = "revision_acknowledged"

    def applies(self, work):
        return work.revision is not None

    def evaluate(self, session, work, zones):
        from app.rules import Evaluation, ancestors, utc

        revision = work.revision
        crew_id = work.crew.id if work.crew else None
        records = receipt_evidence(session, work.zone_id, crew_id, revision, zones)
        relevant, confirmed, acknowledged, statement_times = [], [], [], {}
        resolved_revision_ids = {}
        for item in records:
            if item.review_status == "rejected":
                continue
            covers = item.zone_id in ancestors(work.zone_id, zones)
            exact_crew = crew_id is not None and item.crew_id == crew_id
            trusted = bool(item.history and item.history[-1].status == "confirmed" and (
                item.history[-1].actor_type == "human" or
                item.origin == "seed_baseline" and item.history[-1].actor_type == "seed_import"))
            statement = session.get(models.Event, item.statement_ref) if item.origin == "llm_statement" else None
            target = session.get(models.Revision, item.revision_id) if item.revision_id else None
            if item.origin == "llm_statement":
                if (statement is None or item.source_ref != f"source:{statement.source_message_id}"
                        or statement.intent != "revision_acknowledgment"
                        or statement.details.get("plan_reference") != revision.plan_id):
                    continue
                if item.revision_id is None and statement.details.get("revision_label"):
                    # Cross-channel delivery may precede revision registration.
                    # Resolve only the exact immutable plan/label assertion;
                    # never rewrite Evidence scope or create a confirmation.
                    matches = session.scalars(select(models.Revision).where(
                        models.Revision.plan_id == statement.details["plan_reference"],
                        models.Revision.label == statement.details["revision_label"],
                    )).all()
                    target = matches[0] if len(matches) == 1 else None
                if target and (statement.details.get("revision_label") != target.label
                               or utc(statement.source.sent_at) < utc(target.issued_at)):
                    continue
                if statement.crew_id != item.crew_id or item.zone_id not in statement.zone_ids:
                    continue
                statement_times[item.id] = utc(statement.source.sent_at)
            resolved_revision_ids[item.id] = target.id if target else None
            if trusted and covers and exact_crew and item.claim == "acknowledged" and target:
                acknowledged.append(target)
            if target is None or target.id != revision.id:
                # Ambiguous current-revision counterclaims still require review.
                if not (item.revision_id is None and statement and
                        statement.details.get("revision_label") in {None, revision.label}):
                    continue
            relevant.append(item)
            if trusted and covers and exact_crew and target is not None and target.id == revision.id:
                confirmed.append(item)
        last = max(acknowledged, key=lambda item: item.sequence, default=None)
        context = dict(crew_id=crew_id, plan_id=revision.plan_id, revision_id=revision.id,
                       current_revision=revision.label,
                       acknowledged_revision=last.label if last else None,
                       acknowledged_revision_id=last.id if last else None,
                       affected_zones_origin="unconfirmed_revision_note")
        positives = [item for item in confirmed if item.claim == "acknowledged"]

        def superseded_nonreceipt(item):
            # Receiving a revision later does not make the earlier non-receipt
            # false. Retain both records; only supersede the earlier state for
            # the same exact Crew/Zone/Revision using validated source times.
            return (item.claim == "not_acknowledged" and item.id in statement_times
                    and any(positive.id in statement_times
                            and (item.crew_id, item.zone_id, resolved_revision_ids[item.id])
                            == (positive.crew_id, positive.zone_id, resolved_revision_ids[positive.id])
                            and statement_times[item.id] < statement_times[positive.id]
                            for positive in positives))

        claims = {item.claim for item in relevant if not superseded_nonreceipt(item)}
        if {"acknowledged", "not_acknowledged"} <= claims:
            status, explanation = "contradictory", "Revision receipt statements conflict; unresolved counterclaims require human review."
        elif any(item.claim == "acknowledged" for item in confirmed):
            status, explanation = "satisfied", "Confirmed receipt of the current revision; this does not certify implementation. Awaiting human Flag closure."
        elif any(item.claim == "not_acknowledged" for item in confirmed):
            status, explanation = "not_satisfied", "Confirmed evidence reports that the crew has not received the current revision."
        else:
            status, explanation = "unknown", "Current revision receipt is missing, unconfirmed, stale or outside the required crew/zone/plan scope."
        note_ids = tuple(note.id for note in session.scalars(select(models.Event).where(
            models.Event.intent == "revision")) if note.details.get("revision_id") and
            session.get(models.Revision, note.details["revision_id"]).plan_id == revision.plan_id and
            any(zone_id in ancestors(work.zone_id, zones) or work.zone_id in ancestors(zone_id, zones)
                for zone_id in note.zone_ids))
        return Evaluation(status, explanation, context=context,
                          conflict_key=f"B:{work.zone_id}:{crew_id or 'unassigned'}:{revision.id}",
                          source_event_ids=note_ids)
