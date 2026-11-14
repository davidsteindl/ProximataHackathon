import logging
import os
import time

import httpx
from google.auth.exceptions import GoogleAuthError

from app.api_client import check_api
from app.gmail import GmailClient, GmailError, GmailSettings
from app.gmail_polling import poll_gmail

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    enabled = os.environ.get("GMAIL_ENABLED", "false").lower()
    if enabled not in {"true", "false"}:
        raise SystemExit("GMAIL_ENABLED must be true or false")
    settings = GmailSettings.from_env() if enabled == "true" else None
    interval = settings.poll_seconds if settings else 30
    with httpx.Client() as gmail_http, httpx.Client(
        base_url=os.environ["API_BASE_URL"].rstrip("/"), timeout=90,
    ) as api:
        while True:
            try:
                if settings:
                    poll_gmail(GmailClient(settings, gmail_http), api)
                else:
                    check_api("worker")
            except (httpx.HTTPError, GoogleAuthError, GmailError, OSError, ValueError, KeyError, TypeError) as error:
                logger.warning("Worker poll failed (%s); retry next interval", type(error).__name__)
            time.sleep(interval)


if __name__ == "__main__":
    main()
