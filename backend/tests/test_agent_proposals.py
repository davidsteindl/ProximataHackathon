import pytest

from test_lifecycle import action, signal
from test_rules import initialized, ingest


def proposal(client, **changes):
    flag = client.get("/flags").json()[0]
    return client.post("/agent/proposals", headers={"X-SiteMind-Client": "mcp"}, json={
        "flag_id": flag["id"], "action": "Postpone drywall in 3B",
        "rationale": "Inspection proof is unconfirmed; ask the Superintendent to review.", **changes,
    })


def test_proposal_is_persisted_with_sources_without_any_execution(initialized, seed):
    ingest(initialized)
    before = {path: initialized.get(path).json() for path in ("/flags", "/evidence", "/tasks", "/outbox")}
    response = proposal(initialized)
    assert response.status_code == 201, response.text
    value = response.json()
    assert value["status"] == "proposed" and value["channel"] == "mcp"
    assert f"flag:{before['/flags'][0]['id']}" in value["source_refs"]
    assert any(ref.startswith("source:") for ref in value["source_refs"])
    assert initialized.get(f"/proposals/{value['id']}").json() == value
    assert initialized.get("/proposals", params={"flag_id": value["flag_id"]}).json() == [value]
    assert {path: initialized.get(path).json() for path in before} == before
    assert initialized.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
    assert initialized.get("/proposals").json() == []


@pytest.mark.parametrize("changes", [
    {"status": "approved"}, {"review_status": "confirmed"}, {"actor": "superintendent"},
    {"channel": "dashboard"}, {"source_refs": ["invented:proof"]}, {"action": " "},
    {"rationale": " "}, {"action": "x" * 4001},
])
def test_proposal_rejects_extra_powers_and_invalid_advice(initialized, changes):
    ingest(initialized)
    assert proposal(initialized, **changes).status_code == 422
    assert initialized.get("/proposals").json() == []


def test_unknown_and_closed_flag_proposals_are_rejected(initialized, engine):
    ingest(initialized)
    assert proposal(initialized, flag_id="unknown").status_code == 404
    flag = initialized.get("/flags").json()[0]
    signal(engine, flag["id"], "notified")
    flag = initialized.get(f"/flags/{flag['id']}").json()
    assert action(initialized, flag, "false_alarm").status_code == 200
    response = initialized.post("/agent/proposals", json={
        "flag_id": flag["id"], "action": "Do not execute", "rationale": "Closed Flag",
    })
    assert response.status_code == 409
    assert initialized.get("/proposals/unknown").status_code == 404
