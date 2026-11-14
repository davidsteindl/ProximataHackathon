import base64
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import ingestion, models
from app.extraction import ExtractedBatch, ExtractedEvent, ExtractionError
from test_ingestion_storage import message_payload


@pytest.fixture
def initialized(client, seed, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "cached")
    monkeypatch.delenv("LLM_CACHE_PATH", raising=False)
    assert client.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
    return client


def test_ingest_persists_source_and_returns_source_backed_event(initialized):
    payload = message_payload(sender_id="synthetic-lead")
    response = initialized.post("/ingestion/messages", json=payload)
    assert response.status_code == 201
    result = response.json()
    assert result["source"]["status"] == "processed"
    assert result["source"]["sender_id"] == "synthetic-lead"
    assert result["source"]["text"] == payload["text"]
    event = result["events"][0]
    assert event["zone_ids"] == ["3B"]
    assert event["intent"] == "planned_work"
    assert event["source_message_id"] == result["source"]["id"]
    assert event["source"]["text"] == event["quote"] == payload["text"]
    assert event["starts_at"] == "2026-11-15T05:00:00Z"
    assert event["ends_at"] == "2026-11-15T11:00:00Z"
    assert event["evidence"] == []
    assert initialized.get("/events").json() == [event]
    assert initialized.get(f"/source-messages/{result['source']['id']}").json() == result["source"]


def test_idempotency_reuses_events_and_distinguishes_source_accounts(initialized, monkeypatch):
    payload = message_payload()
    first = initialized.post("/ingestion/messages", json=payload).json()
    original_factory = ingestion.get_extractor
    monkeypatch.setattr(ingestion, "get_extractor", Mock(side_effect=AssertionError("Duplicate extraction")))
    # Equivalent timestamp offsets are normalized before hashing.
    payload["sent_at"] = "2026-11-14T17:05:00Z"
    repeated = initialized.post("/ingestion/messages", json=payload)
    assert repeated.status_code == 200
    assert repeated.json()["duplicate"] is True
    assert repeated.json()["events"] == first["events"]
    assert initialized.post("/ingestion/messages", json={**payload, "text": "changed text"}).status_code == 409
    monkeypatch.setattr(ingestion, "get_extractor", original_factory)
    for changes in [{"source_key": "another-test-chat"}, {"channel": "replay"}]:
        assert initialized.post("/ingestion/messages", json={**payload, **changes}).status_code == 201
    assert len(initialized.get("/events").json()) == 3


def test_irrelevant_and_non_dxf_attachment_only_sources_are_preserved_without_events(initialized, monkeypatch):
    response = initialized.post("/ingestion/messages", json=message_payload(text="Danke, bis später!"))
    assert response.status_code == 201
    assert response.json()["events"] == []
    assert response.json()["source"]["status"] == "processed"
    content = b"synthetic original attachment content"
    attachment = {"file_name": "note.txt", "media_type": "text/plain", "content_base64": base64.b64encode(content).decode()}
    monkeypatch.setattr(ingestion, "get_extractor", Mock(side_effect=AssertionError("Attachment sent to LLM")))
    result = initialized.post("/ingestion/messages", json=message_payload(external_id="attachment", text="", attachments=[attachment])).json()
    assert result["source"]["status"] == "processed"
    assert result["events"] == []
    source_id = result["source"]["id"]
    attachment_id = result["source"]["attachments"][0]["id"]
    download = initialized.get(f"/source-messages/{source_id}/attachments/{attachment_id}")
    assert download.content == content
    assert download.headers["content-disposition"].startswith("attachment;")
    assert initialized.get(f"/source-messages/wrong-source/attachments/{attachment_id}").status_code == 404


def test_failed_extraction_keeps_source_and_retry_creates_exactly_one_result(initialized, monkeypatch):
    original_factory = ingestion.get_extractor
    factory = Mock(side_effect=ExtractionError("provider_unavailable"))
    monkeypatch.setattr(ingestion, "get_extractor", factory)
    first = initialized.post("/ingestion/messages", json=message_payload())
    assert first.status_code == 502
    source_id = first.json()["source"]["id"]
    assert first.json()["source"]["error_code"] == "provider_unavailable"
    assert first.json()["events"] == []
    assert initialized.get(f"/source-messages/{source_id}").json()["text"] == message_payload()["text"]
    monkeypatch.setattr(ingestion, "get_extractor", original_factory)
    response = initialized.post("/ingestion/messages", json=message_payload())
    assert response.status_code == 200
    assert response.json()["duplicate"] is True
    assert response.json()["source"]["id"] == source_id
    assert response.json()["source"]["error_code"] is None
    assert len(response.json()["events"]) == 1
    assert len(initialized.get("/events").json()) == 1


def test_invalid_quote_and_cache_miss_are_visible_without_partial_events(initialized, monkeypatch):
    unknown = initialized.post("/ingestion/messages", json=message_payload(text="uncached message"))
    assert unknown.status_code == 502
    assert unknown.json()["source"]["error_code"] == "cache_miss"
    extractor = Mock(name="synthetic-extractor")
    extractor.name = "test"
    extractor.extract.return_value = ExtractedBatch(events=[
        ExtractedEvent(intent="planned_work", quote="not in the source", confidence=1),
    ])
    monkeypatch.setattr(ingestion, "get_extractor", lambda: extractor)
    response = initialized.post("/ingestion/messages", json=message_payload(external_id="invalid-quote"))
    assert response.status_code == 502
    assert response.json()["source"]["error_code"] == "invalid_quote"
    assert initialized.get("/events").json() == []


def test_mapping_transaction_failure_rolls_back_events_and_evidence(initialized, monkeypatch):
    original = ingestion.build_events

    def fail_after_mapping(session, source, statements):
        original(session, source, statements)
        session.flush()
        raise SQLAlchemyError("synthetic storage failure")

    monkeypatch.setattr(ingestion, "build_events", fail_after_mapping)
    before = initialized.get("/evidence").json()
    response = initialized.post("/ingestion/messages", json=message_payload(
        sender_role="inspector", text="Abnahme der Rohinstallation im 3. OG bestanden.",
    ))
    assert response.status_code == 502
    assert response.json()["source"]["error_code"] == "storage_failed"
    assert initialized.get("/events").json() == []
    assert initialized.get("/evidence").json() == before


def test_active_processing_is_not_duplicated_and_expired_attempt_can_retry(initialized, engine):
    first = initialized.post("/ingestion/messages", json=message_payload(text="uncached message")).json()
    source_id = first["source"]["id"]
    with Session(engine) as session, session.begin():
        session.execute(update(models.SourceMessage).where(models.SourceMessage.id == source_id).values(
            status="processing", processing_token="active-attempt", processing_started_at=datetime.now(UTC),
        ))
    response = initialized.post("/ingestion/messages", json=message_payload(text="uncached message"))
    assert response.status_code == 202
    with Session(engine) as session, session.begin():
        session.execute(update(models.SourceMessage).where(models.SourceMessage.id == source_id).values(
            processing_started_at=datetime.now(UTC) - timedelta(minutes=6),
        ))
    response = initialized.post("/ingestion/messages", json=message_payload(text="uncached message"))
    assert response.status_code == 502
    assert response.json()["source"]["error_code"] == "cache_miss"


@pytest.mark.parametrize("mode", ["cached", "openai_compatible"])
def test_success_claims_stay_unconfirmed_and_preserve_human_confirmation(initialized, engine, monkeypatch, mode):
    before = initialized.get("/evidence").json()
    # Simulate an existing human decision through #5 storage, not a review endpoint.
    with Session(engine) as session, session.begin():
        session.add(models.EvidenceReview(
            evidence_id="example-contradictory-negative", sequence=2, status="confirmed",
            actor_type="human", reviewer_id="synthetic-superintendent", reviewer_role="superintendent",
            decided_at=datetime.now(UTC), recorded_at=datetime.now(UTC),
        ))
    existing = initialized.get("/evidence").json()
    monkeypatch.setenv("LLM_PROVIDER", mode)
    if mode == "openai_compatible":
        monkeypatch.setenv("LLM_BASE_URL", "https://provider.invalid/v1")
        monkeypatch.setenv("LLM_MODEL", "test-model")
        monkeypatch.setenv("LLM_API_KEY", "synthetic-key")

        original_post = httpx.Client.post

        def live_response(self, url, **kwargs):
            if str(url).startswith("/"):
                return original_post(self, url, **kwargs)
            user = json.loads(kwargs["json"]["messages"][1]["content"])
            assert set(user) == {"text", "sender_role"}
            assert "private-sender" not in json.dumps(kwargs["json"])
            result = {"events": [{"intent": "inspection_result", "quote": user["text"], "confidence": 1,
                                  "zones": ["F3"], "inspection_kind": "rough_in", "claim": "passed"}]}
            return httpx.Response(200, request=httpx.Request("POST", url), json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]})

        monkeypatch.setattr(httpx.Client, "post", live_response)
    result = initialized.post("/ingestion/messages", json=message_payload(
        sender_id="private-sender", sender_role="inspector", sender_crew_id=None,
        text="Abnahme der Rohinstallation im 3. OG bestanden.",
    )).json()
    evidence = result["events"][0]["evidence"][0]
    assert evidence["review_status"] == "unconfirmed"
    assert evidence["scope"]["inspection_id"] == "rough-in-F3"
    assert evidence["history"][0]["reviewer_id"] is evidence["history"][0]["decided_at"] is None
    all_evidence = initialized.get("/evidence").json()
    assert len(all_evidence) == len(before) + 1
    assert all(record in all_evidence for record in existing)
    assert next(record for record in initialized.get("/inspections").json() if record["id"] == "rough-in-F3")["status"] == "pending"


def test_ambiguous_claim_warning_seen_and_question_remain_distinct(initialized):
    for ordinal, text in enumerate(["Abnahme dürfte passen", "Warnung gesehen", "welcher plan gilt für 3B?"]):
        result = initialized.post("/ingestion/messages", json=message_payload(external_id=str(ordinal), text=text)).json()
        event = result["events"][0]
        if ordinal == 0:
            assert event["evidence"][0]["review_status"] == "unconfirmed"
            assert event["evidence"][0]["scope"]["inspection_id"] is None
            assert event["evidence"][0]["scope"]["zone_id"] is None
        elif ordinal == 1:
            assert event["intent"] == "observation"
            assert event["evidence"] == []
        else:
            assert event["intent"] == "question"
            assert event["evidence"] == []


def test_new_hero_room_question_is_extracted_without_executing_a_status_query(initialized):
    result = initialized.post("/ingestion/messages", json=message_payload(
        sender_role="superintendent", sender_crew_id=None, text="wie ist der Stand im Bad 3B?",
    )).json()
    event = result["events"][0]
    assert event["intent"] == "question"
    assert event["zone_ids"] == ["3B-BATH"]
    assert event["evidence"] == []


def test_timeline_orders_by_message_time_and_filters_zones_and_half_open_dates(initialized):
    for external_id, sent_at in [("later", "2026-11-14T18:05:00+01:00"), ("earlier", "2026-11-13T18:05:00+01:00")]:
        assert initialized.post("/ingestion/messages", json=message_payload(external_id=external_id, sent_at=sent_at)).status_code == 201
    events = initialized.get("/events").json()
    assert [event["source"]["external_id"] for event in events] == ["earlier", "later"]
    assert len(initialized.get("/events", params={"zone_id": "F3"}).json()) == 2
    assert initialized.get("/events", params={"zone_id": "F3", "include_descendants": False}).json() == []
    assert initialized.get("/events", params={"zone_id": "3A"}).json() == []
    assert len(initialized.get("/events", params={"from_time": "2026-11-14T17:05:00Z"}).json()) == 1
    assert len(initialized.get("/events", params={"to_time": "2026-11-14T17:05:00Z"}).json()) == 1
    assert initialized.get("/events", params={"zone_id": "unknown"}).status_code == 404
    assert initialized.get("/events", params={"from_time": "2026-11-14T00:00:00"}).status_code == 422
    assert initialized.get("/events", params={"from_time": "2026-11-15T00:00:00Z", "to_time": "2026-11-14T00:00:00Z"}).status_code == 422


def test_input_boundary_openapi_and_reset_preserve_seed_provenance(initialized, seed, engine):
    for field in ["review_status", "origin", "history", "events"]:
        assert initialized.post("/ingestion/messages", json=message_payload(**{field: "confirmed"})).status_code == 422
    assert initialized.post("/ingestion/messages", json=message_payload(sender_crew_id="unknown")).status_code == 422
    assert initialized.get("/source-messages/missing").status_code == 404
    initialized.post("/ingestion/messages", json=message_payload(channel="seed"))
    assert initialized.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
    assert initialized.get("/events").json() == []
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(models.SourceMessage)) == 0
    baseline = initialized.get("/evidence").json()
    assert len(baseline) == len(seed.evidence)
    assert all(record["origin"].startswith("seed_") for record in baseline)
    spec = initialized.get("/openapi.json").json()
    assert {"/ingestion/messages", "/source-messages/{source_id}", "/events"} <= spec["paths"].keys()


def test_ingestion_requires_site_baseline(client):
    assert client.post("/ingestion/messages", json=message_payload()).status_code == 409
