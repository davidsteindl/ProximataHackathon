# Telegram in/out and Q&A (Issues #12, #20)

Only synthetic SiteMind data and allowlisted team test accounts are supported.
No webhook, bot credentials in API, direct database access from worker, or new
agent decision authority is introduced. Questions use the Q&A core in API (#19),
which reads the record through our own MCP tools. All replies and decision forwards
use the existing outbox.

## Setup

1. Create a team test bot in BotFather; disable group privacy (`/setprivacy`) so
   the bot can read the allowlisted crew group. Remove any existing webhook before
   using polling. Store its token only in local `TELEGRAM_BOT_TOKEN` (worker).
2. Copy `.env.example`, set `TELEGRAM_ENABLED=true`, set a random
   `TELEGRAM_COMPLIANCE_KEY` shared by API and worker, and supply numeric IDs:

   ```dotenv
   TELEGRAM_ALLOWED_CHATS_JSON='["-1001234567890","123456789"]'
   TELEGRAM_ALLOWED_USERS_JSON='["123456789"]'
   TELEGRAM_SENDER_ROLES_JSON='{"123456789":"crew_lead"}'
   TELEGRAM_SENDER_CREWS_JSON='{"123456789":"drywall"}'
   TELEGRAM_CREW_LEADS_JSON='{"lead-drywall":"123456789"}'
   TELEGRAM_RESPONSIBLE=Team test operator / local contact
   TELEGRAM_RETENTION_DAYS=7
   TELEGRAM_POLL_SECONDS=2
   ```

   Both the **chat and sender** must match. Include each private chat ID as well
   as group IDs. Unmapped roles are `unknown`; Crew IDs must exist in the Site
   Record. Do not derive roles from usernames. Lists default empty (deny all).
   Each Crew Lead must start the bot privately before Telegram can deliver DMs.
   A mapped Lead receives the existing factual Flag warning on Telegram instead
   of Gmail; an unmapped Lead retains existing Gmail routing. Private recipients
   must remain in **both** lists at send time. No automatic fallback bypasses a
   revoked Telegram allowlist.
3. `docker compose up --build`; import the synthetic seed as in the README.
   Add the bot to the allowlisted group using an allowlisted team account: its
   `my_chat_member` join update queues the transparency notice. `/privacy` repeats
   the notice. Unknown slash commands show help and never go to extraction.

No usernames, profile names, phone numbers, forwarded identities, files, edited
messages or bot messages are ingested. Photos are ingested only with the opt-in
`TELEGRAM_PHOTOS_ENABLED=true` (#26, see [COMPLIANCE.md](COMPLIANCE.md)); the
caption is the source text. Otherwise supported inbound content is plain text,
with chat ID, message ID, numeric sender ID, mapped role/Crew and UTC timestamp.
Transport metadata never enters the LLM request. Existing API text redaction and
unconfirmed Evidence policy apply unchanged. Free text is not fully anonymized.

## Questions and Superintendent decisions (#20)

The worker selects plain-text question candidates by `?`, common German/English
question beginnings, explicit confirmation requests, or an extracted `question`
Event. This applies in both allowlisted groups and private chats. Other statements
continue through ordinary ingestion without a Q&A reply. Slash commands retain
the privacy/help behavior above. The heuristic only selects candidates: the API's
Q&A router decides answer, clarification, not-found, decision request, dashboard
review or not-a-question. A not-a-question result sends no reply.

The original message is ingested first and retains its provider identity. The
worker submits only its persisted `source_id` to `POST /telegram/qa`, protected
by the existing worker key. API reads the original text, chat and mapped role;
only redacted text and role go to Q&A routing. No bot token or sender/chat ID is
sent to the router. A missing extraction fixture can leave a failed extraction
source; Q&A can still answer that durable question independently. This does not
invent an extracted Event or confirm any Evidence.

Setup in addition to #12:

- Start `api`, `mcp` and `worker`. Configure `MCP_URL` and Q&A routing as described
  in README #19. `QA_ROUTER_PROVIDER=cached` needs no internet for routing and
  contains the two hero questions for their expected roles (revision: `crew_lead`,
  bathroom status: `superintendent`), plus the documented decision/inspection-review
  examples. Additional phrasings need the live `decisions` router or a cache entry;
  missing fixtures return a retryable error, never a guessed answer.
- Map the test Superintendent's Telegram user ID to `superintendent` in the worker's
  `TELEGRAM_SENDER_ROLES_JSON`, and include that user/chat in both allowlists.
- Set the existing API `SUPERINTENDENT_EMAIL` to a team test address. Enable the
  existing Gmail worker (`GMAIL_ENABLED=true`, `GMAIL_SEND_ENABLED=true`) with the
  dedicated project mailbox and read/send scopes, as in [GMAIL.md](GMAIL.md).
  Decision requests are forwarded by Gmail, matching existing Superintendent
  notifications. No new credentials or environment variables are introduced.
- `DASHBOARD_BASE_URL` controls links in room replies and decision forwards.

Hero messages from allowlisted test users:

- Crew Lead: `welcher plan gilt für 3B?`. After the Rev-D note/attachment
  is in the record, the answer cites Rev D and its actual day-1 source.
- Superintendent: `wie ist der Stand im Bad 3B?`. The structured response includes
  current revision/receipt Evidence, inspections with review status, Preconditions,
  open Flags, Tasks, latest Events and sources, ending in `/zones/3B-BATH`.
- Crew Lead: `dürfen wir morgen in 3B zumachen?`. The API queues the redacted
  question, source reference and record link to the Superintendent and a chat receipt saying it is **queued**, not approved.
  It creates no Proposal decision, Evidence review or Flag action. If the recipient
  is missing, the operation fails visibly and retries; it does not claim forwarding.
- A request to confirm inspection, revision receipt or Task completion directs
  the responsible person to dashboard review. No chat message can perform it.
  Unconfirmed Evidence and unresolved contradictions remain explicitly labelled.

Answers go back to the original allowlisted chat, using numbered multipart
messages when necessary. The room-view link remains at the end of the complete
response. Questions over 4000 characters receive a shortening request without
routing. Source-derived outbox IDs and dedup keys prevent additional replies or
forwards on repeated updates/restarts. A Q&A failure is retried even if ingestion
already succeeded. Outbound failure keeps the normal leased retry behavior;
uncertain provider responses can still duplicate delivery as described below.
Retries also read persisted question Events through `GET /events?source_id=…`
when the text heuristic does not detect a question, without repeating extraction.

## Privacy and retention

- `/my_data` works only in an allowlisted private bot chat. It exports that
  sender's Telegram source metadata/text and derived Event quotes/details,
  Evidence scope/status and associated Flag IDs. It includes retained derived
  data after raw deletion. Group commands return help, never an export.
- `/delete_my_data` immediately removes that sender's raw texts and attachments,
  cancels pending private export copies, and queues an explanation. This is **not**
  a promise to erase all derived records: source identity/dedup metadata (numeric
  sender/chat/message IDs, timestamps, role/Crew and content hash), Events, Evidence,
  relevant Flag quotes, factual warning content and audit are retained for safety
  traceability. No Evidence status, Flag state or rule is changed. Contact the
  configured responsible operator for further derived-data deletion requests.
- Raw retention is a positive number of days **from API receipt**, default 7.
  Before every Telegram poll and privacy command the API clears expired raw text
  and attachments, invalidates extraction leases and preserves processed identity
  tombstones. Retrying old updates cannot re-import deleted raw content or create
  duplicate Events. Pending export copies for affected senders also expire, so
  exports cannot extend the original raw retention deadline.
- Compliance responses use the same leased outbox as warnings. Their content is
  scrubbed after successful delivery; undelivered copies expire after the configured
  retention period. Sent delivery metadata remains. Telegram itself retains copies
  already delivered; deletion does not remotely erase them. An already in-flight
  provider request cannot be recalled; Telegram delivery is at-least-once after an
  ambiguous send/report failure, as with Gmail.
  Long warnings are numbered multipart messages; success records the last part's
  provider message ID only after all parts send. A partial retry can duplicate parts.
- Q&A reply/decision-forward copies are scrubbed immediately after successful
  delivery (Telegram and Gmail). Deleting or expiring the original question also
  erases both copies and cancels any pending/sending leases, including group
  replies. Delivery metadata and dedup identity remain. In-flight sends and
  already delivered provider copies cannot be recalled.
- Keep worker and API running for scheduled cleanup. Worker continues cleanup with
  Telegram disabled if `TELEGRAM_COMPLIANCE_KEY` remains set. After downtime,
  cleanup runs before resuming ingestion. This is not a production retention or
  authentication service. Backups and Telegram-side retention need operator policy.

## REST/schema changes

- Migration `0009` extends outbox channels with `telegram` and makes `flag_id`
  nullable for compliance replies. The `cancelled` status marks erased/expired
  undelivered replies without claiming they were sent. The one-warning-per-Flag
  constraint remains.
- `POST /outbox/claim?channel=telegram` claims only Telegram rows; default `gmail`
  preserves the Gmail consumer. Delivery errors include `telegram_error`. Only
  delivered Flag warnings can perform the existing `detected → notified` transition.
- `POST /telegram/commands`: `{request_id, sender_id, chat_id, command}` where
  command is `notice`, `my_data`, `delete_my_data` or `help`. Replies are queued
  idempotently per request/chat/command; raw command messages are not stored.
- Migration `0015` adds outbox kinds `qa_reply` and `decision_request`; no new tables.
- `POST /telegram/qa`: `{source_id}` returns `{handled, reply_id}`. Requires
  `X-Telegram-Compliance-Key` and an existing Telegram source. It deduplicates per
  source/kind and queues answer or forward + chat receipt atomically. No database
  transaction/lock spans MCP calls; before queuing, the source is checked again
  for reset/deletion. Q&A errors propagate as safe errors and are retried.
- `POST /telegram/retention` enforces cleanup. All Telegram endpoints require
  `X-Telegram-Compliance-Key`; the worker is trusted to provide allowlisted sender
  IDs. MCP/chat gets neither this key nor review authority. Other MVP endpoints
  still lack production authentication: do not expose this stack publicly.

## Offline verification

`PYTHONPATH=backend python -m pytest backend/tests/test_telegram.py backend/tests/test_telegram_qa.py backend/tests/test_telegram_qa_api.py backend/tests/test_outbox.py`

Tests use a mocked Telegram HTTP API and the real ingestion, rules, outbox and
privacy routes over the synthetic SQLite test database. No credentials or live
provider calls are needed. The hero work announcement creates a deterministic
Flag warning for the mapped Crew Lead; “Warnung gesehen” does not acknowledge a
Flag without the separate human dashboard action, and “Abnahme dürfte passen”
does not certify an Inspection.
