from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.lifecycle import InvalidTransition, TRANSITIONS, transition_flag
from test_rules import initialized, ingest, inspection_claim  # noqa: F401


HUMAN = {"actor": "synthetic-superintendent", "role": "superintendent", "channel": "dashboard"}


def action(client, flag, operation, **changes):
    return client.post(f"/flags/{flag['id']}/actions", json={
        **HUMAN, "action": operation, "expected_state": flag["state"],
        "feedback": "confirmed" if operation == "acknowledge" else operation,
        "reason": "Synthetic test decision", **changes,
    })


def signal(engine, flag_id, operation, **changes):
    with Session(engine) as session, session.begin():
        flag = session.get(models.Flag, flag_id)
        transition_flag(session, flag, action=operation, actor="worker", actor_type="system",
                        channel="system", source_ref="outbox:synthetic-delivery", **changes)


def decision(client, evidence_id, status, **changes):
    evidence = next(item for item in client.get("/evidence").json() if item["id"] == evidence_id)
    return client.post(f"/evidence/{evidence_id}/reviews", json={
        **HUMAN, "decision": status, "expected_sequence": (evidence["history"][-1]["sequence"] if evidence["history"] else 0),
        "reason": "Reviewed synthetic source and exact scope", **changes,
    })


@pytest.mark.parametrize("state", ["detected", "notified", "acknowledged", "in_progress", "resolved", "false_alarm"])
@pytest.mark.parametrize("operation", list(TRANSITIONS))
@pytest.mark.parametrize("actor_type", ["human", "system", "agent"])
def test_transition_matrix(state, operation, actor_type):
    flag = models.Flag(id="unit-flag", state=state, open_key="conflict", audit=[])
    allowed, target, required_actor = TRANSITIONS[operation]
    feedback = {"acknowledge": "confirmed", "resolved": "resolved", "false_alarm": "false_alarm"}.get(operation)
    class Storage:
        def add(self, _):
            pass
    kwargs = dict(action=operation, actor="demo-superintendent", actor_type=actor_type,
                  role="superintendent", channel="dashboard", source_ref="test:source",
                  feedback=feedback, reason="Synthetic reason")
    if state not in allowed or actor_type != required_actor:
        with pytest.raises(InvalidTransition):
            transition_flag(Storage(), flag, **kwargs)
        assert flag.state == state and flag.audit == []
    else:
        transition_flag(Storage(), flag, **kwargs)
        assert flag.state == target
        assert (flag.audit[0].from_state, flag.audit[0].to_state) == (state, target)
        assert flag.audit[0].source_ref == "test:source"
        assert flag.open_key == (None if target in {"resolved", "false_alarm"} else "conflict")


def test_full_lifecycle_preserves_feedback_and_independent_evidence(initialized, engine):
    evidence_id = inspection_claim(initialized)
    ingest(initialized)
    flag = initialized.get("/flags").json()[0]
    assert not flag["awaiting_human_closure"]
    assert action(initialized, flag, "resolved").status_code == 409
    signal(engine, flag["id"], "notified")
    signal(engine, flag["id"], "escalated")
    flag = initialized.get(f"/flags/{flag['id']}").json()
    response = action(initialized, flag, "acknowledge")
    assert response.status_code == 200, response.text
    acknowledged = response.json()
    assert acknowledged["state"] == "acknowledged"
    assert acknowledged["evaluation"] == "unknown"
    assert acknowledged["evidence"][0]["review_status"] == "unconfirmed"
    assert action(initialized, flag, "acknowledge").status_code == 409
    assert action(initialized, acknowledged, "resolved").status_code == 409
    # #13's validated human approval calls the shared integration function.
    with Session(engine) as session, session.begin():
        transition_flag(session, session.get(models.Flag, flag["id"]), action="action_approved",
                        actor=HUMAN["actor"], actor_type="human", role="superintendent",
                        channel="dashboard", source_ref="proposal:synthetic-approved")
    progress = initialized.get(f"/flags/{flag['id']}").json()
    resolved = action(initialized, progress, "resolved").json()
    assert resolved["state"] == "resolved"
    assert resolved["evaluation"] == "unknown"
    assert not resolved["awaiting_human_closure"]
    assert initialized.get("/flags").json() == []
    assert initialized.get("/flags?status=closed").json() == [resolved]
    assert [item["action"] for item in resolved["audit"]] == [
        "detected", "notified", "escalated", "acknowledge", "action_approved", "resolved",
    ]
    assert resolved["audit"][-1]["feedback"] == "resolved"
    assert resolved["audit"][-1]["reason"] == "Synthetic test decision"
    assert resolved["audit"][-1]["actor_role"] == "superintendent"
    assert resolved["audit"][-1]["source_ref"] == f"flag:{flag['id']}"
    # Review does not recreate closed work; a distinct new announcement can.
    assert decision(initialized, evidence_id, "rejected").status_code == 200
    assert initialized.get("/flags").json() == []
    ingest(initialized, external_id="new-work")
    assert initialized.get("/flags").json()[0]["id"] != flag["id"]
    with Session(engine) as session:
        audit = session.scalar(select(models.FlagAudit).where(models.FlagAudit.flag_id == flag["id"]))
        audit.actor = "overwrite"
        with pytest.raises(ValueError, match="append-only"):
            session.commit()


def test_review_without_flag_then_rejection_and_confirmation_recheck(initialized):
    evidence_id = inspection_claim(initialized)
    assert initialized.get("/flags").json() == []
    confirmed = decision(initialized, evidence_id, "confirmed")
    assert confirmed.status_code == 200, confirmed.text
    record = confirmed.json()
    assert record["scope"]["inspection_id"] == "rough-in-F3"
    assert record["quote"] and record["source_ref"]
    assert record["history"][-1]["reviewer_id"] == HUMAN["actor"]
    assert record["history"][-1]["reviewer_role"] == HUMAN["role"]
    assert record["history"][-1]["decided_at"]
    ingest(initialized)
    assert initialized.get("/flags").json() == []
    assert decision(initialized, evidence_id, "rejected").status_code == 200
    flag = initialized.get("/flags").json()[0]
    assert flag["state"] == "detected" and not flag["awaiting_human_closure"]
    assert decision(initialized, evidence_id, "confirmed").status_code == 200
    updated = initialized.get("/flags").json()[0]
    assert updated["state"] == "detected" and updated["awaiting_human_closure"]
    assert updated["audit"][-1]["actor"] == HUMAN["actor"]
    assert updated["audit"][-1]["source_ref"] == f"evidence:{evidence_id}"
    assert decision(initialized, evidence_id, "rejected", expected_sequence=1).status_code == 409
    assert decision(initialized, evidence_id, "confirmed").status_code == 409


@pytest.mark.parametrize("channel", ["mcp", "chat", "system", "telegram"])
def test_agent_channels_cannot_review_or_change_flags(initialized, channel):
    evidence_id = inspection_claim(initialized)
    ingest(initialized)
    flag = initialized.get("/flags").json()[0]
    assert decision(initialized, evidence_id, "confirmed", channel=channel).status_code == 422
    assert decision(initialized, evidence_id, "rejected", channel=channel).status_code == 422
    assert action(initialized, flag, "false_alarm", channel=channel).status_code == 422
    assert action(initialized, flag, "action_approved").status_code == 422
    assert action(initialized, flag, "notified").status_code == 422
    assert decision(initialized, evidence_id, "confirmed", role="agent").status_code == 422


def test_permissions_feedback_and_invalid_requests(initialized, engine):
    evidence_id = inspection_claim(initialized)
    ingest(initialized)
    flag = initialized.get("/flags").json()[0]
    signal(engine, flag["id"], "notified")
    flag = initialized.get("/flags").json()[0]
    assert action(initialized, flag, "false_alarm", reason="  ").status_code == 422
    assert action(initialized, flag, "false_alarm", feedback="resolved").status_code == 409
    payload = {**HUMAN, "action": "false_alarm", "expected_state": "notified", "reason": "test"}
    assert initialized.post(f"/flags/{flag['id']}/actions", json=payload).status_code == 422
    assert action(initialized, flag, "acknowledge", role="crew_lead", actor="lead-plumbing").status_code == 403
    assert decision(initialized, evidence_id, "confirmed", role="crew_lead", actor="lead-drywall").status_code == 403
    acknowledged = action(initialized, flag, "acknowledge", role="crew_lead", actor="lead-drywall")
    assert acknowledged.status_code == 200
    assert action(initialized, acknowledged.json(), "false_alarm").status_code == 200
    assert action(initialized, acknowledged.json(), "false_alarm").status_code == 409
    assert action(initialized, {"id": "missing", "state": "notified"}, "false_alarm").status_code == 404
    assert initialized.post("/evidence/missing/reviews", json={**HUMAN, "decision": "confirmed", "expected_sequence": 1, "reason": "test"}).status_code == 404


@pytest.mark.parametrize("kind,scope", [
    ("inspection", {"zone_id": "3B", "inspection_id": "rough-in-F3"}),
    ("inspection", {"zone_id": "F3", "inspection_id": None}),
    ("task_completion", {"zone_id": "3B", "task_id": "drywall-F3"}),
    ("revision_acknowledgment", {"zone_id": "F4", "crew_id": "plumbing", "revision_id": "A-103-C"}),
])
def test_mismatched_scope_cannot_be_confirmed_but_can_be_rejected(initialized, engine, kind, scope):
    claims = {"inspection": "passed", "task_completion": "completed", "revision_acknowledgment": "acknowledged"}
    with Session(engine) as session, session.begin():
        session.add(models.Evidence(id="bad-scope", origin="seed_statement", source_ref="seed:test",
                                    quote="Synthetic statement", kind=kind, claim=claims[kind], **scope,
                                    history=[models.EvidenceReview(sequence=1, status="unconfirmed",
                                             actor_type="seed_import", recorded_at=datetime.now(UTC))]))
    assert decision(initialized, "bad-scope", "confirmed").status_code == 422
    assert decision(initialized, "bad-scope", "rejected").status_code == 200


@pytest.mark.parametrize("kind,scope,actor", [
    ("task_completion", {"zone_id": "F3", "task_id": "drywall-F3"}, "lead-drywall"),
    ("revision_acknowledgment", {"zone_id": "F3", "crew_id": "plumbing", "revision_id": "A-103-C"}, "lead-plumbing"),
])
def test_responsible_crew_can_review_own_scoped_claims(initialized, engine, kind, scope, actor):
    with Session(engine) as session, session.begin():
        session.add(models.Evidence(id="own-claim", origin="seed_statement", source_ref="seed:test",
                                    quote="Synthetic statement", kind=kind,
                                    claim="completed" if kind == "task_completion" else "acknowledged", **scope,
                                    history=[models.EvidenceReview(sequence=1, status="unconfirmed",
                                             actor_type="seed_import", recorded_at=datetime.now(UTC))]))
    assert decision(initialized, "own-claim", "confirmed", role="crew_lead", actor="lead-plumbing" if actor == "lead-drywall" else "lead-drywall").status_code == 403
    assert decision(initialized, "own-claim", "confirmed", role="crew_lead", actor=actor).status_code == 200


def test_source_mismatch_and_unresolved_counterclaim(initialized, engine):
    evidence_id = inspection_claim(initialized)
    ingest(initialized)
    assert decision(initialized, evidence_id, "confirmed").status_code == 200
    with Session(engine) as session, session.begin():
        original = session.get(models.Evidence, evidence_id)
        # A failed claim for an unresolved Inspection remains a genuine conflict.
        statement = session.get(models.Event, original.statement_ref)
        conflicting = models.Event(
            id="counterclaim-event", source_message_id=statement.source_message_id,
            ordinal=1, intent="inspection_result", actor="inspector", quote="Inspection failed",
            confidence=1, time_precision="unknown", unresolved_zones=[],
            details={"inspection_kind": "rough_in"}, created_at=datetime.now(UTC),
            zones=[session.get(models.Zone, "F3")],
        )
        session.add(conflicting)
        session.add(models.Evidence(id="counterclaim", origin="llm_statement",
                                    source_ref=original.source_ref, statement_ref=conflicting.id,
                                    quote=conflicting.quote, kind="inspection", claim="failed", zone_id="F3",
                                    history=[models.EvidenceReview(sequence=1, status="unconfirmed",
                                             actor_type="statement_ingestion", recorded_at=datetime.now(UTC))]))
        session.add(models.Evidence(id="wrong-source", origin="llm_statement",
                                    source_ref="source:missing", statement_ref=original.statement_ref,
                                    quote=original.quote, kind="inspection", claim="passed", zone_id="F3",
                                    inspection_id="rough-in-F3", history=[]))
    flag = initialized.get("/flags").json()[0]
    assert flag["evaluation"] == "contradictory" and not flag["awaiting_human_closure"]
    assert decision(initialized, "wrong-source", "confirmed", expected_sequence=0).status_code == 422
    assert decision(initialized, "counterclaim", "confirmed").status_code == 422
    assert decision(initialized, "counterclaim", "rejected").status_code == 200
    assert initialized.get("/flags").json()[0]["awaiting_human_closure"]


def test_closed_flag_does_not_claim_it_is_waiting_for_closure(initialized, engine):
    evidence_id = inspection_claim(initialized)
    ingest(initialized)
    flag = initialized.get("/flags").json()[0]
    signal(engine, flag["id"], "notified")
    assert decision(initialized, evidence_id, "confirmed").status_code == 200
    satisfied = initialized.get("/flags").json()[0]
    assert satisfied["awaiting_human_closure"]
    closed = action(initialized, satisfied, "false_alarm").json()
    assert closed["state"] == "false_alarm"
    assert not closed["awaiting_human_closure"]
    assert "awaiting" not in closed["explanation"]


def test_lifecycle_migration_follows_outbox_and_round_trips(engine):
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect
    from conftest import BACKEND

    config = Config(str(BACKEND / "alembic.ini"))
    assert ScriptDirectory.from_config(config).get_heads() == ["0010"]
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0007")
        inspector = inspect(connection)
        assert "outbox_messages" in inspector.get_table_names()
        assert "context" in {column["name"] for column in inspector.get_columns("flags")}
        assert "feedback" not in {column["name"] for column in inspector.get_columns("flag_audit")}
        assert "reason" not in {column["name"] for column in inspector.get_columns("evidence_reviews")}
        command.upgrade(config, "head")
        assert compare_metadata(MigrationContext.configure(connection), models.Base.metadata) == []


@pytest.mark.parametrize("receipt_zone", ["F3", "3B", "3B-BATH"])
def test_dashboard_receipt_scope_covers_changed_descendant(initialized, monkeypatch, receipt_zone):
    from test_revision_rules import statement, receipt, plumbing

    statement(initialized, monkeypatch, zones=["3B-BATH"])
    evidence_id = receipt(initialized, monkeypatch, zones=[receipt_zone])
    before = next(item for item in initialized.get("/evidence").json() if item["id"] == evidence_id)
    response = decision(initialized, evidence_id, "confirmed", role="crew_lead", actor="lead-plumbing")
    assert response.status_code == 200, response.text
    assert response.json()["scope"] == before["scope"]
    flag = plumbing(initialized)
    assert flag["zone_id"] == "3B-BATH"
    assert flag["evaluation"] == "satisfied"
    assert flag["state"] == "detected" and flag["awaiting_human_closure"]


def test_dashboard_confirms_late_registered_revision_without_rewriting_evidence(initialized, monkeypatch):
    from test_revision_rules import statement, receipt, plumbing

    evidence_id = receipt(initialized, monkeypatch)
    before = next(item for item in initialized.get("/evidence").json() if item["id"] == evidence_id)
    assert before["scope"]["revision_id"] is None
    assert decision(initialized, evidence_id, "confirmed").status_code == 422
    statement(initialized, monkeypatch)
    assert plumbing(initialized)["evaluation"] == "unknown"
    response = decision(initialized, evidence_id, "confirmed")
    assert response.status_code == 200, response.text
    after = response.json()
    for key in ("scope", "source_ref", "statement_ref", "quote"):
        assert after[key] == before[key]
    assert after["history"][:-1] == before["history"]
    assert after["history"][-1]["actor_type"] == "human"
    assert plumbing(initialized)["evaluation"] == "satisfied"
    assert decision(initialized, evidence_id, "rejected").status_code == 200
    assert plumbing(initialized)["evaluation"] == "unknown"


@pytest.mark.parametrize("changes", [
    {"label": None}, {"label": "E"}, {"plan": None}, {"plan": "A-102"},
    {"crew": "ambiguous"}, {"zones": ["F4"]},
    {"sent_at": "2026-11-13T09:00:00+01:00"},
])
def test_dashboard_does_not_confirm_invalid_late_revision_scope(initialized, monkeypatch, changes):
    from test_revision_rules import statement, receipt, plumbing

    evidence_id = receipt(initialized, monkeypatch, **changes)
    statement(initialized, monkeypatch)
    response = decision(initialized, evidence_id, "confirmed")
    assert response.status_code == 422, response.text
    assert plumbing(initialized)["evaluation"] != "satisfied"
    assert decision(initialized, evidence_id, "rejected").status_code == 200
