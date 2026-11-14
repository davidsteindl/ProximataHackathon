"""Read-only Gmail adapter. Credentials and mailbox content stay in the worker."""

import base64
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from html.parser import HTMLParser
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from pydantic import TypeAdapter

from app.ingestion_schemas import SenderRole, SourceMessageInput

READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_URL = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailError(Exception):
    """Safe, content-free error suitable for logs."""


@dataclass(frozen=True)
class GmailSettings:
    mailbox: str
    label: str = "INBOX"
    token_file: str = "/gmail/token.json"
    poll_seconds: float = 15
    sender_roles: dict[str, SenderRole] | None = None

    @classmethod
    def from_env(cls):
        mailbox = os.environ.get("GMAIL_MAILBOX", "").strip().lower()
        if not mailbox or parseaddr(mailbox)[1] != mailbox or "@" not in mailbox:
            raise GmailError("invalid_mailbox")
        try:
            interval = float(os.environ.get("GMAIL_POLL_SECONDS", "15"))
            if not 1 <= interval <= 3600:
                raise ValueError
            roles = TypeAdapter(dict[str, SenderRole]).validate_python(
                json.loads(os.environ.get("GMAIL_SENDER_ROLES_JSON") or "{}"),
            )
        except (ValueError, TypeError):
            raise GmailError("invalid_polling_configuration") from None
        return cls(
            mailbox=mailbox, label=os.environ.get("GMAIL_LABEL", "INBOX").strip(),
            token_file=os.environ.get("GMAIL_TOKEN_FILE", "/gmail/token.json"),
            poll_seconds=interval, sender_roles={key.lower(): value for key, value in roles.items()},
        )


def save_token(credentials, path):
    """Replace atomically; never print a token or place it in the image."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(credentials.to_json(), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


class GmailClient:
    def __init__(self, settings, http, credentials=None):
        self.settings, self.http = settings, http
        self.credentials = credentials or Credentials.from_authorized_user_file(settings.token_file)
        if set(self.credentials.scopes or ()) != {READ_SCOPE}:
            raise GmailError("expected_readonly_scope")

    def get(self, resource, **params):
        if not self.credentials.valid:
            self.credentials.refresh(Request())
            save_token(self.credentials, self.settings.token_file)
        response = self.http.get(
            f"{GMAIL_URL}/{resource}", params=params,
            headers={"Authorization": f"Bearer {self.credentials.token}"}, timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def message_ids(self):
        # Validate the authenticated account before reading any message content.
        if self.get("profile").get("emailAddress", "").lower() != self.settings.mailbox:
            raise GmailError("mailbox_mismatch")
        label_id = None
        if self.settings.label:
            labels = self.get("labels").get("labels", [])
            label_id = next((label["id"] for label in labels if label["name"] == self.settings.label), None)
            if label_id is None:
                raise GmailError("label_not_found")
        page = None
        while True:
            params = {"maxResults": 100, "q": "-in:sent -in:drafts", "includeSpamTrash": "false"}
            if label_id:
                params["labelIds"] = label_id
            if page:
                params["pageToken"] = page
            result = self.get("messages", **params)
            for message in result.get("messages", []):
                yield message["id"], label_id
            page = result.get("nextPageToken")
            if not page:
                break

    def read_message(self, message_id, label_id):
        from urllib.parse import quote

        message = self.get(f"messages/{quote(message_id, safe='')}", format="raw")
        # A label may have been removed since list(). Never ingest outside the selected label.
        labels = message.get("labelIds", [])
        if (label_id and label_id not in labels) or {"SENT", "DRAFT", "SPAM", "TRASH"}.intersection(labels):
            return None
        return decode_message(message, self.settings)


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"br", "p", "div", "li", "tr"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "li", "tr"} and not self.hidden:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _body_text(part):
    """Select one multipart alternative; never treat attached messages as body text."""
    if part.get_filename() or part.get_content_disposition() == "attachment":
        return ""
    if part.is_multipart():
        children = list(part.iter_parts())
        if part.get_content_subtype() == "alternative":
            children.sort(key=lambda child: child.get_content_type() != "text/plain")
            return next((text for child in children if (text := _body_text(child)).strip()), "")
        return "\n".join(filter(None, (_body_text(child) for child in children)))
    if part.get_content_type() == "text/plain":
        return part.get_content().strip()
    if part.get_content_type() == "text/html":
        parser = _HTMLText()
        parser.feed(part.get_content())
        return "".join(parser.parts).strip()
    return ""


def _attachments(part):
    if part.get_filename() or part.get_content_disposition() == "attachment":
        # RFC822 attachments are preserved as complete messages, not traversed as input.
        content = part.get_payload(decode=True)
        if content is None and part.get_content_type() == "message/rfc822":
            content = b"\n".join(child.as_bytes() for child in part.get_payload())
        if content is None:
            raise GmailError("unsupported_attachment")
        yield {
            "file_name": part.get_filename() or "attachment.bin",
            "media_type": part.get_content_type(),
            "content_base64": base64.b64encode(content).decode("ascii"),
        }
    elif part.is_multipart():
        for child in part.iter_parts():
            yield from _attachments(child)


def decode_message(message, settings):
    raw = base64.b64decode(message["raw"] + "=" * (-len(message["raw"]) % 4), altchars=b"-_", validate=True)
    mail = BytesParser(policy=policy.default).parsebytes(raw)
    sender = parseaddr(str(mail.get("From", "")))[1]
    if not sender:
        raise GmailError("missing_sender")
    subject, body = str(mail.get("Subject", "")).strip(), _body_text(mail).strip()
    # Subject is part of source text, using the existing ingestion contract unchanged.
    text = f"Subject: {subject}\n\n{body}" if subject else body
    return SourceMessageInput(
        channel="gmail", source_key=settings.mailbox, external_id=message["id"],
        sender_id=sender, sender_role=(settings.sender_roles or {}).get(sender.lower(), "unknown"),
        # Gmail internalDate is stable, UTC and independent of missing/forged Date headers.
        sent_at=datetime.fromtimestamp(int(message["internalDate"]) / 1000, UTC),
        text=text, attachments=list(_attachments(mail)),
    )
