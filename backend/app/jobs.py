"""Time-based jobs (#14): morning scan of the schedule and escalation timer.

The worker triggers both via REST on its clock; replay (#22) can trigger them
on demand with a simulated ``as_of``. Both are idempotent: dedup keeps one open
Flag per conflict and a Flag escalates at most once. Neither closes a Flag,
confirms Evidence or approves anything.
"""

import os
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app import models
from app.lifecycle import transition_flag
from app.outbox import enqueue_escalation
from app.rules import evaluate_site, utc
from app.schemas import Identifier, Record, Timestamp
from app.site_api import Database

router = APIRouter(prefix="/jobs", tags=["Jobs"])
OPEN = ("detected", "notified", "acknowledged", "in_progress")


def number_env(name, default):
    try:
        value = float(os.environ.get(name) or default)
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


def scan_window(as_of, timezone, lookahead_days):
    """From ``as_of`` to the end of the local day ``lookahead_days`` later."""
    local = utc(as_of).astimezone(ZoneInfo(timezone))
    last_day = local.date() + timedelta(days=lookahead_days)
    end = datetime.combine(last_day + timedelta(days=1), time(), tzinfo=ZoneInfo(timezone))
    return utc(as_of), end.astimezone(UTC)


def scan_tasks(session, start, end):
    tasks = session.scalars(select(models.Task).order_by(models.Task.starts_at, models.Task.id)).all()
    return [task for task in tasks if start <= utc(task.starts_at) < end]


def run_morning_scan(session, as_of, lookahead_days=None):
    """Check Preconditions of work starting soon, using the schedule alone."""
    site = session.scalar(select(models.Site).with_for_update())
    if site is None:
        raise LookupError("No site record; import the seed first")
    days = int(number_env("SCAN_LOOKAHEAD_DAYS", 1) if lookahead_days is None else lookahead_days)
    start, end = scan_window(as_of, site.timezone, days)
    tasks = scan_tasks(session, start, end)
    before = {flag.id: len(flag.audit) for flag in session.scalars(select(models.Flag))}
    evaluate_site(session, source_ref=f"scan:{start.isoformat()}", actor="morning_scan",
                  channel="system", scan_tasks=tasks, scan_at=start)
    session.flush()
    created, updated = [], []
    for flag in session.scalars(select(models.Flag).where(models.Flag.state.in_(OPEN))
                                .order_by(models.Flag.created_at, models.Flag.id)):
        if flag.id not in before:
            created.append(flag.id)
        elif len(flag.audit) != before[flag.id]:
            updated.append(flag.id)
    return dict(as_of=start, window_end=end, task_ids=[task.id for task in tasks],
                created_flag_ids=created, updated_flag_ids=updated)


def had_reaction(flag):
    # Human lifecycle actions carry a role; system/worker entries do not.
    return any(item.actor_role is not None for item in flag.audit)


def detected_at(session, flag):
    """Detection time on the trigger's clock, comparable with a simulated ``as_of``:
    the source message's ``sent_at`` (replay keeps its simulated time) for Event
    Flags, ``created_at`` (the scan's ``as_of``) for schedule Flags."""
    detection = next((item for item in flag.audit if item.action == "detected"), None)
    if detection and detection.source_ref and detection.source_ref.startswith("source:"):
        message = session.get(models.SourceMessage, detection.source_ref.removeprefix("source:"))
        if message is not None:
            return utc(message.sent_at)
    return utc(flag.created_at)


def run_escalations(session, as_of, hours=None):
    """Escalate each Flag without human reaction after X hours, exactly once."""
    session.scalar(select(models.Site).with_for_update())
    hours = number_env("ESCALATION_HOURS", 4) if hours is None else hours
    threshold = timedelta(hours=hours)
    now = datetime.now(UTC)
    escalated = []
    flags = session.scalars(select(models.Flag).where(models.Flag.state.in_(["detected", "notified"]))
                            .order_by(models.Flag.created_at, models.Flag.id)).all()
    for flag in flags:
        if had_reaction(flag) or any(item.action == "escalated" for item in flag.audit):
            continue
        if utc(as_of) - detected_at(session, flag) < threshold:
            continue
        message = enqueue_escalation(session, flag, hours, now)
        transition_flag(session, flag, action="escalated", actor="escalation_timer",
                        actor_type="system", channel="system", source_ref=f"outbox:{message.id}")
        escalated.append(flag.id)
    session.flush()
    return dict(as_of=utc(as_of), threshold_hours=hours, escalated_flag_ids=escalated)


class JobRequest(Record):
    """Optional simulated clock for replay; defaults to the server time."""
    as_of: Timestamp | None = None


class ScanResult(Record):
    as_of: Timestamp
    window_end: Timestamp
    task_ids: list[Identifier]
    created_flag_ids: list[Identifier]
    updated_flag_ids: list[Identifier]


class EscalationResult(Record):
    as_of: Timestamp
    threshold_hours: float
    escalated_flag_ids: list[Identifier]


@router.post("/morning-scan", response_model=ScanResult)
def morning_scan(session: Database, request: JobRequest | None = None):
    try:
        result = run_morning_scan(session, (request and request.as_of) or datetime.now(UTC))
    except LookupError as error:
        raise HTTPException(409, str(error)) from error
    session.commit()
    return result


@router.post("/escalation", response_model=EscalationResult)
def escalation(session: Database, request: JobRequest | None = None):
    result = run_escalations(session, (request and request.as_of) or datetime.now(UTC))
    session.commit()
    return result
