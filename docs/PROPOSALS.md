# Advisor proposals and Superintendent approval (#13)

The advisor explains a Flag and proposes measures. It only advises (PLAN §3.2):
it cannot confirm Evidence, change or close a Flag, or send anything on its own.
Only the Superintendent can approve or reject a Proposal, and only in the dashboard.

## Flow

1. The rule engine creates a Flag. The worker calls `POST /flags/{id}/advice` once
   for each open Flag that has no advice yet. The LLM runs only inside `api`.
2. `api` builds the facts from the record and sends them to the advisor:
   - the Flag, with the rule's evaluation and explanation
   - triggering sources (redacted quote, channel, sender role, time), marked as unconfirmed statements
   - relevant Evidence with its current `review_status`
   - the Inspection or Revision, scheduled Tasks in the Flag zone's ancestors, crew IDs and trades,
     and the sibling zones with their open-Flag counts

   No crew lead names, emails, phone numbers or usernames are sent. The Inspection row's
   own `status` is left out, because only confirmed Evidence counts as proof.
   Quotes reuse ingestion's masking of each source's known sender ID, including
   bare usernames and short numeric identifiers. LLM-extracted Evidence resolves
   that ID through its originating Event. Original quotes stay in the Site Record.
3. The output (`explanation`, up to three `proposals`) must pass `validate_advice`,
   or it is rejected with 502 and nothing is stored:
   - the explanation cites at least one triggering source (`[S1]`), and every rationale cites at least one handle
   - every `[handle]` is one the advisor was given (`S<n>`, `E<n>`, `flag`, `task:<id>`, `inspection:<id>`, `revision:<id>`)
   - affected crews, tasks and zones are IDs taken from those facts
   - the crew follow-up `message` contains no citation handles
4. Stored: `flag_advice` (explanation, cited handles → record refs) and the existing `proposals`
   (`action`, `rationale`, `affected_crews/tasks/zones`, `message`, status `proposed`).
   The Flag audit records `advice_generated`. If there are proposals, an `approval_request`
   email goes to `SUPERINTENDENT_EMAIL` with a link to `/#flag-{id}`.
5. `POST /proposals/{id}/decisions` (Superintendent, `channel: dashboard`, nonblank reason):
   - **rejected**: the Proposal becomes `rejected` and the audit records `proposal_rejected`.
     Nothing else changes: no message, no Flag state change.
   - **approved**: requires the Flag to be `acknowledged` or `in_progress`, so acknowledging
     stays a separate human action. The audit records `proposal_approved`. An
     `acknowledged` Flag then moves to `in_progress` via `action_approved`
     (`source_ref: proposal:{id}`). Each affected Crew Lead receives a `proposal_followup`
     through the outbox, by Telegram if mapped in `TELEGRAM_CREW_LEADS_JSON`, otherwise by email.

Approval never confirms Evidence, re-evaluates a Precondition or closes the Flag;
tests cover this. Crew Leads get 403; `mcp`/`chat` channels and agent roles get 422.
Each Proposal is decided once; a second decision returns 409. A closed Flag cannot
receive advice or decisions (409).

The existing MCP `POST /agent/proposals` remains a storage-only suggestion path.
Those rows retain their Flag, channel, source references and creation time and
remain `proposed`; they have no reviewed crew-delivery targets or message, so the
decision endpoint rejects them with 409. Agent-tagged clients cannot call the
dashboard decision endpoint. `GET /proposals[/{id}]` preserves the existing record
fields and can also read advisor records (`channel: advisor`) and their decided
status. The Flag inbox's approval flow uses the advisor records in `FlagAdvice`.

`GET /flags` and `GET /flags/{id}` include `advice` (or `null`). Each citation's
Evidence `review_status` is read live, so a later human review stays visible.

## Outbox

Migration `0014` extends `outbox_messages.kind` with `approval_request`,
`proposal_followup` and `compliance_reply`, retaining `warning` and `escalation`.
It replaces the one-message-per-Flag-and-kind
constraint with a unique `dedup_key` (`warning:<flag>`, `escalation:<flag>`, `approval:<advice>`,
`followup:<proposal>:<lead>`; NULL for Telegram compliance replies). Only a
delivered `warning` moves `detected` → `notified`.
It follows the merged `0013` learning migration and extends the existing
`proposals` table with nullable advice/ordinal/message/decision fields and empty
affected-party lists for existing rows. Existing agent suggestions are retained
on upgrade and downgrade to `0013`; only the new advisor rows are removed on downgrade.

## Offline and live

With `LLM_PROVIDER=cached`, advice comes from `backend/demo/advice-cache.json`, keyed
by Flag type, zone, task and Precondition. The hero Flag A entry proposes postponing
closing work in 3B and moving the drywall crew to 3A/3C for non-closing work. Other
Flags return `cache_miss` (502), the worker logs it and retries on the next pass.
The contradictory hero entry also matches the Evidence snapshot (citation handles,
origins, kinds, claims, scopes and review statuses). A human review or an additional
statement changes that snapshot: incompatible cached wording returns `cache_miss`,
without storing advice or queuing an approval request. Generic entries that cite
no individual Evidence continue to use the deterministic Flag evaluation.
With `openai_compatible`, the same provider settings as extraction are used.

Hero check: import the seed, ingest `backend/demo/closing-work.json`, wait for the
worker (or `POST /flags/{id}/advice`), acknowledge the Flag in the dashboard, then
approve the Proposal as Superintendent. The Flag shows `in_progress` and the outbox
holds the follow-up for `lead-drywall`.

## Not included

- Advice is generated once per Flag. It is not regenerated when the evaluation changes; `created_at` shows how old it is.
- Site Knowledge (#21) is not part of the facts yet.
- Approval does not change the schedule. Follow-up messages are the only effect.
