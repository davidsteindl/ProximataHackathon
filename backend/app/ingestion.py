"""Persist sources before advisory extraction; commit each result atomically."""

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import models, schemas
from app import rules  # Register atomic Event/EvidenceReview rule evaluation hooks.
from app.event_mapping import build_events
from app.extraction import ExtractionError, get_extractor, redact_text, validate_quotes
from app.ingestion_schemas import EventView, IngestionResult, SourceMessageView


def source_identity(payload):
    return (
        models.SourceMessage.channel == payload.channel,
        models.SourceMessage.source_key == payload.source_key,
        models.SourceMessage.external_id == payload.external_id,
    )


def store_source(session, payload):
    digest = hashlib.sha256(json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    try:
        with session.begin():
            existing = session.scalar(select(models.SourceMessage).where(*source_identity(payload)))
            if existing is not None:
                if existing.payload_hash != digest:
                    raise HTTPException(409, "Source identity already exists with different content")
                return existing.id, True
            site = session.scalar(select(models.Site))
            if site is None:
                raise HTTPException(409, "Import the Site baseline before ingesting messages")
            if payload.sender_crew_id and session.get(models.Crew, payload.sender_crew_id) is None:
                raise HTTPException(422, "Unknown sender_crew_id")
            source = models.SourceMessage(
                id=uuid4().hex, site_id=site.id, payload_hash=digest,
                received_at=datetime.now(UTC), status="pending",
                **payload.model_dump(exclude={"attachments"}),
            )
            source.attachments = []
            for attachment in payload.attachments:
                content = base64.b64decode(attachment.content_base64)
                source.attachments.append(models.SourceAttachment(
                    id=uuid4().hex, file_name=attachment.file_name, media_type=attachment.media_type,
                    sha256=hashlib.sha256(content).hexdigest(), content=content,
                ))
            session.add(source)
            session.flush()
            source_id = source.id
        return source_id, False
    except IntegrityError:
        # A concurrent delivery may have won the unique identity constraint.
        with session.begin():
            existing = session.scalar(select(models.SourceMessage).where(*source_identity(payload)))
            if existing is None:
                raise HTTPException(409, "Source storage conflicted; retry this message") from None
            if existing.payload_hash != digest:
                raise HTTPException(409, "Source identity already exists with different content") from None
            return existing.id, True


def process_source(session, source_id, extractor_factory=None):
    token, now = uuid4().hex, datetime.now(UTC)
    with session.begin():
        claimed = session.execute(
            update(models.SourceMessage).where(
                models.SourceMessage.id == source_id,
                or_(
                    models.SourceMessage.status.in_(["pending", "failed"]),
                    (models.SourceMessage.status == "processing")
                    & (models.SourceMessage.processing_started_at < now - timedelta(minutes=5)),
                ),
            ).values(status="processing", processing_token=token, processing_started_at=now, error_code=None)
            .execution_options(synchronize_session=False)
        ).rowcount
        if not claimed:
            return
        session.expire_all()
        source = session.get(models.SourceMessage, source_id)
        text, role, sender_id = source.text, source.sender_role, source.sender_id
    # No database transaction or row lock is held during the provider call.
    backend = None
    try:
        if text.strip():
            extractor = (extractor_factory or get_extractor)()
            backend = extractor.name
            redacted = redact_text(text, sender_id)
            batch = extractor.extract(redacted, role)
            statements = validate_quotes(batch, redacted, text)
        else:
            statements, backend = [], "attachment_only"
        with session.begin():
            source = session.scalar(select(models.SourceMessage).where(
                models.SourceMessage.id == source_id, models.SourceMessage.processing_token == token,
            ).with_for_update())
            if source is None:
                return  # Reset or a newer attempt owns this source now.
            build_events(session, source, statements)
            source.status, source.error_code = "processed", None
            source.processing_token, source.processing_started_at = None, None
            source.extraction_backend = backend
    except (ExtractionError, SQLAlchemyError) as error:
        session.rollback()
        code = error.code if isinstance(error, ExtractionError) else "storage_failed"
        with session.begin():
            session.execute(update(models.SourceMessage).where(
                models.SourceMessage.id == source_id, models.SourceMessage.processing_token == token,
            ).values(
                status="failed", error_code=code, processing_token=None,
                processing_started_at=None, extraction_backend=backend,
            ))


def event_views(session, events):
    if not events:
        return []
    evidence_by_event = {}
    for evidence in session.scalars(select(models.Evidence).where(
        models.Evidence.statement_ref.in_([event.id for event in events]),
    ).order_by(models.Evidence.id)):
        evidence_by_event.setdefault(evidence.statement_ref, []).append(schemas.EvidenceView.model_validate(evidence))
    return [EventView.model_validate(event).model_copy(update={
        "evidence": evidence_by_event.get(event.id, []),
    }) for event in events]


def ingestion_result(session, source_id, duplicate):
    source = session.get(models.SourceMessage, source_id)
    if source is None:
        raise HTTPException(409, "Source was removed by a concurrent demo reset; submit it again")
    events = session.scalars(select(models.Event).where(
        models.Event.source_message_id == source_id,
    ).order_by(models.Event.ordinal)).all()
    return IngestionResult(source=SourceMessageView.model_validate(source), events=event_views(session, events), duplicate=duplicate)
