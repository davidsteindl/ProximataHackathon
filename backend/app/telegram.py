"""Polling Telegram adapter. Credentials and provider traffic stay in worker."""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
from pydantic import TypeAdapter

from app.ingestion_schemas import SenderRole, SourceMessageInput


class TelegramError(Exception):
    pass


@dataclass
class TelegramSettings:
    token: str = field(repr=False)
    chats: set[str]
    users: set[str]
    compliance_key: str = field(repr=False)
    roles: dict[str, str]
    crews: dict[str, str]
    poll_seconds: int = 2

    @classmethod
    def from_env(cls):
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        key = os.environ.get("TELEGRAM_COMPLIANCE_KEY", "")
        chat_values = json.loads(os.environ.get("TELEGRAM_ALLOWED_CHATS_JSON") or "[]")
        user_values = json.loads(os.environ.get("TELEGRAM_ALLOWED_USERS_JSON") or "[]")
        if not isinstance(chat_values, list) or not isinstance(user_values, list):
            raise ValueError("Telegram allowlists must be arrays")
        chats, users = {str(value) for value in chat_values}, {str(value) for value in user_values}
        roles = json.loads(os.environ.get("TELEGRAM_SENDER_ROLES_JSON") or "{}")
        crews = json.loads(os.environ.get("TELEGRAM_SENDER_CREWS_JSON") or "{}")
        interval = int(os.environ.get("TELEGRAM_POLL_SECONDS", "2"))
        if not token or not key or interval < 1:
            raise ValueError("Telegram requires token, compliance key and positive poll interval")
        if any(not re.fullmatch(r"-?[1-9][0-9]{0,18}", value) for value in chats) or any(
            not re.fullmatch(r"[1-9][0-9]{0,18}", value) for value in users
        ):
            raise ValueError("Telegram allowlists require numeric IDs")
        if not isinstance(roles, dict) or not isinstance(crews, dict):
            raise ValueError("Telegram role and Crew maps must be objects")
        for role in roles.values():
            TypeAdapter(SenderRole).validate_python(role)
        return cls(token, chats, users, key, roles, crews, interval)


class TelegramClient:
    def __init__(self, settings, http):
        self.settings, self.http = settings, http
        self.offset = 0

    def call(self, method, payload):
        try:
            response = self.http.post(
                f"https://api.telegram.org/bot{self.settings.token}/{method}", json=payload,
            )
            response.raise_for_status()
            result = response.json()
            if result.get("ok") is not True:
                raise TelegramError("telegram_rejected")
            return result["result"]
        except (httpx.HTTPError, ValueError, KeyError):
            raise TelegramError("telegram_unavailable") from None

    def updates(self):
        return self.call("getUpdates", {"offset": self.offset, "timeout": 0,
                                       "allowed_updates": ["message", "my_chat_member"]})

    def allowed(self, chat, sender):
        return str(chat) in self.settings.chats and str(sender) in self.settings.users

    def send_warning(self, message):
        recipient = str(message["recipient"])
        if not self.allowed(recipient, recipient):
            raise TelegramError("recipient_not_allowlisted")
        return self.send(message)

    def send(self, message):
        recipient = str(message["recipient"])
        if recipient not in self.settings.chats:
            raise TelegramError("chat_not_allowlisted")
        if not recipient.startswith("-") and recipient not in self.settings.users:
            raise TelegramError("user_not_allowlisted")
        content = message["content"]
        chunks = ([content] if len(content.encode("utf-16-le")) // 2 <= 4096
                  else [content[start:start + 1800] for start in range(0, len(content), 1800)])
        if not content:
            raise TelegramError("empty_message")
        for index, chunk in enumerate(chunks):
            text = f"Teil {index + 1}/{len(chunks)}\n{chunk}" if len(chunks) > 1 else chunk
            result = self.call("sendMessage", {"chat_id": recipient, "text": text})
        return str(result["message_id"])


def handle_update(telegram, api, update):
    message = update.get("message") or update.get("my_chat_member") or {}
    chat = message.get("chat", {})
    sender = message.get("from", {})
    if not telegram.allowed(chat.get("id"), sender.get("id")) or sender.get("is_bot", False):
        return
    sender_id, chat_id = str(sender["id"]), str(chat["id"])
    command = None
    membership = update.get("my_chat_member")
    text = message.get("text", "")
    if membership:
        if (membership["old_chat_member"]["status"] in {"left", "kicked"}
                and membership["new_chat_member"]["status"] in {"member", "administrator"}):
            command = "notice"
    elif text.startswith("/"):
        name = text.split()[0].split("@")[0]
        command = {"/my_data": "my_data", "/delete_my_data": "delete_my_data",
                   "/privacy": "notice"}.get(name, "help")
        if command in {"my_data", "delete_my_data"} and chat_id != sender_id:
            command = "help"
    elif text.strip():
        response = api.get("/source-messages", params={
            "channel": "telegram", "source_key": chat_id,
            "external_id": str(message["message_id"]),
        })
        response.raise_for_status()
        existing = response.json()
        if not existing or existing["status"] != "processed":
            source = SourceMessageInput(
                channel="telegram", source_key=chat_id, external_id=str(message["message_id"]),
                sender_id=sender_id, sender_role=telegram.settings.roles.get(sender_id, "unknown"),
                sender_crew_id=telegram.settings.crews.get(sender_id),
                sent_at=datetime.fromtimestamp(message["date"], UTC), text=text,
            )
            response = api.post("/ingestion/messages", json=source.model_dump(mode="json"))
            response.raise_for_status()
            if response.json()["source"]["status"] != "processed":
                raise TelegramError("ingestion_pending")
    if command:
        response = api.post("/telegram/commands", headers={
            "X-Telegram-Compliance-Key": telegram.settings.compliance_key,
        }, json={
            "request_id": str(update["update_id"]), "sender_id": sender_id,
            "chat_id": chat_id, "command": command,
        })
        response.raise_for_status()


def poll_telegram(telegram, api):
    headers = {"X-Telegram-Compliance-Key": telegram.settings.compliance_key}
    response = api.post("/telegram/retention", headers=headers)
    response.raise_for_status()
    failed_offset = None
    for update in telegram.updates():
        try:
            handle_update(telegram, api, update)
        except (httpx.HTTPError, TelegramError, ValueError, LookupError, TypeError):
            if failed_offset is None:
                failed_offset = update["update_id"]
        if failed_offset is None:
            telegram.offset = update["update_id"] + 1
    if failed_offset is not None:
        telegram.offset = failed_offset
        raise TelegramError("update_deferred")


def deliver_telegram_outbox(telegram, api):
    response = api.post("/outbox/claim", params={"channel": "telegram"})
    response.raise_for_status()
    message = response.json()
    if message is None:
        return
    result = {"lease_token": message["lease_token"]}
    try:
        if message["flag_id"] is None or str(message["recipient"]).startswith("-"):
            provider_id = telegram.send(message)
        else:
            provider_id = telegram.send_warning(message)
        result.update(status="sent", provider_message_id=provider_id)
    except (TelegramError, ValueError, TypeError):
        result.update(status="failed", error_code="telegram_error")
    response = api.post(f"/outbox/{message['id']}/result", json=result)
    response.raise_for_status()
