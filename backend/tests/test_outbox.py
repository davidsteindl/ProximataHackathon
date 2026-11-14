from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app import models, rules
from conftest import BACKEND
from test_rules import initialized, ingest


def test_outbox_migration_extends_revision_notes_and_round_trips(engine):
    config = Config(str(BACKEND / "alembic.ini"))
    assert ScriptDirectory.from_config(config).get_heads() == ["0007"]
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0006")
        inspector = inspect(connection)
        assert "outbox_messages" not in inspector.get_table_names()
        assert "email" not in {column["name"] for column in inspector.get_columns("crew_leads")}
        assert "context" in {column["name"] for column in inspector.get_columns("flags")}
        assert next(column for column in inspector.get_columns("revisions")
                    if column["name"] == "file_name")["nullable"]
        command.upgrade(config, "head")
        assert compare_metadata(MigrationContext.configure(connection), models.Base.metadata) == []


def warning(client):
    ingest(client)
    rows = client.get('/outbox').json()
    assert len(rows) == 1
    return rows[0]


def claim(client):
    response = client.post('/outbox/claim')
    assert response.status_code == 200, response.text
    return response.json()


def report(client, item, **changes):
    return client.post(f"/outbox/{item['id']}/result", json={
        'lease_token': item['lease_token'], 'status': 'sent', 'provider_message_id': 'gmail-test', **changes,
    })


def due(engine):
    with Session(engine) as session, session.begin():
        session.scalar(select(models.OutboxMessage)).available_at = datetime.now(UTC) - timedelta(seconds=1)


def test_warning_is_atomic_deduplicated_and_factual(initialized, engine, monkeypatch):
    monkeypatch.setenv('DASHBOARD_BASE_URL', 'https://demo.example.test')
    row = warning(initialized)
    assert row['status'] == 'pending' and row['attempts'] == 0
    assert row['recipient'] is None
    assert 'rough-in-F3' in row['content']
    assert 'Evaluation at detection: unknown' in row['content']
    assert 'unconfirmed statement' in row['content']
    assert f"https://demo.example.test/#flag-{row['flag_id']}" in row['content']
    assert 'source:' in row['content']
    ingest(initialized, external_id='another-work-source')
    with Session(engine) as session:
        rules.evaluate_site(session)
        session.flush()
        session.rollback()
    assert initialized.get('/outbox').json() == [row]
    assert initialized.get('/outbox', params={'flag_id': row['flag_id']}).json() == [row]


def test_recipient_comes_from_site_record_and_success_notifies_once(initialized, engine):
    with Session(engine) as session, session.begin():
        session.get(models.CrewLead, 'lead-drywall').email = 'crew@example.test'
    warning(initialized)
    item = claim(initialized)
    assert item['recipient'] == 'crew@example.test'
    assert item['attempts'] == 1
    assert claim(initialized) is None
    assert report(initialized, item).status_code == 200
    flag = initialized.get('/flags').json()[0]
    assert flag['state'] == 'notified'
    assert {x['action'] for x in flag['audit']} >= {'delivery_attempted', 'delivery_sent', 'notified'}
    assert report(initialized, item).status_code == 200
    assert initialized.get('/flags').json()[0] == flag
    assert claim(initialized) is None


def test_failure_visible_retries_and_rejects_stale_worker(initialized, engine):
    warning(initialized)
    first = claim(initialized)
    response = report(initialized, first, status='failed', provider_message_id=None, error_code='gmail_error')
    assert response.status_code == 200
    assert response.json()['status'] == 'failed'
    assert initialized.get('/flags').json()[0]['state'] == 'detected'
    assert claim(initialized) is None
    due(engine)
    second = claim(initialized)
    assert second['attempts'] == 2 and second['lease_token'] != first['lease_token']
    assert report(initialized, first).status_code == 409
    # Crash after claiming: lease expiry makes the durable message available again.
    due(engine)
    third = claim(initialized)
    assert third['attempts'] == 3
    assert report(initialized, second).status_code == 409
    assert report(initialized, third).status_code == 200


@pytest.mark.parametrize('state', ['acknowledged', 'in_progress', 'resolved', 'false_alarm'])
def test_delivery_never_regresses_or_closes_flag(initialized, engine, state):
    warning(initialized)
    item = claim(initialized)
    with Session(engine) as session, session.begin():
        session.get(models.Flag, item['flag_id']).state = state
    assert report(initialized, item).status_code == 200
    assert initialized.get(f"/flags/{item['flag_id']}").json()['state'] == state


def test_invalid_delivery_report_and_reset(initialized, seed):
    warning(initialized)
    item = claim(initialized)
    assert report(initialized, item, provider_message_id=None).status_code == 422
    assert report(initialized, item, status='failed').status_code == 422
    assert report(initialized, item, status='failed', provider_message_id=None, error_code='missing_recipient').status_code == 200
    assert initialized.get('/outbox').json()[0]['error_code'] == 'missing_recipient'
    assert initialized.post('/seed/import', json=seed.model_dump(mode='json')).status_code == 200
    assert initialized.get('/outbox').json() == []


def test_flag_and_outbox_rollback_together(initialized, engine, monkeypatch):
    from app import outbox
    original = outbox.enqueue_flag_warning
    def fail(*args):
        original(*args)
        raise RuntimeError('synthetic transaction failure')
    monkeypatch.setattr(outbox, 'enqueue_flag_warning', fail)
    with pytest.raises(RuntimeError, match='synthetic'):
        ingest(initialized)
    with Session(engine) as session:
        assert session.scalar(select(models.Flag)) is None
        assert session.scalar(select(models.OutboxMessage)) is None
