"""Deterministic schedule impact; never reschedules work or grants permission."""

import json
import os
import re
from collections import defaultdict
from datetime import UTC

from sqlalchemy import select

from app import models

HOLD_ACTION = "Put blocked Tasks on hold"
HOLD_MESSAGE = "Tasks on hold; do not continue without talking to your supervisor (Superintendent)."


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def detect_blocked_tasks(flag, tasks, zones, as_of):
    """Zone + descendants and the matched Task (possibly floor-wide), then successors.

    Traverse even historical intermediate nodes; return only unfinished scheduled
    work at the trigger time. Visited IDs bound traversal for malformed cycles.
    """
    if flag.state in {"resolved", "false_alarm"} or flag.evaluation == "satisfied":
        return []
    scope = {flag.zone_id}
    while True:
        expanded = scope | {zone.id for zone in zones if zone.parent_id in scope}
        if expanded == scope:
            break
        scope = expanded
    successors = defaultdict(set)
    for task in tasks:
        for predecessor in task.predecessor_ids:
            successors[predecessor].add(task.id)
    visited = set()
    pending = [task.id for task in tasks if task.zone_id in scope or task.id == flag.task_id]
    while pending:
        task_id = pending.pop()
        if task_id in visited:
            continue
        visited.add(task_id)
        pending.extend(successors[task_id] - visited)
    return sorted((task for task in tasks if task.id in visited and utc(task.ends_at) > utc(as_of)),
                  key=lambda task: (utc(task.starts_at), task.id))


def blocked_tasks(session, flag, as_of=None):
    # Replay follows the source clock, not the wall clock of the demo machine.
    if as_of is None:
        reference = flag.audit[0].source_ref if flag.audit else ""
        source = session.get(models.SourceMessage, reference.removeprefix("source:")) if reference.startswith("source:") else None
        as_of = source.sent_at if source else flag.created_at
    return detect_blocked_tasks(flag, session.scalars(select(models.Task)).all(),
                                session.scalars(select(models.Zone)).all(), as_of)


def crew_routes(crew):
    from app.outbox import lead_route
    yield "lead", *lead_route(crew.lead)
    group = json.loads(os.environ.get("TELEGRAM_CREW_GROUPS_JSON") or "{}").get(crew.id)
    # Groups only: positive Telegram IDs are individual contacts, never crew groups.
    if group is not None and re.fullmatch(r"-[1-9][0-9]{0,18}", str(group)):
        yield "group", "telegram", str(group)


def enqueue_blocked_notices(session, flag, now):
    """One factual notice per Flag/Crew/route; original warning serves its lead."""
    from app.outbox import enqueue, flag_link
    tasks = blocked_tasks(session, flag)
    by_crew = defaultdict(list)
    for task in tasks:
        by_crew[task.crew_id].append(task)
    existing = {row.dedup_key for row in session.scalars(select(models.OutboxMessage).where(
        models.OutboxMessage.flag_id == flag.id))}
    existing.update(row.dedup_key for row in session.new if isinstance(row, models.OutboxMessage))
    events = [link.event or session.get(models.Event, link.event_id) for link in flag.sources]
    sources = "\n".join(f"Source: {item.source.channel}, source:{item.source_message_id}: {item.quote}"
                        for item in events)
    if not sources:
        sources = f"Source: site schedule, task:{flag.task_id}; scan {flag.created_at.isoformat()}."
    for crew_id, crew_tasks in sorted(by_crew.items()):
        crew = session.get(models.Crew, crew_id)
        for route, channel, recipient in crew_routes(crew):
            key = (f"warning:{flag.id}" if route == "lead" and crew.lead_id == flag.responsible_id
                   else f"blocked:{flag.id}:{crew_id}:{route}")
            if key in existing:
                continue
            enqueue(session, flag, "warning", key, recipient,
                    f"SiteMind factual notice — Zone {flag.zone_id}",
                    f"Tasks affected by Flag {flag.type}: {', '.join(task.id for task in crew_tasks)}.\n"
                    f"Open Precondition: {flag.precondition}; evaluation {flag.evaluation}. {flag.explanation}\n"
                    f"{sources}\nCheck with the Superintendent before starting.\n"
                    "This is factual information; work decisions require the Superintendent.\n"
                    f"Details: {flag_link(flag.id)}", now, channel)
            existing.add(key)
            flag.audit.append(models.FlagAudit(action="blocked_notice_queued", actor="rule_engine", channel=channel,
                source_ref=f"outbox-key:{key}", recorded_at=now))
