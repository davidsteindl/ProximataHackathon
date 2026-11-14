import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.telegram import (
    TelegramClient, TelegramError, TelegramSettings, deliver_telegram_outbox, poll_telegram,
)
from test_gmail_polling import initialized


HEADERS = {"X-Telegram-Compliance-Key": "synthetic-worker-key"}


@pytest.fixture
def telegram_api(initialized, monkeypatch):
    monkeypatch.setenv("TELEGRAM_COMPLIANCE_KEY", "synthetic-worker-key")
    monkeypatch.setenv("TELEGRAM_RETENTION_DAYS", "7")
    monkeypatch.setenv("TELEGRAM_CREW_LEADS_JSON", '{"lead-drywall":"123"}')
    return initialized


def message(text="morgen früh machen wir 3B zu, platten sind da", *, sender=123, chat=-100, number=1):
    return {"update_id": number, "message": {
        "message_id": number, "from": {"id": sender, "username": "never_store_me"},
        "chat": {"id": chat, "type": "private" if chat == sender else "supergroup"},
        "date": int(datetime.now(UTC).timestamp()), "text": text,
    }}


def bot(updates, *, failure=False):
    calls = []

    def handle(request):
        method = request.url.path.rsplit("/", 1)[-1]
        payload = json.loads(request.content)
        calls.append((method, payload))
        if failure:
            return httpx.Response(429, json={"ok": False, "description": "sensitive provider response"})
        result = updates if method == "getUpdates" else {"message_id": 456}
        return httpx.Response(200, json={"ok": True, "result": result})

    http = httpx.Client(transport=httpx.MockTransport(handle))
    settings = TelegramSettings("synthetic-token", {"-100", "123"}, {"123"},
                                "synthetic-worker-key", {"123": "crew_lead"}, {"123": "drywall"})
    return TelegramClient(settings, http), http, calls


def command(api, name, number="1", **changes):
    return api.post("/telegram/commands", headers=HEADERS, json={
        "request_id": number, "sender_id": "123", "chat_id": "123", "command": name, **changes,
    })


@pytest.mark.parametrize("sender,chat", [(999, -100), (123, -999), (999, -999)])
def test_non_allowlisted_messages_and_commands_are_not_processed(telegram_api, sender, chat):
    telegram, http, calls = bot([message(sender=sender, chat=chat),
                                message("/my_data", sender=sender, chat=chat, number=2)])
    with http:
        poll_telegram(telegram, telegram_api)
    assert telegram.offset == 3
    assert telegram_api.get("/events").json() == []
    assert telegram_api.get("/outbox").json() == []
    assert telegram_api.get("/source-messages", params={
        "channel": "telegram", "source_key": str(chat), "external_id": "1",
    }).json() is None
    assert [name for name, _ in calls] == ["getUpdates"]


def test_hero_ingestion_warning_and_retry_are_source_backed(telegram_api):
    telegram, http, calls = bot([message()])
    with http:
        poll_telegram(telegram, telegram_api)
        poll_telegram(telegram, telegram_api)
        events = telegram_api.get("/events").json()
        assert len(events) == 1
        event = events[0]
        assert event["intent"] == "planned_work"
        assert event["source"]["sender_id"] == "123"
        assert "never_store_me" not in json.dumps(event)
        assert event["source"]["source_key"] == "-100"
        assert all(evidence["review_status"] == "unconfirmed" for evidence in event["evidence"])
        deliver_telegram_outbox(telegram, telegram_api)
    warning = telegram_api.get("/outbox").json()[0]
    assert warning["status"] == "sent" and warning["provider_message_id"] == "456"
    assert telegram_api.get("/flags").json()[0]["state"] == "notified"
    sends = [payload for name, payload in calls if name == "sendMessage"]
    assert len(sends) == 1 and sends[0]["chat_id"] == "123"
    assert "unconfirmed statement" in sends[0]["text"]


@pytest.mark.parametrize("text,intent", [("Warnung gesehen", "observation"),
    ("Abnahme dürfte passen", "inspection_result"), ("welcher plan gilt für 3B?", "question")])
def test_other_hero_messages_remain_advisory(telegram_api, monkeypatch, text, intent):
    from app import qa
    from test_qa import routing
    monkeypatch.setattr(qa, "ask", AsyncMock(return_value=qa.Answer(
        kind="answer", text="Synthetic record answer [revision:A-103-C]", routing=routing("revision_in_force", "3B"))))
    telegram, http, _ = bot([message(text)])
    with http:
        poll_telegram(telegram, telegram_api)
    event = telegram_api.get("/events").json()[0]
    assert event["intent"] == intent
    assert all(item["review_status"] == "unconfirmed" for item in event["evidence"])
    assert telegram_api.get("/flags").json() == []


def test_join_notice_is_outboxed_deduplicated_and_transparent(telegram_api):
    update = {"update_id": 7, "my_chat_member": {
        "chat": {"id": -100}, "from": {"id": 123},
        "old_chat_member": {"status": "left"}, "new_chat_member": {"status": "member"},
    }}
    telegram, http, calls = bot([update])
    with http:
        poll_telegram(telegram, telegram_api)
        poll_telegram(telegram, telegram_api)
        rows = telegram_api.get("/outbox").json()
        assert len(rows) == 1 and rows[0]["flag_id"] is None
        assert "7 Tage" in rows[0]["content"] and "Verantwortlich" in rows[0]["content"]
        assert "keine Personenkennzahlen" in rows[0]["content"]
        assert [name for name, _ in calls] == ["getUpdates", "getUpdates"]
        deliver_telegram_outbox(telegram, telegram_api)
    assert calls[-1][1]["chat_id"] == "-100"
    assert telegram_api.get("/outbox").json()[0]["content"] == "[delivered compliance reply]"


def test_access_is_private_and_deletion_preserves_derived_evidence(telegram_api, engine):
    telegram, http, _ = bot([message()])
    with http:
        poll_telegram(telegram, telegram_api)
    before = telegram_api.get("/events").json()[0]
    assert command(telegram_api, "my_data", chat_id="-100").status_code == 422
    assert command(telegram_api, "my_data").status_code == 200
    export = [row for row in telegram_api.get("/outbox").json() if row["flag_id"] is None]
    assert before["quote"] in "".join(row["content"] for row in export)
    assert command(telegram_api, "delete_my_data", "2").status_code == 200
    after = telegram_api.get("/events").json()[0]
    assert after["source"]["text"] == ""
    assert after["quote"] == before["quote"] and after["evidence"] == before["evidence"]
    assert telegram_api.get("/flags").json()[0]["state"] == "detected"
    with Session(engine) as session:
        assert all(session.get(models.OutboxMessage, row["id"]).content == "[deleted compliance reply]"
                   for row in export)
    assert command(telegram_api, "my_data", "3").status_code == 200
    exported = [row["content"] for row in telegram_api.get("/outbox").json()
                if row["flag_id"] is None and row["status"] == "pending"]
    assert before["id"] in "".join(exported)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
        "ok": True, "result": [message()],
    }))) as provider:
        telegram.http = provider
        poll_telegram(telegram, telegram_api)
    assert telegram_api.get("/events").json()[0]["source"]["text"] == ""


def test_retention_removes_only_expired_telegram_raw_and_export_copies(telegram_api, engine):
    telegram, http, _ = bot([message()])
    with http:
        poll_telegram(telegram, telegram_api)
    command(telegram_api, "my_data")
    with Session(engine) as session, session.begin():
        source = session.scalar(select(models.SourceMessage))
        source.received_at = datetime.now(UTC) - timedelta(days=8)
        source_id = source.id
    response = telegram_api.post("/telegram/retention", headers=HEADERS)
    assert response.json() == {"raw_messages_erased": 1}
    assert telegram_api.get(f"/source-messages/{source_id}").json()["text"] == ""
    assert telegram_api.get("/events").json()[0]["quote"] != ""
    assert all(row["content"] == "[expired compliance reply]" for row in
               telegram_api.get("/outbox").json() if row["flag_id"] is None)
    assert telegram_api.post("/telegram/retention", headers=HEADERS).json() == {"raw_messages_erased": 0}


def test_worker_credential_is_required(telegram_api):
    assert telegram_api.post("/telegram/retention").status_code == 403
    assert telegram_api.post("/telegram/commands", json={}).status_code == 403


def test_group_privacy_command_never_exports_data(telegram_api):
    telegram, http, _ = bot([message("/my_data")])
    with http:
        poll_telegram(telegram, telegram_api)
    rows = telegram_api.get("/outbox").json()
    assert len(rows) == 1 and "Privater Bot-Chat" in rows[0]["content"]
    assert telegram_api.get("/events").json() == []


def test_ingestion_failure_retries_same_update_without_acknowledgment(telegram_api):
    telegram, http, _ = bot([message()])
    api = Mock(wraps=telegram_api)
    api.get.side_effect = httpx.ConnectError("sensitive")
    with http:
        with pytest.raises(TelegramError):
            poll_telegram(telegram, api)
        assert telegram.offset == 1
        poll_telegram(telegram, telegram_api)
    assert telegram.offset == 2
    assert len(telegram_api.get("/events").json()) == 1


def test_provider_failure_is_safe_and_warning_stays_retryable(telegram_api):
    telegram, http, _ = bot([message()])
    with http:
        poll_telegram(telegram, telegram_api)
    failed, provider, _ = bot([], failure=True)
    with provider:
        deliver_telegram_outbox(failed, telegram_api)
        with pytest.raises(TelegramError) as error:
            failed.updates()
    assert "synthetic-token" not in str(error.value) and "sensitive" not in str(error.value)
    row = telegram_api.get("/outbox").json()[0]
    assert row["status"] == "failed" and row["error_code"] == "telegram_error"
    assert telegram_api.get("/flags").json()[0]["state"] == "detected"


def test_warning_recipient_must_be_allowlisted_user_and_chat():
    telegram, http, calls = bot([])
    with http:
        for recipient in ("999", "-100"):
            with pytest.raises(TelegramError):
                telegram.send_warning({"recipient": recipient, "content": "warning"})
    assert calls == []


def test_settings_validate_roles_and_require_credentials(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "synthetic-token")
    monkeypatch.setenv("TELEGRAM_COMPLIANCE_KEY", "synthetic-worker-key")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHATS_JSON", '["-100","123"]')
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS_JSON", '["123"]')
    assert TelegramSettings.from_env().users == {"123"}
    monkeypatch.setenv("TELEGRAM_SENDER_ROLES_JSON", '{"123":"admin"}')
    with pytest.raises(ValueError):
        TelegramSettings.from_env()
    monkeypatch.setenv("TELEGRAM_SENDER_ROLES_JSON", '{}')
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    with pytest.raises(ValueError):
        TelegramSettings.from_env()


def test_failed_extraction_does_not_block_privacy_commands(telegram_api):
    updates = [message("no offline extraction fixture for this synthetic text"),
               message("/delete_my_data", chat=123, number=2)]
    telegram, http, _ = bot(updates)
    with http:
        with pytest.raises(TelegramError):
            poll_telegram(telegram, telegram_api)
        source = telegram_api.get("/source-messages", params={
            "channel": "telegram", "source_key": "-100", "external_id": "1",
        }).json()
        assert source["text"] == "" and source["status"] == "processed"
        poll_telegram(telegram, telegram_api)
    assert telegram.offset == 3
    assert len(telegram_api.get("/outbox").json()) == 1


def test_large_unicode_warning_is_numbered_and_within_provider_limit():
    telegram, http, calls = bot([])
    with http:
        provider_id = telegram.send_warning({"recipient": "123", "content": "🚧" * 5000})
    assert provider_id == "456"
    assert len(calls) == 3
    assert all(len(payload["text"].encode("utf-16-le")) // 2 <= 4096 for _, payload in calls)
    assert calls[0][1]["text"].startswith("Teil 1/3")


def test_retention_cancels_export_lease_instead_of_claiming_delivery(telegram_api, engine):
    command(telegram_api, "my_data")
    claimed = telegram_api.post("/outbox/claim", params={"channel": "telegram"}).json()
    with Session(engine) as session, session.begin():
        session.get(models.OutboxMessage, claimed["id"]).created_at = datetime.now(UTC) - timedelta(days=8)
    telegram_api.post("/telegram/retention", headers=HEADERS).raise_for_status()
    result = telegram_api.post(f"/outbox/{claimed['id']}/result", json={
        "lease_token": claimed["lease_token"], "status": "sent", "provider_message_id": "late-send",
    })
    assert result.status_code == 409
    row = telegram_api.get("/outbox").json()[0]
    assert row["status"] == "cancelled" and row["sent_at"] is None
    assert telegram_api.post("/outbox/claim", params={"channel": "telegram"}).json() is None


def test_access_does_not_export_another_senders_data(telegram_api, engine):
    telegram, http, _ = bot([message()])
    with http:
        poll_telegram(telegram, telegram_api)
    with Session(engine) as session, session.begin():
        session.scalar(select(models.SourceMessage)).sender_id = "999"
    command(telegram_api, "my_data")
    reply = next(row for row in telegram_api.get("/outbox").json() if row["flag_id"] is None)
    assert reply["content"].endswith("[]")
    command(telegram_api, "delete_my_data", "2")
    assert telegram_api.get("/events").json()[0]["source"]["text"] != ""


def test_retention_uses_configured_days_and_removes_attachments(telegram_api, engine, monkeypatch):
    telegram, http, _ = bot([message()])
    with http:
        poll_telegram(telegram, telegram_api)
    with Session(engine) as session, session.begin():
        source = session.scalar(select(models.SourceMessage))
        source.text = ""
        source.received_at = datetime.now(UTC) - timedelta(days=3)
        session.add(models.SourceAttachment(id="raw-attachment", source_message_id=source.id,
                    file_name="synthetic.txt", media_type="text/plain", sha256="0" * 64, content=b"synthetic"))
    assert telegram_api.post("/telegram/retention", headers=HEADERS).json()["raw_messages_erased"] == 0
    monkeypatch.setenv("TELEGRAM_RETENTION_DAYS", "2")
    assert telegram_api.post("/telegram/retention", headers=HEADERS).json()["raw_messages_erased"] == 1
    with Session(engine) as session:
        assert session.get(models.SourceAttachment, "raw-attachment") is None


def test_only_redacted_text_and_role_reach_extractor(telegram_api, monkeypatch):
    from app import ingestion
    from app.extraction import ExtractedBatch

    extractor = Mock()
    extractor.name = "mock"
    extractor.extract.return_value = ExtractedBatch(events=[])
    monkeypatch.setattr(ingestion, "get_extractor", lambda: extractor)
    telegram, http, _ = bot([message("Kontakt @synthetic_user test@example.test +43 660 1234567")])
    with http:
        poll_telegram(telegram, telegram_api)
    args = extractor.extract.call_args.args
    assert len(args) == 2 and args[1] == "crew_lead"
    assert all(value not in args[0] for value in ("synthetic_user", "test@example.test", "+43 660 1234567"))
    assert extractor.extract.call_args.kwargs == {}


def test_worker_runs_delivery_even_after_poll_failure(monkeypatch):
    from app import worker

    telegram, http, _ = bot([])
    monkeypatch.setenv("API_BASE_URL", "http://api.test")
    monkeypatch.setenv("GMAIL_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_ENABLED", "true")
    monkeypatch.setattr(worker.TelegramSettings, "from_env", lambda: telegram.settings)
    monkeypatch.setattr(worker, "check_api", Mock())
    monkeypatch.setattr(worker, "poll_telegram", Mock(side_effect=TelegramError("synthetic")))
    delivery = Mock()
    monkeypatch.setattr(worker, "deliver_telegram_outbox", delivery)
    monkeypatch.setattr(worker.time, "sleep", Mock(side_effect=StopIteration))
    with http, pytest.raises(StopIteration):
        worker.main()
    delivery.assert_called_once()
    worker.time.sleep.assert_called_once_with(2)


def test_worker_keeps_retention_running_with_bot_disabled(monkeypatch):
    from app import worker

    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"raw_messages_erased": 0})

    factory = httpx.Client
    monkeypatch.setattr(worker.httpx, "Client", lambda *args, **kwargs: factory(
        *args, **kwargs, transport=httpx.MockTransport(handle)))
    monkeypatch.setenv("API_BASE_URL", "http://api.test")
    monkeypatch.setenv("GMAIL_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_COMPLIANCE_KEY", "synthetic-worker-key")
    monkeypatch.setattr(worker, "check_api", Mock())
    monkeypatch.setattr(worker.time, "sleep", Mock(side_effect=StopIteration))
    with pytest.raises(StopIteration):
        worker.main()
    # Scheduled jobs (#14) also call the API; exactly one retention call is made.
    retention = [call for call in calls if call.url.path == "/telegram/retention"]
    assert len(retention) == 1
    assert retention[0].headers["X-Telegram-Compliance-Key"] == "synthetic-worker-key"


def test_seed_reset_replays_sources_without_confirming_evidence(telegram_api, seed):
    telegram, http, _ = bot([message("Abnahme dürfte passen")])
    with http:
        poll_telegram(telegram, telegram_api)
        original = telegram_api.get("/events").json()[0]
        assert original["evidence"][0]["review_status"] == "unconfirmed"
        command(telegram_api, "my_data")
        assert telegram_api.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
        assert telegram_api.get("/outbox").json() == []
        poll_telegram(telegram, telegram_api)
    replay = telegram_api.get("/events").json()[0]
    assert replay["id"] != original["id"]
    assert replay["evidence"][0]["review_status"] == "unconfirmed"


def test_lost_command_response_does_not_duplicate_private_exports(telegram_api):
    telegram, http, _ = bot([message("/my_data", chat=123)])
    api = Mock(wraps=telegram_api)

    def post(path, **kwargs):
        response = telegram_api.post(path, **kwargs)
        if path == "/telegram/commands":
            raise httpx.ReadTimeout("synthetic lost response")
        return response

    api.post.side_effect = post
    with http:
        with pytest.raises(TelegramError):
            poll_telegram(telegram, api)
        poll_telegram(telegram, telegram_api)
    assert len(telegram_api.get("/outbox").json()) == 1


def test_revoked_private_user_never_receives_pending_export(telegram_api):
    command(telegram_api, "my_data")
    telegram, http, calls = bot([])
    telegram.settings.users.clear()
    with http:
        deliver_telegram_outbox(telegram, telegram_api)
    assert calls == []
    assert telegram_api.get("/outbox").json()[0]["status"] == "failed"
