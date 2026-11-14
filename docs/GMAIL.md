# Gmail inbound (#11)

The worker polls a dedicated **team project test account**, optionally restricted
by a label, and forwards source messages through `POST /ingestion/messages`.
It never connects to PostgreSQL. Gmail is disabled by default; the existing
health-only worker and offline ingestion continue to work without Google access.

## Google Cloud and OAuth (one-time local setup)

1. In Google Cloud Console, create/select the team's project and enable **Gmail
   API**. This Cloud project can also serve outbound Gmail in #10; this issue
   requests **only** `https://www.googleapis.com/auth/gmail.readonly`.
   `gmail.metadata` cannot read message bodies/attachments. No modify, send,
   full-mailbox management, password, service account or domain delegation is used.
2. Configure the **Google Auth platform / OAuth consent screen**: app name,
   support/contact details, audience **External**, publishing status **Testing**
   (or the team's permitted Internal audience). Add the dedicated project account
   under **Test users**. Only use team test accounts and synthetic messages.
3. Create an OAuth client with application type **Desktop app** and download its
   JSON to `.gmail/client-secret.json` at the repository root. A desktop client's
   local loopback callback needs no public server or webhook. Use the same
   repository worktree as the Compose stack. `.gmail/` is gitignored; never commit,
   upload, paste into chat, or include these files in an image.
4. Install the backend development requirements in a local Python environment,
   then run from the repository root:

   ```powershell
   $env:PYTHONPATH = 'backend'
   python -m app.gmail_auth
   ```

   POSIX shell: `PYTHONPATH=backend python -m app.gmail_auth`.
   The browser opens a Google login/consent flow. Select the **dedicated project
   test mailbox**, approve read-only access, and complete the loopback redirect.
   The command saves `.gmail/token.json` with offline refresh credentials; it
   never prints tokens. It also accepts `--client-secret <path>` and
   `--token <path>` if running outside the root. Both defaults are local paths,
   whereas `GMAIL_TOKEN_FILE` below is a container path.
5. Copy `.env.example` to `.env` if needed, retain your existing ports/passwords,
   and configure (replace example addresses with the team's accounts):

   ```dotenv
   GMAIL_ENABLED=true
   GMAIL_MAILBOX=sitemind-project@example.test
   GMAIL_LABEL=INBOX
   GMAIL_TOKEN_FILE=/gmail/token.json
   GMAIL_POLL_SECONDS=15
   GMAIL_SENDER_ROLES_JSON='{"architect@example.test":"architect","inspector@example.test":"inspector"}'
   ```

   `GMAIL_MAILBOX` must equal Gmail's authenticated profile address. A mismatch
   stops that poll **before** any message content is read. Labels use their exact
   Gmail **name** (e.g. `SiteMind`); the worker resolves the ID each poll. A missing
   label fails closed. Apply a Gmail filter to label incoming project mail before
   a poll. Explicitly set `GMAIL_LABEL=` to read the dedicated mailbox without a
   label restriction. Sent mail, drafts, spam and trash are always excluded;
   unread status is neither required nor changed. Do not send the demo mails from
   the receiving account itself (Gmail can label these as SENT).
6. Start the stack and import the baseline if it is not already present:

   ```sh
   docker compose up --build -d --wait
   docker compose exec api python -m app.seed
   docker compose logs --tail 50 worker
   ```

   **The seed command resets the demo Site Record, sources and Events.** Run it
   once to initialize a fresh stack; omit it for an existing populated baseline.
   After changing `.env`, recreate the worker with `docker compose up -d worker`.
   The default poll pause is 15 seconds, configurable between 1 and 3600 seconds.
   A pass processes messages sequentially; Gmail/API and extraction duration adds
   to this pause. Reload the dashboard to see newly ingested Events.

Compose mounts `.gmail/` read/write **only into worker** at `/gmail`. The write
access persists refreshed OAuth tokens atomically across restarts. Neither API,
MCP nor web receive these files or Gmail environment variables; the API alone
receives the LLM key. Keep this directory restricted to your local user. Each
worktree has its own `.gmail/`; copy/setup the authorized files locally as needed.

### Test-mode pitfalls and recovery

- External apps in **Testing** permit only registered test users. Add the project
  mailbox to Test users before signing in; otherwise consent can fail with
  `access_denied`. An unverified-app warning is expected for the team's test app;
  use only your own team's known Cloud project.
- Gmail scopes are outside the basic profile exception: refresh tokens for an
  External/Testing app expire after **7 days**. Access tokens also expire normally
  and are refreshed automatically. When refresh fails (`invalid_grant`, expired
  or revoked consent), rerun the local OAuth command and recreate/retry the
  worker. Restarting alone does not repair an expired refresh token.
- The command requests offline access and explicit consent. If no refresh token
  is returned, remove the team's app grant in the project account's Google
  Account connections and authorize again. Do not print tokens for diagnosis.
- The inbound worker requires a token requested with exactly `gmail.readonly`;
  a broader existing grant/token must be replaced with the inbound grant. #10
  can reuse the Cloud project/client setup and decide its minimal sending scopes
  in that issue; inbound does not request sending in advance.
- Messages that cannot be decoded or exceed ingestion's existing limits (5
  attachments, 2,000,000 bytes each, 50,000 text characters) are deferred as a
  whole, without silently truncating content or dropping an attachment. Move/fix
  an unsuitable test mail or its label. Other valid messages continue processing.
- Logs contain error **types** and aggregate counts, not message bodies, senders,
  provider responses or tokens. `HTTPStatusError` can indicate Gmail permission/
  quota failures or ingestion/extraction failure. Inspect the ingestion source
  status/error code via the API; configuration problems can be checked against
  the local settings above. There is no automatic live-LLM fallback.

## Hero-mail smoke test

For the default offline extraction cache, map the actual two sending test-account
addresses to `architect` and `inspector` as above. Send these exact **subjects and
plain-text bodies** to `GMAIL_MAILBOX` from the respective accounts. Avoid a mail
signature or quoted reply; cached mode matches the complete decoded text and role.
The test does require Gmail connectivity; only extraction is offline.

| Sender role | Subject | Body | Attachment |
| --- | --- | --- | --- |
| architect | `Plan A-103 Rev D` | `Plan A-103 Rev D: Badwand 3B um 30 cm verschoben, Abwasserleitung neu geführt.` | `cad/plans/A-103_RevD.dxf` |
| inspector | `Abnahme verschoben` | `Abnahme der Rohinstallation im 3. OG auf Tag 4 verschoben.` | none |
| inspector | `Abnahme Rohinstallation` | `Abnahme der Rohinstallation im 3. OG bestanden.` | none |

After a poll and extraction, reload the dashboard: the source-backed Events appear
in its timeline. Zone/date filters must include the source timestamp (today for
newly sent mail); the message text's `Tag 4` remains relative to the seeded demo
start date. Inspection claims remain **unconfirmed Evidence**, including the
positive result. The plan email does not import geometry, compute a diff, create
Flags or certify crew acknowledgments. Those remain #15/#17 and the rule workflow.

The source preserves parsed From address, Gmail message ID, Gmail `internalDate`
in UTC, subject and MIME-decoded body. `internalDate` is Gmail's message timestamp
(usually receipt time), not the untrusted RFC Date header. Subject uses the existing
text field: `Subject: <subject>` followed by a blank line and the body. Plain text
is preferred to a duplicate HTML alternative; HTML-only mail becomes readable
text. Attachments use the existing ingestion storage/download API. Sender roles
are explicitly configured, default to `unknown` and never establish confirmation.
For arbitrary texts/signatures use the existing live LLM configuration in API.

Use `GET /events` or the source's timeline entry to find its source/attachment IDs,
then download the original with
`GET /source-messages/{source_id}/attachments/{attachment_id}` and compare it to
`cad/plans/A-103_RevD.dxf`. The DXF bytes are unchanged. Storage does not imply
geometry extraction; no automatic CAD operation is added here.

Every poll enumerates the selected messages with pagination, then checks the exact
`(gmail, mailbox, Gmail message ID)` identity in the API. Processed sources,
including irrelevant messages with zero Events, are skipped **before** downloading
mail content. Failed/pending/interrupted deliveries retry through the idempotent
entry point. A lost HTTP response, worker restart or concurrent delivery cannot
create a second source/Event set. No Gmail labels/read status are mutated, and no
local dedup database needs synchronizing. This simple demo approach rescans the
selected label; keep it dedicated and small. A demo seed reset deliberately removes
stored identities and therefore allows the still-selected mails to be ingested
again. Remove/archive the demo mails from the selected label before a clean reset
if you do not want that replay.

## Automated verification

```sh
python -X utf8 -m pytest backend/tests
# From the root, set PYTHONPATH=backend in your shell first.
docker compose --env-file .env.example config --quiet
```

Gmail HTTP/OAuth are mocked. Tests cover account/label boundaries, pagination,
plain/HTML MIME alternatives, metadata, exact original DXF bytes through ingestion,
all three hero Events, unconfirmed Evidence, persistent deduplication, failed
extraction retry, lost responses and seed reset. No real mailbox is read by tests;
a live consent/mail-delivery smoke test requires your local team credentials.

Official setup/protocol references:

- https://developers.google.com/workspace/gmail/api/quickstart/python
- https://developers.google.com/workspace/gmail/api/auth/scopes
- https://developers.google.com/identity/protocols/oauth2#expiration
- https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list
- https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get
