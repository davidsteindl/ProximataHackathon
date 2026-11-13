import json
from datetime import UTC, datetime
from unittest.mock import Mock

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.event_mapping import build_events, resolve_zones
from app.extraction import (
    CachedExtractor, ExtractedBatch, ExtractedEvent, ExtractionError,
    OpenAICompatibleExtractor, TimeReference, get_extractor, redact_text,
    resolve_time, validate_quotes,
)
from app.seed import import_seed
from conftest import BACKEND
from test_ingestion_storage import source_record

CACHE = BACKEND / "demo" / "extraction-cache.json"


def test_offline_hero_work_maps_zone_trade_and_absolute_time_without_network(engine, seed, monkeypatch):
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: pytest.fail("Offline network call"))
    with Session(engine) as session:
        import_seed(session, seed)
        source = source_record(seed)
        session.add(source)
        session.flush()
        batch = CachedExtractor(CACHE).extract(source.text, source.sender_role)
        statements = validate_quotes(batch, source.text, source.text)
        event = build_events(session, source, statements)[0]
        session.commit()
        assert (event.intent, event.trade, event.activity, event.crew_id) == ("planned_work", "drywall", "closing_work", "drywall")
        assert event.zone_ids == ["3B"]
        assert event.starts_at.replace(tzinfo=UTC) == datetime(2026, 11, 15, 5, tzinfo=UTC)
        assert event.ends_at.replace(tzinfo=UTC) == datetime(2026, 11, 15, 11, tzinfo=UTC)
        assert event.time_precision == "part_of_day"
        assert event.quote == source.text


@pytest.mark.parametrize("entry", json.loads(CACHE.read_text())["entries"])
def test_all_synthetic_cache_entries_pass_same_extraction_and_quote_validation(entry):
    batch = CachedExtractor(CACHE).extract(redact_text(entry["text"]), entry["sender_role"])
    statements = validate_quotes(batch, redact_text(entry["text"]), entry["text"])
    assert len(statements) == len(entry["result"]["events"])


def test_cache_miss_or_invalid_cache_never_falls_back_to_live(tmp_path):
    with pytest.raises(ExtractionError, match="cache_miss"):
        CachedExtractor(CACHE).extract("uncached synthetic message", "unknown")
    path = tmp_path / "invalid.json"
    path.write_text('{"version": 2}')
    with pytest.raises(ExtractionError, match="invalid_cache"):
        CachedExtractor(path).extract("test", "unknown")
    with pytest.raises(ExtractionError, match="invalid_cache"):
        CachedExtractor(tmp_path / "missing.json").extract("test", "unknown")


def test_live_request_contains_only_redacted_text_and_role_and_validates_json(monkeypatch):
    text = "@crew_test meldet: Abnahme passt. Kontakt +43 660 1234567, test@example.test"
    sanitized = redact_text(text)
    batch = {"events": [{"intent": "inspection_result", "quote": sanitized, "claim": "passed", "confidence": 0.99}]}
    request = httpx.Request("POST", "https://provider.invalid/v1/chat/completions")
    response = httpx.Response(200, request=request, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(batch)}}]})
    post = Mock(return_value=response)
    monkeypatch.setattr(httpx.Client, "post", post)
    result = OpenAICompatibleExtractor("https://provider.invalid/v1", "test-model", "synthetic-key").extract(sanitized, "inspector")
    payload = post.call_args.kwargs["json"]
    assert json.loads(payload["messages"][1]["content"]) == {"text": sanitized, "sender_role": "inspector"}
    assert all(identifier not in json.dumps(payload) for identifier in ["crew_test", "660", "test@example.test"])
    assert payload["response_format"] == {"type": "json_object"}
    assert validate_quotes(result, sanitized, text)[0].quote == text


@pytest.mark.parametrize("content", [
    "not JSON", '{"events":[{"intent":"inspection_result","quote":"passed","confidence":1,"review_status":"confirmed"}]}',
    '{"events":[{"intent":"planned_work","quote":"work","confidence":2}]}',
    '{"events":[{"intent":"create_flag","quote":"work","confidence":1}]}',
])
def test_live_invalid_or_privileged_output_is_rejected(monkeypatch, content):
    response = httpx.Response(200, request=httpx.Request("POST", "https://provider.invalid"), json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]})
    monkeypatch.setattr(httpx.Client, "post", Mock(return_value=response))
    with pytest.raises(ExtractionError, match="invalid_extraction"):
        OpenAICompatibleExtractor("https://provider.invalid/v1", "test-model", "synthetic-key").extract("work", "crew_lead")


def test_provider_failure_uses_safe_error_and_configuration_is_explicit(monkeypatch):
    monkeypatch.setattr(httpx.Client, "post", Mock(side_effect=httpx.ConnectError("secret response")))
    with pytest.raises(ExtractionError, match="^provider_unavailable$"):
        OpenAICompatibleExtractor("https://provider.invalid/v1", "test-model", "synthetic-key").extract("work", "crew_lead")
    monkeypatch.setenv("LLM_PROVIDER", "cached")
    assert isinstance(get_extractor(), CachedExtractor)
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_API_KEY", "")
    with pytest.raises(ExtractionError, match="provider_not_configured"):
        get_extractor()
    monkeypatch.setenv("LLM_PROVIDER", "unsupported")
    with pytest.raises(ExtractionError, match="provider_not_configured"):
        get_extractor()


def test_redaction_keeps_dates_and_original_quote_positions_but_removes_contact_identifiers():
    text = "Am 2026-11-14 meldet @crew_test an a@example.test: +43 660 1234567, 06601234567."
    redacted = redact_text(text)
    assert len(text) == len(redacted)
    assert "2026-11-14" in redacted
    assert all(value not in redacted for value in ["crew_test", "example.test", "660", "06601234567"])
    assert "plain_sender" not in redact_text("plain_sender meldet fertig", "plain_sender")
    batch = ExtractedBatch(events=[ExtractedEvent(intent="observation", quote="invented text", confidence=1)])
    with pytest.raises(ExtractionError, match="invalid_quote"):
        validate_quotes(batch, redacted, text)


def test_zone_resolution_supports_known_aliases_and_retains_unknown_or_ambiguous_labels(seed):
    ids, unresolved = resolve_zones(["wohnung 3b", "3. OG", "Bad 3B", "9Z", "Bad"], seed.zones)
    assert ids == {"3B", "F3", "3B-BATH"}
    assert unresolved == ["9Z", "Bad"]
    assert resolve_zones(["3B"], [*seed.zones, models.Zone(id="ambiguous", kind="room", name="3B")]) == (set(), ["3B"])


def test_temporal_resolution_uses_message_local_date_and_preserves_precision(seed):
    sent_at = datetime(2026, 11, 14, 23, 30, tzinfo=UTC)  # Already day 3 in Vienna.
    start, end, precision = resolve_time(TimeReference(expression="morgen", day_offset=1), sent_at, seed.site)
    assert start == datetime(2026, 11, 15, 23, tzinfo=UTC)
    assert end == datetime(2026, 11, 16, 23, tzinfo=UTC)
    assert precision == "day"
    start, end, precision = resolve_time(TimeReference(expression="Tag 4", scenario_day=4), sent_at, seed.site)
    assert start == datetime(2026, 11, 15, 23, tzinfo=UTC)
    assert resolve_time(None, sent_at, seed.site) == (None, None, "unspecified")
    for day in ("2026-03-29", "2026-10-25"):
        reference = TimeReference(expression="02:30", calendar_date=day, local_time="02:30")
        assert resolve_time(reference, sent_at, seed.site) == (None, None, "unresolved")
    with pytest.raises(ValidationError):
        TimeReference(expression="morgen", day_offset=1, scenario_day=3)


@pytest.mark.parametrize("intent,claim,extra,zone", [
    ("inspection_result", "passed", {"inspection_kind": "rough_in"}, "F3"),
    ("inspection_result", "passed", {"inspection_kind": "rough_in"}, "3B"),
    ("task_completion", "completed", {"task_reference": "drywall-F3"}, "F3"),
    ("revision_acknowledgment", "acknowledged", {"plan_reference": "A-103", "revision_label": "C"}, "F3"),
    ("revision_acknowledgment", "acknowledged", {"plan_reference": "A-103", "revision_label": "D"}, "3B"),
])
def test_high_confidence_claims_create_only_unconfirmed_scoped_evidence(engine, seed, intent, claim, extra, zone):
    with Session(engine) as session:
        import_seed(session, seed)
        source = source_record(seed)
        session.add(source)
        session.flush()
        statement = ExtractedEvent(intent=intent, quote=source.text, confidence=1, claim=claim, zones=[zone], **extra)
        event = build_events(session, source, [statement])[0]
        session.commit()
        evidence = session.scalar(select(models.Evidence).where(models.Evidence.statement_ref == event.id))
        assert evidence.review_status == "unconfirmed"
        assert evidence.origin == "llm_statement"
        assert evidence.source_ref == f"source:{source.id}"
        assert evidence.history[0].reviewer_id is evidence.history[0].decided_at is None
        assert evidence.history[0].actor_type == "statement_ingestion"
        if intent == "inspection_result":
            assert evidence.inspection_id == ("rough-in-F3" if zone == "F3" else None)
        if extra.get("revision_label") == "D":
            assert evidence.revision_id is None
        assert session.get(models.Inspection, "rough-in-F3").status == "pending"
        baseline = session.get(models.Evidence, "baseline-rough-in-F3")
        assert baseline.review_status == "confirmed"
        assert baseline.claim == "pending"
