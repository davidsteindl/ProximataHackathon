"""Transactional factual Flag warnings; only the worker performs delivery."""

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import Field
from sqlalchemy import select

from app import models
from app.lifecycle import transition_flag
from app.schemas import Identifier, Record, Timestamp
from app.site_api import Database

router = APIRouter(tags=["Outbox"])


class OutboxView(Record):
    id: Identifier
    flag_id: Identifier | None
    kind: Literal["warning", "escalation", "approval_request", "proposal_followup", "compliance_reply", "qa_reply", "decision_request"]
    recipient: str | None
    channel: Literal["gmail", "telegram"]
    subject: str
    content: str
    status: Literal["pending", "sending", "sent", "failed", "cancelled"]
    attempts: int
    available_at: Timestamp
    error_code: str | None
    provider_message_id: str | None
    created_at: Timestamp
    sent_at: Timestamp | None


class ClaimView(OutboxView):
    lease_token: Identifier


class DeliveryResult(Record):
    lease_token: Identifier
    status: Literal["sent", "failed"]
    provider_message_id: str | None = Field(default=None, min_length=1, max_length=200)
    error_code: Literal["gmail_error", "telegram_error", "missing_recipient"] | None = None


def dashboard_link(flag):
    base = os.environ.get("DASHBOARD_BASE_URL", "http://localhost:3000").rstrip("/")
    return f"{base}/#flag-{flag.id}"


def flag_link(flag_id):
    return f"{os.environ.get('DASHBOARD_BASE_URL', 'http://localhost:3000').rstrip('/')}/#flag-{flag_id}"


def lead_route(lead):
    """Crew Leads mapped in TELEGRAM_CREW_LEADS_JSON get Telegram, others email."""
    telegram = json.loads(os.environ.get("TELEGRAM_CREW_LEADS_JSON") or "{}").get(lead.id) if lead else None
    return ("telegram", str(telegram)) if telegram else ("gmail", lead.email if lead else None)


def enqueue(session, flag, kind, dedup_key, recipient, subject, content, now, channel="gmail"):
    session.add(models.OutboxMessage(
        id=uuid4().hex, flag=flag, kind=kind, dedup_key=dedup_key, recipient=recipient,
        channel=channel, subject=subject, content=content,
        status="pending", attempts=0, available_at=now, created_at=now,
    ))


def enqueue_flag_warning(session, flag, statement, crew, now, task=None):
    """Queue the factual warning; ``statement`` is None for schedule-only scan Flags."""
    lead = session.get(models.CrewLead, crew.lead_id) if crew else None
    if statement is not None:
        source = (f"Source: {statement.source.channel}, source:{statement.source_message_id}.\n"
                  f"Work announcement (unconfirmed statement): {statement.quote}\n")
    else:
        source = (f"Source: morning scan of the site schedule, {task.id} "
                  f"starts {task.starts_at.isoformat()} (no message received).\n")
    from app.blocked_tasks import blocked_tasks
    affected = blocked_tasks(session, flag, statement.source.sent_at if statement is not None else flag.created_at)
    content = (
        f"Flag {flag.type}: {flag.activity} in Zone {flag.zone_id}.\n"
        f"Task: {flag.task_id or 'unresolved'}.\n"
        f"Required Precondition: {flag.precondition}; Inspection: {flag.inspection_id or 'unresolved'}.\n"
        f"Evaluation at detection: {flag.evaluation}. {flag.explanation}\n"
        f"{source}"
        f"Affected Tasks: {', '.join(item.id for item in affected) or 'unresolved'}.\n"
        "Check with the Superintendent before starting.\n"
        f"Current details: {dashboard_link(flag)}\n"
        "This warning conveys facts only. Work decisions require the Superintendent."
    )
    channel, recipient = lead_route(lead)
    enqueue(session, flag, "warning", f"warning:{flag.id}", recipient,
            f"SiteMind Flag {flag.type} — Zone {flag.zone_id}", content, now, channel)



def enqueue_escalation(session, flag, hours, now):
    """Queue the factual escalation to the Superintendent (next level, PLAN §3.3)."""
    message = models.OutboxMessage(
        id=uuid4().hex, flag=flag, kind="escalation", dedup_key=f"escalation:{flag.id}",
        recipient=os.environ.get("SUPERINTENDENT_EMAIL") or None, channel="gmail",
        subject=f"SiteMind escalation: Flag {flag.type} — Zone {flag.zone_id}",
        content=(
            f"Flag {flag.type}: {flag.activity} in Zone {flag.zone_id} has had no human reaction "
            f"for {hours:g} hours since detection.\n"
            f"Task: {flag.task_id or 'unresolved'}. State: {flag.state}. "
            f"Responsible Crew Lead: {flag.responsible.name if flag.responsible else 'unassigned'}.\n"
            f"Required Precondition: {flag.precondition}; current evaluation: {flag.evaluation}. {flag.explanation}\n"
            f"Current details: {dashboard_link(flag)}\n"
            "This escalation conveys facts only; it does not change, approve or close anything."
        ),
        status="pending", attempts=0, available_at=now, created_at=now,
    )
    session.add(message)
    return message


def audit(session, message, action, now):
    if message.flag_id is None:
        return
    session.add(models.FlagAudit(flag_id=message.flag_id, action=action, actor="worker",
        channel=message.channel, source_ref=f"outbox:{message.id}", recorded_at=now))


@router.get("/outbox", response_model=list[OutboxView])
def list_outbox(session: Database, flag_id: str | None = None):
    query = select(models.OutboxMessage).order_by(models.OutboxMessage.created_at)
    if flag_id is not None:
        query = query.where(models.OutboxMessage.flag_id == flag_id)
    return session.scalars(query).all()


@router.post("/outbox/claim", response_model=ClaimView | None)
def claim_outbox(session: Database, channel: Literal["gmail", "telegram"] = "gmail"):
    now = datetime.now(UTC)
    with session.begin():
        message = session.scalar(select(models.OutboxMessage).where(
            models.OutboxMessage.status.in_(["pending", "sending", "failed"]), models.OutboxMessage.available_at <= now,
            models.OutboxMessage.channel == channel,
        ).order_by(models.OutboxMessage.available_at, models.OutboxMessage.id)
          .with_for_update(skip_locked=True).limit(1))
        if message is None:
            return None
        # A lease recovers messages after a worker crash; stale reports are rejected.
        message.status, message.lease_token = "sending", uuid4().hex
        message.attempts += 1
        message.available_at = now + timedelta(minutes=5)
        audit(session, message, "delivery_attempted", now)
        session.flush()
        result = ClaimView.model_validate(message)
    return result


@router.post("/outbox/{message_id}/result", response_model=OutboxView)
def delivery_result(message_id: str, result: DeliveryResult, session: Database):
    now = datetime.now(UTC)
    with session.begin():
        session.scalar(select(models.Site).with_for_update())
        message = session.scalar(select(models.OutboxMessage).where(
            models.OutboxMessage.id == message_id).with_for_update())
        if message is None:
            raise HTTPException(404, "Outbox message not found")
        if message.lease_token != result.lease_token:
            raise HTTPException(409, "Stale delivery lease")
        if message.status == "sent" and result.status == "sent":
            return OutboxView.model_validate(message)
        if message.status != "sending":
            raise HTTPException(409, "Message is not being delivered")
        if result.status == "sent" and (not result.provider_message_id or result.error_code):
            raise HTTPException(422, "Successful delivery requires a provider message ID and no error")
        if result.status == "failed" and (not result.error_code or result.provider_message_id):
            raise HTTPException(422, "Failed delivery requires an error code and no provider message ID")
        message.status = result.status
        message.error_code = result.error_code
        message.provider_message_id = result.provider_message_id
        if result.status == "sent":
            message.sent_at = now
            flag = session.scalar(select(models.Flag).where(models.Flag.id == message.flag_id).with_for_update())
            # Only the Crew Lead warning notifies; an escalation is not that notification.
            if (flag is not None and message.kind == "warning" and flag.state == "detected"
                    and message.dedup_key == f"warning:{flag.id}"):
                transition_flag(session, flag, action="notified", actor="worker",
                                actor_type="system", channel=message.channel,
                                source_ref=f"outbox:{message.id}")
            if message.kind in {"qa_reply", "decision_request"}:
                message.content = f"[delivered {message.kind}]"
            elif message.channel == "telegram" and message.flag_id is None:
                message.content = "[delivered compliance reply]"
        else:
            message.available_at = now + timedelta(seconds=min(60 * 2 ** min(message.attempts - 1, 6), 3600))
        audit(session, message, "delivery_" + result.status, now)
        session.flush()
        view = OutboxView.model_validate(message)
    return view
