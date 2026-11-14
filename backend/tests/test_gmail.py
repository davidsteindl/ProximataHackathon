import base64
from datetime import UTC, datetime
from email.message import EmailMessage
from unittest.mock import Mock

import httpx
import pytest
from pydantic import ValidationError

from app.gmail import GmailClient, GmailError, GmailSettings, READ_SCOPE, decode_message


MAILBOX = "project@example.test"
SETTINGS = GmailSettings(MAILBOX, sender_roles={"architect@example.test": "architect"})


def gmail_message(subject="Plan revision", body="Badwand 3B verschoben.", attachments=(), html=None, sender="architect@example.test"):
    mail = EmailMessage()
    mail["From"] = f"Team test sender <{sender}>"
    mail["To"] = MAILBOX
    mail["Subject"] = subject
    mail["Date"] = "Thu, 01 Jan 1970 00:00:00 +0000"
    mail.set_content(body)
    if html is not None:
        mail.add_alternative(html, subtype="html")
    for name, content in attachments:
        mail.add_attachment(content, maintype="application", subtype="octet-stream", filename=name)
    return {
        "id": "gmail-1", "internalDate": "1794561300000", "labelIds": ["INBOX"],
        "raw": base64.urlsafe_b64encode(mail.as_bytes()).decode().rstrip("="),
    }


def credentials():
    return Mock(valid=True, scopes=[READ_SCOPE], token="test-access-token")


def test_mime_metadata_alternatives_and_original_dxf():
    content = b"0\r\nSECTION\r\n\xff\x00\r\nEOF\r\n"
    source = decode_message(gmail_message(
        subject="Änderung 3B", attachments=[("A-103_RevD.dxf", content)],
        html="<p>Duplicate alternative must not appear</p>",
    ), SETTINGS)
    assert source.channel == "gmail"
    assert source.source_key == MAILBOX
    assert source.external_id == "gmail-1"
    assert source.sender_id == "architect@example.test"
    assert source.sender_role == "architect"
    assert source.sent_at == datetime.fromtimestamp(1794561300, UTC)
    assert source.text == "Subject: Änderung 3B\n\nBadwand 3B verschoben."
    assert source.attachments[0].file_name == "A-103_RevD.dxf"
    assert base64.b64decode(source.attachments[0].content_base64) == content


def test_html_only_mail_unknown_sender_role():
    mail = EmailMessage()
    mail["From"] = "someone@example.test"
    mail["Subject"] = "Inspection"
    mail.set_content("<p>Abnahme &amp; 3B</p><script>secret()</script><p>Tag 4</p>", subtype="html")
    data = gmail_message()
    data["raw"] = base64.urlsafe_b64encode(mail.as_bytes()).decode()
    source = decode_message(data, SETTINGS)
    assert source.sender_role == "unknown"
    assert "Abnahme & 3B" in source.text
    assert "Tag 4" in source.text
    assert "secret" not in source.text


@pytest.mark.parametrize("attachments", [
    [("large.dxf", b"x" * 2_000_001)],
    [(f"{i}.dxf", b"test") for i in range(6)],
    [("../escape.dxf", b"test")],
])
def test_ingestion_limits_reject_whole_mail_without_silent_attachment_loss(attachments):
    with pytest.raises(ValidationError):
        decode_message(gmail_message(attachments=attachments), SETTINGS)


def test_attached_email_is_not_ingested_as_body():
    mail = EmailMessage()
    mail["From"] = "architect@example.test"
    mail.set_content("Actual body")
    attached = EmailMessage()
    attached.set_content("Do not extract this as the message body")
    mail.add_attachment(attached, filename="forwarded.eml")
    data = gmail_message()
    data["raw"] = base64.urlsafe_b64encode(mail.as_bytes()).decode()
    source = decode_message(data, SETTINGS)
    assert source.text == "Actual body"
    assert source.attachments[0].file_name == "forwarded.eml"
    assert b"Do not extract" in base64.b64decode(source.attachments[0].content_base64)


def test_mailbox_guard_prevents_reading_content():
    calls = []

    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"emailAddress": "personal@example.test"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = GmailClient(SETTINGS, http, credentials())
        with pytest.raises(GmailError, match="mailbox_mismatch"):
            list(client.message_ids())
    assert calls == ["/gmail/v1/users/me/profile"]


def test_label_filter_pagination_and_read_only_requests():
    calls = []

    def handle(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer test-access-token"
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress": MAILBOX})
        if request.url.path.endswith("/labels"):
            return httpx.Response(200, json={"labels": [{"id": "Label_42", "name": "SiteMind"}]})
        assert request.url.params["labelIds"] == "Label_42"
        assert request.url.params["q"] == "-in:sent -in:drafts"
        assert request.url.params["includeSpamTrash"] == "false"
        if request.url.params.get("pageToken") == "page-2":
            return httpx.Response(200, json={"messages": [{"id": "two"}]})
        return httpx.Response(200, json={"messages": [{"id": "one"}], "nextPageToken": "page-2"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = GmailClient(GmailSettings(MAILBOX, label="SiteMind"), http, credentials())
        assert list(client.message_ids()) == [("one", "Label_42"), ("two", "Label_42")]
    assert len(calls) == 4


def test_missing_label_does_not_fall_back_to_entire_mailbox():
    def handle(request):
        return httpx.Response(200, json={"emailAddress": MAILBOX, "labels": []})

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(GmailError, match="label_not_found"):
            list(GmailClient(SETTINGS, http, credentials()).message_ids())


@pytest.mark.parametrize("labels", [["OTHER"], ["INBOX", "TRASH"], ["INBOX", "SENT"]])
def test_recheck_label_before_ingestion(labels):
    def handle(request):
        assert request.url.params["format"] == "raw"
        return httpx.Response(200, json={"labelIds": labels})

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        assert GmailClient(SETTINGS, http, credentials()).read_message("one", "INBOX") is None


def test_overbroad_scopes_rejected():
    creds = credentials()
    creds.scopes = [READ_SCOPE, "https://mail.google.com/"]
    with pytest.raises(GmailError, match="expected_readonly_scope"):
        GmailClient(SETTINGS, Mock(), creds)


def test_refresh_saves_token_without_exposing_it(tmp_path, monkeypatch):
    creds = credentials()
    creds.valid = False
    creds.to_json.return_value = '{"refresh_token":"test-only"}'
    request_factory = Mock()
    monkeypatch.setattr("app.gmail.Request", request_factory)
    token_file = tmp_path / "token.json"
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={}))) as http:
        GmailClient(GmailSettings(MAILBOX, token_file=str(token_file)), http, creds).get("profile")
    creds.refresh.assert_called_once_with(request_factory.return_value)
    assert token_file.read_text() == creds.to_json.return_value
    assert not token_file.with_suffix(".tmp").exists()


def test_settings(monkeypatch):
    monkeypatch.setenv("GMAIL_MAILBOX", "Project@Example.test")
    monkeypatch.setenv("GMAIL_POLL_SECONDS", "2")
    monkeypatch.setenv("GMAIL_SENDER_ROLES_JSON", '{"Architect@Example.test":"architect"}')
    settings = GmailSettings.from_env()
    assert settings.mailbox == MAILBOX
    assert settings.poll_seconds == 2
    assert settings.sender_roles == {"architect@example.test": "architect"}
    monkeypatch.setenv("GMAIL_POLL_SECONDS", "nan")
    with pytest.raises(GmailError):
        GmailSettings.from_env()


def test_local_oauth_requests_only_read_scope(tmp_path, monkeypatch):
    from app import gmail_auth

    flow = Mock()
    flow.run_local_server.return_value.refresh_token = "test-refresh"
    flow.run_local_server.return_value.to_json.return_value = '{"test":true}'
    factory = Mock(return_value=flow)
    monkeypatch.setattr(gmail_auth.InstalledAppFlow, "from_client_secrets_file", factory)
    token_file = tmp_path / "token.json"
    monkeypatch.setattr("sys.argv", ["gmail_auth", "--client-secret", "client.json", "--token", str(token_file)])
    gmail_auth.main()
    factory.assert_called_once_with("client.json", scopes=[READ_SCOPE])
    assert flow.run_local_server.call_args.kwargs["access_type"] == "offline"
    assert flow.run_local_server.call_args.kwargs["prompt"] == "consent"
    assert token_file.exists()
