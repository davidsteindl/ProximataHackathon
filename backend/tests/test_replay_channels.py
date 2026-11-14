"""Real adapters with mocked providers; provider clocks and scenario clocks stay traceable."""

import base64
import json
from datetime import UTC, datetime
from email.message import EmailMessage
from types import SimpleNamespace

import httpx
import pytest

from app.gmail import GmailSettings, decode_message
from app.replay import ReplayError, Scenario
from app.replay_channels import OnlineChannels, ScenarioAPI
from app.telegram import TelegramClient, TelegramSettings
from conftest import BACKEND
from test_replay import CAD, build_replay


def scenario_step(name):
    scenario = Scenario.model_validate_json((BACKEND / "demo/hero-scenario.json").read_text(encoding="utf-8"))
    return next(step for step in scenario.steps if step.id == name)


def test_online_mail_passes_mime_adapter_and_preserves_provider_identity_and_clock(client):
    replay, _ = build_replay(client, pause=lambda _: "q")
    replay.reset()
    step = scenario_step("revision")
    settings = GmailSettings(mailbox="project@example.test", sender_roles={"architect@example.test": "architect"})
    mail = EmailMessage()
    mail["From"], mail["To"], mail["Subject"] = "architect@example.test", settings.mailbox, step.subject
    mail.set_content(step.text)
    mail.add_attachment((CAD / step.attachment).read_bytes(), maintype="image", subtype="vnd.dxf", filename=step.attachment)
    actual = datetime.now(UTC)
    source = decode_message({"id": "real-provider-id", "internalDate": str(int(actual.timestamp() * 1000)),
                             "raw": base64.urlsafe_b64encode(mail.as_bytes()).decode()}, settings)

    class Mailbox:
        def __init__(self):
            self.settings = settings

        def message_ids(self):
            yield source.external_id, "INBOX"

        def read_message(self, identifier, label):
            return source

    channels = OnlineChannels(client, Mailbox(), None, "online-test", CAD, lambda *args, **kwargs: None,
                              timeout=1, output=lambda _: None)
    result = channels.receive(step, replay.clock.timestamp(step))
    assert result["source"]["channel"] == "gmail"
    assert result["source"]["external_id"] == "real-provider-id"
    assert result["source"]["source_key"] == settings.mailbox
    assert result["source"]["sent_at"] == "2026-11-13T09:15:00Z"
    assert result["events"][0]["details"]["diff_status"] == "succeeded"
    provenance = next(item for item in result["source"]["attachments"] if item["file_name"] == "replay-transport.json")
    audit = client.get(f"/source-messages/{result['source']['id']}/attachments/{provenance['id']}").json()
    assert datetime.fromisoformat(audit["transport_sent_at"]).date() == actual.date()
    assert audit["scenario_sent_at"] == "2026-11-13T10:15:00+01:00"
    assert audit["step"] == step.id


def test_online_telegram_uses_human_allowlist_and_distinct_provider_message_ids(client):
    replay, _ = build_replay(client, pause=lambda _: "q")
    replay.reset()
    before, after = scenario_step("learning_before"), scenario_step("learning_after")
    settings = TelegramSettings(token="synthetic-token", chats={"100"}, users={"100"},
        compliance_key="synthetic-key", roles={"100": "crew_lead"}, crews={"100": "drywall"})
    batch = [
        {"update_id": 1, "message": {"message_id": 1, "date": int(datetime.now(UTC).timestamp()),
            "from": {"id": 100, "is_bot": True}, "chat": {"id": 100}, "text": before.text}},
        {"update_id": 2, "message": {"message_id": 2, "date": int(datetime.now(UTC).timestamp()),
            "from": {"id": 999, "is_bot": False}, "chat": {"id": 100}, "text": before.text}},
        {"update_id": 3, "message": {"message_id": 3, "date": int(datetime.now(UTC).timestamp()),
            "from": {"id": 100, "is_bot": False}, "chat": {"id": 100}, "text": before.text}},
    ]

    def provider(request):
        assert request.url.path.endswith("/getUpdates")
        return httpx.Response(200, json={"ok": True, "result": batch})

    with httpx.Client(transport=httpx.MockTransport(provider)) as http:
        telegram = TelegramClient(settings, http)
        channels = OnlineChannels(client, None, telegram, "telegram-test", CAD, lambda *args, **kwargs: None,
                                  timeout=1, output=lambda _: None)
        original = channels.receive(before, replay.clock.timestamp(before))
        assert original["source"]["channel"] == "telegram"
        assert original["source"]["external_id"] == "3" and original["source"]["sender_id"] == "100"
        assert original["source"]["sender_crew_id"] == "drywall"
        assert telegram.offset == 4
        assert not original["duplicate"]
        # Even identical text must arrive as a new real provider message.
        batch[:] = [{"update_id": 4, "message": {"message_id": 4, "date": int(datetime.now(UTC).timestamp()),
            "from": {"id": 100, "is_bot": False}, "chat": {"id": 100}, "text": after.text}}]
        repeated = channels.receive(after, replay.clock.timestamp(after))
        assert repeated["source"]["id"] != original["source"]["id"]
        assert repeated["source"]["external_id"] == "4" and not repeated["duplicate"]


def test_wrong_cad_attachment_cannot_be_imported_by_online_replay(client):
    step = scenario_step("revision")
    proxy = ScenarioAPI(client, step, datetime.now(UTC), "attachment-test", CAD)
    with pytest.raises(ReplayError, match="exact synthetic attachment"):
        proxy.post("/ingestion/messages", json={"channel": "gmail", "source_key": "project@example.test",
            "external_id": "wrong", "sender_role": "architect", "sent_at": datetime.now(UTC).isoformat(),
            "text": step.source_text, "attachments": []})
    with pytest.raises(ReplayError, match="only ingest"):
        proxy.post("/evidence/example/reviews", json={})


def test_online_timeout_cannot_be_unbounded():
    for value in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ReplayError, match="timeout"):
            OnlineChannels(None, None, None, "invalid", CAD, lambda *args, **kwargs: None, timeout=value)



def test_real_delivery_uses_existing_worker_outbox_and_telegram_allowlists(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CREW_LEADS_JSON", json.dumps({
        "lead-plumbing": "100", "lead-insulation": "101", "lead-drywall": "102",
    }))
    replay, _ = build_replay(client, pause=lambda _: "q")
    replay.reset()
    step = scenario_step("revision")
    replay.channels.receive(step, replay.clock.timestamp(step))
    sent, transcript = [], []

    def provider(request):
        assert request.url.path.endswith("/sendMessage")
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(sent)}})

    settings = TelegramSettings(token="synthetic-token", chats={"100", "101", "102"},
        users={"100", "101", "102"}, compliance_key="synthetic-key", roles={}, crews={})
    with httpx.Client(transport=httpx.MockTransport(provider)) as http:
        telegram = TelegramClient(settings, http)
        channels = OnlineChannels(client, SimpleNamespace(), telegram, "delivery-test", CAD,
                                  lambda kind, **record: transcript.append({"kind": kind, **record}))
        channels.deliver()
    outbox = client.get("/outbox").json()
    assert sent and len(sent) == len(outbox)
    assert all(item["status"] == "sent" and item["channel"] == "telegram" for item in outbox)
    assert all(item["kind"] == "real_delivery" for item in transcript)
    assert all(flag["state"] == "notified" for flag in client.get("/flags").json())


def test_missing_real_recipient_is_not_reported_as_a_successful_delivery(client):
    replay, _ = build_replay(client, pause=lambda _: "q")
    replay.reset()
    step = scenario_step("closing")
    replay.channels.receive(step, replay.clock.timestamp(step))
    channels = OnlineChannels(client, SimpleNamespace(), SimpleNamespace(), "failure", CAD, lambda *args, **kwargs: None)
    with pytest.raises(ReplayError, match="delivery is pending or failed"):
        channels.deliver()
    assert all(item["status"] == "failed" and not item["provider_message_id"] for item in client.get("/outbox").json())
    assert all(flag["state"] == "detected" for flag in client.get("/flags").json())
