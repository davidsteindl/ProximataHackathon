"""Worker REST-only outbox consumer; Gmail failures never discard a message."""

import httpx
from google.auth.exceptions import GoogleAuthError

from app.gmail import GmailError


def deliver_outbox(gmail, api):
    response = api.post("/outbox/claim")
    response.raise_for_status()
    message = response.json()
    if message is None:
        return
    result = {"lease_token": message["lease_token"]}
    try:
        if not message["recipient"]:
            result.update(status="failed", error_code="missing_recipient")
        else:
            provider_id = gmail.send_warning(message)
            result.update(status="sent", provider_message_id=provider_id)
    except (httpx.HTTPError, GoogleAuthError, GmailError, OSError, ValueError, TypeError):
        # Provider responses may contain sensitive data; persist only a safe code.
        result.update(status="failed", error_code="gmail_error")
    # Keep report failures outside the send handler: an uncertain result is
    # retried after lease expiry rather than overwritten with a false failure.
    response = api.post(f"/outbox/{message['id']}/result", json=result)
    response.raise_for_status()
