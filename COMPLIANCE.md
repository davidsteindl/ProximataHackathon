# Compliance notes

## LibreDWG (Issue #4)

LibreDWG is GPL-3.0-or-later and runs exclusively as a separate executable in an
optional converter container. The proprietary Talona application does not link
or import LibreDWG. File-based DWG/DXF exchange is the integration boundary.
When distributing the converter image, preserve GPL notices and provide the
licence and corresponding source for the exact distributed version, including
any modifications. This is not a blanket clearance for future library linking.

Upstream: https://www.gnu.org/software/libredwg/
Pinned source: https://ftp.gnu.org/gnu/libredwg/libredwg-0.13.3.tar.xz

Other product compliance topics remain tracked in issue #23.

## Message extraction (Issue #6)

Only the API receives the configurable LLM key. Its message-specific provider
input is redacted text and an enumerated sender role; source/sender IDs, channel
metadata, timestamps, Site Record data and attachments are excluded. Common phone
numbers, email addresses, `@usernames` and the known sender identity are masked
inside the text. This is a limited MVP safeguard rather than general free-text
anonymisation; the demo uses synthetic data and team test accounts only.

The original source and attachment bytes remain in the API-owned database for
traceability. Quotes link extracted statements to that original source. Even
high-confidence positive results create only unconfirmed Evidence; existing
human decisions and domain outcomes are not overwritten. Typed validation and
this evidence boundary limit extraction errors and prompt injection. The advisory
role alone does not make an extracted claim correct.

The offline cache contains explicitly authored synthetic extraction fixtures and
uses the same validation and evidence policy. No live messages or responses are
automatically copied into it. See [the ingestion contract](docs/INGESTION.md).
Dashboard/API authentication is still absent in the MVP; public exposure is not
part of this implementation. Telegram retention and channel allowlisting are
documented in [Telegram](docs/TELEGRAM.md), the human review action in #9, and provider-specific production
compliance documentation in #23.

## Telegram (Issue #12)

The bot reads whole allowlisted groups (privacy mode off), but only messages from
allowlisted numeric sender IDs enter ingestion. It posts a purpose, retention,
operator and rights notice when an allowlisted team account adds it. Private
access/deletion commands use the API-owned outbox; no per-person metrics or
rankings are introduced. Deletion/retention clears raw text and attachments, not
the safety record: source/dedup metadata, derived Events/Evidence, relevant Flag
quotes and audit remain, explicitly disclosed in notices and deletion replies.
Delivered privacy-export bodies are scrubbed from the outbox. See the Telegram
guide for retained fields, provider copies, retries and operator responsibilities.

This is a synthetic demo, not legal approval for real worker surveillance.
Production legal basis, Austrian works agreement (ArbVG §96/§96a), processor
contracts, EU-region/zero-retention LLM arrangements and authenticated dashboard
access remain separate compliance work (#23). Telegram has non-EU infrastructure
and no end-to-end encryption for bot chats; evaluate Teams or WhatsApp Business
for production rather than treating the demo allowlist as sufficient protection.
