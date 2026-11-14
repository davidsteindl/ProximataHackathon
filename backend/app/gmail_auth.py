"""One-time local OAuth consent for the dedicated project test account."""

import argparse
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from app.gmail import READ_SCOPE, SEND_SCOPE, save_token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-secret", default=".gmail/client-secret.json")
    parser.add_argument("--token", default=".gmail/token.json")
    parser.add_argument("--send", action="store_true", help="Also authorize factual outbox sending")
    args = parser.parse_args()
    flow = InstalledAppFlow.from_client_secrets_file(args.client_secret, scopes=[READ_SCOPE, SEND_SCOPE] if args.send else [READ_SCOPE])
    credentials = flow.run_local_server(
        host="localhost", port=0, access_type="offline", prompt="consent",
        authorization_prompt_message="Open the browser to authorize the project test mailbox.",
        success_message="Authorization complete. You may close this window.",
    )
    if not credentials.refresh_token:
        raise SystemExit("No refresh token received; revoke the app grant and authorize again.")
    save_token(credentials, Path(args.token))
    print("Gmail authorization saved locally. No credentials were printed.")


if __name__ == "__main__":
    main()
