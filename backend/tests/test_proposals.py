import json

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, proposal_api
from app.advisor import Advice, CachedAdvisor, LLMAdvisor
from app.extraction import ExtractionError
from app.worker import request_advice
from conftest import BACKEND
from test_lifecycle import HUMAN, action, signal
from test_rules import initialized, ingest, inspection_claim  # noqa: F401


def hero_flag(client):
    ingest(client)
    return client.get("/flags").json()[0]


def advise(client, flag):
    return client.post(f"/flags/{flag['id']}/advice")


def decide(client, proposal_id, decision, **changes):
    return client.post(f"/proposals/{proposal_id}/decisions", json={
        **HUMAN, "decision": decision, "reason": "Synthetic Superintendent decision", **changes,
    })


def acknowledged(client, engine, flag):
    signal(engine, flag["id"], "notified")
    flag = client.get(f"/flags/{flag['id']}").json()
    response = action(client, flag, "acknowledge")
    assert response.status_code == 200, response.text
    return response.json()


def outbox(client, kind):
    return [row for row in client.get("/outbox").json() if row["kind"] == kind]


class FakeLLM:
    name = "fake:test"

    def __init__(self, result):
        self.result, self.calls = result, []

    def complete(self, prompt, user, schema):
        self.calls.append(user)
        return schema.model_validate(self.result) if isinstance(self.result, dict) else self.result


def cached_result():
    entry = json.loads((BACKEND / "demo" / "advice-cache.json").read_text(encoding="utf-8"))["entries"][0]
    return entry["result"]


def test_hero_flag_a_proposal_approval_informs_crew_lead(initialized, engine, monkeypatch):
    monkeypatch.setenv("SUPERINTENDENT_EMAIL", "superintendent@example.test")
    monkeypatch.setenv("DASHBOARD_BASE_URL", "https://demo.example.test")
    with Session(engine) as session, session.begin():
        session.get(models.CrewLead, "lead-drywall").email = "drywall@example.test"
    evidence_id = inspection_claim(initialized)
    flag = hero_flag(initialized)
    response = advise(initialized, flag)
    assert response.status_code == 200, response.text
    advice = response.json()
    assert advice["backend"] == "cached:v1"
    assert "[S1]" in advice["explanation"] and "unconfirmed" in advice["explanation"]
    assert {item["handle"]: item["ref"] for item in advice["citations"]}["S1"] == f"source:{flag['sources'][0]['source']['id']}"
    proposal = advice["proposals"][0]
    assert proposal["status"] == "proposed" and "Postpone drywall" in proposal["action"]
    assert (proposal["affected_crews"], proposal["affected_zones"]) == (["drywall"], ["3B", "3A", "3C"])
    # Idempotent: one advice and one approval request per Flag.
    assert advise(initialized, flag).json() == advice
    [request] = outbox(initialized, "approval_request")
    assert request["recipient"] == "superintendent@example.test" and request["channel"] == "gmail"
    assert f"https://demo.example.test/#flag-{flag['id']}" in request["content"]
    assert proposal["action"] in request["content"]
    assert outbox(initialized, "proposal_followup") == []

    # Nothing is executed before the Flag is acknowledged and the Proposal approved.
    assert decide(initialized, proposal["id"], "approved").status_code == 409
    flag = acknowledged(initialized, engine, flag)
    response = decide(initialized, proposal["id"], "approved")
    assert response.status_code == 200, response.text
    assert response.json()["proposals"][0]["status"] == "approved"
    assert response.json()["proposals"][0]["decided_by"] == HUMAN["actor"]
    updated = initialized.get(f"/flags/{flag['id']}").json()
    assert updated["state"] == "in_progress"
    assert [entry["action"] for entry in updated["audit"]][-2:] == ["proposal_approved", "action_approved"]
    assert updated["audit"][-1]["source_ref"] == f"proposal:{proposal['id']}"
    [followup] = outbox(initialized, "proposal_followup")
    assert followup["recipient"] == "drywall@example.test"
    assert "do not close walls in 3B" in followup["content"]
    assert "does not close the Flag" in followup["content"]
    # Approval neither confirms Evidence nor closes or re-evaluates the Flag.
    assert updated["evaluation"] == "unknown" and not updated["awaiting_human_closure"]
    evidence = next(item for item in initialized.get("/evidence").json() if item["id"] == evidence_id)
    assert evidence["review_status"] == "unconfirmed"
    assert decide(initialized, proposal["id"], "approved").status_code == 409
    assert decide(initialized, proposal["id"], "rejected").status_code == 409


def test_rejection_changes_nothing(initialized, engine):
    flag = hero_flag(initialized)
    proposal = advise(initialized, flag).json()["proposals"][0]
    flag = acknowledged(initialized, engine, flag)
    before = initialized.get("/outbox").json()
    response = decide(initialized, proposal["id"], "rejected")
    assert response.status_code == 200, response.text
    assert response.json()["proposals"][0]["status"] == "rejected"
    after = initialized.get(f"/flags/{flag['id']}").json()
    assert (after["state"], after["evaluation"]) == ("acknowledged", flag["evaluation"])
    assert initialized.get("/outbox").json() == before
    assert after["audit"][-1]["action"] == "proposal_rejected"
    assert decide(initialized, proposal["id"], "approved").status_code == 409


@pytest.mark.parametrize("changes,status", [
    ({"role": "crew_lead", "actor": "lead-drywall"}, 403),
    ({"channel": "mcp"}, 422),
    ({"channel": "chat"}, 422),
    ({"role": "agent"}, 422),
    ({"reason": "  "}, 422),
])
def test_only_superintendent_in_dashboard_decides(initialized, engine, changes, status):
    flag = hero_flag(initialized)
    proposal = advise(initialized, flag).json()["proposals"][0]
    acknowledged(initialized, engine, flag)
    assert decide(initialized, proposal["id"], "approved", **changes).status_code == status
    assert initialized.get(f"/flags/{flag['id']}").json()["state"] == "acknowledged"
    assert decide(initialized, "missing", "approved").status_code == 404


def invalid(result, **changes):
    result = json.loads(json.dumps(result))
    proposal = {**result["proposals"][0], **changes.pop("proposal", {})}
    return {**result, "proposals": [proposal], **changes}


@pytest.mark.parametrize("result,code", [
    (invalid(cached_result(), explanation="No citation at all."), "invalid_citation"),
    (invalid(cached_result(), explanation="Invented [S9] fact."), "invalid_citation"),
    (invalid(cached_result(), explanation="Only rules [flag], no source."), "invalid_citation"),
    (invalid(cached_result(), proposal={"rationale": "Uncited."}), "invalid_citation"),
    (invalid(cached_result(), proposal={"message": "See [S1]."}), "invalid_citation"),
    (invalid(cached_result(), proposal={"affected_zones": ["4D"]}), "unknown_reference"),
    (invalid(cached_result(), proposal={"affected_crews": ["painters"]}), "unknown_reference"),
    (invalid(cached_result(), proposal={"affected_tasks": ["drywall-F1"]}), "unknown_reference"),
])
def test_output_outside_the_record_is_rejected(initialized, engine, monkeypatch, result, code):
    monkeypatch.setattr(proposal_api, "get_advisor", lambda: LLMAdvisor(FakeLLM(result)))
    flag = hero_flag(initialized)
    response = advise(initialized, flag)
    assert (response.status_code, response.json()["detail"]) == (502, code)
    assert initialized.get(f"/flags/{flag['id']}").json()["advice"] is None
    assert outbox(initialized, "approval_request") == []


def test_mocked_llm_gets_only_record_facts_with_review_status(initialized, engine, monkeypatch):
    with Session(engine) as session, session.begin():
        session.get(models.CrewLead, "lead-drywall").email = "drywall@example.test"
    llm = FakeLLM(cached_result())
    monkeypatch.setattr(proposal_api, "get_advisor", lambda: LLMAdvisor(llm))
    inspection_claim(initialized)
    flag = hero_flag(initialized)
    advice = advise(initialized, flag).json()
    assert advice["backend"] == "fake:test"
    [facts] = llm.calls
    text = json.dumps(facts, ensure_ascii=False)
    assert "drywall@example.test" not in text and "Sam Example" not in text
    assert facts["flag"]["evaluation"] == "unknown"
    assert facts["sources"][0]["status"] == "unconfirmed_statement"
    assert [item["review_status"] for item in facts["evidence"]] == ["unconfirmed"]
    assert {zone["id"] for zone in facts["nearby_zones"]} == {"3A", "3B", "3C", "3D"}
    assert "status" not in facts["inspection"]  # The Inspection row is not proof.


def test_advice_failures_and_closed_flags(initialized, engine, monkeypatch):
    flag = hero_flag(initialized)
    monkeypatch.setattr(proposal_api, "get_advisor", lambda: CachedAdvisor(BACKEND / "missing.json"))
    assert advise(initialized, flag).json()["detail"] == "invalid_cache"
    def unavailable(*_):
        raise ExtractionError("provider_unavailable")
    llm = FakeLLM(None)
    llm.complete = unavailable
    monkeypatch.setattr(proposal_api, "get_advisor", lambda: LLMAdvisor(llm))
    assert advise(initialized, flag).json()["detail"] == "provider_unavailable"
    signal(engine, flag["id"], "notified")
    flag = initialized.get(f"/flags/{flag['id']}").json()
    assert action(initialized, flag, "false_alarm").status_code == 200
    assert advise(initialized, flag).status_code == 409
    assert initialized.post("/flags/missing/advice").status_code == 404


def test_closed_flag_proposal_cannot_be_decided(initialized, engine):
    flag = hero_flag(initialized)
    proposal = advise(initialized, flag).json()["proposals"][0]
    flag = acknowledged(initialized, engine, flag)
    assert action(initialized, flag, "false_alarm").status_code == 200
    assert decide(initialized, proposal["id"], "approved").status_code == 409


def test_worker_requests_advice_once_per_open_flag(initialized):
    flag = hero_flag(initialized)
    calls = []

    class Api:
        def get(self, path):
            return initialized.get(path)

        def post(self, path):
            calls.append(path)
            return initialized.post(path)

    request_advice(Api())
    request_advice(Api())
    assert calls == [f"/flags/{flag['id']}/advice"]
    assert initialized.get(f"/flags/{flag['id']}").json()["advice"]["proposals"]


def test_seed_reset_and_migration_backfill(initialized, engine, seed):
    flag = hero_flag(initialized)
    advise(initialized, flag)
    assert initialized.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
    with Session(engine) as session:
        assert session.scalar(select(models.Proposal)) is None
        assert session.scalar(select(models.FlagAdvice)) is None
    ingest(initialized)
    config = Config(str(BACKEND / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0009")
        command.upgrade(config, "head")
    with Session(engine) as session:
        message = session.scalar(select(models.OutboxMessage))
        assert (message.kind, message.dedup_key) == ("warning", f"warning:{message.flag_id}")


def test_agent_suggestions_stay_unapproved_alongside_advisor_proposals(initialized, engine):
    flag = hero_flag(initialized)
    response = initialized.post("/agent/proposals", headers={"X-SiteMind-Client": "mcp"}, json={
        "flag_id": flag["id"], "action": "Postpone drywall in 3B", "rationale": "Unconfirmed proof",
    })
    assert response.status_code == 201, response.text
    agent = response.json()
    proposal = advise(initialized, flag).json()["proposals"][0]
    records = initialized.get("/proposals", params={"flag_id": flag["id"]}).json()
    assert {item["id"] for item in records} == {agent["id"], proposal["id"]}
    assert initialized.get(f"/proposals/{agent['id']}").json() == agent
    assert initialized.get(f"/proposals/{proposal['id']}").json()["channel"] == "advisor"
    flag = acknowledged(initialized, engine, flag)
    assert decide(initialized, agent["id"], "approved").status_code == 409
    blocked = initialized.post(f"/proposals/{proposal['id']}/decisions",
        headers={"X-SiteMind-Client": "mcp"}, json={**HUMAN, "decision": "approved", "reason": "Agent request"})
    assert blocked.status_code == 403
    assert outbox(initialized, "proposal_followup") == []
    assert decide(initialized, proposal["id"], "approved").status_code == 200
    assert initialized.get(f"/proposals/{proposal['id']}").json()["status"] == "approved"
    assert initialized.get(f"/proposals/{agent['id']}").json() == agent


def test_migration_preserves_existing_agent_suggestions(initialized, engine):
    flag = hero_flag(initialized)
    agent = initialized.post("/agent/proposals", json={
        "flag_id": flag["id"], "action": "Keep agent advice", "rationale": "Retain source provenance",
    }).json()
    assert advise(initialized, flag).status_code == 200
    config = Config(str(BACKEND / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0010")
        command.upgrade(config, "head")
    assert initialized.get(f"/proposals/{agent['id']}").json() == agent
    assert initialized.get("/proposals").json() == [agent]
    assert initialized.get(f"/flags/{flag['id']}").json()["advice"] is None


def test_migration_preserves_warning_and_escalation(initialized, engine):
    from datetime import UTC, datetime
    from app.outbox import enqueue_escalation

    flag = hero_flag(initialized)
    with Session(engine) as session, session.begin():
        enqueue_escalation(session, session.get(models.Flag, flag["id"]), 4, datetime.now(UTC))
    before = {row["id"]: row for row in initialized.get("/outbox").json()}
    assert {row["kind"] for row in before.values()} == {"warning", "escalation"}
    config = Config(str(BACKEND / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0013")
        command.upgrade(config, "head")
    after = {row["id"]: row for row in initialized.get("/outbox").json()}
    assert after == before
    with Session(engine) as session:
        rows = session.scalars(select(models.OutboxMessage)).all()
        assert {row.dedup_key for row in rows} == {f"warning:{flag['id']}", f"escalation:{flag['id']}"}


def test_cached_hero_advice_is_valid_schema():
    assert Advice.model_validate(cached_result()).proposals


def test_full_seed_hero_advice_names_the_unresolved_contradiction(client, seed):
    assert client.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
    flag = hero_flag(client)
    assert flag["evaluation"] == "contradictory"
    advice = advise(client, flag).json()
    assert "unresolved" in advice["explanation"] and "not satisfied" in advice["explanation"]
    statuses = {item["handle"]: item["review_status"] for item in advice["citations"]}
    assert statuses["E1"] == "confirmed" and statuses["E3"] == statuses["E4"] == "unconfirmed"


@pytest.mark.parametrize("evidence_id,decision", [
    ("baseline-rough-in-F3", "rejected"),
    ("example-ambiguous", "confirmed"),
])
def test_fresh_cached_advice_rejects_changed_evidence_reviews(client, seed, monkeypatch, evidence_id, decision):
    monkeypatch.setenv("LLM_PROVIDER", "cached")
    assert client.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
    flag = hero_flag(client)
    reviewed = client.post(f"/evidence/{evidence_id}/reviews", json={
        **HUMAN, "decision": decision, "expected_sequence": 1,
        "reason": "Synthetic Evidence review before the first advice request",
    })
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["review_status"] == decision
    assert client.get(f"/flags/{flag['id']}").json()["evaluation"] == "contradictory"
    response = advise(client, flag)
    assert (response.status_code, response.json().get("detail")) == (502, "cache_miss")
    assert client.get(f"/flags/{flag['id']}").json()["advice"] is None
    assert outbox(client, "approval_request") == []


def test_cached_advice_rejects_an_additional_evidence_statement(client, seed, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "cached")
    assert client.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
    flag = hero_flag(client)
    inspection_claim(client)
    assert client.get(f"/flags/{flag['id']}").json()["evaluation"] == "contradictory"
    response = advise(client, flag)
    assert (response.status_code, response.json().get("detail")) == (502, "cache_miss")
    assert client.get(f"/flags/{flag['id']}").json()["advice"] is None
    assert outbox(client, "approval_request") == []
