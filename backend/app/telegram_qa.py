"""Worker-only Telegram questions: record answers and durable human decision requests."""

import hashlib
import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app import models, qa
from app.extraction import redact_text
from app.schemas import Identifier, Record
from app.site_api import Database
from app.telegram_compliance import authorize_worker, enforce_retention

router = APIRouter(tags=["Telegram Q&A"], dependencies=[Depends(authorize_worker)])


class TelegramQuestion(Record):
    source_id: Identifier


class TelegramReply(Record):
    handled: bool
    reply_id: str | None = None


def message_id(source_id, kind):
    return "tgqa-" + hashlib.sha256(f"{kind}:{source_id}".encode()).hexdigest()[:48]


def enqueue(session, source_id, kind, channel, recipient, text, now):
    row = models.OutboxMessage(
        id=message_id(source_id, kind), kind=kind, channel=channel,
        dedup_key=f"telegram-{kind}:{source_id}", recipient=recipient,
        subject="SiteMind: decision requested" if kind == "decision_request" else "SiteMind record answer",
        content=text, status="pending", attempts=0, created_at=now, available_at=now,
    )
    session.add(row)
    return row


@router.post("/telegram/qa", response_model=TelegramReply)
async def answer_telegram(question: TelegramQuestion, session: Database):
    enforce_retention(session)
    # No transaction/lock is held while the Q&A core calls MCP back into the API.
    with session.begin():
        source = session.get(models.SourceMessage, question.source_id)
        if source is None or source.channel != "telegram":
            raise HTTPException(404, "Telegram source not found")
        existing = session.get(models.OutboxMessage, message_id(source.id, "qa_reply"))
        if existing is not None:
            return TelegramReply(handled=True, reply_id=existing.id)
        if not source.text.strip():
            return TelegramReply(handled=False)  # Deleted/expired raw data must not be re-imported.
        source_id, text, role, chat = source.id, source.text, source.sender_role, source.source_key

    if len(text) > 4000:
        kind, reply_text, zone_id = "clarification", "Please ask a question of at most 4000 characters.", None
    else:
        answer = await qa.ask(qa.Question(text=text, sender_role=role))
        kind, reply_text, zone_id = answer.kind, answer.text, answer.zone_id
    if kind == "not_a_question":
        return TelegramReply(handled=False)

    # Lock in the same order as ingestion/reset, then recheck identity and deletion.
    with session.begin():
        session.scalar(select(models.Site).with_for_update())
        source = session.scalar(select(models.SourceMessage).where(
            models.SourceMessage.id == source_id).with_for_update())
        if source is None:
            raise HTTPException(404, "Telegram source no longer exists")
        existing = session.get(models.OutboxMessage, message_id(source_id, "qa_reply"))
        if existing is not None:
            return TelegramReply(handled=True, reply_id=existing.id)
        if source.text != text:
            return TelegramReply(handled=False)
        now = datetime.now(UTC)
        if kind == "decision_request":
            recipient = os.environ.get("SUPERINTENDENT_EMAIL", "").strip()
            if not recipient:
                raise HTTPException(503, "superintendent_not_configured")
            base = os.environ.get("DASHBOARD_BASE_URL", "http://localhost:3000").rstrip("/")
            link = f"{base}/zones/{zone_id}" if zone_id else f"{base}/"
            enqueue(session, source_id, "decision_request", "gmail", recipient,
                    f"A {role} requests a Superintendent decision. Zone: {zone_id or 'unresolved'}.\n"
                    f"Question (redacted): {redact_text(text)}\n"
                    f"Source: source:{source_id} (Telegram).\nReview the record: {link}\n"
                    "No approval, Evidence confirmation, Proposal decision or Flag change was performed.", now)
            reply_text = ("Your request is queued for the Superintendent to decide. "
                          "It has not been approved. No Evidence or Flag decision was made. "
                          f"[source:{source_id}]")
        reply = enqueue(session, source_id, "qa_reply", "telegram", chat, reply_text, now)
        session.flush()
        return TelegramReply(handled=True, reply_id=reply.id)
