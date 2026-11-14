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
part of this implementation. Automated Telegram retention and channel allowlisting
remain in #12, the human review action in #9, and provider-specific production
compliance documentation in #23.
