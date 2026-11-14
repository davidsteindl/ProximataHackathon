import base64
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.ingestion_schemas import SourceMessageInput
from app.seed import import_seed


def message_payload(**changes):
    return {
        "channel": "telegram", "source_key": "synthetic-crew-chat", "external_id": "42",
        "sender_role": "crew_lead", "sender_crew_id": "drywall",
        "sent_at": "2026-11-14T18:05:00+01:00",
        "text": "morgen früh machen wir 3B zu, platten sind da", **changes,
    }


def source_record(seed, **changes):
    fields = dict(
        id="source-1", site_id=seed.site.id, channel="telegram", source_key="test-chat",
        external_id="42", payload_hash="0" * 64, sender_role="crew_lead", sender_crew_id="drywall",
        text="morgen früh machen wir 3B zu, platten sind da", status="pending",
        sent_at=datetime(2026, 11, 14, 17, 5, tzinfo=UTC), received_at=datetime.now(UTC),
    )
    return models.SourceMessage(**(fields | changes))


def test_source_contract_accepts_original_attachment_and_normalizes_time():
    content = b"synthetic DXF bytes"
    message = SourceMessageInput.model_validate(message_payload(attachments=[{
        "file_name": "A-103_RevD.dxf", "media_type": "application/dxf",
        "content_base64": base64.b64encode(content).decode(),
    }]))
    assert message.sent_at.hour == 17
    assert base64.b64decode(message.attachments[0].content_base64) == content


@pytest.mark.parametrize("changes", [
    {"sent_at": "2026-11-14T18:05:00"}, {"text": " "}, {"review_status": "confirmed"},
    {"sender_role": "invented"}, {"attachments": [{"file_name": "../plan.dxf", "media_type": "application/dxf", "content_base64": "YQ=="}]},
    {"attachments": [{"file_name": "plan.dxf", "media_type": "application/dxf", "content_base64": "not base64"}]},
])
def test_source_contract_rejects_invalid_data_and_caller_confirmation(changes):
    with pytest.raises(ValidationError):
        SourceMessageInput.model_validate(message_payload(**changes))


def test_database_rejects_duplicate_source_identity_and_event_ordinal(engine, seed):
    with Session(engine) as session:
        import_seed(session, seed)
        source = source_record(seed)
        session.add(source)
        session.commit()
        session.add(source_record(seed, id="source-2"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        for event_id in ("event-1", "event-2"):
            session.add(models.Event(
                id=event_id, source_message_id="source-1", ordinal=0, intent="planned_work",
                quote=source.text, confidence=0.99, time_precision="unspecified",
                unresolved_zones=[], details={}, created_at=datetime.now(UTC),
            ))
        with pytest.raises(IntegrityError):
            session.commit()


def test_seed_reset_clears_ingestion_records_and_keeps_baseline_provenance(engine, seed):
    with Session(engine) as session:
        import_seed(session, seed)
        source = source_record(seed)
        source.attachments = [models.SourceAttachment(
            id="attachment-1", file_name="plan.dxf", media_type="application/dxf",
            sha256="0" * 64, content=b"original synthetic bytes",
        )]
        session.add(source)
        session.flush()
        session.add(models.Event(
            id="event-1", source_message_id=source.id, ordinal=0, intent="planned_work",
            quote=source.text, confidence=0.99, time_precision="unspecified",
            unresolved_zones=[], details={}, created_at=datetime.now(UTC), zones=[session.get(models.Zone, "3B")],
        ))
        session.commit()
        import_seed(session, seed)
        for model in (models.SourceMessage, models.SourceAttachment, models.Event):
            assert session.scalar(select(func.count()).select_from(model)) == 0
        assert session.scalar(select(func.count()).select_from(models.Evidence)) == len(seed.evidence)
