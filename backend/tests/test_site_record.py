from copy import deepcopy
from datetime import date
from unittest.mock import patch

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app import models, schemas
from app.seed import import_seed
from conftest import BACKEND


def import_snapshot(engine, seed):
    with Session(engine) as session:
        return import_seed(session, seed)


def test_seed_covers_agreed_zone_ids_and_hero_initial_state(seed):
    zones = {zone.id: zone for zone in seed.zones}
    assert len(zones) == 23
    assert {zone.id for zone in seed.zones if zone.kind == "unit"} == {
        f"{floor}{unit}" for floor in range(1, 5) for unit in "ABCD"
    }
    assert zones["F3"].parent_id == "B1"
    assert zones["3B"].parent_id == "F3"
    assert zones["3B-BATH"].parent_id == "3B"
    assert zones["3B-BATH-WALL"].parent_id == "3B-BATH"
    drywall = next(task for task in seed.tasks if task.id == "drywall-F3")
    assert (drywall.starts_at.date() - seed.site.start_date).days == 2
    assert next(item for item in seed.inspections if item.id == "rough-in-F3").status == "pending"
    assert any(item.crew_id == "plumbing" and item.revision_id == "A-103-C" for item in seed.acknowledgments)


def test_import_repeats_and_resets_modified_and_additional_records(engine, seed, client):
    first = import_snapshot(engine, seed)
    before = {path: client.get(path).json() for path in ("/site", "/zones", "/tasks", "/crews", "/plans", "/inspections")}
    with Session(engine) as session, session.begin():
        session.get(models.Inspection, "rough-in-F3").status = "passed"
        session.get(models.Crew, "plumbing").name = "Changed"
        session.add(models.Zone(id="obsolete", site_id=seed.site.id, parent_id="3B", kind="room", name="Obsolete"))
    assert import_snapshot(engine, seed) == first
    assert {path: client.get(path).json() for path in before} == before
    assert import_snapshot(engine, seed) == first


def test_import_transaction_rolls_back_after_database_failure(engine, seed):
    import_snapshot(engine, seed)
    with Session(engine) as session:
        with patch.object(session, "flush", side_effect=RuntimeError("failure after delete")):
            with pytest.raises(RuntimeError):
                import_seed(session, seed)
    with Session(engine) as session:
        assert session.get(models.Zone, "3B").parent_id == "F3"
        assert session.get(models.Site, seed.site.id).start_date == date(2026, 11, 13)


@pytest.mark.parametrize("invalid", [
    "unknown_parent", "wrong_parent_kind", "duplicate_zone", "missing_floor_height",
    "unknown_crew", "unknown_predecessor", "cyclic_tasks", "invalid_time_range",
    "naive_timestamp", "unknown_revision_zone", "wrong_plan_floor", "unknown_ack_crew",
    "ack_before_revision", "invalid_inspection_status", "unknown_inspection_zone",
    "duplicate_acknowledgment", "duplicate_revision_sequence",
])
def test_invalid_snapshot_is_rejected_without_changing_stored_state(client, seed, invalid):
    payload = seed.model_dump(mode="json")
    assert client.post("/seed/import", json=payload).status_code == 200
    data = deepcopy(payload)
    if invalid == "unknown_parent":
        data["zones"][-1]["parent_id"] = "missing"
    elif invalid == "wrong_parent_kind":
        data["zones"][-1]["parent_id"] = "B1"
    elif invalid == "duplicate_zone":
        data["zones"].append(data["zones"][0])
    elif invalid == "missing_floor_height":
        next(item for item in data["zones"] if item["id"] == "F3")["height_m"] = None
    elif invalid == "unknown_crew":
        data["tasks"][0]["crew_id"] = "missing"
    elif invalid == "unknown_predecessor":
        data["tasks"][0]["predecessor_ids"] = ["missing"]
    elif invalid == "cyclic_tasks":
        data["tasks"][0]["predecessor_ids"] = [data["tasks"][1]["id"]]
    elif invalid == "invalid_time_range":
        data["tasks"][0]["ends_at"] = data["tasks"][0]["starts_at"]
    elif invalid == "naive_timestamp":
        data["tasks"][0]["starts_at"] = "2026-11-13T07:00:00"
    elif invalid == "unknown_revision_zone":
        data["revisions"][0]["zone_ids"] = ["missing"]
    elif invalid == "wrong_plan_floor":
        data["revisions"][0]["zone_ids"] = ["3B"]
    elif invalid == "unknown_ack_crew":
        data["acknowledgments"][0]["crew_id"] = "missing"
    elif invalid == "ack_before_revision":
        data["acknowledgments"][0]["acknowledged_at"] = "2026-11-01T00:00:00Z"
    elif invalid == "invalid_inspection_status":
        data["inspections"][0]["status"] = "unknown"
    elif invalid == "unknown_inspection_zone":
        data["inspections"][0]["zone_id"] = "missing"
    elif invalid == "duplicate_acknowledgment":
        data["acknowledgments"].append(data["acknowledgments"][0])
    elif invalid == "duplicate_revision_sequence":
        revision = {**data["revisions"][0], "id": "duplicate", "label": "D"}
        data["revisions"].append(revision)
    response = client.post("/seed/import", json=data)
    assert response.status_code == 422
    assert client.get("/site").json() == payload["site"]
    assert len(client.get("/tasks").json()) == 12


def test_zone_tree_crews_and_inspections_read_api(engine, seed, client):
    import_snapshot(engine, seed)
    root = client.get("/zones").json()[0]
    assert root["id"] == "B1"
    floor = next(item for item in root["children"] if item["id"] == "F3")
    assert floor["height_m"] == 3
    assert floor["elevation_m"] == 6
    assert {item["id"] for item in floor["children"]} == {"3A", "3B", "3C", "3D"}
    assert next(item for item in client.get("/crews").json() if item["id"] == "plumbing")["lead"]["name"] == "Alex Example"
    response = client.get("/inspections", params={"zone_id": "F3"})
    assert response.status_code == 200
    assert {item["kind"] for item in response.json()} == {"rough_in", "insulation"}
    assert all(item["status"] == "pending" for item in response.json())
    assert len(client.get("/inspections", params={"zone_id": "B1"}).json()) == 8
    assert client.get("/inspections", params={"zone_id": "3B"}).json() == []


def test_task_filters_use_subtrees_and_half_open_overlap_in_utc(engine, seed, client):
    import_snapshot(engine, seed)
    params = {"zone_id": "F3", "from_time": "2026-11-15T07:00:00+01:00", "to_time": "2026-11-15T17:00:00+01:00"}
    response = client.get("/tasks", params=params)
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["drywall-F3"]
    assert response.json()[0]["predecessor_ids"] == ["insulation-F3"]
    assert len(client.get("/tasks", params={"zone_id": "B1"}).json()) == 12
    assert client.get("/tasks", params={"zone_id": "B1", "include_descendants": False}).json() == []
    assert client.get("/tasks", params={"from_time": "2026-11-15T16:00:00Z"}).json() == []
    assert client.get("/tasks", params={"to_time": "2026-11-13T07:00:00Z"}).json() == []
    assert client.get("/tasks", params={"zone_id": "missing"}).status_code == 404
    assert client.get("/tasks", params={"from_time": "2026-11-15T00:00:00"}).status_code == 422
    assert client.get("/tasks", params={"from_time": "2026-11-15T00:00:00Z", "to_time": "2026-11-14T00:00:00Z"}).status_code == 422


def test_plan_current_revision_uses_sequence_and_preserves_ack_history(engine, seed, client):
    data = seed.model_dump(mode="json")
    data["revisions"].append({
        "id": "A-103-AA", "plan_id": "A-103", "label": "AA", "sequence": 4,
        "issued_at": "2026-11-13T09:15:00Z", "file_name": "A-103_RevAA.dwg", "zone_ids": ["3B"],
    })
    import_snapshot(engine, schemas.Seed.model_validate(data))
    plan = next(item for item in client.get("/plans").json() if item["id"] == "A-103")
    assert plan["floor_id"] == "F3"
    assert plan["current_revision"]["label"] == "AA"
    assert plan["current_revision"]["acknowledgments"] == []
    assert plan["revisions"][0]["acknowledgments"][0]["crew_id"] == "plumbing"
    assert plan["revisions"][0]["label"] == "C"


def test_empty_record_and_openapi_contract(client):
    assert client.get("/site").json() is None
    for path in ("/zones", "/tasks", "/crews", "/plans", "/inspections", "/evidence"):
        assert client.get(path).json() == []
    spec = client.get("/openapi.json").json()
    assert {"/site", "/zones", "/tasks", "/crews", "/plans", "/inspections", "/seed/import", "/evidence"} <= spec["paths"].keys()
    assert "Seed" in spec["components"]["schemas"]


def test_migration_matches_models_and_round_trips(engine):
    config = Config(str(BACKEND / "alembic.ini"))
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, models.Base.metadata) == []
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
        assert inspect(connection).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
        assert "revision_acknowledgments" in inspect(connection).get_table_names()
        assert "evidence_reviews" in inspect(connection).get_table_names()
