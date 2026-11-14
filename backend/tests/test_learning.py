from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.extraction import ExtractedBatch, ExtractedEvent, get_extractor
from app.lifecycle import transition_flag
from test_lifecycle import action, decision, signal
from test_rules import initialized, ingest, inspection_claim  # noqa: F401

QUESTION = "Können wir morgen früh 3B zumachen?"


def false_alarm(client, *, correct=True):
    original = ingest(client, text=QUESTION)
    flag = client.get("/flags").json()[0]
    delivery = client.post("/outbox/claim").json()
    assert delivery["flag_id"] == flag["id"]
    assert client.post(f"/outbox/{delivery['id']}/result", json={
        "lease_token": delivery["lease_token"], "status": "sent",
        "provider_message_id": f"synthetic-local:{delivery['id']}",
    }).status_code == 200
    flag = client.get(f"/flags/{flag['id']}").json()
    response = action(client, flag, "false_alarm", reason="A question, not an announcement",
                      correction_event_id=original["events"][0]["id"] if correct else None)
    assert response.status_code == 200, response.text
    return original, response.json()


def test_exact_replay_corrected_with_feedback_source_and_knowledge_reference(initialized, engine):
    original, flag = false_alarm(initialized)
    knowledge = initialized.get("/site-knowledge").json()
    assert len(knowledge) == 1
    entry = knowledge[0]
    assert entry["feedback"] == "false_alarm"
    assert entry["flag_id"] == flag["id"]
    assert entry["source_ids"] == [original["source"]["id"]]
    assert entry["reason"] == "A question, not an announcement"
    replay = ingest(initialized, text=QUESTION, external_id="question-replay", channel="replay")
    event = replay["events"][0]
    assert event["intent"] == "question"
    assert event["evidence"] == []
    assert event["details"]["learning"] == {
        "knowledge_id": entry["id"], "feedback_id": entry["feedback_id"],
        "flag_id": flag["id"], "source_message_id": original["source"]["id"],
        "event_id": original["events"][0]["id"],
        "original_intent": "planned_work", "corrected_intent": "question",
    }
    assert initialized.get("/flags").json() == []
    context = initialized.get("/context/zones/3B").json()
    contextual_event = next(item for item in context["events"] if item["id"] == event["id"])
    assert contextual_event["details"]["learning"] == event["details"]["learning"]
    assert initialized.get(f"/flags/{flag['id']}").json()["state"] == "false_alarm"
    assert initialized.get("/metrics/flag-feedback").json()[-1]["confirmed_share"] == 0


def test_feedback_alone_never_suppresses_work(initialized, engine):
    false_alarm(initialized, correct=False)
    replay = ingest(initialized, text=QUESTION, external_id="new-question")
    assert replay["events"][0]["intent"] == "planned_work"
    assert len(initialized.get("/flags").json()) == 1


def test_genuine_work_and_high_confidence_inspection_remain_unsafe(initialized, engine):
    false_alarm(initialized)
    evidence_id = inspection_claim(initialized)
    ingest(initialized, external_id="genuine-hero")
    flag = initialized.get("/flags").json()[0]
    assert flag["evaluation"] == "unknown"
    assert flag["state"] == "detected"
    evidence = next(item for item in initialized.get("/evidence").json() if item["id"] == evidence_id)
    assert evidence["review_status"] == "unconfirmed"
    assert evidence["history"][0]["actor_type"] != "human"


@pytest.mark.parametrize("changes", [{"sender_crew_id": "plumbing"}, {"sender_role": "crew"}, {"text": QUESTION + " Jetzt wirklich."}])
def test_scope_does_not_generalize(initialized, engine, monkeypatch, changes):
    false_alarm(initialized)

    class Extractor:
        name = "test"

        def extract(self, text, sender_role):
            return ExtractedBatch(events=[ExtractedEvent(
                intent="planned_work", quote=text, confidence=0.99, zones=["3B"],
                activity="closing_work", trade="drywall",
            )])

    monkeypatch.setattr("app.ingestion.get_extractor", Extractor)
    replay = ingest(initialized, **{"text": QUESTION, "external_id": "different-scope", **changes})
    assert replay["events"][0]["intent"] == "planned_work"
    assert "learning" not in replay["events"][0]["details"]


def test_correction_validation_and_agent_boundary_are_atomic(initialized, engine):
    original = ingest(initialized, text=QUESTION)
    flag = initialized.get("/flags").json()[0]
    signal(engine, flag["id"], "notified")
    flag = initialized.get(f"/flags/{flag['id']}").json()
    for changes in (
        {"correction_event_id": "unlinked"},
        {"correction_event_id": original["events"][0]["id"], "channel": "mcp"},
        {"correction_event_id": original["events"][0]["id"], "role": "agent"},
    ):
        assert action(initialized, flag, "false_alarm", **changes).status_code == 422
    for client_kind in ("mcp", "chat", "agent"):
        assert initialized.post(f"/flags/{flag['id']}/actions", headers={"X-SiteMind-Client": client_kind}, json={}).status_code == 403
    assert action(initialized, flag, "acknowledge", correction_event_id=original["events"][0]["id"]).status_code == 422
    assert initialized.get("/site-knowledge").json() == []
    assert initialized.get(f"/flags/{flag['id']}").json()["state"] == "notified"


def test_verbal_ok_claim_in_same_message_is_not_corrected_or_confirmed(initialized, engine, monkeypatch):
    text = QUESTION + " Der Prüfer hat die Rohinstallation im 3. OG mündlich freigegeben."

    class Extractor:
        name = "test"

        def extract(self, text, sender_role):
            return ExtractedBatch(events=[
                ExtractedEvent(intent="planned_work", quote=QUESTION, confidence=0.99,
                               zones=["3B"], activity="closing_work", trade="drywall"),
                ExtractedEvent(intent="inspection_result", quote=text[len(QUESTION) + 1:],
                               confidence=1, zones=["F3"], claim="passed", inspection_kind="rough_in"),
            ])

    monkeypatch.setattr("app.ingestion.get_extractor", Extractor)
    original = ingest(initialized, text=text)
    flag = initialized.get("/flags").json()[0]
    signal(engine, flag["id"], "notified")
    flag = initialized.get(f"/flags/{flag['id']}").json()
    assert action(initialized, flag, "false_alarm", correction_event_id=original["events"][1]["id"]).status_code == 422
    assert action(initialized, flag, "false_alarm", correction_event_id=original["events"][0]["id"]).status_code == 200
    replay = ingest(initialized, text=text, external_id="verbal-ok-replay")
    assert replay["events"][0]["intent"] == "question"
    claim = replay["events"][1]
    assert claim["intent"] == "inspection_result"
    assert claim["evidence"][0]["review_status"] == "unconfirmed"
    assert "learning" not in claim["details"]


def test_metric_counts_flags_once_and_tracks_verdict_changes(initialized, engine):
    assert initialized.get("/metrics/flag-feedback").json() == []
    ingest(initialized)
    flag = initialized.get("/flags").json()[0]
    signal(engine, flag["id"], "notified")
    flag = initialized.get(f"/flags/{flag['id']}").json()
    confirmed = action(initialized, flag, "acknowledge")
    assert confirmed.status_code == 200
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        audit = session.scalars(select(models.FlagAudit).where(models.FlagAudit.feedback == "confirmed")).one()
        session.execute(models.FlagAudit.__table__.update().where(models.FlagAudit.id == audit.id).values(recorded_at=now - timedelta(days=1)))
    assert action(initialized, confirmed.json(), "false_alarm").status_code == 200
    series = initialized.get("/metrics/flag-feedback").json()
    assert len(series) == 2
    assert [(point["confirmed_flags"], point["reviewed_flags"], point["confirmed_share"]) for point in series] == [(1, 1, 1), (0, 1, 0)]
    assert len(initialized.get("/site-knowledge").json()) == 2


def test_seed_reset_removes_knowledge_and_preserves_unconfirmed_replay(initialized, engine, seed):
    false_alarm(initialized)
    assert initialized.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
    assert initialized.get("/site-knowledge").json() == []
    assert initialized.get("/metrics/flag-feedback").json() == []
    replay = ingest(initialized, text=QUESTION)
    assert replay["events"][0]["intent"] == "planned_work"
    assert initialized.get("/flags").json()


def test_metric_denominator_excludes_unreviewed_flags_and_resolution_is_not_double_counted(initialized, engine):
    false_alarm(initialized)
    ingest(initialized, external_id="real-work")
    assert initialized.get("/metrics/flag-feedback").json()[-1]["reviewed_flags"] == 1
    flag = initialized.get("/flags").json()[0]
    signal(engine, flag["id"], "notified")
    flag = initialized.get(f"/flags/{flag['id']}").json()
    acknowledged = action(initialized, flag, "acknowledge")
    assert acknowledged.status_code == 200
    metric = initialized.get("/metrics/flag-feedback").json()[-1]
    assert (metric["confirmed_flags"], metric["reviewed_flags"], metric["confirmed_share"]) == (1, 2, 0.5)
    with Session(engine) as session, session.begin():
        record = session.get(models.Flag, flag["id"])
        transition_flag(session, record, action="action_approved", actor="synthetic-superintendent",
                        actor_type="human", role="superintendent", channel="dashboard", source_ref="proposal:test")
    flag = initialized.get(f"/flags/{flag['id']}").json()
    assert action(initialized, flag, "resolved").status_code == 200
    assert initialized.get("/metrics/flag-feedback").json()[-1] == metric
    assert len(initialized.get("/site-knowledge").json()) == 3


def test_learning_preserves_human_confirmation_and_unresolved_counterclaim(initialized, monkeypatch):
    evidence_id = inspection_claim(initialized)
    assert decision(initialized, evidence_id, "confirmed").status_code == 200
    cached = get_extractor()
    counterclaim = "Die Rohinstallation im 3. OG ist nicht bestanden."

    class Extractor:
        name = "test"

        def extract(self, text, sender_role):
            if text != counterclaim:
                return cached.extract(text, sender_role)
            return ExtractedBatch(events=[ExtractedEvent(
                intent="inspection_result", quote=text, confidence=1, zones=["F3"],
                inspection_kind="rough_in", claim="failed",
            )])

    monkeypatch.setattr("app.ingestion.get_extractor", Extractor)
    ingest(initialized, text=counterclaim, sender_role="inspector", sender_crew_id=None, external_id="counterclaim")
    before = initialized.get("/evidence").json()
    false_alarm(initialized)
    replay = ingest(initialized, text=QUESTION, external_id="question-replay")
    assert replay["events"][0]["intent"] == "question"
    assert initialized.get("/evidence").json() == before
    ingest(initialized, external_id="genuine-work-after-learning")
    assert initialized.get("/flags").json()[0]["evaluation"] == "contradictory"
