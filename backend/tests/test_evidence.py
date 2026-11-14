from copy import deepcopy
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.seed import import_seed


def store(engine, seed):
    with Session(engine) as session:
        return import_seed(session, seed)


def test_seed_baseline_and_statement_examples_have_distinct_provenance(engine, seed, client):
    assert store(engine, seed).evidence == len(seed.evidence)
    records = client.get("/evidence").json()
    assert len(records) == len(seed.evidence)
    assert len({record["import_ref"] for record in records}) == 1
    assert all(record["imported_at"] is not None for record in records)
    for record in records:
        assert record["source_ref"].startswith("seed:")
        assert record["quote"]
        assert len(record["history"]) == 1
        review = record["history"][0]
        assert review["actor_type"] == "seed_import"
        assert review["reviewer_id"] is review["reviewer_role"] is review["decided_at"] is None
        if record["origin"] == "seed_baseline":
            assert record["review_status"] == "confirmed"
            assert record["statement_ref"] is None
        else:
            assert record["review_status"] == "unconfirmed"
            assert record["statement_ref"].startswith("example-statement-")


def test_missing_ambiguous_and_contradictory_examples_do_not_change_domain_outcome(engine, seed, client):
    store(engine, seed)
    records = {record["id"]: record for record in client.get("/evidence").json()}
    assert records["example-missing-scope"]["scope"]["zone_id"] is None
    assert records["example-missing-scope"]["scope"]["inspection_id"] is None
    assert records["example-ambiguous"]["review_status"] == "unconfirmed"
    pair = [records["example-contradictory-positive"], records["example-contradictory-negative"]]
    assert {record["claim"] for record in pair} == {"passed", "failed"}
    assert pair[0]["scope"] == pair[1]["scope"]
    assert all(record["review_status"] == "unconfirmed" for record in pair)
    inspection = next(item for item in client.get("/inspections").json() if item["id"] == "rough-in-F3")
    assert inspection["status"] == "pending"
    assert client.get("/evidence", params={"inspection_id": "insulation-F3"}).json() == []


@pytest.mark.parametrize("invalid", [
    "confirmed_statement", "invented_human_review", "missing_baseline_scope",
    "wrong_inspection_zone", "wrong_revision_zone", "wrong_exact_revision",
    "claim_mismatch", "mixed_subject", "unknown_reference", "missing_provenance",
    "negative_ack_with_baseline_record",
])
def test_import_rejects_invalid_or_fabricated_confirmation(client, seed, invalid):
    data = seed.model_dump(mode="json")
    assert client.post("/seed/import", json=data).status_code == 200
    baseline = client.get("/evidence").json()
    data = deepcopy(data)
    record = data["evidence"][-1] if invalid == "confirmed_statement" else data["evidence"][0]
    if invalid == "confirmed_statement":
        record["review_status"] = "confirmed"
    elif invalid == "invented_human_review":
        record["history"] = [{"reviewer_id": "fake-reviewer", "status": "confirmed"}]
    elif invalid == "missing_baseline_scope":
        record["scope"]["zone_id"] = None
    elif invalid == "wrong_inspection_zone":
        data["evidence"][4]["scope"]["zone_id"] = "3B"
    elif invalid == "wrong_revision_zone":
        record["scope"]["zone_id"] = "3B"
    elif invalid == "wrong_exact_revision":
        data["acknowledgments"] = [ack for ack in data["acknowledgments"] if ack["revision_id"] != "A-101-C"]
    elif invalid == "claim_mismatch":
        data["evidence"][4]["claim"] = "passed"
    elif invalid == "mixed_subject":
        record["scope"]["task_id"] = "drywall-F3"
    elif invalid == "unknown_reference":
        record["scope"]["revision_id"] = "A-103-D"
    elif invalid == "missing_provenance":
        record["source_ref"] = "telegram:pretend-human-confirmation"
    elif invalid == "negative_ack_with_baseline_record":
        record["claim"] = "not_acknowledged"
    assert client.post("/seed/import", json=data).status_code == 422
    assert client.get("/evidence").json() == baseline


def test_negative_baseline_acknowledgment_without_record_is_accepted(client, seed):
    data = seed.model_dump(mode="json")
    data["evidence"][0]["claim"] = "not_acknowledged"
    data["acknowledgments"] = [
        ack for ack in data["acknowledgments"] if ack["revision_id"] != "A-101-C"
    ]
    assert client.post("/seed/import", json=data).status_code == 200
    record = client.get("/evidence", params={"revision_id": "A-101-C"}).json()[0]
    assert record["claim"] == "not_acknowledged"
    assert record["review_status"] == "confirmed"


def test_read_api_filters_scope_status_and_exposes_review_history(engine, seed, client):
    store(engine, seed)
    params = {"crew_id": "plumbing", "revision_id": "A-103-C", "review_status": "confirmed"}
    records = client.get("/evidence", params=params).json()
    assert [record["id"] for record in records] == ["baseline-ack-F3"]
    assert records[0]["scope"]["zone_id"] == "F3"
    assert client.get("/evidence", params={"revision_id": "A-103-D"}).json() == []
    assert len(client.get("/evidence", params={"zone_id": "B1"}).json()) == sum(
        item.scope.zone_id is not None for item in seed.evidence
    )
    assert client.get("/evidence", params={"zone_id": "3B"}).json() == []
    assert client.get("/evidence", params={"review_status": "invalid"}).status_code == 422
    assert client.get("/evidence", params={"zone_id": "missing"}).status_code == 404


def add_human_review(session, sequence, status):
    review = models.EvidenceReview(
        evidence_id="example-ambiguous", sequence=sequence, status=status,
        actor_type="human", reviewer_id="demo-reviewer", reviewer_role="superintendent",
        decided_at=datetime(2026, 11, 14, 18, tzinfo=UTC),
        recorded_at=datetime.now(UTC),
    )
    session.add(review)
    return review


def test_append_only_history_retains_decisions_without_overwriting_domain_state(engine, seed, client):
    store(engine, seed)
    # Exercise the storage contract for #9, without implementing its action endpoint.
    with Session(engine) as session, session.begin():
        add_human_review(session, 2, "confirmed")
    with Session(engine) as session, session.begin():
        add_human_review(session, 3, "rejected")
    record = next(item for item in client.get("/evidence").json() if item["id"] == "example-ambiguous")
    assert record["review_status"] == "rejected"
    assert [review["status"] for review in record["history"]] == ["unconfirmed", "confirmed", "rejected"]
    assert record["history"][1]["reviewer_id"] == "demo-reviewer"
    assert record["history"][1]["decided_at"] is not None
    assert next(item for item in client.get("/inspections").json() if item["id"] == "rough-in-F3")["status"] == "pending"
    assert record["source_ref"] == "seed:evidence.json#example-ambiguous"
    with Session(engine) as session:
        review = session.scalar(select(models.EvidenceReview).where(models.EvidenceReview.evidence_id == "example-ambiguous"))
        review.status = "rejected"
        with pytest.raises(ValueError, match="append-only"):
            session.commit()
    with Session(engine) as session:
        session.get(models.Evidence, "example-ambiguous").zone_id = "F4"
        with pytest.raises(ValueError, match="immutable"):
            session.commit()


def test_explicit_reset_restores_seed_trust_boundary_and_import_provenance(engine, seed, client):
    store(engine, seed)
    before = client.get("/evidence").json()
    with Session(engine) as session, session.begin():
        add_human_review(session, 2, "confirmed")
        session.add(models.Evidence(
            id="new-llm-statement", origin="llm_statement", statement_ref="statement-from-6",
            source_ref="test-source-message", quote="The inspection has passed.",
            kind="inspection", claim="passed", zone_id="F3", inspection_id="rough-in-F3",
            history=[models.EvidenceReview(
                sequence=1, status="unconfirmed", actor_type="statement_ingestion",
                recorded_at=datetime.now(UTC),
            )],
        ))
    assert next(record for record in client.get("/evidence").json() if record["id"] == "new-llm-statement")["review_status"] == "unconfirmed"
    store(engine, seed)
    after = client.get("/evidence").json()
    assert len(after) == len(before)
    assert after[0]["import_ref"] != before[0]["import_ref"]
    assert all(len(record["history"]) == 1 for record in after)
    assert all(record["review_status"] == "unconfirmed" for record in after if record["origin"] == "seed_statement")
    assert all(record["history"][0]["reviewer_id"] is None for record in after)


def test_task_evidence_scope_is_readable_without_changing_the_scheduled_task(client, seed):
    payload = seed.model_dump(mode="json")
    payload["evidence"].append({
        "id": "example-task", "origin": "seed_statement", "statement_ref": "example-task-statement",
        "source_ref": "seed:task-example", "quote": "Drywall F3 is completed.", "claim": "completed",
        "scope": {"kind": "task_completion", "zone_id": "F3", "task_id": "drywall-F3"},
    })
    assert client.post("/seed/import", json=payload).status_code == 200
    records = client.get("/evidence", params={"task_id": "drywall-F3"}).json()
    assert [record["id"] for record in records] == ["example-task"]
    assert records[0]["review_status"] == "unconfirmed"
    assert client.get("/tasks", params={"zone_id": "F3"}).json()[-1]["id"] == "drywall-F3"


def test_duplicate_review_sequence_cannot_overwrite_an_earlier_decision(engine, seed, client):
    store(engine, seed)
    with Session(engine) as session, session.begin():
        add_human_review(session, 2, "confirmed")
    with Session(engine) as session:
        add_human_review(session, 2, "rejected")
        with pytest.raises(IntegrityError):
            session.commit()
    record = next(item for item in client.get("/evidence").json() if item["id"] == "example-ambiguous")
    assert record["review_status"] == "confirmed"
    assert [review["status"] for review in record["history"]] == ["unconfirmed", "confirmed"]


def test_review_actor_constraints_and_unreviewed_default(engine, seed):
    store(engine, seed)
    with Session(engine) as session:
        session.add(models.EvidenceReview(
            evidence_id="example-ambiguous", sequence=2, status="confirmed",
            actor_type="statement_ingestion", reviewer_id=None, reviewer_role=None,
            decided_at=None, recorded_at=datetime.now(UTC),
        ))
        with pytest.raises(IntegrityError):
            session.commit()
    with Session(engine) as session:
        review = add_human_review(session, 2, "confirmed")
        review.reviewer_role = None
        with pytest.raises(IntegrityError):
            session.commit()
    assert models.Evidence(id="not-yet-reviewed").review_status == "unconfirmed"
