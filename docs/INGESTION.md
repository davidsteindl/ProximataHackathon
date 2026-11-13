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
  cannot contain paths. The API never executes, parses or sends attachments to an LLM.
- `events` and `event_zones`: one extracted statement per source/ordinal, resolved
  zone IDs, unresolved zone labels, intent, actor/crew, activity/trade, confidence,
  relevant original quote and time information. Event IDs are opaque references.
- Relevant inspection, completion and revision-acknowledgment statements also
  create `Evidence` through the existing #5 contract. `statement_ref` is the Event
  ID, `source_ref` is `source:<Source Message ID>`. New records use
  `origin=llm_statement` with an unconfirmed `statement_ingestion` review, without
  a human reviewer or decision timestamp. Confidence is never confirmation.

Migration `0004` extends the CAD migration `0003`; existing evidence and review history are unchanged.
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
