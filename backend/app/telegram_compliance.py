"""Worker-only privacy operations; never changes Evidence or Flag decisions."""

import hashlib
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field
from sqlalchemy import delete, select

from app import models
from app.schemas import Record
from app.site_api import Database


def authorize_worker(x_telegram_compliance_key: str = Header(default="")):
    expected = os.environ.get("TELEGRAM_COMPLIANCE_KEY", "")
    if not expected or not secrets.compare_digest(expected, x_telegram_compliance_key):
        raise HTTPException(403, "Worker credential required")


router = APIRouter(tags=["Telegram compliance"], dependencies=[Depends(authorize_worker)])


class PrivacyCommand(Record):
    request_id: Annotated[str, Field(min_length=1, max_length=200)]
    sender_id: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,18}$")]
    chat_id: Annotated[str, Field(pattern=r"^-?[1-9][0-9]{0,18}$")]
    command: Literal["notice", "my_data", "delete_my_data", "help"]


def retention_days():
    days = int(os.environ.get("TELEGRAM_RETENTION_DAYS", "7"))
    if days < 1:
        raise ValueError("TELEGRAM_RETENTION_DAYS must be positive")
    return days


def erase_raw(session, sources):
    for source in sources:
        session.execute(delete(models.SourceAttachment).where(
            models.SourceAttachment.source_message_id == source.id))
        source.text = ""
        source.status, source.error_code = "processed", None
        source.processing_token, source.processing_started_at = None, None


@router.post("/telegram/retention")
def enforce_retention(session: Database):
    cutoff = datetime.now(UTC) - timedelta(days=retention_days())
    with session.begin():
        sources = session.scalars(select(models.SourceMessage).where(
            models.SourceMessage.channel == "telegram",
            models.SourceMessage.received_at < cutoff,
            (models.SourceMessage.text != "") | models.SourceMessage.attachments.any(),
        ).with_for_update()).all()
        erase_raw(session, sources)
        affected_users = {source.sender_id for source in sources}
        replies = session.scalars(select(models.OutboxMessage).where(
            models.OutboxMessage.channel == "telegram", models.OutboxMessage.flag_id.is_(None),
            (models.OutboxMessage.created_at < cutoff) | models.OutboxMessage.recipient.in_(affected_users),
        ).with_for_update()).all()
        for reply in replies:
            reply.content = "[expired compliance reply]"
            if reply.status != "sent":
                reply.status = "cancelled"
            reply.lease_token = None
    return {"raw_messages_erased": len(sources)}


@router.post("/telegram/commands")
def privacy_command(command: PrivacyCommand, session: Database):
    if command.command in {"my_data", "delete_my_data"} and command.chat_id != command.sender_id:
        raise HTTPException(422, "Privacy commands require a private chat")
    enforce_retention(session)
    identity = hashlib.sha256(f"{command.request_id}:{command.chat_id}:{command.command}".encode()).hexdigest()[:48]
    with session.begin():
        if session.get(models.OutboxMessage, f"tg-{identity}-0") is not None:
            return {"queued": True}
        sources = session.scalars(select(models.SourceMessage).where(
            models.SourceMessage.channel == "telegram",
            models.SourceMessage.sender_id == command.sender_id,
        ).order_by(models.SourceMessage.received_at).with_for_update()).all()
        if command.command == "notice":
            owner = os.environ.get("TELEGRAM_RESPONSIBLE", "SiteMind demo team")
            text = (f"SiteMind verarbeitet Texte und Rollen freigegebener Team-Testaccounts zur Erkennung "
                    f"von Baukonflikten (keine Personenkennzahlen). Rohdaten: {retention_days()} Tage. "
                    f"Verantwortlich: {owner}. Nur synthetische Daten! "
                    "Abgeleitete Events, Nachweise und relevante Flag-Zitate bleiben als Baustellenrecord erhalten. "
                    "Im privaten Bot-Chat: /my_data für Auskunft, /delete_my_data für Rohdatenlöschung. "
                    "Telegram ist nicht Ende-zu-Ende-verschlüsselt. Keine Freigaben per Chat.")
        elif command.command == "my_data":
            data = []
            for source in sources:
                events = session.scalars(select(models.Event).where(
                    models.Event.source_message_id == source.id)).all()
                derived = []
                for event in events:
                    evidence = session.scalars(select(models.Evidence).where(
                        models.Evidence.statement_ref == event.id)).all()
                    flag_ids = session.scalars(select(models.FlagSource.flag_id).where(
                        models.FlagSource.event_id == event.id)).all()
                    derived.append({"id": event.id, "quote": event.quote, "intent": event.intent,
                                    "details": event.details, "flag_ids": flag_ids,
                                    "evidence": [{"id": item.id, "quote": item.quote,
                                                  "review_status": item.review_status, "scope": item.scope}
                                                 for item in evidence]})
                data.append({"source_id": source.id, "chat": source.source_key,
                             "message_id": source.external_id, "role": source.sender_role,
                             "sender_id": source.sender_id, "crew_id": source.sender_crew_id,
                             "sent_at": source.sent_at.isoformat(), "text": source.text,
                             "events": derived})
            text = "Eigene gespeicherte Rohdaten und abgeleitete Events:\n" + json.dumps(data, ensure_ascii=False)
        elif command.command == "delete_my_data":
            erase_raw(session, sources)
            replies = session.scalars(select(models.OutboxMessage).where(
                models.OutboxMessage.channel == "telegram", models.OutboxMessage.flag_id.is_(None),
                models.OutboxMessage.recipient == command.sender_id,
            ).with_for_update()).all()
            for reply in replies:
                reply.content, reply.lease_token = "[deleted compliance reply]", None
                if reply.status != "sent":
                    reply.status = "cancelled"
            text = ("Rohtexte, Anhänge und ausstehende Auskunftskopien gelöscht. Numerische Quell-IDs, "
                    "Zeitpunkte, Rollen, abgeleitete Events, Nachweise, "
                    "Audit und relevante Flag-Zitate bleiben für die Nachvollziehbarkeit erhalten. "
                    "Keine Nachweisentscheidung oder Flag-Änderung. Bereits zugestellte Telegram-Kopien "
                    "werden dadurch nicht gelöscht. Weitere Löschanfragen an den Verantwortlichen.")
        else:
            text = ("Privater Bot-Chat: /my_data und /delete_my_data. /privacy zeigt die Datenschutzhinweise. "
                    "Nachweise, Proposals und Flags werden ausschließlich im Dashboard entschieden.")
        chunks = [text[start:start + 1800] for start in range(0, len(text), 1800)]
        for index, chunk in enumerate(chunks):
            now = datetime.now(UTC)
            content = f"Teil {index + 1}/{len(chunks)}\n{chunk}" if len(chunks) > 1 else chunk
            session.add(models.OutboxMessage(
                id=f"tg-{identity}-{index}", channel="telegram", recipient=command.chat_id,
                subject="SiteMind compliance", content=content, status="pending",
                attempts=0, created_at=now, available_at=now,
            ))
    return {"queued": True}
