"""Question replies are idempotent outbox work, never human decisions."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import anyio
import pytest
from sqlalchemy.orm import Session

from app import models, qa, telegram_qa
from test_rules import initialized, ingest
from test_qa import routing
from test_telegram import HEADERS, command


@pytest.fixture
def question_api(initialized, monkeypatch):
    monkeypatch.setenv("TELEGRAM_COMPLIANCE_KEY", "synthetic-worker-key")
    monkeypatch.setenv("SUPERINTENDENT_EMAIL", "superintendent@example.test")
    return initialized


def source(api, text="welcher plan gilt f\u00fcr 3B?", **changes):
    return ingest(api, channel="telegram", source_key="123", sender_id="123", text=text, **changes)["source"]


def mock_answer(monkeypatch, kind="answer", text="Rev D [revision:A-103-D]", zone="3B"):
    stub = AsyncMock(return_value=qa.Answer(kind=kind, text=text, zone_id=zone,
                                          routing=routing("zone_status", zone or "none")))
    monkeypatch.setattr(telegram_qa.qa, "ask", stub)
    return stub


def request(api, source_id, **changes):
    return api.post("/telegram/qa", headers=HEADERS, json={"source_id": source_id, **changes})


def test_reply_is_source_bound_outboxed_and_idempotent(question_api, monkeypatch):
    original = source(question_api)
    stub = mock_answer(monkeypatch)
    assert question_api.post("/telegram/qa", json={"source_id": original["id"]}).status_code == 403
    response = request(question_api, original["id"])
    assert response.status_code == 200 and response.json()["handled"]
    assert request(question_api, original["id"]).json() == response.json()
    rows = question_api.get("/outbox").json()
    assert len(rows) == 1 and rows[0]["kind"] == "qa_reply"
    assert rows[0]["channel"] == "telegram" and rows[0]["recipient"] == "123"
    assert rows[0]["content"] == "Rev D [revision:A-103-D]"
    assert stub.await_count == 1
    assert stub.call_args.args[0].sender_role == original["sender_role"]
    assert question_api.get("/flags").json() == []


def test_decision_request_and_receipt_are_atomic_and_do_not_claim_approval(question_api, monkeypatch):
    original = source(question_api)
    mock_answer(monkeypatch, "decision_request")
    assert request(question_api, original["id"]).status_code == 200
    assert request(question_api, original["id"]).status_code == 200
    rows = question_api.get("/outbox").json()
    assert len(rows) == 2
    forward = next(row for row in rows if row["kind"] == "decision_request")
    reply = next(row for row in rows if row["kind"] == "qa_reply")
    assert forward["channel"] == "gmail" and forward["recipient"] == "superintendent@example.test"
    assert f"source:{original['id']}" in forward["content"] and "Question (redacted):" in forward["content"]
    assert "queued for the Superintendent" in reply["content"] and "not been approved" in reply["content"]
    assert question_api.get("/proposals").json() == question_api.get("/flags").json() == []


def test_missing_superintendent_does_not_claim_forwarding(question_api, monkeypatch):
    original = source(question_api)
    mock_answer(monkeypatch, "decision_request")
    monkeypatch.delenv("SUPERINTENDENT_EMAIL")
    response = request(question_api, original["id"])
    assert response.status_code == 503 and response.json()["detail"] == "superintendent_not_configured"
    assert question_api.get("/outbox").json() == []


def test_router_failure_is_retryable_without_a_fake_answer(question_api, monkeypatch):
    from fastapi import HTTPException
    original = source(question_api)
    stub = mock_answer(monkeypatch)
    stub.side_effect = HTTPException(503, "router_unavailable")
    assert request(question_api, original["id"]).status_code == 503
    assert question_api.get("/outbox").json() == []
    stub.side_effect = None
    assert request(question_api, original["id"]).status_code == 200


@pytest.mark.parametrize("operation", ["delete", "expire"])
def test_raw_erasure_cancels_reply_and_forward_copies(question_api, engine, monkeypatch, operation):
    original = source(question_api)
    mock_answer(monkeypatch, "decision_request")
    assert request(question_api, original["id"]).status_code == 200
    if operation == "delete":
        assert command(question_api, "delete_my_data").status_code == 200
    else:
        with Session(engine) as session, session.begin():
            session.get(models.SourceMessage, original["id"]).received_at = datetime.now(UTC) - timedelta(days=8)
        assert question_api.post("/telegram/retention", headers=HEADERS).status_code == 200
    copies = [row for row in question_api.get("/outbox").json() if row["kind"] in {"qa_reply", "decision_request"}]
    assert len(copies) == 2 and all(row["status"] == "cancelled" for row in copies)
    assert all(row["content"] == "[deleted Telegram question copy]" for row in copies)
    request(question_api, original["id"])
    assert len([row for row in question_api.get("/outbox").json() if row["kind"] == "decision_request"]) == 1


def test_deleted_or_nontelegram_source_is_not_answered(question_api, monkeypatch):
    original = source(question_api)
    stub = mock_answer(monkeypatch)
    assert command(question_api, "delete_my_data").status_code == 200
    assert request(question_api, original["id"]).json()["handled"] is False
    stub.assert_not_awaited()
    assert request(question_api, "missing").status_code == 404
    other = ingest(question_api, channel="gmail", external_id="other", text="welcher plan gilt f\u00fcr 3B?")["source"]
    assert other["channel"] != "telegram"
    assert request(question_api, other["id"]).status_code == 404


def test_question_deleted_while_qa_is_running_is_not_copied(question_api, monkeypatch):
    original = source(question_api)
    stub = mock_answer(monkeypatch)
    answer = stub.return_value
    async def erase(_):
        response = await anyio.to_thread.run_sync(lambda: command(question_api, "delete_my_data"))
        assert response.status_code == 200
        return answer
    stub.side_effect = erase
    assert request(question_api, original["id"]).json()["handled"] is False
    assert not any(row["kind"] == "qa_reply" for row in question_api.get("/outbox").json())


def test_nonquestion_does_not_queue_a_reply(question_api, monkeypatch):
    original = source(question_api)
    mock_answer(monkeypatch, "not_a_question", text="")
    assert request(question_api, original["id"]).json()["handled"] is False
    assert question_api.get("/outbox").json() == []


@pytest.mark.parametrize("channel", ["gmail", "telegram"])
def test_erasure_invalidates_leases_for_both_question_copies(question_api, monkeypatch, channel):
    original = source(question_api)
    mock_answer(monkeypatch, "decision_request")
    request(question_api, original["id"]).raise_for_status()
    claimed = question_api.post("/outbox/claim", params={"channel": channel}).json()
    assert claimed is not None
    assert command(question_api, "delete_my_data").status_code == 200
    result = question_api.post(f"/outbox/{claimed['id']}/result", json={
        "lease_token": claimed["lease_token"], "status": "sent", "provider_message_id": "too-late",
    })
    assert result.status_code == 409


def test_long_question_asks_for_shorter_input_without_calling_router(question_api, monkeypatch):
    original = question_api.post("/ingestion/messages", json={
        "channel": "telegram", "source_key": "123", "external_id": "long",
        "sender_id": "123", "sender_role": "crew_lead", "sent_at": datetime.now(UTC).isoformat(),
        "text": "?" * 4001,
    }).json()["source"]
    stub = mock_answer(monkeypatch)
    assert request(question_api, original["id"]).status_code == 200
    assert "at most 4000" in question_api.get("/outbox").json()[0]["content"]
    stub.assert_not_awaited()
