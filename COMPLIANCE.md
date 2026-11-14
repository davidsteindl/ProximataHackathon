# SiteMind compliance and deployment limits

This is the submission compliance overview for the Talona track. The MVP is a
local demonstration with synthetic construction records and voluntary team test
accounts. It is **not approved for real workers or third-party data**. Test-account
addresses and numeric Telegram identifiers can still be personal data. These
notes describe controls and gaps, not a legal certification.

## Purpose, legal basis and responsibility

The purpose is to detect construction conflicts associated with Zones, Tasks and
trades, explain their sources, and support responsible human decisions. There
are no per-person performance metrics, rankings or automated employment decisions.
Reviewer identities in the audit trail provide decision traceability and must
not be repurposed for productivity monitoring.

Use only team-controlled test accounts and synthetic text, drawings and photos;
inform participating team members of processing and deletion limits. Set
`TELEGRAM_RESPONSIBLE` to the actual test operator/contact. This setting neither
appoints a production controller nor establishes a lawful basis.

Before workplace deployment, the operator and Talona must identify controller
and processor responsibilities and document a GDPR Article 6 basis, necessity,
proportionality and retention for each purpose. Legitimate interests under
Article 6(1)(f) would require a documented balancing assessment; it is not assumed
here. Employee consent is not a blanket solution given the employment power
imbalance. Provide Articles 13/14 notices and procedures for access, correction,
objection and erasure, including derived records and backups. Assess whether a
DPIA under Article 35 is required before deployment.

## Austrian works council: ArbVG §96 / §96a

Even a safety-oriented chat record can enable worker monitoring. Where applicable,
control measures affecting human dignity require works council consent under
ArbVG §96(1)(3); automated personnel-data systems may engage §96a(1)(1).
Complete the assessment and any required Betriebsvereinbarung before workplace
use. The absence of rankings does not settle this. Address purpose, collected
fields, access, review rights, retention, and a prohibition on individual
performance or disciplinary use. Where no works council exists, obtain advice
on applicable employee-protection requirements rather than assuming none apply.

## Data flow and minimisation

Only `api` accesses PostgreSQL. Channel adapters in `worker` submit messages to
`POST /ingestion/messages`; outbound application messages use the API-owned
outbox. Gmail OAuth files and the Telegram bot token are available only to
`worker`; model keys only to `api`. The separate `TELEGRAM_COMPLIANCE_KEY`
protects the intended worker privacy/Q&A routes, not the whole API.

| Live processing path | Model input | Local record / limitations |
| --- | --- | --- |
| Text extraction | Redacted message text and enumerated sender role, plus fixed instructions/schema | Original text, transport identity/time and attachment bytes remain in the API-owned record. Transport metadata and CAD files are not sent to text extraction. |
| Advisor | Structured Flag, Task, Zone, Crew, Revision and Evidence facts, citation handles, source times/channels and redacted source quotes | No contact addresses, Telegram sender/chat IDs or reviewer identities. This is additional site context beyond the text-extraction payload. |
| Q&A routing | Redacted question and role, fixed question types and available Zone IDs/names | Answers are rendered from our own MCP tool results; the router does not generate the answer. |
| Opt-in photo findings | Image bytes, redacted caption and sender role | The image is **not anonymised**. Faces, signs or contact details in pixels can leave the API. Keep photos synthetic. |

Text redaction masks common email addresses, phone numbers, `@handles` and,
in extraction/advisor paths, the known sender identity. This is limited
pattern-based masking, not general anonymisation: names, addresses and unusual
formats can remain. Structured advisory context and Zone labels also need a
minimisation review before live deployment. The synthetic-only policy remains
necessary.

`LLM_PROVIDER=cached`, `QA_ROUTER_PROVIDER=cached` and `VISION_PROVIDER=cached`
use authored synthetic fixtures without contacting model providers. Cache misses
do not silently fall back to live calls. Live messages/responses are not
automatically added to fixtures.

## LLM provider: DPA, EU region and zero data retention

The repository contains no signed processor agreement, verified EU processing
commitment or activated zero-data-retention entitlement. Neither an API key nor
an OpenAI-compatible API establishes those properties. Before sending personal
data to any live model provider, the controller must:

- Conclude an Article 28 DPA/AVV; review subprocessors, training use, security,
  deletion, incident handling and Chapter V international transfers.
- Verify EU processing/storage for the **specific endpoint and model**, including
  logging and support access. Record the provider, region, approved data categories
  and terms in the deployment's processing record.
- Obtain and verify zero data retention for every API feature used, or document
  actual retention and an approved alternative. Account eligibility and endpoint
  exclusions matter; this MVP does not configure or verify provider-side ZDR.

Extraction/advisor/vision use the configurable `LLM_BASE_URL`; a base URL alone
does not establish EU residency. Live Q&A uses the fixed
`https://api.openai.com/v1/decisions` endpoint with `OPENAI_API_KEY`, with **no
configurable EU endpoint in this MVP**. Keep routing cached until its exact
deployment arrangement is reviewed. Changing extraction's URL does not change
Q&A routing. Local deletion cannot recall inputs already sent to a provider.

## Telegram and Gmail

Telegram polling is opt-in. Both numeric chat and sender allowlists must match;
empty lists deny all. Group privacy mode is disabled, so the bot can receive
whole-group updates before the worker discards disallowed senders. Use team-only
groups. On joining through an allowlisted team account the bot queues a purpose,
operator and retention notice; `/privacy` repeats it. Private `/my_data` and
`/delete_my_data` are available only to allowlisted accounts. None of these
commands reviews Evidence, approves Proposals or closes Flags.

Telegram bot chats have **no end-to-end encryption** and Telegram has non-EU
infrastructure. Allowlists do not solve platform access or international-transfer
risks. For production, evaluate Teams or WhatsApp Business with actual business/API
terms, processor arrangements, residency and transfer safeguards; neither is
automatically compliant. The MVP implements neither replacement.

Gmail uses a dedicated project **test mailbox**, optionally filtered by an exact
label. OAuth requests only `gmail.readonly`, plus `gmail.send` when sending is
enabled. A label is not an OAuth scope boundary: read-only permission covers the
authorised mailbox. Do not connect a personal/company mailbox. The worker checks
the authorised account and rejects broader grants. External/Testing refresh
tokens for these scopes expire after seven days.
See [Gmail setup](docs/GMAIL.md) and [Telegram setup](docs/TELEGRAM.md).

## Retention, access and deletion

| Data | Implemented behaviour | Remaining responsibility |
| --- | --- | --- |
| Telegram raw text, captions and source attachments, including photos | Erased after `TELEGRAM_RETENTION_DAYS` (default 7, positive days from API receipt), or immediately by private `/delete_my_data`. Identity tombstones prevent re-import. | Keep API and worker running for cleanup. Provider copies and backups are separate. |
| Telegram privacy exports and Q&A/decision-forward bodies | Scrubbed after successful delivery. Raw deletion/expiry cancels associated pending copies; undelivered privacy exports also expire. | In-flight sends and already delivered provider copies cannot be recalled. |
| Source metadata, Events, Evidence, relevant Flag quotes, warning snapshots and audit | Retained for traceability after raw deletion, including numeric identity/dedup fields. `/my_data` includes retained derived records. | This is **not full erasure**. Define lawful retention, access and further deletion procedures before production. |
| Gmail sources/attachments, CAD originals/geometry, seed/replay sources, derived record and local transcripts | No general automatic TTL or per-user deletion mechanism. The Telegram TTL applies only to Telegram sources. | Operator must define a policy; use only synthetic contents. Local `.replay/` files need separate cleanup. |

Keep the worker key set for cleanup even if Telegram polling is disabled.
Seed/reset replaces the whole demo Site Record, including Evidence history,
Flags, Proposals, learning, outbox and geometry; it is not a production erasure
or backup policy. `docker compose down --volumes` removes the stack's database
volume, not mailboxes, Telegram history, bind-mounted files, other stacks or backups.

## Human Evidence review and autonomous-operation boundary

LLM-extracted Events, including vision findings and high-confidence success
claims, are **unconfirmed statements**. They can trigger deterministic checks,
but cannot satisfy a Precondition until a responsible human reviews the source
and confirms that exact Evidence in the dashboard. Review works without a Flag.
The API validates status and scope (Zone, Inspection/Task or Crew + Revision),
records person, time, source and decision, and re-evaluates rules after review.

Preconditions evaluate to `satisfied`, `not_satisfied`, `unknown` or
`contradictory`. Missing, stale, unconfirmed, mismatched or unresolved
contradictory Evidence cannot count as satisfied. New counterclaims remain
visible for review; the LLM cannot overwrite human confirmations. Evidence
confirmation/rejection, Flag acknowledgment, Proposal approval and Flag closure
are separate actions. Even a subsequently satisfied Precondition leaves an
existing Flag open until a human closes it with `resolved` / `false_alarm`
feedback and a reason.

Only deterministic rules create Flags. Automatic scans, factual warnings and
escalation provide information; operative instructions require human approval.
MCP/chat cannot confirm/reject Evidence, approve Proposals or close Flags.
Requests marked `X-SiteMind-Client: mcp|chat|agent` may mutate only
`POST /agent/proposals`, storing a proposal without executing it.

Explicit synthetic baseline Evidence has `seed_baseline` provenance and a seed
import audit, never an invented human decision. Replayed LLM claims remain
unconfirmed offline. CAD events establish geometry and affected Zones, not passed
Inspections, Crew receipt or completed Tasks. Learning corrects a specific
extraction error with traceable feedback; it cannot confirm Evidence, erase
genuine conflicts, disable checks or change safety rules. Safety-rule changes
require separate human approval, narrow scope and audit.

## Prompt injection, extraction errors and missing authentication

Messages, CAD labels, quotes and images are untrusted input. Typed schemas,
verbatim quote checks, constrained identifiers, citation validation and MCP tool
limits reduce model influence. Unconfirmed Evidence and API scope validation
prevent extracted claims from becoming automatic work clearances.
**“The LLM only advises” alone does not prevent incorrect inputs.** Wrong
extraction, missed conflicts, misleading explanations and malicious source
instructions remain possible. Reviewers must inspect sources and uncertainty.

The dashboard role switcher is **not authentication**. Most API endpoints and MCP
lack production identity/access control: callers can omit/spoof the client header
or impersonate a reviewer. The worker key covers selected Telegram routes only.
Compose publishes host ports on all interfaces by default. Use a trusted local
machine/network, restrict access with the host firewall, and do not expose the
stack publicly. Production needs authenticated identities, server-side roles,
authorised scope, service credentials, TLS, CSRF/session controls and audit
protection. Recorded MVP reviewer identity is a demo assertion.

## Ownership, secrets and CAD licences

Talona-specific rules override the general public/MIT submission rule: all work
belongs to Talona, the repository stays **private**, and no MIT licence is granted
for the application. See [general rules](general-rules.md). Third-party licence
obligations still apply; preserve notices and review resolved dependencies before
distributing application/container bundles.

`.env.example` contains placeholders and a public local-development password,
not deployment credentials. `.env`, `.gmail/`, `.venv/` and `.replay/` are
ignored. Never commit real keys, OAuth files, personal mail addresses, exports or
photos, or include secrets in images, screenshots or submission/video materials.
Restrict local credential files and rotate accidentally exposed credentials.

DXF extraction uses `ezdxf` (MIT-licensed dependency); its permissive licence does
not license SiteMind under MIT. LibreDWG **0.13.3, GPL-3.0-or-later** runs only as
a separate executable in an optional converter container. SiteMind neither links
nor imports it; the boundary is command-line execution and DWG/DXF files.
DWG import/export and automatic converter integration are outside the MVP.
When distributing that converter image, preserve GPL notices and supply the
licence and corresponding source for the exact version, including modifications.
Process separation does not waive those obligations or approve future linking.
ODA is not used; review its licence before any future use.

- [CAD converter decision and limits](docs/CAD-CONVERTER.md)
- [Photo processing, faces and Evidence limits](docs/COMPLIANCE.md)
- [GDPR text (Articles 5, 6, 13–22, 28, 35, 44–49)](https://eur-lex.europa.eu/eli/reg/2016/679/oj)
- [ArbVG §96](https://www.ris.bka.gv.at/NormDokument.wxe?Abfrage=Bundesnormen&Gesetzesnummer=10008329&Paragraf=96) / [§96a](https://www.ris.bka.gv.at/NormDokument.wxe?Abfrage=Bundesnormen&Gesetzesnummer=10008329&Paragraf=96a)
- [LibreDWG upstream](https://www.gnu.org/software/libredwg/) / [pinned source](https://ftp.gnu.org/gnu/libredwg/libredwg-0.13.3.tar.xz)
