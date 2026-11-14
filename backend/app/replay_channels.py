"""Worker-side real-channel replay using the existing Gmail and Telegram adapters.

Test users send the prompted messages from their own mail/Telegram clients.
Bot-authored Telegram messages cannot stand in for inbound user messages.
"""

import base64
import json
import math
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import httpx

from app.gmail import GmailClient, GmailSettings
from app.gmail_polling import poll_gmail
from app.ingestion_schemas import SourceMessageInput
from app.outbox_delivery import deliver_outbox
from app.replay import ReplayError, request
from app.telegram import TelegramClient, TelegramSettings, deliver_telegram_outbox, handle_update


def matches(source, step):
    return (source.text == step.source_text and source.sender_role == step.sender_role
            and source.sender_crew_id == step.sender_crew_id)


def has_attachment(source, step, plans):
    if not step.attachment:
        return True
    expected = (plans / step.attachment).read_bytes()
    return any(item.file_name == step.attachment and base64.b64decode(item.content_base64) == expected
               for item in source.attachments)


class ScenarioAPI:
    """Keep real provider identities, simulated source time and the original transport time."""
    def __init__(self, api, step, sent_at, run_id, plans):
        self.api, self.step, self.sent_at, self.run_id, self.plans = api, step, sent_at, run_id, plans
        self.result = None

    def get(self, path, **kwargs):
        return self.api.get(path, **kwargs)

    def post(self, path, **kwargs):
        if path != "/ingestion/messages":
            raise ReplayError("Online replay adapter may only ingest source messages")
        source = SourceMessageInput.model_validate(kwargs["json"])
        if not matches(source, self.step):
            raise ReplayError("Received message does not match the current scenario step")
        if not has_attachment(source, self.step, self.plans):
            raise ReplayError(f"Expected exact synthetic attachment {self.step.attachment}")
        provenance = {"mode": "online", "run_id": self.run_id, "step": self.step.id,
                      "transport_sent_at": source.sent_at.isoformat(), "scenario_sent_at": self.sent_at.isoformat()}
        attachments = [item.model_dump() for item in source.attachments] + [{
            "file_name": "replay-transport.json", "media_type": "application/json",
            "content_base64": base64.b64encode(json.dumps(provenance).encode()).decode(),
        }]
        # Revalidate the normal ingestion schema, including the attachment limit.
        payload = SourceMessageInput.model_validate({**source.model_dump(), "sent_at": self.sent_at, "attachments": attachments})
        response = self.api.post(path, json=payload.model_dump(mode="json"))
        if not response.is_error:
            self.result = response.json()
        return response


class SingleMail:
    """A selected, freshly received test mail still runs through poll_gmail."""
    def __init__(self, gmail, source):
        self.settings, self.source = gmail.settings, source

    def message_ids(self):
        yield self.source.external_id, None

    def read_message(self, message_id, label_id):
        return self.source


class OnlineChannels:
    def __init__(self, api, gmail, telegram, run_id, plans, log, *, timeout=180, output=print, sleep=time.sleep):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ReplayError("Online message timeout must be finite and positive")
        self.api, self.gmail, self.telegram = api, gmail, telegram
        self.run_id, self.plans, self.log = run_id, plans, log
        self.timeout, self.output, self.sleep = timeout, output, sleep
        self.used, self.delivered = set(), set()

    def receive(self, step, sent_at):
        since = datetime.now(UTC) - timedelta(seconds=1)
        proxy = ScenarioAPI(self.api, step, sent_at, self.run_id, self.plans)
        self.output(f"REAL {step.channel.upper()}: send from test role {step.sender_role}, Crew {step.sender_crew_id or '-'}")
        if step.channel == "gmail":
            self.output(f"To: {self.gmail.settings.mailbox}\nSubject: {step.subject}\nBody: {step.text}")
            if step.attachment:
                self.output(f"Attach: {self.plans / step.attachment}")
        else:
            self.output(f"Send as an allowlisted human test user in an allowlisted chat: {step.text}")
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if step.channel == "gmail":
                for identifier, label in self.gmail.message_ids():
                    identity = ("gmail", identifier)
                    if identity in self.used:
                        continue
                    source = self.gmail.read_message(identifier, label)
                    # A mail read once that is old or does not match can never match a later
                    # step either (each step only accepts mails sent after its prompt).
                    if source is None or source.sent_at < since or not matches(source, step):
                        self.used.add(identity)
                        continue
                    if not has_attachment(source, step, self.plans):
                        self.used.add(identity)
                        self.output(f"Mail lacks the unchanged {step.attachment}; resend it with the exact file")
                        continue
                    poll_gmail(SingleMail(self.gmail, source), proxy)
                    if proxy.result is not None:
                        self.used.add(identity)
                        return proxy.result
            else:
                for update in self.telegram.updates():
                    message = update.get("message", {})
                    sender, chat = message.get("from", {}), message.get("chat", {})
                    identifier = str(message.get("message_id"))
                    identity = ("telegram", str(chat.get("id")), identifier)
                    eligible = (identity not in self.used and not sender.get("is_bot", False)
                        and self.telegram.allowed(chat.get("id"), sender.get("id"))
                        and self.telegram.settings.roles.get(str(sender.get("id")), "unknown") == step.sender_role
                        and self.telegram.settings.crews.get(str(sender.get("id"))) == step.sender_crew_id
                        and message.get("text") == step.text
                        and datetime.fromtimestamp(message.get("date", 0), UTC) >= since)
                    if eligible:
                        handle_update(self.telegram, proxy, update)
                    elif update.get("my_chat_member") or message.get("text", "").startswith("/"):
                        # Compliance commands/notices still reach the API; confirming the offset
                        # below would otherwise drop them for good while the worker is stopped.
                        handle_update(self.telegram, self.api, update)
                    self.telegram.offset = update["update_id"] + 1
                    if proxy.result is not None:
                        self.used.add(identity)
                        return proxy.result
            self.sleep(min(2, max(0, deadline - time.monotonic())))
        raise ReplayError(f"No matching real {step.channel} message for {step.id}; check role/Crew mapping and allowlists")

    def deliver(self):
        for _ in range(200):
            before = request(self.api, "get", "/outbox")
            pending = [item for item in before if item["status"] not in {"sent", "cancelled"}]
            if not pending:
                return
            deliver_outbox(self.gmail, self.api)
            deliver_telegram_outbox(self.telegram, self.api)
            after = request(self.api, "get", "/outbox")
            for item in after:
                if item["status"] == "sent" and item["id"] not in self.delivered:
                    self.log("real_delivery", message=item)
                    self.delivered.add(item["id"])
            if [(item["id"], item["status"]) for item in before] == [(item["id"], item["status"]) for item in after]:
                raise ReplayError("Outbox delivery is pending or failed; inspect configuration and retry after the backoff")
        raise ReplayError("Unexpectedly large outbox; stopped channel delivery")


@contextmanager
def online_channels(api, run_id, plans, log, timeout):
    # Reuse the worker's existing configuration. Credentials never enter the API.
    gmail_settings, telegram_settings = GmailSettings.from_env(), TelegramSettings.from_env()
    if not gmail_settings.send_enabled:
        raise ReplayError("Online replay requires GMAIL_SEND_ENABLED=true for factual notifications")
    with httpx.Client(timeout=30) as provider_http:
        gmail = GmailClient(gmail_settings, provider_http)
        telegram = TelegramClient(telegram_settings, provider_http)
        if gmail.get("profile").get("emailAddress", "").lower() != gmail_settings.mailbox:
            raise ReplayError("Dedicated project mailbox does not match the authorized account")
        telegram.call("getMe", {})
        yield OnlineChannels(api, gmail, telegram, run_id, plans, log, timeout=timeout)
