from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from app import ingestion
from app.extraction import ExtractionError
from app.gmail import GmailClient, GmailSettings
from app.gmail_polling import poll_gmail
from test_gmail import MAILBOX, credentials, gmail_message

ROOT = Path(__file__).resolve().parents[2]
HEROES = [
    ("Plan A-103 Rev D", "Plan A-103 Rev D: Badwand 3B um 30 cm verschoben, Abwasserleitung neu geführt.",
     "architect@example.test", "architect"),
    ("Abnahme verschoben", "Abnahme der Rohinstallation im 3. OG auf Tag 4 verschoben.",
     "inspector@example.test", "inspector"),
    ("Abnahme Rohinstallation", "Abnahme der Rohinstallation im 3. OG bestanden.",
     "inspector@example.test", "inspector"),
]


@pytest.fixture
def initialized(client, seed, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "cached")
    monkeypatch.delenv("LLM_CACHE_PATH", raising=False)
    assert client.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
    return client


def make_gmail(message):
    settings = GmailSettings(MAILBOX, sender_roles={"architect@example.test": "architect"})
    calls = []

    def handle(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress": MAILBOX})
        if request.url.path.endswith("/labels"):
            return httpx.Response(200, json={"labels": [{"id": "INBOX", "name": "INBOX"}]})
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": message["id"]}]})
        return httpx.Response(200, json=message)

    http = httpx.Client(transport=httpx.MockTransport(handle))
    return GmailClient(settings, http, credentials()), http, calls


def identity(client, message_id="gmail-1", **changes):
    return client.get("/source-messages", params={
        "channel": "gmail", "source_key": MAILBOX, "external_id": message_id, **changes,
    })


@pytest.mark.parametrize("subject,body,sender,role", HEROES)
def test_hero_mail_to_timeline_and_byte_exact_dxf(initialized, subject, body, sender, role):
    dxf = (ROOT / "cad/plans/A-103_RevD.dxf").read_bytes()
    message = gmail_message(subject, body, attachments=[("A-103_RevD.dxf", dxf)], sender=sender)
    gmail, http, calls = make_gmail(message)
    gmail.settings = GmailSettings(MAILBOX, sender_roles={sender: role})
    with http:
        assert identity(initialized).json() is None
        assert poll_gmail(gmail, initialized) == 1
        source = identity(initialized).json()
        assert source["status"] == "processed"
        assert source["text"] == f"Subject: {subject}\n\n{body}"
        attachment = source["attachments"][0]
        url = f"/source-messages/{source['id']}/attachments/{attachment['id']}"
        assert initialized.get(url).content == dxf
        timeline = initialized.get("/events").json()
        assert len(timeline) == 1
        assert timeline[0]["source"]["id"] == source["id"]
        assert timeline[0]["quote"] == body
        assert all(evidence["review_status"] == "unconfirmed" for evidence in timeline[0]["evidence"])
        # New client instance represents a restarted worker; no local cursor is needed.
        restarted = GmailClient(gmail.settings, http, credentials())
        assert poll_gmail(restarted, initialized) == 0
        assert len(initialized.get("/events").json()) == 1
        assert sum(path.endswith("/messages/gmail-1") for path in calls) == 1
        assert identity(initialized, channel="telegram").json() is None
        assert identity(initialized, source_key="another@example.test").json() is None
        assert initialized.get("/source-messages").status_code == 422


def test_extraction_failure_is_retried_and_seed_reset_allows_replay(initialized, seed, monkeypatch):
    subject, body, _, _ = HEROES[0]
    gmail, http, _ = make_gmail(gmail_message(subject, body))
    original = ingestion.get_extractor
    failing = Mock()
    failing.name = "mock"
    failing.extract.side_effect = ExtractionError("provider_unavailable")
    monkeypatch.setattr(ingestion, "get_extractor", lambda: failing)
    with http:
        assert poll_gmail(gmail, initialized) == 0
        first = identity(initialized).json()
        assert first["status"] == "failed"
        assert initialized.get("/events").json() == []
        monkeypatch.setattr(ingestion, "get_extractor", original)
        assert poll_gmail(gmail, initialized) == 1
        assert identity(initialized).json()["id"] == first["id"]
        assert poll_gmail(gmail, initialized) == 0
        assert initialized.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
        assert identity(initialized).json() is None
        assert poll_gmail(gmail, initialized) == 1
        assert len(initialized.get("/events").json()) == 1


def test_lost_ingestion_response_can_be_retried_without_duplicate_events(initialized):
    subject, body, _, _ = HEROES[0]
    gmail, http, calls = make_gmail(gmail_message(subject, body))

    class LostResponse:
        get = initialized.get

        def post(self, *args, **kwargs):
            initialized.post(*args, **kwargs)
            raise httpx.ReadTimeout("simulated lost response")

    with http:
        assert poll_gmail(gmail, LostResponse()) == 0
        assert poll_gmail(gmail, initialized) == 0
        assert len(initialized.get("/events").json()) == 1
        assert sum(path.endswith("/messages/gmail-1") for path in calls) == 1


def test_invalid_mail_and_api_outage_do_not_block_other_mail(caplog):
    gmail = Mock()
    gmail.settings.mailbox = MAILBOX
    gmail.message_ids.return_value = [("bad", "INBOX"), ("good", "INBOX")]
    source = Mock()
    source.model_dump.return_value = {"test": "source"}
    gmail.read_message.side_effect = [ValueError("private message content"), source]
    api = Mock()
    api.get.return_value.json.return_value = None
    api.post.return_value.json.return_value = {"source": {"status": "processed"}}
    assert poll_gmail(gmail, api) == 1
    assert "private message content" not in caplog.text
    assert api.post.call_count == 1
    gmail.message_ids.return_value = [("retry", "INBOX")]
    api.get.side_effect = httpx.ConnectError("private response")
    assert poll_gmail(gmail, api) == 0
    assert "private response" not in caplog.text


def test_processed_irrelevant_mail_is_skipped(initialized):
    # Empty subject keeps the existing synthetic irrelevant-message fixture unchanged.
    message = gmail_message("", "Danke, bis später!")
    gmail, http, calls = make_gmail(message)
    gmail.settings = GmailSettings(MAILBOX, sender_roles={"architect@example.test": "crew_lead"})
    with http:
        assert poll_gmail(gmail, initialized) == 1
        assert poll_gmail(gmail, initialized) == 0
        assert initialized.get("/events").json() == []
        assert sum(path.endswith("/messages/gmail-1") for path in calls) == 1


@pytest.mark.parametrize("enabled,interval", [("false", 30), ("true", 2)])
def test_worker_enable_switch_and_configurable_interval(monkeypatch, enabled, interval):
    from app import worker

    monkeypatch.setenv("API_BASE_URL", "http://api:8000")
    monkeypatch.setenv("GMAIL_ENABLED", enabled)
    monkeypatch.setenv("GMAIL_MAILBOX", MAILBOX)
    monkeypatch.setenv("GMAIL_POLL_SECONDS", "2")
    monkeypatch.setenv("GMAIL_SENDER_ROLES_JSON", "")
    health, poll, gmail_factory = Mock(), Mock(), Mock()
    monkeypatch.setattr(worker, "check_api", health)
    monkeypatch.setattr(worker, "poll_gmail", poll)
    monkeypatch.setattr(worker, "GmailClient", gmail_factory)
    pause = Mock(side_effect=StopIteration)
    monkeypatch.setattr(worker.time, "sleep", pause)
    with pytest.raises(StopIteration):
        worker.main()
    pause.assert_called_once_with(interval)
    assert health.call_count == (enabled == "false")
    assert poll.call_count == gmail_factory.call_count == (enabled == "true")
