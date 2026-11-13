import logging
import os

import httpx

logger = logging.getLogger(__name__)


def check_api(service: str) -> None:
    url = os.environ["API_BASE_URL"].rstrip("/") + "/health"
    response = httpx.get(url, timeout=5)
    response.raise_for_status()
    logger.info("%s reached api: %s", service, response.json())
