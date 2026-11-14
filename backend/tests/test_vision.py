"""Photo evidence from Telegram (#26): vision findings stay unconfirmed statements."""

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from app import ingestion, models, vision
from app.extraction import ExtractionError
from app.telegram import TelegramClient, TelegramSettings, poll_telegram
from app.vision import OpenAICompatibleVisionExtractor, VisionBatch
from test_gmail_polling import initialized  # noqa: F401

PHOTO = (Path(__file__).resolve().parents[1] / "demo" / "photos" / "3B-wall-closed.png").read_bytes()
HUMAN = {"actor": "synthetic-superintendent", "role": "superintendent", "channel": "dashboard"}
HEADERS = {"X-Telegram-Compliance-Key": "synthetic-worker-key"}
AFTER_INSPECTION = "2026-11-15T07:30:00Z"


@pytest.fixture
def api(initialized, monkeypatch):  # noqa: F811
    monkeypatch.setenv("VISION_PROVIDER", "cached")
    monkeypatch.delenv("VISION_CACHE_PATH", raising=False)
    monkeypatch.setenv("TELEGRAM_COMPLIANCE_KEY", "synthetic-worker-key")
    return initialized


class FakeVision:
    name = "vision_fake"

    def __init__(self, batch):
        self.batch, self.calls = batch, []

    def describe(self, image, media_type, caption, sender_role):
        self.calls.append((image, media_type, caption, sender_role))
        if isinstance(self.batch, Exception):
            raise self.batch
        return VisionBatch.model_validate(self.batch)


def use_vision(monkeypatch, batch):
    fake = FakeVision(batch)
    monkeypatch.setattr(ingestion, "get_vision_extractor", lambda: fake)
    return fake


def photo(api, caption="3B ist schon zu", *, number="p1", channel="telegram", image=PHOTO,
          sent_at=AFTER_INSPECTION, media_type="image/png"):
    return api.post("/ingestion/messages", json={
        "channel": channel, "source_key": "-100", "external_id": number, "sender_id": "123",
        "sender_role": "crew_lead", "sender_crew_id": "drywall", "sent_at": sent_at, "text": caption,
        "attachments": [{"file_name": "wall.png", "media_type": media_type,
                         "content_base64": base64.b64encode(image).decode()}],
    })


def announce(api):
    response = api.post("/ingestion/messages", json={
        "channel": "telegram", "source_key": "-100", "external_id": "t1", "sender_id": "123",
        "sender_role": "crew_lead", "sender_crew_id": "drywall", "sent_at": "2026-11-14T16:00:00Z",
        "text": "morgen früh machen wir 3B zu, platten sind da",
    })
    assert response.status_code == 201
    return response.json()


def open_flags(api):
    return [flag for flag in api.get("/flags").json() if flag["state"] not in {"resolved", "false_alarm"}]


def hero_flags(api):
    return [flag for flag in open_flags(api) if flag["type"] == "A" and flag["task_id"] == "drywall-F3"]


def test_hero_photo_yields_finding_and_attaches_to_the_hero_flag(api):
    announce(api)
    [flag] = hero_flags(api)
    response = photo(api)
    assert response.status_code == 201
    result = response.json()
    [event] = result["events"]
    attachment = result["source"]["attachments"][0]
    assert event["origin"] == "llm_vision"
    assert event["intent"] == "observation" and event["activity"] == "closing_work"
    assert event["zone_ids"] == ["3B"] and event["quote"] == "3B" and event["confidence"] == 0.93
    assert event["details"]["visual_finding"].startswith("Wall boarded")
    assert event["details"]["attachment_id"] == attachment["id"]
    assert result["source"]["extraction_backend"] == "vision_cached:v1"
    # Same conflict: the photo is attached to the existing Flag, no duplicate.
    [same] = hero_flags(api)
    assert same["id"] == flag["id"]
    detail = api.get(f"/flags/{flag['id']}").json()
    assert event["id"] in {source["id"] for source in detail["sources"]}
    assert detail["evaluation"] != "satisfied" and detail["state"] in {"detected", "notified"}
    # The stored image is the source, downloadable as an attachment.
    stored = api.get(f"/source-messages/{result['source']['id']}/attachments/{attachment['id']}")
    assert stored.content == PHOTO


def test_photo_of_closed_wall_alone_creates_the_deterministic_flag(api):
    response = photo(api)
    [event] = response.json()["events"]
    [flag] = hero_flags(api)
    assert flag["zone_id"] == "3B" and flag["evaluation"] != "satisfied"
    [warning] = api.get("/outbox", params={"flag_id": flag["id"]}).json()
    assert "Photo finding (unconfirmed LLM interpretation, confidence 0.93)" in warning["content"]
    assert event["id"] in {item["id"] for item in api.get(f"/flags/{flag['id']}").json()["sources"]}


@pytest.mark.parametrize("work_state", ["open", "unclear"])
def test_photo_without_closed_work_creates_no_flag(api, monkeypatch, work_state):
    use_vision(monkeypatch, {"findings": [{"finding": "Open wall with visible pipes.", "confidence": 0.9,
                                           "zones": ["3B"], "quote": "3B", "work_state": work_state}]})
    [event] = photo(api).json()["events"]
    assert event["activity"] is None
    assert hero_flags(api) == []


def test_high_confidence_vision_inspection_claim_cannot_satisfy_until_human_confirms(api, monkeypatch):
    announce(api)
    [flag] = hero_flags(api)
    use_vision(monkeypatch, {"findings": [{
        "finding": "Readable inspection tag: rough-in passed.", "confidence": 0.99, "zones": ["3. OG"],
        "quote": "3. OG", "inspection_kind": "rough_in", "inspection_claim": "passed"}]})
    result = photo(api, "Abnahme 3. OG Etikett").json()
    [event] = result["events"]
    [evidence] = event["evidence"]
    assert event["intent"] == "inspection_result" and event["origin"] == "llm_vision"
    assert evidence["origin"] == "llm_statement" and evidence["review_status"] == "unconfirmed"
    assert evidence["scope"]["inspection_id"] == "rough-in-F3"
    assert api.get(f"/flags/{flag['id']}").json()["evaluation"] != "satisfied"
    # Only the human Evidence review (#9) makes the photo count; it closes nothing.
    reviewed = api.post(f"/evidence/{evidence['id']}/reviews", json={
        **HUMAN, "decision": "confirmed", "expected_sequence": 1, "reason": "Checked the tag in the photo"})
    assert reviewed.status_code == 200
    # The seed's unconfirmed "failed" counterclaim still needs its own review.
    assert api.get(f"/flags/{flag['id']}").json()["evaluation"] == "contradictory"
    counter = next(item for item in api.get("/evidence").json() if item["id"] == "example-contradictory-negative")
    assert api.post("/evidence/example-contradictory-negative/reviews", json={
        **HUMAN, "decision": "rejected", "expected_sequence": counter["history"][-1]["sequence"],
        "reason": "Superseded by the photographed tag"}).status_code == 200
    after = api.get(f"/flags/{flag['id']}").json()
    assert after["evaluation"] == "satisfied"
    assert after["state"] not in {"resolved", "false_alarm"}


def test_only_redacted_caption_role_and_image_reach_the_vision_model(api, monkeypatch):
    fake = use_vision(monkeypatch, {"findings": []})
    response = photo(api, "3B zu, ruf an 0664 1234567 oder mail a@example.test")
    assert response.status_code == 201 and response.json()["events"] == []
    [(image, media_type, caption, role)] = fake.calls
    assert image == PHOTO and media_type == "image/png" and role == "crew_lead"
    assert "1234567" not in caption and "a@example.test" not in caption and "123" not in caption


def test_vision_failure_keeps_source_for_retry(api, monkeypatch):
    use_vision(monkeypatch, ExtractionError("provider_unavailable"))
    failed = photo(api)
    assert failed.status_code == 502 and failed.json()["source"]["error_code"] == "provider_unavailable"
    assert hero_flags(api) == []
    monkeypatch.setattr(ingestion, "get_vision_extractor", vision.get_vision_extractor)
    retried = photo(api)
    assert retried.status_code == 200 and retried.json()["events"][0]["origin"] == "llm_vision"


def test_quote_must_come_from_the_caption(api, monkeypatch):
    use_vision(monkeypatch, {"findings": [{"finding": "Closed wall.", "confidence": 0.9, "zones": ["3B"],
                                           "quote": "4C", "work_state": "closed"}]})
    response = photo(api)
    assert response.status_code == 502 and response.json()["source"]["error_code"] == "invalid_quote"


def test_caption_free_photo_uses_photo_placeholder_quote(api, monkeypatch):
    use_vision(monkeypatch, {"findings": [{"finding": "Closed wall.", "confidence": 0.8, "work_state": "closed"}],
                             "people_visible": True})
    [event] = photo(api, "").json()["events"]
    assert event["quote"] == "[Foto]" and event["zone_ids"] == []
    assert event["details"]["people_visible"] is True
    assert hero_flags(api) == []  # No zone: nothing is guessed from the image.


def test_images_from_other_channels_are_not_sent_to_vision(api, monkeypatch):
    fake = use_vision(monkeypatch, {"findings": []})
    photo(api, "Logo im Anhang", channel="replay")
    assert fake.calls == []


def test_retention_erases_photo_but_keeps_the_derived_record(api, engine):
    result = photo(api).json()
    with Session(engine) as session, session.begin():
        session.execute(update(models.SourceMessage).values(received_at=datetime.now(UTC) - timedelta(days=30)))
    assert api.post("/telegram/retention", headers=HEADERS).json()["raw_messages_erased"] == 1
    source = api.get(f"/source-messages/{result['source']['id']}").json()
    assert source["attachments"] == [] and source["text"] == ""
    [event] = api.get("/events").json()
    assert event["details"]["visual_finding"] and hero_flags(api)


def telegram_bot(updates, *, photos=True, image=PHOTO):
    calls = []

    def handle(request):
        calls.append(request.url.path)
        if "/file/" in request.url.path:
            return httpx.Response(200, content=image)
        method = request.url.path.rsplit("/", 1)[-1]
        result = {"getUpdates": updates, "getFile": {"file_path": "photos/file_1.jpg"}}.get(method, {"message_id": 1})
        return httpx.Response(200, json={"ok": True, "result": result})

    http = httpx.Client(transport=httpx.MockTransport(handle))
    settings = TelegramSettings("synthetic-token", {"-100", "123"}, {"123"}, "synthetic-worker-key",
                                {"123": "crew_lead"}, {"123": "drywall"}, photos=photos)
    return TelegramClient(settings, http), http, calls


def photo_update(caption="3B ist schon zu", sizes=None):
    return {"update_id": 1, "message": {
        "message_id": 7, "from": {"id": 123}, "chat": {"id": -100, "type": "supergroup"},
        "date": int(datetime(2026, 11, 15, 7, 30, tzinfo=UTC).timestamp()), "caption": caption,
        "photo": sizes or [{"file_id": "small", "width": 90, "height": 60, "file_size": 900},
                           {"file_id": "large", "width": 320, "height": 240, "file_size": len(PHOTO)}],
    }}


def test_worker_downloads_allowlisted_photo_and_ingests_it(api):
    telegram, http, calls = telegram_bot([photo_update()])
    with http:
        poll_telegram(telegram, api)
    assert "/filesynthetic-token" not in calls and any(path.endswith("/photos/file_1.jpg") for path in calls)
    [event] = api.get("/events").json()
    assert event["origin"] == "llm_vision" and event["source"]["text"] == "3B ist schon zu"
    assert event["source"]["attachments"][0]["media_type"] == "image/jpeg"
    assert hero_flags(api)


def test_worker_ignores_photos_unless_enabled(api):
    telegram, http, calls = telegram_bot([photo_update()], photos=False)
    with http:
        poll_telegram(telegram, api)
    assert api.get("/events").json() == [] and not any("getFile" in path for path in calls)


def test_oversized_photo_is_skipped_without_blocking_the_update_offset(api):
    huge = [{"file_id": "huge", "width": 4000, "height": 3000, "file_size": 5_000_000}]
    telegram, http, calls = telegram_bot([photo_update(caption="", sizes=huge)])
    with http:
        poll_telegram(telegram, api)
    assert telegram.offset == 2 and api.get("/events").json() == []


def test_openai_compatible_vision_request_carries_only_image_and_redacted_caption(monkeypatch):
    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        content = json.dumps({"findings": [{"finding": "Closed wall.", "confidence": 0.7, "work_state": "closed"}]})
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]})

    real = httpx.Client
    monkeypatch.setattr(vision.httpx, "Client", lambda **kwargs: real(transport=httpx.MockTransport(handle)))
    extractor = OpenAICompatibleVisionExtractor("https://llm.example.test/v1", "vision-model", "synthetic-key")
    batch = extractor.describe(PHOTO, "image/png", "3B zu, Tel 0664 1234567", "crew_lead")
    assert batch.findings[0].work_state == "closed"
    [request] = seen
    text, image = request["messages"][1]["content"]
    assert json.loads(text["text"]) == {"caption": "3B zu, Tel ############", "sender_role": "crew_lead"}
    assert image["image_url"]["url"] == "data:image/png;base64," + base64.b64encode(PHOTO).decode()
    assert "only set people_visible=true if people appear" in request["messages"][0]["content"]
