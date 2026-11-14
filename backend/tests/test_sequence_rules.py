import json
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app import ingestion, models, rules
from app.extraction import ExtractedBatch, ExtractedEvent
from conftest import BACKEND
from test_lifecycle import signal
from test_rules import ingest


@pytest.fixture
def sequence_site(client, seed, monkeypatch, engine):
    monkeypatch.setenv("LLM_PROVIDER", "cached")
    monkeypatch.delenv("LLM_CACHE_PATH", raising=False)
    seed.evidence = [item for item in seed.evidence if item.scope.kind not in {"inspection", "task_completion"}]
    assert client.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
    with Session(engine) as session, session.begin():
        task = session.get(models.Task, "drywall-F3")
        task.predecessors = [session.get(models.Task, "plumbing-F3")]
    return client


def completion(client, monkeypatch, *, claim="completed", zone="F3", reference="plumbing-F3",
               external_id="completion", sent_at="2026-11-14T17:00:00+01:00"):
    extractor = Mock()
    extractor.name = "test"
    text = f"Synthetic task completion claim: {claim}."
    extractor.extract.return_value = ExtractedBatch(events=[ExtractedEvent(
        intent="task_completion", quote=text, confidence=1, zones=[zone],
        claim=claim, task_reference=reference,
    )])
    with monkeypatch.context() as context:
        context.setattr(ingestion, "get_extractor", lambda: extractor)
        result = ingest(client, text=text, external_id=external_id, sent_at=sent_at,
                        sender_crew_id="plumbing")
    return result["events"][0]["evidence"][0]


def decision(client, evidence, status="confirmed", **changes):
    response = client.post(f'/evidence/{evidence["id"]}/reviews', json={
        "actor": "synthetic-superintendent", "role": "superintendent", "channel": "dashboard",
        "expected_sequence": evidence["history"][-1]["sequence"],
        "decision": status, "reason": "Reviewed synthetic task completion source.", **changes,
    })
    assert response.status_code == 200, response.text
    return response.json()


def sequence_flag(client):
    return next(flag for flag in client.get("/flags").json() if flag["type"] == "C")


def test_missing_predecessor_creates_source_backed_deduplicated_flag(sequence_site, engine):
    first = ingest(sequence_site)
    flag = sequence_flag(sequence_site)
    assert (flag["task_id"], flag["zone_id"], flag["evaluation"], flag["precondition"]) == (
        "drywall-F3", "3B", "unknown", "predecessors_completed",
    )
    assert "plumbing-F3" in flag["explanation"]
    assert flag["context"]["predecessors"][0]["source_refs"] == ["task:plumbing-F3"]
    assert flag["sources"][0]["id"] == first["events"][0]["id"]
    assert flag["responsible"]["id"] == "lead-drywall"
    assert flag["notifications"]
    ingest(sequence_site, external_id="second-start")
    with Session(engine) as session, session.begin():
        rules.evaluate_site(session)
    assert sequence_flag(sequence_site)["id"] == flag["id"]
    assert len(sequence_flag(sequence_site)["sources"]) == 2


def test_unconfirmed_success_confirmation_and_rejection_never_close_flag(sequence_site, monkeypatch):
    proof = completion(sequence_site, monkeypatch)
    ingest(sequence_site)
    flag = sequence_flag(sequence_site)
    assert flag["evaluation"] == "unknown"
    assert proof["id"] in {item["id"] for item in flag["evidence"]}
    assert len(flag["sources"]) == 2
    confirmed = decision(sequence_site, proof)
    updated = sequence_flag(sequence_site)
    assert (updated["id"], updated["state"], updated["evaluation"]) == (flag["id"], "detected", "satisfied")
    assert updated["awaiting_human_closure"]
    assert updated["audit"][-1]["channel"] == "dashboard"
    decision(sequence_site, confirmed, "rejected")
    assert sequence_flag(sequence_site)["evaluation"] == "unknown"


def test_confirmed_completion_before_work_prevents_flag(sequence_site, monkeypatch):
    decision(sequence_site, completion(sequence_site, monkeypatch))
    ingest(sequence_site)
    assert all(flag["type"] != "C" for flag in sequence_site.get("/flags").json())


def test_explicit_task_start_outside_schedule_without_crew_is_checked(sequence_site, monkeypatch):
    extractor = Mock()
    extractor.name = "test"
    text = "Synthetic early start of Drywall F3."
    extractor.extract.return_value = ExtractedBatch(events=[ExtractedEvent(
        intent="planned_work", quote=text, confidence=1, zones=["3B"],
        task_reference="drywall-F3", time={"expression": "today", "day_offset": 0},
    )])
    monkeypatch.setattr(ingestion, "get_extractor", lambda: extractor)
    ingest(sequence_site, text=text, sender_crew_id=None, sender_role="superintendent")
    assert sequence_flag(sequence_site)["task_id"] == "drywall-F3"


def test_tasks_without_predecessors_do_not_require_completion(sequence_site, engine):
    with Session(engine) as session, session.begin():
        task = session.get(models.Task, "plumbing-F3")
        assert not task.predecessors
        rules.evaluate_site(session, scan_tasks=[task])
    assert sequence_site.get("/flags").json() == []


@pytest.mark.parametrize("zone,reference,sent_at", [
    ("F2", "plumbing-F2", "2026-11-14T17:00:00+01:00"),
    ("F3", "insulation-F3", "2026-11-14T17:00:00+01:00"),
    ("F3", None, "2026-11-14T17:00:00+01:00"),
    ("3B", "plumbing-F3", "2026-11-14T17:00:00+01:00"),
    ("F3", "plumbing-F3", "2026-11-12T17:00:00+01:00"),
])
def test_mismatched_ambiguous_or_stale_success_is_not_proof(sequence_site, monkeypatch, zone, reference, sent_at):
    proof = completion(sequence_site, monkeypatch, zone=zone, reference=reference, sent_at=sent_at)
    if proof["scope"]["task_id"]:
        decision(sequence_site, proof)
    else:
        response = sequence_site.post(f'/evidence/{proof["id"]}/reviews', json={
            "actor": "synthetic-superintendent", "role": "superintendent", "channel": "dashboard",
            "expected_sequence": 1, "decision": "confirmed", "reason": "Ambiguous scope.",
        })
        assert response.status_code == 422
    ingest(sequence_site)
    assert sequence_flag(sequence_site)["evaluation"] == "unknown"


@pytest.mark.parametrize("reference", ["plumbing-F3", None])
def test_counterclaim_preserves_confirmation_until_human_rejection(sequence_site, monkeypatch, reference):
    proof = decision(sequence_site, completion(sequence_site, monkeypatch))
    counterclaim = completion(sequence_site, monkeypatch, claim="not_completed", external_id="counterclaim", reference=reference)
    ingest(sequence_site)
    assert sequence_flag(sequence_site)["evaluation"] == "contradictory"
    evidence = {item["id"]: item for item in sequence_flag(sequence_site)["evidence"]}
    assert evidence[proof["id"]]["review_status"] == "confirmed"
    decision(sequence_site, counterclaim, "rejected")
    assert sequence_flag(sequence_site)["evaluation"] == "satisfied"


def test_confirmed_negative_is_not_satisfied(sequence_site, monkeypatch):
    decision(sequence_site, completion(sequence_site, monkeypatch, claim="not_completed"))
    ingest(sequence_site)
    assert sequence_flag(sequence_site)["evaluation"] == "not_satisfied"


def test_all_predecessors_must_have_confirmed_evidence(sequence_site, engine, monkeypatch):
    with Session(engine) as session, session.begin():
        task = session.get(models.Task, "drywall-F3")
        task.predecessors.append(session.get(models.Task, "plumbing-F2"))
    decision(sequence_site, completion(sequence_site, monkeypatch))
    ingest(sequence_site)
    flag = sequence_flag(sequence_site)
    assert flag["evaluation"] == "unknown"
    assert {item["evaluation"] for item in flag["context"]["predecessors"]} == {"satisfied", "unknown"}
    decision(sequence_site, completion(sequence_site, monkeypatch, zone="F2", reference="plumbing-F2",
                                      external_id="cross-zone-predecessor"))
    assert sequence_flag(sequence_site)["evaluation"] == "satisfied"


def test_schedule_scan_uses_same_rule_and_rechecks_reviews(sequence_site, engine, monkeypatch):
    with Session(engine) as session, session.begin():
        rules.evaluate_site(session, scan_tasks=[session.get(models.Task, "drywall-F3")])
    flag = sequence_flag(sequence_site)
    assert flag["zone_id"] == "F3"
    assert flag["audit"][0]["source_ref"].startswith("schedule:drywall-F3@")
    decision(sequence_site, completion(sequence_site, monkeypatch))
    assert sequence_flag(sequence_site)["evaluation"] == "satisfied"
    ingest(sequence_site)
    assert len([item for item in sequence_site.get("/flags").json() if item["type"] == "C"]) == 1


def test_context_includes_completion_sources_and_mcp_cannot_confirm(sequence_site, monkeypatch):
    proof = completion(sequence_site, monkeypatch)
    ingest(sequence_site)
    context = sequence_site.get("/context/zones/3B").json()
    evaluation = next(item for item in context["preconditions"] if item["name"] == "predecessors_completed")
    assert proof["source_ref"] in evaluation["source_refs"]
    for channel in ("mcp", "chat", "agent"):
        response = sequence_site.post(f'/evidence/{proof["id"]}/reviews', headers={"X-SiteMind-Client": channel}, json={
            "actor": "synthetic-superintendent", "role": "superintendent", "channel": "dashboard",
            "expected_sequence": 1, "decision": "confirmed", "reason": "Not allowed.",
        })
        assert response.status_code == 403
    assert sequence_flag(sequence_site)["evaluation"] == "unknown"


def test_human_closed_sequence_flag_is_not_reopened(sequence_site, engine, monkeypatch):
    ingest(sequence_site)
    flag = sequence_flag(sequence_site)
    signal(engine, flag["id"], "notified")
    response = sequence_site.post(f'/flags/{flag["id"]}/actions', json={
        "actor": "synthetic-superintendent", "role": "superintendent", "channel": "dashboard",
        "action": "false_alarm", "feedback": "false_alarm", "reason": "Synthetic human feedback.",
        "expected_state": "notified",
    })
    assert response.status_code == 200, response.text
    proof = completion(sequence_site, monkeypatch)
    decision(sequence_site, proof)
    assert all(item["type"] != "C" for item in sequence_site.get("/flags").json())
    ingest(sequence_site, external_id="new-work")
    assert all(item["type"] != "C" for item in sequence_site.get("/flags").json())


def test_seed_scenario_flags_missing_predecessor_and_reset_preserves_provenance(client, seed, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "cached")
    monkeypatch.delenv("LLM_CACHE_PATH", raising=False)
    payload = json.loads((BACKEND / "demo" / "out-of-sequence.json").read_text())
    for _ in range(2):
        assert client.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
        assert client.get("/flags").json() == []
        response = client.post("/ingestion/messages", json=payload)
        assert response.status_code == 201, response.text
        flag = sequence_flag(client)
        assert (flag["task_id"], flag["zone_id"], flag["evaluation"]) == ("drywall-F1", "F1", "not_satisfied")
        assert "insulation-F1" in flag["explanation"]
        assert flag["sources"][0]["quote"] == payload["text"]
        [proof] = flag["evidence"]
        assert proof["origin"] == "seed_baseline"
        assert proof["source_ref"] == "seed:schedule.csv#insulation-F1"
        assert proof["history"][0]["actor_type"] == "seed_import"
        assert proof["history"][0]["reviewer_id"] is None
        assert client.post("/ingestion/messages", json=payload).status_code == 200
        assert sequence_flag(client)["id"] == flag["id"]
