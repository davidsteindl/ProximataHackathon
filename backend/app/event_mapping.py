"""Resolve extracted labels against the Site Record, without changing domain outcomes."""

import re
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app import models
from app.extraction import resolve_time
from app.revision_rules import register_note


def normalized(label):
    return re.sub(r"[\s._-]+", "", label.casefold())


def resolve_zones(labels, zones):
    aliases = {}
    for zone in zones:
        names = [zone.id, zone.name]
        if zone.kind == "unit":
            names += [f"Wohnung {zone.id}"]
        elif zone.kind == "floor" and re.fullmatch(r"F\d+", zone.id):
            names += [f"{zone.id[1:]}. OG", f"{zone.id[1:]}. Obergeschoss"]
        elif zone.kind == "room" and zone.id.endswith("-BATH"):
            names += [f"Bad {zone.parent_id}"]
        for label in names:
            aliases.setdefault(normalized(label), set()).add(zone.id)
    resolved, unresolved = set(), []
    for label in labels:
        matches = aliases.get(normalized(label), set())
        if len(matches) == 1:
            resolved.update(matches)
        else:
            unresolved.append(label)
    return resolved, unresolved


def resolve_named(label, records):
    if label is None:
        return None
    matches = [record for record in records if normalized(label) in {
        normalized(record.id), normalized(getattr(record, "name", record.id)),
    }]
    return matches[0] if len(matches) == 1 else None


def build_events(session, source, statements):
    """Flush Events and their Evidence together so rules see the complete batch."""
    with session.no_autoflush:
        return _build_events(session, source, statements)


def _build_events(session, source, statements):
    # Serialize note sequence registration with ingestion/review rule checks.
    session.scalar(select(models.Site).with_for_update())
    site = session.get(models.Site, source.site_id)
    zones = session.scalars(select(models.Zone).where(models.Zone.site_id == site.id)).all()
    zone_by_id = {zone.id: zone for zone in zones}
    crews = session.scalars(select(models.Crew)).all()
    inspections = session.scalars(select(models.Inspection)).all()
    tasks = session.scalars(select(models.Task)).all()
    revisions = session.scalars(select(models.Revision)).all()
    result = []
    for ordinal, statement in enumerate(statements):
        zone_ids, unresolved = resolve_zones(statement.zones, zones)
        crew = resolve_named(statement.crew, crews)
        if statement.crew is None and source.sender_crew_id:
            crew = session.get(models.Crew, source.sender_crew_id)
        starts_at, ends_at, precision = resolve_time(statement.time, source.sent_at, site)
        event = models.Event(
            id=uuid4().hex, source_message_id=source.id, ordinal=ordinal,
            intent=statement.intent, actor=statement.actor or source.sender_role,
            crew_id=crew.id if crew else None, activity=statement.activity, trade=statement.trade,
            quote=statement.quote, confidence=statement.confidence,
            starts_at=starts_at, ends_at=ends_at, time_precision=precision,
            time_expression=statement.time.expression if statement.time else None,
            unresolved_zones=unresolved,
            details=statement.model_dump(mode="json", include={"claim", "inspection_kind", "task_reference", "plan_reference", "revision_label", "crew"}),
            created_at=datetime.now(UTC), zones=[zone_by_id[key] for key in sorted(zone_ids)],
        )
        register_note(session, event, source, revisions, zone_by_id)
        session.add(event)
        result.append(event)
        if statement.claim is None:
            continue
        # Ambiguous/missing zones remain explicitly unresolved, never global scope.
        for zone_id in sorted(zone_ids) or [None]:
            fields = dict(zone_id=zone_id, inspection_id=None, task_id=None, crew_id=None, revision_id=None)
            if statement.intent == "inspection_result":
                kind = "inspection"
                matches = [inspection for inspection in inspections if inspection.zone_id == zone_id and inspection.kind == statement.inspection_kind]
                fields["inspection_id"] = matches[0].id if len(matches) == 1 else None
            elif statement.intent == "task_completion":
                kind = "task_completion"
                task = resolve_named(statement.task_reference, tasks)
                fields["task_id"] = task.id if task is not None and task.zone_id == zone_id else None
            else:
                kind = "revision_acknowledgment"
                fields["crew_id"] = crew.id if crew else None
                matches = [revision for revision in revisions if revision.plan_id == statement.plan_reference and revision.label == statement.revision_label]
                if len(matches) == 1:
                    revision = matches[0]
                    plan = session.get(models.Plan, revision.plan_id)
                    from app.rules import ancestors
                    if zone_id and plan.floor_id in ancestors(zone_id, zone_by_id):
                        fields["revision_id"] = revision.id
            session.add(models.Evidence(
                id=uuid4().hex, origin="llm_statement", statement_ref=event.id,
                source_ref=f"source:{source.id}", quote=statement.quote,
                kind=kind, claim=statement.claim, **fields,
                history=[models.EvidenceReview(
                    sequence=1, status="unconfirmed", actor_type="statement_ingestion",
                    recorded_at=datetime.now(UTC),
                )],
            ))
    return result
