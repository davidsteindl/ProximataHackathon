"""Telegram -> ingestion -> Q&A -> real MCP/API -> outbox -> mocked transports."""

import json
from contextlib import asynccontextmanager
from unittest.mock import Mock

import anyio
import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app import mcp_server, qa
from app.outbox_delivery import deliver_outbox
from app.telegram import TelegramError, deliver_telegram_outbox, is_question, poll_telegram
from conftest import BACKEND
from test_lifecycle import decision
from test_qa import FixedRouter, REVISION_QUESTION, STATUS_QUESTION, routing
from test_rules import ingest
from test_telegram import HEADERS, bot, initialized, message, telegram_api


@pytest.fixture
def qa_stack(telegram_api, monkeypatch):
    monkeypatch.setenv("QA_ROUTER_PROVIDER", "cached")
    monkeypatch.setenv("SUPERINTENDENT_EMAIL", "superintendent@example.test")
    monkeypatch.setenv("DASHBOARD_BASE_URL", "https://demo.example.test")
    original_client = httpx.AsyncClient
    calls = []

    async def api_transport(request):
        calls.append(request)
        response = await anyio.to_thread.run_sync(lambda: telegram_api.request(
            request.method, str(request.url), headers=dict(request.headers), content=request.content))
        return httpx.Response(response.status_code, headers=response.headers, content=response.content)

    def factory(**kwargs):
        if kwargs.get("base_url") == "http://api:8000":
            kwargs["transport"] = httpx.MockTransport(api_transport)
        return original_client(**kwargs)

    monkeypatch.setenv("API_BASE_URL", "http://api:8000")
    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", factory)

    @asynccontextmanager
    async def tools():
        server = mcp_server.create_server()
        app = server.streamable_http_app()
        async with server.session_manager.run():
            async with original_client(transport=httpx.ASGITransport(app=app)) as http:
                async with streamable_http_client("http://mcp/mcp", http_client=http) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        yield qa.tool_caller(session)

    monkeypatch.setattr(qa, "mcp_tools", tools)
    async def no_external(*args, **kwargs):
        raise AssertionError("Unmocked external provider traffic")
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_external)
    return telegram_api, calls


def revision(api):
    return ingest(api, **json.loads((BACKEND / "demo" / "revision-note.json").read_text(encoding="utf-8")))


def replies(api):
    return [row for row in api.get("/outbox").json() if row["kind"] == "qa_reply"]


def test_hero_revision_question_replies_with_rev_d_and_real_source_via_mcp(qa_stack):
    api, record_calls = qa_stack
    note = revision(api)
    telegram, http, calls = bot([message(REVISION_QUESTION)])
    with http:
        poll_telegram(telegram, api)
        poll_telegram(telegram, api)
        assert len(replies(api)) == 1
        reply = replies(api)[0]
        assert "Rev D is the latest recorded revision" in reply["content"]
        assert f"source:{note['source']['id']}" in reply["content"] and "(day 1)" in reply["content"]
        assert all(call.method == "GET" and call.headers["X-SiteMind-Client"] == "mcp" for call in record_calls)
        # Existing factual warnings keep their queue position; drain them before the answer.
        for _ in range(sum(row["channel"] == "telegram" for row in api.get("/outbox").json())):
            deliver_telegram_outbox(telegram, api)
    sent = [payload for name, payload in calls if name == "sendMessage" and payload["chat_id"] == "-100"]
    assert len(sent) == 1
    assert "Rev D" in sent[0]["text"]
    assert replies(api)[0]["content"] == "[delivered qa_reply]"


def test_superintendent_room_reply_keeps_status_sources_and_room_link_last(qa_stack):
    api, _ = qa_stack
    revision(api)
    ingest(api)
    telegram, http, _ = bot([message(STATUS_QUESTION, chat=123)])
    telegram.settings.roles["123"] = "superintendent"
    with http:
        poll_telegram(telegram, api)
    content = replies(api)[0]["content"]
    assert "Status of" in content and "3B-BATH" in content
    assert "Rev D" in content and "Recorded receipt evidence" in content
    assert "UNCONFIRMED claim" in content and "Open Flag A" in content and "Task " in content
    assert "Latest:" in content and "[source:" in content
    assert content.endswith("Room view: https://demo.example.test/zones/3B-BATH")


def test_room_reply_labels_confirmed_conflicting_evidence(qa_stack):
    api, _ = qa_stack
    assert decision(api, "example-contradictory-positive", "confirmed").status_code == 200
    assert decision(api, "example-contradictory-negative", "confirmed").status_code == 200
    ingest(api)
    telegram, http, _ = bot([message(STATUS_QUESTION)])
    telegram.settings.roles["123"] = "superintendent"
    with http:
        poll_telegram(telegram, api)
    text = replies(api)[0]["content"]
    assert "'passed' confirmed" in text and "'failed' confirmed" in text
    assert "CONTRADICTORY (unresolved)" in text


def test_decision_question_is_forwarded_once_without_an_answer_or_approval(qa_stack):
    api, _ = qa_stack
    telegram, http, calls = bot([message("d\u00fcrfen wir morgen in 3B zumachen?")])
    with http:
        poll_telegram(telegram, api)
        poll_telegram(telegram, api)
        deliver_telegram_outbox(telegram, api)
    forwards = [row for row in api.get("/outbox").json() if row["kind"] == "decision_request"]
    assert len(forwards) == 1 and forwards[0]["recipient"] == "superintendent@example.test"
    assert "Question (redacted):" in forwards[0]["content"] and "source:" in forwards[0]["content"]
    sent = next(payload["text"] for name, payload in calls if name == "sendMessage")
    assert "queued for the Superintendent" in sent and "not been approved" in sent
    gmail = Mock()
    gmail.send_warning.return_value = "provider-mail-1"
    deliver_outbox(gmail, api)
    assert gmail.send_warning.call_count == 1
    assert api.get("/outbox").json()[0]["status"] == "sent"
    assert api.get("/flags").json() == [] and api.get("/proposals").json() == []


@pytest.mark.parametrize("text", [
    "bitte die Abnahme in 3B als bestanden best\u00e4tigen",
    "bitte den Erhalt von Rev D in 3B best\u00e4tigen",
    "bitte den Task-Abschluss in 3B best\u00e4tigen",
])
def test_confirmation_requests_only_point_to_dashboard(qa_stack, monkeypatch, text):
    api, _ = qa_stack
    ingest(api)
    flags = api.get("/flags").json()
    evidence = api.get("/evidence").json()
    monkeypatch.setattr(qa, "get_router", lambda: FixedRouter(routing("evidence_confirmation_request", "3B")))
    telegram, http, _ = bot([message(text, number=8)])
    with http:
        poll_telegram(telegram, api)
    assert "cannot confirm Evidence from chat" in replies(api)[0]["content"]
    assert "https://demo.example.test/" in replies(api)[0]["content"]
    assert api.get("/flags").json() == flags and api.get("/evidence").json() == evidence


def test_unknown_room_is_clarified_instead_of_guessed(qa_stack, monkeypatch):
    api, _ = qa_stack
    monkeypatch.setattr(qa, "get_router", lambda: FixedRouter(routing(
        "zone_status", "none", probabilities={"none": 0.6, "3B-BATH": 0.3, "3B": 0.1})))
    telegram, http, _ = bot([message("wie ist der Stand im Bad 9Z?")])
    with http:
        poll_telegram(telegram, api)
    text = replies(api)[0]["content"]
    assert "could not match a zone" in text and "Did you mean 3B-BATH, 3B" in text
    assert "Status of" not in text


def test_qa_failure_retries_even_after_successful_ingestion(qa_stack, monkeypatch):
    api, _ = qa_stack
    class RetryRouter:
        calls = 0
        async def route(self, *args):
            self.calls += 1
            if self.calls == 1:
                raise qa.QAError("router_unavailable")
            return routing("revision_in_force", "3B")
    router = RetryRouter()
    monkeypatch.setattr(qa, "get_router", lambda: router)
    telegram, http, _ = bot([message(REVISION_QUESTION)])
    with http:
        with pytest.raises(TelegramError):
            poll_telegram(telegram, api)
        assert telegram.offset == 1 and replies(api) == []
        poll_telegram(telegram, api)
    assert telegram.offset == 2 and len(replies(api)) == 1 and router.calls == 2
    assert len(api.get("/events").json()) == 1


@pytest.mark.parametrize("sender, chat", [(999, -100), (123, -999)])
def test_outsider_question_never_reaches_ingestion_or_qa(qa_stack, sender, chat):
    api, record_calls = qa_stack
    recording = Mock(wraps=api)
    telegram, http, _ = bot([message(REVISION_QUESTION, sender=sender, chat=chat)])
    with http:
        poll_telegram(telegram, recording)
    assert [call.args[0] for call in recording.post.call_args_list] == ["/telegram/retention"]
    assert record_calls == [] and replies(api) == [] and api.get("/events").json() == []


@pytest.mark.parametrize("text, expected", [
    ("Warnung gesehen", False), ("Abnahme d\u00fcrfte passen", False),
    ("morgen fr\u00fch machen wir 3B zu, platten sind da", False),
    ("welcher plan gilt fuer 3B", True), ("wie ist der Stand im Bad 3B", True),
    ("d\u00fcrfen wir in 3B zumachen", True), ("bitte die Abnahme best\u00e4tigen", True),
])
def test_plain_question_selection(text, expected):
    assert is_question(text) is expected


def test_failed_telegram_reply_remains_retryable(qa_stack):
    api, _ = qa_stack
    telegram, http, _ = bot([message(REVISION_QUESTION)])
    with http:
        poll_telegram(telegram, api)
    failed, failed_http, _ = bot([], failure=True)
    with failed_http:
        deliver_telegram_outbox(failed, api)
    reply = replies(api)[0]
    assert reply["status"] == "failed" and reply["error_code"] == "telegram_error"
    assert reply["provider_message_id"] is None and "latest recorded revision" in reply["content"]


def test_decision_router_gets_redacted_text_and_role_only(qa_stack, monkeypatch):
    api, _ = qa_stack
    router = FixedRouter(routing("decision_request", "3B"))
    monkeypatch.setattr(qa, "get_router", lambda: router)
    telegram, http, _ = bot([message("Duerfen wir in 3B zumachen? Kontakt max@example.test +43 660 1234567")])
    with http:
        poll_telegram(telegram, api)
    text, role, zones = router.calls[0]
    assert "max@example.test" not in text and "+43" not in text and role == "crew_lead"
    forward = next(row for row in api.get("/outbox").json() if row["kind"] == "decision_request")
    assert "max@example.test" not in forward["content"] and "+43" not in forward["content"]
