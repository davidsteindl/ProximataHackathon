import base64
import json
from email import policy
from email.parser import BytesParser
from unittest.mock import Mock

import httpx
import pytest

from app.gmail import GmailClient, GmailError, GmailSettings, READ_SCOPE, SEND_SCOPE
from app.outbox_delivery import deliver_outbox
from test_rules import initialized, ingest


def credentials():
    return Mock(valid=True, token='test-token', scopes=[READ_SCOPE, SEND_SCOPE])


def settings():
    return GmailSettings('project@example.test', send_enabled=True)


def test_hero_to_mocked_gmail_updates_dashboard_status(initialized, engine):
    from sqlalchemy.orm import Session
    from app import models
    with Session(engine) as session, session.begin():
        session.get(models.CrewLead, 'lead-drywall').email = 'crew@example.test'
    ingest(initialized)
    received = []
    def handle(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'emailAddress': 'project@example.test'})
        assert request.url.path.endswith('/messages/send')
        raw = base64.urlsafe_b64decode(json.loads(request.content)['raw'])
        mail = BytesParser(policy=policy.default).parsebytes(raw)
        received.append(mail)
        return httpx.Response(200, json={'id': 'sent-hero'})
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        deliver_outbox(GmailClient(settings(), http, credentials()), initialized)
    assert len(received) == 1
    mail = received[0]
    assert mail['To'] == 'crew@example.test'
    assert mail['From'] == 'project@example.test'
    assert 'Zone 3B' in mail['Subject']
    assert 'rough-in-F3' in mail.get_content()
    assert 'source:' in mail.get_content() and '/#flag-' in mail.get_content()
    flag = initialized.get('/flags').json()[0]
    assert flag['state'] == 'notified'
    assert flag['notifications'][0]['provider_message_id'] == 'sent-hero'
    assert flag['notifications'][0]['status'] == 'sent'


@pytest.mark.parametrize('failure', ['gmail', 'missing', 'lost_report'])
def test_worker_failure_keeps_durable_message(initialized, engine, failure):
    from sqlalchemy.orm import Session
    from app import models
    if failure != 'missing':
        with Session(engine) as session, session.begin():
            session.get(models.CrewLead, 'lead-drywall').email = 'crew@example.test'
    ingest(initialized)
    gmail = Mock()
    gmail.send_warning.side_effect = GmailError('safe') if failure == 'gmail' else None
    gmail.send_warning.return_value = 'sent-id'
    if failure == 'lost_report':
        api = Mock()
        api.post.side_effect = [initialized.post('/outbox/claim'), httpx.ReadTimeout('lost')]
        with pytest.raises(httpx.ReadTimeout):
            deliver_outbox(gmail, api)
    else:
        deliver_outbox(gmail, initialized)
    message = initialized.get('/outbox').json()[0]
    assert message['status'] == ('sending' if failure == 'lost_report' else 'failed')
    assert initialized.get('/flags').json()[0]['state'] == 'detected'
    if failure == 'missing':
        gmail.send_warning.assert_not_called()
        assert message['error_code'] == 'missing_recipient'
    elif failure == 'gmail':
        assert message['error_code'] == 'gmail_error'


def test_empty_outbox_does_not_contact_gmail(initialized):
    gmail = Mock()
    deliver_outbox(gmail, initialized)
    gmail.send_warning.assert_not_called()


@pytest.mark.parametrize('case', ['disabled', 'wrong_mailbox', 'readonly_token', 'broad_scope'])
def test_outbound_account_and_scope_guards(case):
    config, creds = settings(), credentials()
    if case == 'disabled':
        config = GmailSettings('project@example.test')
        creds.scopes = [READ_SCOPE]
    elif case == 'readonly_token':
        creds.scopes = [READ_SCOPE]
    elif case == 'broad_scope':
        creds.scopes += ['https://mail.google.com/']
    calls = []
    def handle(request):
        calls.append(request.method)
        return httpx.Response(200, json={'emailAddress': 'personal@example.test'})
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(GmailError):
            GmailClient(config, http, creds).send_warning({'recipient': 'crew@example.test'})
    assert 'POST' not in calls


def test_oauth_send_is_explicit(tmp_path, monkeypatch):
    from app import gmail_auth
    flow = Mock()
    flow.run_local_server.return_value.refresh_token = 'test'
    flow.run_local_server.return_value.to_json.return_value = '{}'
    factory = Mock(return_value=flow)
    monkeypatch.setattr(gmail_auth.InstalledAppFlow, 'from_client_secrets_file', factory)
    monkeypatch.setattr('sys.argv', ['gmail_auth', '--send', '--token', str(tmp_path / 'token.json')])
    gmail_auth.main()
    assert factory.call_args.kwargs['scopes'] == [READ_SCOPE, SEND_SCOPE]


def test_inbound_failure_does_not_prevent_outbound_pass(monkeypatch):
    from app import worker
    monkeypatch.setenv('GMAIL_ENABLED', 'true')
    monkeypatch.setenv('API_BASE_URL', 'http://api.test')
    monkeypatch.setattr(worker.GmailSettings, 'from_env', lambda: settings())
    monkeypatch.setattr(worker, 'GmailClient', Mock())
    monkeypatch.setattr(worker, 'poll_gmail', Mock(side_effect=GmailError('synthetic')))
    deliver = Mock()
    monkeypatch.setattr(worker, 'deliver_outbox', deliver)
    class StopLoop(Exception):
        pass
    monkeypatch.setattr(worker.time, 'sleep', Mock(side_effect=StopLoop))
    with pytest.raises(StopLoop):
        worker.main()
    deliver.assert_called_once()


@pytest.mark.parametrize('address', ['crew@example.test\r\nBcc: x@example.test', 'a,b@example.test', 'not-an-email', ''])
def test_seed_rejects_invalid_delivery_addresses(seed, address):
    from app.schemas import Seed
    from pydantic import ValidationError
    payload = seed.model_dump()
    payload['crew_leads'][0]['email'] = address
    with pytest.raises(ValidationError):
        Seed.model_validate(payload)
