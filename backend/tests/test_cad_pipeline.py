import io
import json
from pathlib import Path

import ezdxf
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.cad_extract import contains, line_overlaps_polygon
from app.cad_import import import_plan
from app.seed import import_seed

CAD = Path(__file__).resolve().parents[2] / "cad"
ENTRIES = json.loads((CAD / "import-metadata.json").read_text())


@pytest.fixture
def seeded(engine, seed):
    with Session(engine) as session:
        import_seed(session, seed)
    return engine


def upload(client, entry, source=None, **metadata_changes):
    metadata = {**entry["metadata"], **metadata_changes}
    path = CAD / entry["file"]
    return client.post("/geometry/import", data=metadata, files={
        "file": (path.name, path.read_bytes() if source is None else source, "image/vnd.dxf"),
    })


def changed_source(change):
    doc = ezdxf.readfile(CAD / ENTRIES[2]["file"])
    change(doc)
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode(doc.encoding)


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda entry: entry["metadata"]["revision_id"])
def test_all_committed_plans_import_and_keep_original_source(seeded, client, entry):
    response = upload(client, entry)
    assert response.status_code == 200, response.text
    revision_id = entry["metadata"]["revision_id"]
    geometry = client.get("/geometry", params={"revision_id": revision_id}).json()[0]
    assert geometry["units"] == "m"
    assert geometry["floor_id"] == entry["metadata"]["floor_id"]
    assert geometry["floor_height_m"] == 3
    assert geometry["floor_elevation_m"] == (int(geometry["floor_id"][1:]) - 1) * 3
    assert {element["kind"] for element in geometry["elements"]} == {"unit", "room", "wall", "door", "plumbing_fixture", "drain"}
    assert len([element for element in geometry["elements"] if element["kind"] == "unit"]) == 4
    assert len([element for element in geometry["elements"] if element["kind"] == "room"]) == 24
    assert geometry["ignored_layers"] == []
    source = client.get(f"/geometry/revisions/{revision_id}/source")
    assert source.status_code == 200
    assert source.content == (CAD / entry["file"]).read_bytes()
    assert geometry["source_sha256"] == response.json()["source_sha256"]
    assert upload(client, entry).json() == response.json()


def test_3b_geometry_links_room_and_element_zones_and_uses_metre_coordinates(seeded, client):
    entry = ENTRIES[2]
    assert upload(client, entry).status_code == 200
    geometry = client.get("/geometry", params={"zone_id": "3B", "revision_id": "A-103-C"}).json()[0]
    elements = {element["element_id"]: element for element in geometry["elements"]}
    for element in elements.values():
        assert "3B" in element["zone_ids"]
    with Session(seeded) as session:
        stored = session.scalars(select(models.GeometryElement).where(models.GeometryElement.revision_id == "A-103-C")).all()
        for element in stored:
            if element.element_id.startswith("3B-"):
                assert "3B" in element.zone_ids, element.element_id
    wall = elements["3B-BATH-WALL"]
    assert {"3B", "3B-BATH", "3B-STOR", "3B-BATH-WALL"} <= set(wall["zone_ids"])
    assert wall["shape"]["segments"] == [[[22, 5.5], [22, 8.5]]]
    assert wall["shape"]["thickness_m"] == pytest.approx(0.1)
    assert elements["3B-DOOR-01"]["shape"]["width_m"] == 1
    assert elements["3B-FIXT-01"]["shape"]["block_name"] == "WC"
    assert elements["3B-FIXT-01"]["shape"]["position"] == [21.55, 5.9]
    bath = client.get("/geometry", params={"zone_id": "3B-BATH"}).json()[0]
    assert all("3B-BATH" in element["zone_ids"] or "3B-BATH-WALL" in element["zone_ids"] for element in bath["elements"])


def test_revisions_are_independent_latest_query_is_deterministic_and_no_domain_actions_occur(seeded, client):
    before_evidence = client.get("/evidence").json()
    for entry in reversed(ENTRIES):
        assert upload(client, entry).status_code == 200
    latest = client.get("/geometry").json()
    assert {item["revision_id"] for item in latest} == {"A-101-C", "A-102-C", "A-103-D", "A-104-C"}
    for label, x in (("C", 22), ("D", 22.3)):
        item = client.get("/geometry", params={"revision_id": f"A-103-{label}", "zone_id": "3B-BATH-WALL"}).json()[0]
        assert item["elements"][0]["shape"]["segments"][0][0][0] == pytest.approx(x)
    assert len(client.get("/geometry", params={"floor_id": "F3"}).json()) == 1
    assert client.get("/geometry", params={"floor_id": "F4", "zone_id": "3B"}).json() == []
    assert client.get("/geometry", params={"zone_id": "missing"}).status_code == 404
    assert client.get("/geometry", params={"floor_id": "3B"}).status_code == 404
    assert client.get("/geometry", params={"revision_id": "missing"}).status_code == 404
    assert client.get("/evidence").json() == before_evidence
    plan = next(item for item in client.get("/plans").json() if item["id"] == "A-103")
    assert plan["current_revision"]["label"] == "D"
    assert plan["current_revision"]["acknowledgments"] == []
    assert plan["current_revision"]["zone_ids"] == []  # changed-zone discovery is #17
    assert plan["revisions"][0]["acknowledgments"][0]["revision_id"] == "A-103-C"


def test_shared_wall_associates_both_units_and_door_on_boundary_links_3b(seeded, client):
    assert upload(client, ENTRIES[2]).status_code == 200
    item = client.get("/geometry", params={"floor_id": "F3"}).json()[0]
    elements = {element["element_id"]: element for element in item["elements"]}
    assert {"3A", "3B"} <= set(elements["F3-WALL-08"]["zone_ids"])
    assert "3B" in elements["3B-DOOR-01"]["zone_ids"]


def test_unknown_layers_are_reported_and_ignored(seeded, client):
    def add_unknown(doc):
        doc.layers.new("CUSTOM-NOTES")
        doc.modelspace().add_circle((0, 0), 100, dxfattribs={"layer": "CUSTOM-NOTES"})
    response = upload(client, ENTRIES[2], changed_source(add_unknown))
    assert response.status_code == 200, response.text
    assert response.json()["ignored_layers"] == [{"layer": "CUSTOM-NOTES", "entity_count": 1}]
    geometry = client.get("/geometry", params={"floor_id": "F3"}).json()[0]
    assert geometry["ignored_layers"] == response.json()["ignored_layers"]
    assert all(element["layer"] != "CUSTOM-NOTES" for element in geometry["elements"])


@pytest.mark.parametrize("invalid", ["unreadable", "wrong_units", "unknown_label", "missing_label", "duplicate_id", "curved_wall", "open_area"])
def test_invalid_plan_does_not_create_revision_or_geometry(seeded, client, invalid):
    def change(doc):
        if invalid == "wrong_units":
            doc.units = ezdxf.units.M
        elif invalid in {"unknown_label", "missing_label"}:
            label = next(entity for entity in doc.modelspace().query("TEXT") if entity.dxf.text == "3B-BATH")
            if invalid == "unknown_label":
                label.dxf.text = "UNKNOWN-ROOM"
            else:
                doc.modelspace().delete_entity(label)
        elif invalid == "duplicate_id":
            walls = list(doc.modelspace().query('LWPOLYLINE[layer=="A-WALL"]'))
            walls[1].set_xdata("SITEMIND", walls[0].get_xdata("SITEMIND"))
        elif invalid == "curved_wall":
            wall = next(iter(doc.modelspace().query('LWPOLYLINE[layer=="A-WALL"]')))
            points = list(wall.get_points())
            x, y, start, end, _ = points[0]
            points[0] = (x, y, start, end, 0.5)
            wall.set_points(points)
        elif invalid == "open_area":
            next(iter(doc.modelspace().query('LWPOLYLINE[layer=="A-AREA"]'))).closed = False
    data = b"not a DXF" if invalid == "unreadable" else changed_source(change)
    response = upload(client, ENTRIES[2], data, revision_id="A-103-X", label="X", sequence=10)
    assert response.status_code == 422, response.text
    with Session(seeded) as session:
        assert session.get(models.Revision, "A-103-X") is None
        assert session.scalar(select(func.count()).select_from(models.PlanGeometry)) == 0


def test_metadata_and_source_conflicts_do_not_overwrite_original(seeded, client):
    entry = ENTRIES[2]
    assert upload(client, entry, floor_id="F4").status_code == 422
    assert upload(client, entry, sequence=44).status_code == 409
    assert upload(client, entry).status_code == 200
    assert upload(client, entry, changed_source(lambda doc: doc.modelspace().add_text("Changed", dxfattribs={"layer": "A-ANNO-TTLB"}))).status_code == 409
    assert client.get("/geometry/revisions/A-103-C/source").content == (CAD / entry["file"]).read_bytes()


def test_seed_reset_cascades_geometry_and_sources(seeded, seed, client):
    for entry in ENTRIES:
        assert upload(client, entry).status_code == 200
    with Session(seeded) as session:
        import_seed(session, seed)
    assert client.get("/geometry").json() == []
    assert client.get("/geometry/revisions/A-103-C/source").status_code == 404
    with Session(seeded) as session:
        assert session.scalar(select(func.count()).select_from(models.GeometryElement)) == 0


def test_fallback_handle_ids_are_explicit_when_xdata_is_absent(seeded, client):
    def remove_xdata(doc):
        for entity in doc.modelspace():
            if entity.has_xdata("SITEMIND"):
                entity.discard_xdata("SITEMIND")
    response = upload(client, ENTRIES[2], changed_source(remove_xdata))
    assert response.status_code == 200, response.text
    elements = client.get("/geometry").json()[0]["elements"]
    assert all(element["element_id"].startswith("handle:") for element in elements if element["kind"] == "wall")
    assert any(element["element_id"] == "3B-BATH" for element in elements)


def test_segment_membership_handles_shared_boundaries_and_excludes_corner_only_touch():
    polygon = [(0, 0), (2, 0), (2, 2), (0, 2)]
    assert contains((0, 1), polygon)
    assert line_overlaps_polygon((0, -1), (0, 3), polygon)
    assert line_overlaps_polygon((-1, 1), (3, 1), polygon)
    assert not line_overlaps_polygon((-1, -1), (0, 0), polygon)
    assert not line_overlaps_polygon((-1, -1), (-2, -2), polygon)
