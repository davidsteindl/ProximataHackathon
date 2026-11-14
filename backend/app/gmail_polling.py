"""Polling forwards sources only through the API; no local dedup database."""

import logging

import httpx
from google.auth.exceptions import GoogleAuthError

from app.gmail import GmailError

logger = logging.getLogger(__name__)


def poll_gmail(gmail, api):
    delivered = 0
    for message_id, label_id in gmail.message_ids():
        try:
            response = api.get("/source-messages", params={
                "channel": "gmail", "source_key": gmail.settings.mailbox, "external_id": message_id,
            })
            response.raise_for_status()
            existing = response.json()
            if existing and existing["status"] == "processed":
                continue
            source = gmail.read_message(message_id, label_id)
            if source is None:
                continue
            response = api.post("/ingestion/messages", json=source.model_dump(mode="json"))
            response.raise_for_status()
            if response.json()["source"]["status"] == "processed":
                delivered += 1
        except (httpx.HTTPError, GoogleAuthError, GmailError, OSError, ValueError, KeyError, TypeError) as error:
            # Do not log responses, message content, sender addresses or OAuth credentials.
            # Leave the source eligible for another attempt; one bad mail cannot block the rest.
            logger.warning("Gmail message deferred (%s); retry next poll", type(error).__name__)
    logger.info("Gmail poll complete: %d messages processed", delivered)
    return delivered
