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
