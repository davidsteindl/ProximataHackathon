import logging
import time

import httpx

from app.api_client import check_api


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            check_api("worker")
        except httpx.HTTPError:
            logging.exception("worker could not reach a healthy api")
        time.sleep(30)


if __name__ == "__main__":
    main()
