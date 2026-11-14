import pytest

from test_lifecycle import HUMAN, decision
from test_rules import initialized, ingest, inspection_claim


def test_zone_status_includes_covering_schedule_and_no_sibling_clearance(initialized):
    response = initialized.get("/context/zones/3B")
    assert response.status_code == 200, response.text
    status = response.json()
    assert status["zone"]["id"] == "3B"
    assert {zone["id"] for zone in status["zones"]} >= {"3B", "3B-BATH", "3B-BATH-WALL"}
    assert "3C" not in {zone["id"] for zone in status["zones"]}
    assert "drywall-F3" in {task["id"] for task in status["tasks"]}
    assert "rough-in-F3" in {item["id"] for item in status["inspections"]}
    assert all(item["evaluation"] == "unknown" for item in status["preconditions"])
    assert status["open_flags"] == []
    assert status["source_refs"] and "not grant clearance" in status["safety_notice"]
    assert initialized.get("/context/zones/absent").status_code == 404


def test_preconditions_follow_human_review_without_closing_flags(initialized):
    evidence_id = inspection_claim(initialized)
    ingest(initialized)
    status = initialized.get("/context/zones/3B").json()
    checks = [item for item in status["preconditions"] if item["name"] == "inspection_passed"]
    assert checks and {item["evaluation"] for item in checks} == {"unknown"}
    assert all(item["source_refs"] for item in checks)
    assert next(item for item in status["evidence"] if item["id"] == evidence_id)["review_status"] == "unconfirmed"
    flags_before = initialized.get("/flags").json()
    assert initialized.get("/context/zones/3B").status_code == 200
    assert initialized.get("/flags").json() == flags_before
    assert decision(initialized, evidence_id, "confirmed").status_code == 200
    status = initialized.get("/context/zones/3B").json()
    assert {item["evaluation"] for item in status["preconditions"] if item["name"] == "inspection_passed"} == {"satisfied"}
    assert status["open_flags"][0]["awaiting_human_closure"]
    assert status["open_flags"][0]["state"] == "detected"
    assert decision(initialized, evidence_id, "rejected").status_code == 200
    status = initialized.get("/context/zones/3B").json()
    assert {item["evaluation"] for item in status["preconditions"] if item["name"] == "inspection_passed"} == {"unknown"}


def test_search_and_timeline_preserve_review_status_sources_and_time_bounds(initialized):
    evidence_id = inspection_claim(initialized)
    ingest(initialized)
    results = initialized.get("/context/search", params={"query": evidence_id, "zone_id": "3B"}).json()
    evidence = next(item for item in results["entries"] if item["kind"] == "evidence")
    assert evidence["record"]["review_status"] == "unconfirmed"
    assert evidence["source_refs"][0].startswith("source:")
    assert decision(initialized, evidence_id, "confirmed").status_code == 200
    timeline = initialized.get("/context/timeline", params={"zone_id": "3B"}).json()
    assert all(item["source_refs"] for item in timeline["entries"])
    reviews = [item for item in timeline["entries"] if "/review/" in item["record_ref"]]
    assert any(item["record"]["review"]["status"] == "confirmed" for item in reviews)
    assert any("/audit/" in item["record_ref"] for item in timeline["entries"])
    assert any(item["kind"] == "event" and item["record"]["evidence"] for item in timeline["entries"])
    bounded = initialized.get("/context/timeline", params={
        "zone_id": "3B", "from_time": "2020-01-01T00:00:00Z", "to_time": "2020-01-02T00:00:00Z",
    }).json()
    assert bounded["entries"] == []
    assert initialized.get("/context/timeline", params={
        "from_time": "2026-11-15T00:00:00Z", "to_time": "2026-11-14T00:00:00Z",
    }).status_code == 422
    limited = initialized.get("/context/search", params={"query": "3B", "limit": 1}).json()
    assert len(limited["entries"]) == 1 and limited["truncated"] and limited["total_matches"] > 1
    assert initialized.get("/context/search", params={"query": " "}).status_code == 422
    assert initialized.get("/context/search", params={"query": "3B", "limit": 201}).status_code == 422


@pytest.mark.parametrize("agent", ["mcp", "chat", "agent"])
@pytest.mark.parametrize("path", [
    "/evidence/example/reviews", "/flags/example/actions", "/seed/import",
    "/ingestion/messages", "/geometry/import", "/outbox/example/status",
    "/proposals/example/approve",
])
def test_api_denies_direct_and_indirect_agent_mutations(initialized, path, agent):
    evidence_before = initialized.get("/evidence").json()
    response = initialized.post(path, headers={"X-SiteMind-Client": agent}, json={
        **HUMAN, "decision": "confirmed", "expected_sequence": 0, "reason": "Pretending to be human",
    })
    assert response.status_code == 403
    assert initialized.get("/evidence").json() == evidence_before
