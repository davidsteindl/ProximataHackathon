from types import SimpleNamespace

from app.cad_schemas import Element, Shape
from app.plan_diff import compare_elements
from test_cad_pipeline import ENTRIES, seeded, upload  # noqa: F401


def test_hero_revision_diff_only_affects_3b(seeded, client):
    for entry in ENTRIES[2:4]:
        assert upload(client, entry).status_code == 200
    response = client.get('/geometry/revisions/A-103-D/diff')
    assert response.status_code == 200, response.text
    diff = response.json()
    assert diff['previous_revision_id'] == 'A-103-C'
    assert diff['origin'] == 'deterministic_plan_diff'
    assert diff['affected_zone_ids'] == ['3B']
    changes = {item['element_id']: item for item in diff['zones'][0]['changes']}
    assert {'3B-BATH-WALL', '3B-SANR-03'} <= changes.keys()
    assert changes['3B-BATH-WALL']['change'] == 'moved'
    assert all(key.startswith('3B') for key in changes)


def test_identical_geometry_is_empty_even_with_new_revision_metadata(seeded, client):
    from test_cad_pipeline import CAD

    assert upload(client, ENTRIES[2]).status_code == 200
    assert upload(client, ENTRIES[3], (CAD / ENTRIES[2]['file']).read_bytes()).status_code == 200
    assert client.get('/geometry/revisions/A-103-D/diff').json()['zones'] == []


def test_diff_reports_add_remove_and_old_and_new_zone_membership():
    zones = {key: SimpleNamespace(kind=kind) for key, kind in [('F3', 'floor'), ('3A', 'unit'), ('3B', 'unit')]}

    def element(key, zone, x=0):
        return Element(element_id=key, kind='drain', layer='P-SANR', shape=Shape(position=(x, 0)), zone_ids=['F3', zone])

    before = [element('removed', '3A'), element('moved', '3A')]
    after = [element('added', '3B'), element('moved', '3B', 1)]
    groups = compare_elements(before, after, zones)
    assert {group.zone_id: [(item.element_id, item.change) for item in group.changes] for group in groups} == {
        '3A': [('moved', 'moved'), ('removed', 'removed')],
        '3B': [('added', 'added'), ('moved', 'moved')],
    }
    assert compare_elements(before, list(reversed(before)), zones) == []


def test_missing_diff_inputs_are_explicit(seeded, client):
    assert client.get('/geometry/revisions/missing/diff').status_code == 404
    assert client.get('/geometry/revisions/A-103-C/diff').status_code == 409
