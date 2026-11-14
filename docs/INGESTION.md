# Source Messages and extracted Events (#6)

The API owns ingestion storage. Channel adapters and replay submit the same
`SourceMessageInput`; they never write to the database. Only synthetic messages
and team test accounts are supported for the demo.

## Storage contract

- `source_messages`: original text, sender identity/role as known, message and
  receipt timestamps, channel, source key, external ID, payload hash and processing
  status. Identity is `(channel, source_key, external_id)`: a Telegram source key
  identifies a chat; a Gmail source key identifies the dedicated project mailbox.
- `source_attachments`: original bytes, filename, media type and SHA-256, linked
  to the source. Input uses base64, at most five attachments of 2 MB each. Filenames
  cannot contain paths. This ingestion path never executes, parses or sends
  attachments to an LLM; the separate CAD API handles geometry imports.
- `events` and `event_zones`: one extracted statement per source/ordinal, resolved
  zone IDs, unresolved zone labels, intent, actor/crew, activity/trade, confidence,
  relevant original quote and time information. Event IDs are opaque references.
- Relevant inspection, completion and revision-acknowledgment statements also
  create `Evidence` through the existing #5 contract. `statement_ref` is the Event
  ID, `source_ref` is `source:<Source Message ID>`. New records use
  `origin=llm_statement` with an unconfirmed `statement_ingestion` review, without
  a human reviewer or decision timestamp. Confidence is never confirmation.

Migration `0004` extends the CAD migration `0003`; existing evidence and review
history are unchanged.
The explicit demo seed reset deletes these new referencing tables before replacing
the baseline, preserving atomic reset and labelled seed provenance. It is not the
runtime ingestion path. The guided replay workflow remains in #22.

All extracted Events are statements, not clearance. Existing confirmed evidence,
Inspection outcomes, Task schedules and Revision acknowledgments are never
overwritten by extraction. The separate human review and rule evaluation workflows
belong to #9 and #7/#8. Gmail/Telegram adapters and CAD processing are outside #6.

## Extraction and offline mode

`LLM_PROVIDER=cached` is the default. It reads the explicit synthetic results in
`backend/demo/extraction-cache.json` and makes no network calls. Each result is
looked up by redacted message text and sender role and runs through the same typed
validation, source-quote validation, zone/time mapping and unconfirmed Evidence
creation as live output. Uncached text fails visibly with `cache_miss`; there is
no automatic live fallback. These are authored demo fixtures, not human-reviewed
evidence or a claim that a live model was called.

For live extraction set `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL` (including
the API's `/v1` prefix), `LLM_MODEL` and `LLM_API_KEY`. The configured model/provider
must support Chat Completions JSON mode (`response_format: {"type":"json_object"}`).
The API independently validates the result against its Pydantic schema and rejects
unknown fields, privileged actions, non-finite/out-of-range confidence and quotes
that do not occur in the supplied text. JSON mode itself does not guarantee schema
adherence. Official protocol reference:
https://developers.openai.com/api/docs/guides/structured-outputs

`LLM_TIMEOUT_SECONDS` defaults to 30 (maximum 120); all settings, including a custom
`LLM_CACHE_PATH`, are listed in `.env.example`. The key is passed only to `api`.
The cache path is inside that container; custom files must be added to its image
or explicitly mounted there. No runtime message or provider response is silently
written to a cache. Extend the version-1 file with synthetic text, role and a valid
`result.events` array to prepare other offline examples.

Only message text and the sender role are sent as message-specific LLM input.
Phone numbers, email addresses, `@usernames` and a known sender identity appearing
in the text are masked before extraction. Length-preserving masking lets the API
recover the exact original quote without sending that original identifier.
Source IDs, sender/crew identities, timestamps, zone lists, other Site Record data
and attachment names/contents are not sent. The system prompt/schema is static.
This is an MVP redaction safeguard, not a guarantee of arbitrary free-text
anonymisation. Use only synthetic data and team test accounts.

Time resolution uses the source's message timestamp and the Site's IANA timezone,
never the server's current date. Explicit `Tag N` uses the Site start date.
An exact local time becomes UTC; a day or part of day remains an interval with
its original expression and precision. Demo conventions: morning 06:00–12:00,
afternoon 12:00–18:00, evening 18:00–22:00, night 22:00–06:00. These intervals
are interpretations, not exact start commitments. Ambiguous/nonexistent local
clock times at DST changes stay unresolved. Missing times stay null.

Zone resolution accepts exact IDs/names and narrowly defined aliases (e.g.
`Wohnung 3B`, `3. OG`, `Bad 3B`). Ambiguous and unknown labels are preserved in
`unresolved_zones`, never assigned to a guessed or global scope. Evidence subject
references are resolved only when the existing subject and exact zone match;
an unseen revision such as Rev D stays unresolved with its original plan/label
in Event details. Extraction does not create or change authoritative revisions.

## REST contract

| Endpoint | Behaviour |
|---|---|
| `POST /ingestion/messages` | Store original source and attempt extraction synchronously; return `{source, events, duplicate}` |
| `GET /source-messages/{id}` | Original text, provenance, processing status/error and attachment metadata |
| `GET /source-messages/{id}/attachments/{attachment_id}` | Original bytes as an attachment download; metadata includes SHA-256 |
| `GET /events` | Chronological Events with source/quote, resolved/unresolved scope, time interpretation and linked Evidence/history |

The request requires `channel`, `source_key`, `external_id`, timezone-aware
`sent_at`, `text`, and optionally `sender_id`, `sender_role`, `sender_crew_id`,
`attachments`. Sender roles are `architect`, `inspector`, `crew_lead`, `crew`,
`superintendent`, `unknown` (default). A supplied crew must exist. Channel is an
adapter-defined lowercase identifier, e.g. `gmail`, `telegram`, `seed`, `replay`.
There must be text or an attachment; text is limited to 50,000 characters.
An attachment has `file_name`, `media_type`, `content_base64`. Review status,
Events, seed provenance and human decisions cannot be supplied by a caller.

Load the static Site baseline first. Ingestion does not use `/seed/import`;
even `channel=seed` creates unconfirmed statements. The separate baseline import
remains an explicit, destructive demo bootstrap operation with seed provenance.

Example request is `backend/demo/closing-work.json`; send it with:

```sh
curl http://localhost:8000/ingestion/messages \
  -H 'Content-Type: application/json' \
  --data-binary @backend/demo/closing-work.json
```

Run from the repository root after Compose startup and seed import. The cached
hero messages and roles are listed verbatim in `backend/demo/extraction-cache.json`.
The file is only extraction fixtures; guided scenario playback, simulated clock,
channel adapters and pauses for human decisions remain in #22.

### Idempotency, failure and retry

- New completed source: `201`. Re-delivery of the same normalized request:
  `200`, `duplicate=true`, same source/Event/Evidence IDs, no second LLM call.
- The same identity with different content/metadata is `409`; the original is
  unchanged. Corrections must be new source messages. No baseline is also `409`.
- Irrelevant text or non-DXF attachment-only input: `processed`, no Events.
  Attachment-only messages bypass the LLM. DXF attachments can produce
  deterministic revision Events and Conflict B (#17), including without text.
- Provider/cache/schema/quote failure: `502` with the stored source and a safe
  `error_code` (`provider_unavailable`, `provider_not_configured`, `cache_miss`,
  `invalid_cache`, `invalid_extraction`, `invalid_quote`). No partial Events or
  Evidence are committed. Storage failure is reported as `storage_failed` when
  the database remains available to record it. Provider bodies/secrets are never
  returned as error text. Exception: if a DXF diff succeeds despite text extraction
  failure, the source is `processed` and retains the extraction `error_code`;
  its deterministic Event is committed with no extracted statements.
- Re-deliver the exact request to retry a failed source. Requests already being
  processed return `202`; they do not launch a second extraction. A crashed
  processing attempt can be reclaimed by re-delivery after five minutes. Attempt
  tokens prevent a late old attempt from committing over a newer one.
- A unique source constraint and unique Event ordinal enforce dedup in storage.
  Source persistence, processing claim and final result are separate transactions;
  no transaction/row lock spans the provider call. All Events, Evidence and the
  final success status are committed together. There is no background retry queue
  or channel polling in #6.

`GET /events` orders by Source Message `sent_at`, source ID and extraction ordinal.
Filters: `zone_id`, `include_descendants` (default true), `from_time` inclusive,
`to_time` exclusive. Time filters apply to the original message timestamp, not
the claimed future activity time. Unknown zones return `404`; naive timestamps
or non-increasing ranges return `422`. Unknown source/attachment IDs return `404`.
The dashboard shows the same chronological timeline with expandable original
sources and separate evidence review labels; reload it to fetch new records.

## Gmail adapter identity lookup (#11)

`GET /source-messages?channel=gmail&source_key=<mailbox>&external_id=<Gmail ID>`
requires all three exact identity parameters and returns one `SourceMessageView`,
or JSON `null` if absent. This read-only extension lets the worker skip sources
whose status is `processed`, including irrelevant messages with zero Events,
without downloading mail content again. Other statuses remain eligible for
idempotent delivery through `POST /ingestion/messages`. The API's existing unique
constraint remains authoritative under concurrent deliveries or worker restarts.
No schema migration or worker database access is introduced. A seed reset removes
these identities too; mail still in the configured selection can then be replayed.

Gmail source keys are the verified project mailbox address (lowercase), external
IDs are Gmail message IDs, sender IDs are the parsed From address, and timestamps
are Gmail `internalDate` in UTC. Subject and MIME-decoded body use the existing
`text` field as `Subject: <subject>\n\n<body>` (no prefix for an empty subject).
Original attachment bytes go through the existing attachment contract. DXF
import/diff is performed in the API ingestion path, never by the adapter.
`Event.origin` distinguishes `llm_statement` from `deterministic_plan_diff`;
CAD provenance, zone overrides and explicit note fallback are documented in
[CAD-PIPELINE.md](CAD-PIPELINE.md#plan-diff-17). Setup: [GMAIL.md](GMAIL.md).
