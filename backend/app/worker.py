import logging
import os
import time

import httpx
from google.auth.exceptions import GoogleAuthError

from app.api_client import check_api
from app.gmail import GmailClient, GmailError, GmailSettings
from app.gmail_polling import poll_gmail
from app.outbox_delivery import deliver_outbox
from app.telegram import TelegramClient, TelegramError, TelegramSettings, deliver_telegram_outbox, poll_telegram

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    enabled = os.environ.get("GMAIL_ENABLED", "false").lower()
    if enabled not in {"true", "false"}:
        raise SystemExit("GMAIL_ENABLED must be true or false")
    settings = GmailSettings.from_env() if enabled == "true" else None
    telegram_enabled = os.environ.get("TELEGRAM_ENABLED", "false").lower()
    if telegram_enabled not in {"true", "false"}:
        raise SystemExit("TELEGRAM_ENABLED must be true or false")
    telegram_settings = TelegramSettings.from_env() if telegram_enabled == "true" else None
    interval = settings.poll_seconds if settings else 30
    if telegram_settings:
        interval = min(interval, telegram_settings.poll_seconds)
    with httpx.Client() as gmail_http, httpx.Client(
        base_url=os.environ["API_BASE_URL"].rstrip("/"), timeout=90,
    ) as api:
        telegram = TelegramClient(telegram_settings, gmail_http) if telegram_settings else None
        while True:
            try:
                if settings:
                    poll_gmail(GmailClient(settings, gmail_http), api)
                else:
                    check_api("worker")
            except (httpx.HTTPError, GoogleAuthError, GmailError, OSError, ValueError, LookupError, TypeError) as error:
                logger.warning("Worker poll failed (%s); retry next interval", type(error).__name__)
            if settings and settings.send_enabled:
                try:
                    deliver_outbox(GmailClient(settings, gmail_http), api)
                except (httpx.HTTPError, GoogleAuthError, GmailError, OSError, ValueError, LookupError, TypeError) as error:
                    logger.warning("Outbox delivery failed (%s); retry next interval", type(error).__name__)
            if telegram:
                for operation in (poll_telegram, deliver_telegram_outbox):
                    try:
                        operation(telegram, api)
                    except (TelegramError, httpx.HTTPError, ValueError, LookupError, TypeError) as error:
                        logger.warning("Telegram operation deferred (%s)", type(error).__name__)
            elif os.environ.get("TELEGRAM_COMPLIANCE_KEY"):
                try:
                    response = api.post("/telegram/retention", headers={
                        "X-Telegram-Compliance-Key": os.environ["TELEGRAM_COMPLIANCE_KEY"],
                    })
                    response.raise_for_status()
                except (httpx.HTTPError, ValueError) as error:
                    logger.warning("Telegram retention deferred (%s)", type(error).__name__)
            time.sleep(interval)


if __name__ == "__main__":
    main()
