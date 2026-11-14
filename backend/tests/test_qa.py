"""Q&A core (#19): mocked routing, answers only from our own MCP tools."""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import anyio
import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import insert

from app import mcp_server, models, qa
from conftest import BACKEND
from test_lifecycle import decision
from test_revision_rules import receipt
from test_mcp_server import api_transport  # noqa: F401 - fixture
from test_rules import ingest, initialized, inspection_claim  # noqa: F401 - fixture

REVISION_QUESTION = "welcher plan gilt für 3B?"
STATUS_QUESTION = "wie ist der Stand im Bad 3B?"


def routing(question_type, zone, type_confidence=0.95, zone_confidence=0.95, probabilities=None):
    return qa.Routing(
        question_type=qa.Choice(value=question_type, confidence=type_confidence),
        zone=qa.Choice(value=zone, confidence=zone_confidence, probabilities=probabilities or {zone: zone_confidence}),
    )


class FixedRouter:
    def __init__(self, result):
        self.result, self.calls = result, []

    async def route(self, text, sender_role, zones):
        self.calls.append((text, sender_role, [zone["id"] for zone in zones]))
        return self.result


def ask(text, sender_role="crew_lead", qa_router=None):
    """Run qa.answer against the real in-process MCP server, which calls the real API."""
    result = {}

    async def run():
        server = mcp_server.create_server()
        app = server.streamable_http_app()
        async with server.session_manager.run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
                async with streamable_http_client("http://mcp/mcp", http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result["answer"] = await qa.answer(text, sender_role, qa.tool_caller(session),
                                                           qa_router or qa.CachedRouter())

    anyio.run(run)
    return result["answer"]


@pytest.fixture
def hero(initialized, api_transport):  # noqa: F811
    note = ingest(initialized, **json.loads((BACKEND / "demo" / "revision-note.json").read_text(encoding="utf-8")))
    inspection = inspection_claim(initialized)
    ingest(initialized)  # "morgen früh machen wir 3B zu" -> Flag A
    return {"note": note, "inspection": inspection, "requests": api_transport}


def test_revision_question_answers_rev_d_with_mail_source_from_day_one(hero):
    answer = ask(REVISION_QUESTION)
    assert answer.kind == "answer" and answer.zone_id == "3B"
    assert "Plan A-103 Rev D is the latest recorded revision, issued 2026-11-13 10:15 (day 1)" in answer.text
    assert "from architect" in answer.text and "extracted statement, unconfirmed" in answer.text
    assert f"source:{hero['note']['source']['id']}" in answer.source_refs
    # Uses only MCP: every record request is the MCP server's, none writes.
    assert hero["requests"] and all(request.headers["X-SiteMind-Client"] == "mcp" and request.method == "GET"
                                    for request in hero["requests"])


def test_room_status_lists_record_with_sources_labels_and_room_link(hero):
    answer = ask(STATUS_QUESTION, "superintendent")
    assert answer.kind == "answer" and answer.zone_id == "3B-BATH"
    text = answer.text
    assert text.startswith("Status of ")
    assert "Rev D" in text
    assert "Inspection rough_in (rough-in-F3)" in text and "'passed' UNCONFIRMED claim [source:" in text
    assert "Evidence revision_acknowledgment (zone_id F3, crew_id plumbing, revision_id A-103-C)" in text
    assert "Open Flag A for drywall-F3" in text and any(ref.startswith("flag:") for ref in answer.source_refs)
    assert "unknown (no valid confirmed evidence)" in text
    assert "Task " in text and "Latest: " in text
    assert "not proof" in text
    assert text.endswith("Room view: http://localhost:3000/zones/3B-BATH")
    # No clearance claim: only predecessor completion may be satisfied, and only
    # through the explicit F3 seed baseline (#25). Inspection and revision
    # Preconditions stay unconfirmed, and Flag A stays open.
    satisfied = [line for line in text.splitlines()
                 if "satisfied." in line.replace("NOT satisfied", "")]
    assert all(line.startswith("Precondition predecessors_completed for ") for line in satisfied), satisfied


def test_contradictory_evaluation_is_labelled(hero, monkeypatch):
    real = qa.status_lines

    async def contradictory(tools, zone_id, site, base):
        async def patched(name, **arguments):
            result = await tools(name, **arguments)
            if name == "get_zone_status":
                result["preconditions"] = [dict(item, evaluation="contradictory") for item in result["preconditions"]]
            return result
        return await real(patched, zone_id, site, base)

    monkeypatch.setattr(qa, "status_lines", contradictory)
    assert "CONTRADICTORY (unresolved)" in ask(STATUS_QUESTION, "superintendent").text


@pytest.mark.parametrize("result", [
    routing("zone_status", "3B", type_confidence=0.3),
    routing("not_a_known_type", "3B"),
])
def test_low_type_confidence_asks_back(hero, result):
    answer = ask("???", qa_router=FixedRouter(result))
    assert answer.kind == "clarification" and not answer.source_refs


@pytest.mark.parametrize("result, suggestions", [
    (routing("zone_status", "none", probabilities={"none": 0.5, "3B-BATH": 0.3, "9Z": 0.1, "3B": 0.1}),
     ["3B-BATH", "3B"]),
    (routing("zone_status", "3B", zone_confidence=0.4, probabilities={"3B": 0.4, "3C": 0.35}), ["3B", "3C"]),
    (routing("revision_in_force", "9Z", probabilities={"9Z": 0.95}), []),
    (routing("revision_in_force", "none", zone_confidence=1.0, probabilities={"none": 0.99, "B1": 0.001}), []),
])
def test_unknown_or_uncertain_zone_is_not_guessed(hero, result, suggestions):
    answer = ask("wie ist der Stand im Bad 9Z?", qa_router=FixedRouter(result))
    assert answer.kind == "clarification" and answer.suggestions == suggestions
    assert "could not match a zone" in answer.text and not answer.source_refs
    assert all("/context/" not in request.url.path for request in hero["requests"])


def test_decision_request_is_not_answered(hero):
    answer = ask("dürfen wir morgen in 3B zumachen?")
    assert answer.kind == "decision_request" and answer.zone_id == "3B" and not answer.source_refs
    assert {request.url.path for request in hero["requests"]} == {"/site", "/zones"}


def test_confirmation_request_points_to_dashboard_and_changes_nothing(hero):
    answer = ask("bitte die Abnahme in 3B als bestanden bestätigen")
    assert answer.kind == "dashboard_review" and "dashboard" in answer.text
    assert {request.url.path for request in hero["requests"]} == {"/site", "/zones"}
    # The inspection claim is still unconfirmed afterwards.
    assert "'passed' UNCONFIRMED claim [source:" in ask(STATUS_QUESTION, "superintendent").text


def test_other_record_question_says_record_has_no_answer(hero):
    answer = ask("wer hat die Platten bestellt?", qa_router=FixedRouter(routing("other_record_question", "3B")))
    assert answer.kind == "not_found" and "no direct answer" in answer.text


def test_not_a_question_returns_empty_text(hero):
    answer = ask("morgen früh machen wir 3B zu", qa_router=FixedRouter(routing("not_a_question", "3B")))
    assert answer.kind == "not_a_question" and answer.text == ""


def test_router_gets_redacted_text_and_zone_choices_only(hero):
    router = FixedRouter(routing("decision_request", "3B"))
    ask("ruf mich an +43 660 1234567 oder max@example.com, dürfen wir in 3B?", "crew_lead", router)
    text, role, zones = router.calls[0]
    assert "+43" not in text and "@example.com" not in text and role == "crew_lead"
    assert {"3B", "3B-BATH", "F3", "B1"} <= set(zones)


def decisions_reply(question_type="zone_status", zone="3B-BATH", zone_answer=None):
    return {"model": "gpt-6-luna", "usage": {}, "answers": [
        {"type": "choice", "name": "question_type", "choice": question_type, "confidence": 0.9,
         "probabilities": [{"value": question_type, "probability": 0.9}, {"value": "other_record_question",
                                                                         "probability": 0.1}]},
        zone_answer or {"type": "choice", "name": "zone", "choice": zone, "confidence": 0.8,
                        "probabilities": [{"value": zone, "probability": 0.8}, {"value": "3B", "probability": 0.2}]},
    ]}


def decisions(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(qa.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs))
    zones = [{"id": "3B", "kind": "unit", "name": "Wohnung 3B"}, {"id": "3B-BATH", "kind": "room", "name": "Bad"}]
    return anyio.run(qa.DecisionsRouter("test-key").route, "wie ist der Stand im Bad 3B?", "superintendent", zones)


def test_decisions_router_wire_format(monkeypatch):
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(200, json=decisions_reply())

    result = decisions(monkeypatch, handler)
    request = seen["request"]
    assert str(request.url) == "https://api.openai.com/v1/decisions"
    assert request.headers["Authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["model"] == "gpt-6-luna"
    assert body["input"][0]["content"][0]["data"] == {"text": "wie ist der Stand im Bad 3B?",
                                                      "sender_role": "superintendent"}
    question_type, zone = body["questions"]
    assert {item["value"] for item in question_type["choices"]} == set(qa.QUESTION_TYPES)
    assert [item["value"] for item in zone["choices"]] == ["3B", "3B-BATH", "none"]
    assert all(question["type"] == "choice" for question in body["questions"])
    assert result.question_type.value == "zone_status" and result.zone.value == "3B-BATH"
    assert result.zone.confidence == 0.8 and result.zone.probabilities == {"3B-BATH": 0.8, "3B": 0.2}


def test_decisions_refusal_becomes_zero_confidence(monkeypatch):
    result = decisions(monkeypatch, lambda request: httpx.Response(200, json=decisions_reply(
        zone_answer={"type": "refusal", "name": "zone"})))
    assert result.zone.confidence == 0


@pytest.mark.parametrize("response, code", [
    (httpx.Response(403, json={"error": "forbidden"}), "router_unavailable"),
    (httpx.Response(200, json={"answers": []}), "invalid_routing"),
])
def test_decisions_errors_are_safe_codes(monkeypatch, response, code):
    with pytest.raises(qa.QAError) as error:
        decisions(monkeypatch, lambda request: response)
    assert error.value.code == code


def test_provider_switch(monkeypatch):
    monkeypatch.setenv("QA_ROUTER_PROVIDER", "cached")
    assert isinstance(qa.get_router(), qa.CachedRouter)
    monkeypatch.setenv("QA_ROUTER_PROVIDER", "decisions")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(qa.QAError):
        qa.get_router()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert isinstance(qa.get_router(), qa.DecisionsRouter)


def test_endpoint_uses_mcp_tools_and_maps_cache_miss_to_503(client, monkeypatch):
    monkeypatch.setenv("QA_ROUTER_PROVIDER", "cached")

    @asynccontextmanager
    async def fake_tools():
        async def call(name, **arguments):
            assert name == "list_zones"
            return {"site": None, "zones": [{"id": "3B", "kind": "unit", "name": "Wohnung 3B", "children": []}]}
        yield call

    monkeypatch.setattr(qa, "mcp_tools", fake_tools)
    response = client.post("/qa", json={"text": "dürfen wir morgen in 3B zumachen?", "sender_role": "crew_lead"})
    assert response.status_code == 200 and response.json()["kind"] == "decision_request"
    response = client.post("/qa", json={"text": "unbekannte Frage", "sender_role": "crew_lead"})
    assert response.status_code == 503 and response.json()["detail"] == "cache_miss"


def test_qa_core_has_no_direct_data_access():
    assert not {"models", "Session", "Database", "get_session", "select"} & set(vars(qa))


@pytest.mark.parametrize("status, label", [
    ("confirmed", "confirmed"), ("rejected", "rejected"), (None, "UNCONFIRMED claim"),
])
def test_revision_answer_uses_current_receipt_evidence(hero, initialized, monkeypatch, status, label):
    evidence_id = receipt(initialized, monkeypatch)
    if status:
        assert decision(initialized, evidence_id, status).status_code == 200
    evidence = next(item for item in initialized.get("/evidence").json() if item["id"] == evidence_id)
    answer = ask(REVISION_QUESTION)
    assert f"plumbing (zone 3B): 'acknowledged' {label} [{evidence['source_ref']}]" in answer.text
    assert evidence["source_ref"] in answer.source_refs
    assert "Recorded receipt evidence for Rev D: none recorded" not in answer.text
    assert "not proof of implementation or clearance" in answer.text


def test_receipt_recorded_before_revision_registration_keeps_its_review_status(initialized, api_transport, monkeypatch):
    with monkeypatch.context() as receipt_patch:
        evidence_id = receipt(initialized, receipt_patch)
    ingest(initialized, **json.loads((BACKEND / "demo" / "revision-note.json").read_text(encoding="utf-8")))
    assert decision(initialized, evidence_id, "confirmed").status_code == 200
    answer = ask(REVISION_QUESTION)
    assert "plumbing (zone 3B): 'acknowledged' confirmed" in answer.text


@pytest.mark.parametrize("status", ["confirmed", "rejected"])
def test_latest_source_labels_use_current_human_evidence_review(hero, initialized, status):
    assert decision(initialized, hero["inspection"], status).status_code == 200
    answer = ask(STATUS_QUESTION, "superintendent")
    latest = next(line for line in answer.text.splitlines()
                  if line.startswith("Latest:") and "inspection_result" in line)
    assert f"extracted statement; Evidence: 'passed' {status}" in latest
    assert "unconfirmed" not in latest.lower()
    assert f"'passed' {status}" in answer.text


def test_current_revision_and_source_survive_a_truncated_timeline(hero, initialized, engine):
    baseline = next(item for item in initialized.get("/evidence").json()
                    if item["origin"] == "seed_baseline" and item["scope"]["revision_id"] == "A-103-C")
    stamp = datetime(2026, 11, 13, 8, 0, tzinfo=UTC)
    # A long real review history must not hide the later-issued Rev D. Seed receipt
    # review times here are before Rev D and independent of the newly ingested sources.
    with engine.begin() as connection:
        connection.execute(insert(models.EvidenceReview), [dict(
            evidence_id=baseline["id"], sequence=2+i,
            status="rejected" if i % 2 == 0 else "confirmed", actor_type="human",
            reviewer_id="synthetic-superintendent", reviewer_role="superintendent",
            decided_at=stamp, recorded_at=stamp, reason="Synthetic receipt review history",
        ) for i in range(205)])
    timeline = initialized.get("/context/timeline", params={"zone_id": "3B", "limit": 200}).json()
    assert timeline["truncated"]
    assert not any(item["kind"] == "revision" and item["record"]["id"] == "A-103-D"
                   for item in timeline["entries"])
    answer = ask(REVISION_QUESTION)
    assert "Rev D is the latest recorded revision" in answer.text
    assert "Rev C is the latest recorded revision" not in answer.text
    assert f"source:{hero['note']['source']['id']}" in answer.source_refs
    assert "from architect" in answer.text
