from types import SimpleNamespace

import pytest

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


def hero_payload(content=None, text=None):
    import base64
    import json
    from conftest import BACKEND
    from test_cad_pipeline import CAD

    payload = json.loads((BACKEND / 'demo/revision-note.json').read_text())
    if text is not None:
        payload['text'] = text
    payload['attachments'] = [{
        'file_name': 'A-103_RevD.dxf', 'media_type': 'image/vnd.dxf',
        'content_base64': base64.b64encode((CAD / ENTRIES[3]['file']).read_bytes() if content is None else content).decode(),
    }]
    return payload


def test_hero_mail_diff_drives_b_and_retains_source_and_evidence_boundary(seeded, client, monkeypatch):
    from test_revision_rules import plumbing, receipt
    from test_rules import review

    assert upload(client, ENTRIES[2]).status_code == 200
    before = client.get('/evidence').json()
    payload = hero_payload()
    result = client.post('/ingestion/messages', json=payload).json()
    assert result['source']['status'] == 'processed', result
    event = result['events'][0]
    assert event['origin'] == 'deterministic_plan_diff'
    assert event['details']['plan_diff']['affected_zone_ids'] == ['3B']
    assert event['zone_ids'] == ['3B']
    assert event['quote'] == payload['text']
    assert event['details']['attachment_id'] == result['source']['attachments'][0]['id']
    assert client.get('/evidence').json() == before
    flag = plumbing(client)
    assert flag['context']['affected_zones_origin'] == 'deterministic_plan_diff'
    assert flag['context']['acknowledged_revision'] == 'C'
    assert flag['evaluation'] == 'unknown'
    assert {item['zone_id'] for item in client.get('/flags').json()} == {'3B'}
    assert client.post('/ingestion/messages', json=payload).json()['events'] == result['events']
    assert next(plan for plan in client.get('/plans').json() if plan['id'] == 'A-103')['current_revision']['zone_ids'] == ['3B']
    evidence_id = receipt(client, monkeypatch)
    assert plumbing(client)['evaluation'] == 'unknown'
    review(seeded, evidence_id, 'confirmed')
    assert plumbing(client)['evaluation'] == 'satisfied'
    assert plumbing(client)['state'] == 'detected'
    review(seeded, evidence_id, 'rejected')
    assert plumbing(client)['evaluation'] == 'unknown'


def test_geometry_overrides_broad_note_before_flags_are_created(seeded, client, monkeypatch):
    from test_revision_rules import statement

    assert upload(client, ENTRIES[2]).status_code == 200
    result = statement(client, monkeypatch, zones=['F3'], attachments=hero_payload()['attachments'])
    assert result['events'][0]['zone_ids'] == ['3B']
    assert {flag['zone_id'] for flag in client.get('/flags').json()} == {'3B'}
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app import models
    with Session(seeded) as session:
        messages = session.scalars(select(models.OutboxMessage)).all()
        assert messages
        assert all(session.get(models.Flag, message.flag_id).zone_id == '3B' for message in messages)
    statement(client, monkeypatch, external_id='later-broad-note', zones=['F3'])
    assert {flag['zone_id'] for flag in client.get('/flags').json()} == {'3B'}


def test_identical_attachment_does_not_fall_back_to_note_zones(seeded, client):
    from test_cad_pipeline import CAD

    assert upload(client, ENTRIES[2]).status_code == 200
    result = client.post('/ingestion/messages', json=hero_payload((CAD / ENTRIES[2]['file']).read_bytes())).json()
    assert result['events'][0]['zone_ids'] == []
    assert result['events'][0]['details']['diff_status'] == 'succeeded'
    assert client.get('/flags').json() == []


def test_attachment_only_revision_does_not_need_llm(seeded, client):
    assert upload(client, ENTRIES[2]).status_code == 200
    result = client.post('/ingestion/messages', json=hero_payload(text='')).json()
    assert result['source']['extraction_backend'] == 'attachment_only'
    assert result['events'][0]['origin'] == 'deterministic_plan_diff'
    assert {flag['zone_id'] for flag in client.get('/flags').json()} == {'3B'}


@pytest.mark.parametrize('missing_baseline', [False, True])
def test_diff_failure_preserves_note_fallback_and_marks_reason(seeded, client, missing_baseline):
    if not missing_baseline:
        assert upload(client, ENTRIES[2]).status_code == 200
    result = client.post('/ingestion/messages', json=hero_payload(None if missing_baseline else b'broken DXF')).json()
    assert result['source']['status'] == 'processed'
    event = result['events'][0]
    assert event['origin'] == 'llm_statement'
    assert event['details']['diff_status'] == 'failed'
    assert event['details']['diff_error']
    flags = client.get('/flags').json()
    assert flags
    assert all(flag['context']['diff_status'] == 'failed' for flag in flags)
    assert all(flag['context']['affected_zones_origin'] == 'unconfirmed_revision_note' for flag in flags)
    assert client.get('/geometry/revisions/A-103-D/source').status_code == 404


def test_deterministic_diff_survives_llm_failure(seeded, client, monkeypatch):
    from unittest.mock import Mock
    from app import ingestion
    from app.extraction import ExtractionError

    assert upload(client, ENTRIES[2]).status_code == 200
    extractor = Mock()
    extractor.name = 'unavailable'
    extractor.extract.side_effect = ExtractionError('provider_unavailable')
    monkeypatch.setattr(ingestion, 'get_extractor', lambda: extractor)
    response = client.post('/ingestion/messages', json=hero_payload())
    assert response.status_code == 201
    result = response.json()
    assert result['source']['status'] == 'processed'
    assert result['source']['error_code'] == 'provider_unavailable'
    assert result['events'][0]['origin'] == 'deterministic_plan_diff'
    assert {flag['zone_id'] for flag in client.get('/flags').json()} == {'3B'}


@pytest.mark.parametrize('changes', [{'crew': 'drywall'}, {'zones': ['3A']}, {'label': 'C'}])
def test_diff_does_not_accept_confirmed_mismatched_receipt(seeded, client, monkeypatch, changes):
    from test_revision_rules import plumbing, receipt
    from test_rules import review

    assert upload(client, ENTRIES[2]).status_code == 200
    client.post('/ingestion/messages', json=hero_payload())
    evidence_id = receipt(client, monkeypatch, **changes)
    review(seeded, evidence_id, 'confirmed')
    assert plumbing(client)['evaluation'] == 'unknown'


def test_seed_reset_removes_diff_events_and_source_provenance(seeded, seed, client):
    from sqlalchemy.orm import Session
    from app.seed import import_seed

    assert upload(client, ENTRIES[2]).status_code == 200
    assert client.post('/ingestion/messages', json=hero_payload()).status_code == 201
    with Session(seeded) as session:
        import_seed(session, seed)
    assert client.get('/events').json() == []
    assert client.get('/flags').json() == []
    assert client.get('/geometry').json() == []


def test_unassignable_changed_geometry_requires_fallback():
    from app.cad_extract import InvalidPlan

    element = Element(element_id='hall', kind='wall', layer='A-WALL', shape=Shape(), zone_ids=['F3'])
    with pytest.raises(InvalidPlan, match='unit zone'):
        compare_elements([], [element], {'F3': SimpleNamespace(kind='floor')})


def test_diff_does_not_skip_missing_immediately_previous_geometry(seeded, client, monkeypatch):
    from test_revision_rules import statement

    assert upload(client, ENTRIES[2]).status_code == 200
    statement(client, monkeypatch)  # Register D without geometry.
    assert upload(client, ENTRIES[3], revision_id='A-103-E', label='E', sequence=5).status_code == 200
    assert client.get('/geometry/revisions/A-103-E/diff').status_code == 409


def test_failed_text_and_diff_leave_source_retryable_without_partial_events(seeded, client, monkeypatch):
    from unittest.mock import Mock
    from app import ingestion
    from app.extraction import ExtractionError

    extractor = Mock()
    extractor.name = 'unavailable'
    extractor.extract.side_effect = ExtractionError('provider_unavailable')
    monkeypatch.setattr(ingestion, 'get_extractor', lambda: extractor)
    payload = hero_payload()
    failed = client.post('/ingestion/messages', json=payload)
    assert failed.status_code == 502
    assert client.get('/events').json() == []
    assert client.get('/flags').json() == []
    assert upload(client, ENTRIES[2]).status_code == 200
    retried = client.post('/ingestion/messages', json=payload)
    assert retried.status_code == 200
    assert retried.json()['source']['id'] == failed.json()['source']['id']
    assert retried.json()['events'][0]['origin'] == 'deterministic_plan_diff'
