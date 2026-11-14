"""Conflict B: note scope, source-backed receipt and the human Evidence boundary."""

import json
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app import ingestion, models, rules
from app.extraction import ExtractedBatch, ExtractedEvent
from conftest import BACKEND
from test_rules import initialized, ingest, review


def statement(client, monkeypatch, *, external_id="note", intent="revision", zones=None,
              plan="A-103", label="D", crew=None, claim=None,
              sent_at="2026-11-13T10:15:00+01:00", **changes):
    text = f"Synthetic {intent} {external_id}"
    extractor = Mock(name="offline extractor")
    extractor.name = "test"
    extractor.extract.return_value = ExtractedBatch(events=[ExtractedEvent(
        intent=intent, quote=text, confidence=1, zones=["3B"] if zones is None else zones,
        plan_reference=plan, revision_label=label, crew=crew, claim=claim,
        activity="plan_revision" if intent == "revision" else "revision_receipt",
    )])
    monkeypatch.setattr(ingestion, "get_extractor", lambda: extractor)
    return ingest(client, external_id=external_id, text=text, sender_role="architect",
                  sender_crew_id=None, sent_at=sent_at, **changes)


def receipt(client, monkeypatch, **changes):
    values = dict(external_id="receipt", intent="revision_acknowledgment", crew="plumbing",
                  claim="acknowledged", sent_at="2026-11-13T11:00:00+01:00") | changes
    result = statement(client, monkeypatch, **values)
    return result["events"][0]["evidence"][0]["id"]


def plumbing(client):
    return next(flag for flag in client.get("/flags").json() if
                flag["type"] == "B" and flag["context"]["crew_id"] == "plumbing")


def test_hero_note_registers_revision_and_flags_current_and_future_crews(initialized):
    payload = json.loads((BACKEND / "demo" / "revision-note.json").read_text(encoding="utf-8"))
    result = ingest(initialized, **payload)
    flag = plumbing(initialized)
    assert flag["zone_id"] == "3B"
    assert flag["task_id"] == "plumbing-F3"
    assert flag["responsible"]["id"] == "lead-plumbing"
    assert flag["context"] == dict(crew_id="plumbing", plan_id="A-103", revision_id="A-103-D",
        current_revision="D", acknowledged_revision="C", acknowledged_revision_id="A-103-C",
        affected_zones_origin="unconfirmed_revision_note")
    assert flag["evaluation"] == "unknown"
    assert flag["sources"][0]["id"] == result["events"][0]["id"]
    assert flag["sources"][0]["source"]["id"] == result["source"]["id"]
    assert all(item["zone_id"] == "3B" for item in initialized.get("/flags").json())
    plans = initialized.get("/plans").json()
    plan = next(item for item in plans if item["id"] == "A-103")
    assert plan["current_revision"]["label"] == "D"
    assert plan["current_revision"]["file_name"] is None


def test_unconfirmed_receipt_confirmation_rejection_and_no_flag_closure(initialized, engine, monkeypatch):
    statement(initialized, monkeypatch)
    evidence_id = receipt(initialized, monkeypatch)
    assert plumbing(initialized)["evaluation"] == "unknown"
    assert any(item["id"] == evidence_id and item["review_status"] == "unconfirmed"
               for item in plumbing(initialized)["evidence"])
    review(engine, evidence_id, "confirmed")
    confirmed = plumbing(initialized)
    assert confirmed["evaluation"] == "satisfied"
    assert confirmed["state"] == "detected"
    assert confirmed["context"]["acknowledged_revision"] == "D"
    assert confirmed["audit"][-1]["actor"] == "synthetic-superintendent"
    assert "does not certify implementation" in confirmed["explanation"]
    review(engine, evidence_id, "rejected")
    assert plumbing(initialized)["evaluation"] == "unknown"


@pytest.mark.parametrize("changes", [
    {"crew": "drywall"}, {"crew": "ambiguous"}, {"zones": ["3A"]},
    {"zones": ["3B-BATH"]}, {"zones": []}, {"plan": "A-102"}, {"plan": None},
    {"label": "C"}, {"label": None}, {"sent_at": "2026-11-12T13:00:00Z"},
])
def test_mismatched_ambiguous_and_stale_receipt_never_satisfies(initialized, engine, monkeypatch, changes):
    statement(initialized, monkeypatch)
    evidence_id = receipt(initialized, monkeypatch, **changes)
    review(engine, evidence_id, "confirmed")
    assert plumbing(initialized)["evaluation"] == "unknown"


def test_floor_receipt_covers_unit_and_new_counterclaim_requires_review(initialized, engine, monkeypatch):
    statement(initialized, monkeypatch)
    evidence_id = receipt(initialized, monkeypatch, zones=["F3"])
    review(engine, evidence_id, "confirmed")
    assert plumbing(initialized)["evaluation"] == "satisfied"
    counterclaim = receipt(initialized, monkeypatch, external_id="counterclaim", zones=["3B-BATH"],
                           claim="not_acknowledged", sent_at="2026-11-13T12:00:00+01:00")
    assert plumbing(initialized)["evaluation"] == "contradictory", plumbing(initialized)
    review(engine, counterclaim, "rejected")
    assert plumbing(initialized)["evaluation"] == "satisfied"


def test_confirmed_negative_is_not_satisfied(initialized, engine, monkeypatch):
    statement(initialized, monkeypatch)
    evidence_id = receipt(initialized, monkeypatch, claim="not_acknowledged")
    review(engine, evidence_id, "confirmed")
    assert plumbing(initialized)["evaluation"] == "not_satisfied"


def test_warning_seen_is_not_a_receipt_and_day_two_surfaces_both_preconditions(initialized, monkeypatch):
    statement(initialized, monkeypatch)
    # Use the real cached offline extractor after the synthetic note.
    from app.extraction import get_extractor
    monkeypatch.setattr(ingestion, "get_extractor", get_extractor)
    warning = ingest(initialized, external_id="warning", sender_crew_id="plumbing",
                     text="Warnung gesehen", sent_at="2026-11-13T11:00:00+01:00")
    assert warning["events"][0]["evidence"] == []
    assert plumbing(initialized)["evaluation"] == "unknown"
    ingest(initialized, external_id="closing")
    closing = [flag for flag in initialized.get("/flags").json() if flag["task_id"] == "drywall-F3"]
    assert {flag["type"] for flag in closing} == {"A", "B"}
    assert all(flag["evaluation"] == "unknown" for flag in closing)
    b = next(flag for flag in closing if flag["type"] == "B")
    assert {event["intent"] for event in b["sources"]} == {"revision", "planned_work"}


def test_repeat_notes_and_scan_deduplicate_and_reset_restores_baseline(initialized, engine, seed, monkeypatch):
    statement(initialized, monkeypatch)
    first = plumbing(initialized)
    statement(initialized, monkeypatch, external_id="second-note")
    with Session(engine) as session, session.begin():
        rules.evaluate_site(session)
    assert plumbing(initialized)["id"] == first["id"]
    assert len(plumbing(initialized)["sources"]) == 2
    assert len(plumbing(initialized)["audit"]) == 1
    assert initialized.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
    assert initialized.get("/flags").json() == []
    plan = next(item for item in initialized.get("/plans").json() if item["id"] == "A-103")
    assert plan["current_revision"]["label"] == "C"


@pytest.mark.parametrize("changes", [{"zones": []}, {"zones": ["2B"]}, {"zones": ["unknown"]},
                                      {"plan": "unknown"}, {"label": None}])
def test_unresolvable_notes_do_not_invent_revision_or_global_scope(initialized, monkeypatch, changes):
    statement(initialized, monkeypatch, **changes)
    assert initialized.get("/flags").json() == []
    plan = next(item for item in initialized.get("/plans").json() if item["id"] == "A-103")
    assert plan["current_revision"]["label"] == "C"


def test_late_older_note_cannot_advance_latest_revision(initialized, monkeypatch):
    statement(initialized, monkeypatch)
    statement(initialized, monkeypatch, external_id="old-note", label="B", sent_at="2026-11-11T10:00:00Z")
    assert plumbing(initialized)["context"]["current_revision"] == "D"
    plans = initialized.get("/plans").json()
    assert next(item for item in plans if item["id"] == "A-103")["current_revision"]["label"] == "D"


def test_new_revision_requires_new_receipt_even_after_human_closure(initialized, engine, monkeypatch):
    statement(initialized, monkeypatch)
    first = plumbing(initialized)
    evidence_id = receipt(initialized, monkeypatch)
    review(engine, evidence_id, "confirmed")
    with Session(engine) as session, session.begin():
        flag = session.get(models.Flag, first["id"])
        flag.state, flag.open_key = "resolved", None
        flag.audit.append(models.FlagAudit(action="resolved", actor="synthetic-superintendent",
            channel="dashboard", source_ref="test:resolved", recorded_at=datetime.now(UTC)))
    with Session(engine) as session, session.begin():
        rules.evaluate_site(session)
    assert not any(flag["context"]["crew_id"] == "plumbing" for flag in initialized.get("/flags").json())
    statement(initialized, monkeypatch, external_id="revision-E", label="E", sent_at="2026-11-13T14:00:00Z")
    new = plumbing(initialized)
    assert new["id"] != first["id"]
    assert new["context"]["current_revision"] == "E"
    assert new["context"]["acknowledged_revision"] == "D"
    assert new["evaluation"] == "unknown"

@pytest.mark.parametrize("cad_first", [True, False])
def test_note_and_cad_import_share_revision_without_certifying_receipt(initialized, monkeypatch, cad_first):
    from test_cad_pipeline import ENTRIES, upload

    entry = next(item for item in ENTRIES if item["metadata"]["revision_id"] == "A-103-D")
    if cad_first:
        assert upload(initialized, entry).status_code == 200
        assert initialized.get("/flags").json() == []
    statement(initialized, monkeypatch, sent_at="2026-11-13T10:20:00+01:00")
    if not cad_first:
        result = upload(initialized, entry)
        assert result.status_code == 200, result.text
    plan = next(item for item in initialized.get("/plans").json() if item["id"] == "A-103")
    assert len(plan["revisions"]) == 2
    assert plan["current_revision"]["file_name"] == "A-103_RevD.dxf"
    assert plumbing(initialized)["evaluation"] == "unknown"
    assert plumbing(initialized)["context"]["acknowledged_revision"] == "C"
    assert plumbing(initialized)["context"]["affected_zones_origin"] == "unconfirmed_revision_note"


def test_expired_work_is_not_reflagged_for_a_later_revision(initialized, monkeypatch):
    statement(initialized, monkeypatch)
    statement(initialized, monkeypatch, external_id="later-E", label="E", sent_at="2026-11-14T10:00:00Z")
    flags = initialized.get("/flags").json()
    assert not any(flag["context"]["crew_id"] == "plumbing" and
                   flag["context"]["current_revision"] == "E" for flag in flags)


def test_counterclaim_is_evaluated_in_its_ingestion_transaction(initialized, monkeypatch):
    statement(initialized, monkeypatch)
    evidence_id = receipt(initialized, monkeypatch)
    # A counterclaim must affect the evaluation in its own ingestion transaction.
    negative = receipt(initialized, monkeypatch, external_id="negative", claim="not_acknowledged")
    flag = plumbing(initialized)
    assert flag["evaluation"] == "contradictory"
    assert {item["id"] for item in flag["evidence"]} >= {evidence_id, negative}


def test_floor_work_is_limited_to_the_notes_affected_unit(initialized, engine, monkeypatch):
    statement(initialized, monkeypatch)
    result = statement(initialized, monkeypatch, external_id="floor-work", intent="planned_work",
                       zones=["F3"], crew="drywall", plan=None, label=None,
                       sent_at="2026-11-14T18:05:00+01:00")
    flags = initialized.get("/flags").json()
    assert all(flag["zone_id"] == "3B" for flag in flags if flag["type"] == "B")
    b = next(flag for flag in flags if flag["type"] == "B" and flag["context"]["crew_id"] == "drywall")
    assert result["events"][0]["id"] in {source["id"] for source in b["sources"]}


def test_closing_one_crews_flag_does_not_skip_another_crews_review(initialized, engine, monkeypatch):
    statement(initialized, monkeypatch)
    flag_id = plumbing(initialized)["id"]
    with Session(engine) as session, session.begin():
        flag = session.get(models.Flag, flag_id)
        flag.state, flag.open_key = "false_alarm", None
        flag.audit.append(models.FlagAudit(action="false_alarm", actor="synthetic-superintendent",
            channel="dashboard", source_ref="test:other-crew", recorded_at=datetime.now(UTC)))
    evidence_id = receipt(initialized, monkeypatch, crew="drywall")
    review(engine, evidence_id, "confirmed")
    flag = next(item for item in initialized.get("/flags").json() if
                item["type"] == "B" and item["context"]["crew_id"] == "drywall")
    assert flag["evaluation"] == "satisfied"
