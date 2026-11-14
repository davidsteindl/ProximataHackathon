from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, rules
from conftest import BACKEND
from test_ingestion_storage import message_payload


@pytest.fixture
def initialized(client, seed, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "cached")
    monkeypatch.delenv("LLM_CACHE_PATH", raising=False)
    # Start without the separate illustrative conflicting inspection statements.
    seed.evidence = [item for item in seed.evidence if item.scope.kind != "inspection"]
    assert client.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
    return client


def ingest(client, **changes):
    response = client.post("/ingestion/messages", json=message_payload(**changes))
    assert response.status_code in (200, 201), response.text
    return response.json()


def inspection_claim(client, **changes):
    return ingest(client, external_id="inspection", sender_role="inspector", sender_crew_id=None,
                  text="Abnahme der Rohinstallation im 3. OG bestanden.", **changes)["events"][0]["evidence"][0]["id"]


def review(engine, evidence_id, status):
    with Session(engine) as session, session.begin():
        record = session.get(models.Evidence, evidence_id)
        session.add(models.EvidenceReview(
            evidence_id=evidence_id, sequence=record.history[-1].sequence + 1,
            status=status, actor_type="human", reviewer_id="synthetic-superintendent",
            reviewer_role="superintendent", decided_at=datetime.now(UTC), recorded_at=datetime.now(UTC),
        ))


def test_hero_creates_exactly_one_source_backed_flag(initialized):
    result = ingest(initialized)
    flags = initialized.get("/flags").json()
    assert len(flags) == 1
    flag = flags[0]
    assert (flag["type"], flag["zone_id"], flag["task_id"], flag["inspection_id"]) == (
        "A", "3B", "drywall-F3", "rough-in-F3",
    )
    assert flag["state"] == "detected"
    assert flag["evaluation"] == "unknown"
    assert flag["responsible"]["id"] == "lead-drywall"
    assert flag["sources"][0]["quote"] == message_payload()["text"]
    assert flag["sources"][0]["source"]["id"] == result["source"]["id"]
    assert flag["audit"][0]["channel"] == "telegram"
    assert flag["audit"][0]["actor"] == "rule_engine"
    assert initialized.get(f"/flags/{flag['id']}").json() == flag
    assert initialized.get("/flags/missing").status_code == 404


def test_repeat_message_new_source_and_scan_deduplicate(initialized, engine):
    ingest(initialized)
    first = initialized.get("/flags").json()[0]
    ingest(initialized)
    ingest(initialized, external_id="second-announcement")
    for _ in range(2):
        with Session(engine) as session, session.begin():
            rules.evaluate_site(session)
    flags = initialized.get("/flags").json()
    assert len(flags) == 1
    assert flags[0]["id"] == first["id"]
    assert len(flags[0]["sources"]) == 2
    assert len(flags[0]["audit"]) == 1


def test_unconfirmed_success_is_insufficient_and_confirmation_does_not_close(initialized, engine):
    evidence_id = inspection_claim(initialized)
    ingest(initialized)
    flag = initialized.get("/flags").json()[0]
    assert flag["evaluation"] == "unknown"
    review(engine, evidence_id, "confirmed")
    confirmed = initialized.get("/flags").json()[0]
    assert confirmed["id"] == flag["id"]
    assert confirmed["evaluation"] == "satisfied"
    assert confirmed["state"] == "detected"
    assert confirmed["evidence"][0]["review_status"] == "confirmed"
    assert confirmed["audit"][-1]["source_ref"] == f"evidence:{evidence_id}"
    assert confirmed["audit"][-1]["actor"] == "synthetic-superintendent"
    review(engine, evidence_id, "rejected")
    assert initialized.get("/flags").json()[0]["evaluation"] == "unknown"


def test_confirmed_proof_before_work_suppresses_new_flag(initialized, engine):
    evidence_id = inspection_claim(initialized)
    review(engine, evidence_id, "confirmed")
    ingest(initialized)
    assert initialized.get("/flags").json() == []
    # Evidence rejection must discover the still-announced work without a new Event.
    review(engine, evidence_id, "rejected")
    assert initialized.get("/flags").json()[0]["evaluation"] == "unknown"


@pytest.mark.parametrize("claim,expected", [("failed", "not_satisfied"), ("pending", "not_satisfied"), ("passed", "satisfied")])
def test_scoped_synthetic_baseline(initialized, engine, claim, expected):
    with Session(engine) as session, session.begin():
        session.add(models.Evidence(
            id="baseline-test", origin="seed_baseline", source_ref="seed:inspection-test", quote="Synthetic baseline",
            kind="inspection", claim=claim, zone_id="F3", inspection_id="rough-in-F3",
            history=[models.EvidenceReview(sequence=1, status="confirmed", actor_type="seed_import", recorded_at=datetime.now(UTC))],
        ))
    ingest(initialized)
    flags = initialized.get("/flags").json()
    if expected == "satisfied":
        assert flags == []
    else:
        assert flags[0]["evaluation"] == expected
        assert claim in flags[0]["explanation"]


@pytest.mark.parametrize("scope", ["wrong_zone", "wrong_inspection", "missing", "stale"])
def test_invalid_scope_and_stale_proof_do_not_suppress_flag(initialized, engine, scope):
    if scope == "stale":
        evidence_id = inspection_claim(initialized, sent_at="2026-11-13T18:05:00+01:00")
    else:
        with Session(engine) as session, session.begin():
            session.add(models.Evidence(
                id="invalid-proof", origin="seed_statement", statement_ref="synthetic", source_ref="seed:test",
                quote="Synthetic scoped statement", kind="inspection", claim="passed",
                zone_id="F2" if scope == "wrong_zone" else "F3",
                inspection_id={"wrong_zone": "rough-in-F3", "wrong_inspection": "insulation-F3", "missing": None}[scope],
                history=[models.EvidenceReview(sequence=1, status="unconfirmed", actor_type="seed_import", recorded_at=datetime.now(UTC))],
            ))
        evidence_id = "invalid-proof"
    review(engine, evidence_id, "confirmed")
    ingest(initialized)
    assert initialized.get("/flags").json()[0]["evaluation"] == "unknown"


def test_counterclaim_requires_review_and_cannot_overwrite_confirmation(initialized, engine):
    evidence_id = inspection_claim(initialized)
    review(engine, evidence_id, "confirmed")
    ingest(initialized)
    assert initialized.get("/flags").json() == []
    # A source-backed contrary claim is unconfirmed but requires review.
    with Session(engine) as session, session.begin():
        original = session.get(models.Evidence, evidence_id)
        session.add(models.Evidence(
            id="counterclaim", origin="seed_statement", statement_ref="synthetic-counterclaim", source_ref="seed:counterclaim",
            quote="Synthetic failed inspection counterclaim", kind="inspection", claim="failed",
            zone_id="F3", inspection_id="rough-in-F3",
            history=[models.EvidenceReview(sequence=1, status="unconfirmed", actor_type="seed_import", recorded_at=datetime.now(UTC))],
        ))
        assert original.review_status == "confirmed"
    ingest(initialized, external_id="repeat-with-conflict")
    flag = initialized.get("/flags").json()[0]
    assert flag["evaluation"] == "contradictory"
    assert len(flag["sources"]) == 2
    review(engine, "counterclaim", "rejected")
    assert initialized.get("/flags").json()[0]["evaluation"] == "satisfied"
    assert initialized.get("/flags").json()[0]["state"] == "detected"


def test_nonwork_events_and_unresolved_zones_do_not_invent_flags(initialized):
    ingest(initialized, text="Warnung gesehen")
    ingest(initialized, text="welcher plan gilt für 3B?", external_id="question")
    assert initialized.get("/flags").json() == []


@pytest.mark.parametrize("case", ["missing", "ambiguous", "nearer", "no_task", "unassigned", "unresolved"])
def test_work_and_inspection_resolution(initialized, engine, case):
    ingest(initialized)
    with Session(engine) as session, session.begin():
        statement = session.scalar(select(models.Event).where(models.Event.intent == "planned_work"))
        zones = {zone.id: zone for zone in session.scalars(select(models.Zone))}
        if case == "missing":
            session.delete(session.get(models.Inspection, "rough-in-F1"))
            statement.zones = [zones["1B"]]
        elif case in {"ambiguous", "nearer"}:
            session.add(models.Inspection(
                id="extra-inspection", zone_id="F3" if case == "ambiguous" else "3B",
                kind="rough_in", status="passed", scheduled_at=datetime(2026, 11, 14, 15, tzinfo=UTC),
            ))
        elif case == "no_task":
            statement.starts_at = datetime(2026, 11, 20, tzinfo=UTC)
            statement.ends_at = datetime(2026, 11, 21, tzinfo=UTC)
        elif case == "unassigned":
            statement.crew_id, statement.trade = None, None
        else:
            statement.zones, statement.unresolved_zones = [], ["Unknown Zone"]
        session.flush()
        work = list(rules.affected_work(session, statement, zones))
        if case == "unresolved":
            assert work == []
            return
        evaluation = rules.InspectionPassed().evaluate(session, work[0], zones)
        assert evaluation.status == "unknown"
        if case in {"missing", "ambiguous"}:
            assert evaluation.inspection_id is None
        elif case == "nearer":
            # Raw Inspection.status=passed is insufficient, even at a closer scope.
            assert evaluation.inspection_id == "extra-inspection"
        elif case == "no_task":
            assert work[0].task is None
            assert work[0].crew.lead_id == "lead-drywall"
        else:
            assert work[0].crew is work[0].task is None


def test_relationship_review_reevaluates_atomically_with_correct_audit(initialized, engine):
    evidence_id = inspection_claim(initialized)
    ingest(initialized)
    with Session(engine) as session, session.begin():
        record = session.get(models.Evidence, evidence_id)
        record.history.append(models.EvidenceReview(
            sequence=2, status="confirmed", actor_type="human", reviewer_id="synthetic-reviewer",
            reviewer_role="superintendent", decided_at=datetime.now(UTC), recorded_at=datetime.now(UTC),
        ))
    flag = initialized.get("/flags").json()[0]
    assert flag["evaluation"] == "satisfied"
    assert flag["audit"][-1]["source_ref"] == f"evidence:{evidence_id}"
    assert flag["audit"][-1]["actor"] == "synthetic-reviewer"
    # A rolled-back rejection must not leave a changed Flag or audit record.
    with Session(engine) as session:
        record = session.get(models.Evidence, evidence_id)
        record.history.append(models.EvidenceReview(
            sequence=3, status="rejected", actor_type="human", reviewer_id="synthetic-reviewer",
            reviewer_role="superintendent", decided_at=datetime.now(UTC), recorded_at=datetime.now(UTC),
        ))
        session.flush()
        session.rollback()
    assert initialized.get("/flags").json()[0] == flag


@pytest.mark.parametrize("claim_zone", ["F3", "3B", "3B-BATH", "3B-BATH-WALL"])
def test_new_llm_counterclaim_triggers_review_without_changing_confirmation(initialized, engine, monkeypatch, claim_zone):
    from unittest.mock import Mock
    from app import ingestion
    from app.extraction import ExtractedBatch, ExtractedEvent

    evidence_id = inspection_claim(initialized)
    review(engine, evidence_id, "confirmed")
    ingest(initialized)
    extractor = Mock(name="synthetic-counterclaim")
    extractor.name = "test"
    extractor.extract.return_value = ExtractedBatch(events=[ExtractedEvent(
        intent="inspection_result", quote="Synthetic inspection failed.", confidence=1,
        zones=[claim_zone], inspection_kind="rough_in", claim="failed",
    )])
    monkeypatch.setattr(ingestion, "get_extractor", lambda: extractor)
    ingest(initialized, external_id="llm-counterclaim", text="Synthetic inspection failed.")
    flag = initialized.get("/flags").json()[0]
    assert flag["evaluation"] == "contradictory"
    assert {item["review_status"] for item in flag["evidence"]} == {"confirmed", "unconfirmed"}
    failed = next(item for item in flag["evidence"] if item["claim"] == "failed")
    review(engine, failed["id"], "rejected")
    assert initialized.get("/flags").json()[0]["evaluation"] == "satisfied"


def test_next_precondition_reuses_shared_engine(initialized, monkeypatch):
    class ExtraPrecondition:
        type = "test"
        name = "test_requirement"

        def applies(self, work):
            return work.event.intent == "planned_work"

        def evaluate(self, session, work, zones):
            return rules.Evaluation("unknown", "Synthetic extra requirement")

    monkeypatch.setattr(rules, "PRECONDITIONS", (*rules.PRECONDITIONS, ExtraPrecondition()))
    ingest(initialized)
    assert {flag["type"] for flag in initialized.get("/flags").json()} == {"A", "test"}


def test_seed_reset_clears_flags_links_and_audit(initialized, engine, seed):
    ingest(initialized)
    assert initialized.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
    assert initialized.get("/flags").json() == []
    with Session(engine) as session:
        for model in (models.Flag, models.FlagSource, models.FlagAudit):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_inbox_sorts_severity_and_has_no_mutation_routes(initialized, engine):
    ingest(initialized)
    with Session(engine) as session, session.begin():
        first = session.scalar(select(models.Flag))
        for severity in ("low", "medium"):
            session.add(models.Flag(**{
                column.name: getattr(first, column.name) for column in models.Flag.__table__.columns
                if column.name not in {"id", "open_key", "severity"}
            }, id=severity, open_key=severity, severity=severity))
    assert [item["severity"] for item in initialized.get("/flags").json()] == ["high", "medium", "low"]
    assert initialized.post("/flags", json={}).status_code == 405
    assert initialized.patch("/flags/low", json={"state": "resolved"}).status_code == 405


def test_migration_matches_models_and_downgrades(engine):
    with engine.begin() as connection:
        assert compare_metadata(MigrationContext.configure(connection), models.Base.metadata) == []
        config = Config(str(BACKEND / "alembic.ini"))
        config.attributes["connection"] = connection
        command.downgrade(config, "0004")
        command.upgrade(config, "head")


@pytest.mark.parametrize("zone,kind", [("3A-BATH", "rough_in"), ("3B-BATH", "insulation")])
def test_unrelated_counterclaims_do_not_invalidate_confirmed_inspection(initialized, engine, monkeypatch, zone, kind):
    from unittest.mock import Mock
    from app import ingestion
    from app.extraction import ExtractedBatch, ExtractedEvent

    evidence_id = inspection_claim(initialized)
    review(engine, evidence_id, "confirmed")
    ingest(initialized)
    extractor = Mock()
    extractor.name = "test"
    extractor.extract.return_value = ExtractedBatch(events=[ExtractedEvent(
        intent="inspection_result", quote="Synthetic unrelated inspection failed.", confidence=1,
        zones=[zone], inspection_kind=kind, claim="failed",
    )])
    monkeypatch.setattr(ingestion, "get_extractor", lambda: extractor)
    ingest(initialized, external_id="unrelated-counterclaim", text="Synthetic unrelated inspection failed.")
    assert initialized.get("/flags").json() == []


def test_confirmed_descendant_claim_cannot_certify_ancestor_inspection(initialized, engine, monkeypatch):
    from unittest.mock import Mock
    from app import ingestion
    from app.extraction import ExtractedBatch, ExtractedEvent

    original = ingestion.get_extractor
    extractor = Mock()
    extractor.name = "test"
    extractor.extract.return_value = ExtractedBatch(events=[ExtractedEvent(
        intent="inspection_result", quote="Synthetic bathroom inspection passed.", confidence=1,
        zones=["3B-BATH"], inspection_kind="rough_in", claim="passed",
    )])
    monkeypatch.setattr(ingestion, "get_extractor", lambda: extractor)
    result = ingest(initialized, external_id="descendant-pass", text="Synthetic bathroom inspection passed.")
    evidence = result["events"][0]["evidence"][0]
    assert evidence["scope"]["inspection_id"] is None
    review(engine, evidence["id"], "confirmed")
    monkeypatch.setattr(ingestion, "get_extractor", original)
    ingest(initialized)
    flag = initialized.get("/flags").json()[0]
    assert flag["evaluation"] == "unknown"
    assert flag["evidence"][0]["id"] == evidence["id"]
