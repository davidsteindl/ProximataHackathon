# Conflict A and the Flag inbox (#7)

`GET /flags` returns open Flags ordered by severity (high, medium, low), then
creation time and ID. `GET /flags/{id}` returns one Flag, or 404. Both include
affected Zone/Task/activity, required Inspection, responsible Crew Lead, current
Precondition evaluation, timestamps, triggering Events with original Source
Messages/quotes, Evidence with review history, and the Flag audit trail.
These endpoints are read-only. Lifecycle actions and dashboard Evidence review
belong to #9; ingestion, MCP and chat cannot approve Evidence here.

## Rule contract

For the hero MVP, `planned_work` Events with activity `closing_work`, `drywall`
or `insulation` require a confirmed **rough_in** Inspection. The separate
insulation Inspection is not an additional MVP requirement (PLAN §7 day 4).
The extraction prompt uses the canonical `closing_work` activity for explicit
closure announcements; deliveries and questions do not qualify.
Every new Event triggers a recheck. Only closing-work announcements create work
candidates; missing/unresolved zones never become invented global work scope.

The nearest ancestor (including the work Zone) with a rough-in Inspection
defines the requirement. Multiple Inspections at that level are ambiguous and
evaluate as unknown. No matching Inspection also evaluates as unknown. Task
matching uses the work Zone/ancestors, Crew or trade, and overlapping Event time;
only a unique match at the nearest level is linked. Work without a matching Task
is still checked. Responsibility comes from its Crew or a unique trade Crew;
missing responsibility is explicitly shown as unassigned.

Evidence must name the selected Inspection **and its exact Zone**, have source
provenance, and remain unrejected. A confirmed positive can satisfy the
requirement only with a human review or explicit `seed_baseline` import.
Confidence and `Inspection.status` alone never satisfy it. An LLM success claim
whose Source Message predates the required Inspection's scheduled time is stale.
This is a conservative freshness boundary using the current Site Record fields;
there is no invented expiry period or automatic certification from CAD.
Source-backed claims in the work Zone/ancestors with the same inspection kind
but an unresolved Inspection ID are also shown for review. Such claims cannot
satisfy the requirement; an unresolved negative can contradict a confirmed pass.

- `satisfied`: valid confirmed passed proof, with no unresolved counterclaim.
- `not_satisfied`: confirmed failed or pending proof without a conflicting pass.
- `unknown`: missing, unconfirmed-only, stale, ambiguous or mismatched proof.
- `contradictory`: applicable passed and failed/pending claims disagree,
  including unconfirmed counterclaims. Explicit human rejection resolves a
  counterclaim. An earlier synthetic pending baseline permits a later confirmed
  pass as the normal inspection progression; a failed claim is never silently
  superseded.

## Persistence and integration

Migration `0005` adds `flags`, `flag_sources`, and `flag_audit`. The deterministic
open conflict key uses type, work Zone, matched Task (otherwise Crew/unassigned)
and Precondition. Repeat deliveries, distinct announcements and later scans
attach to the same open Flag. Each Event is linked once. Site row locking
serializes evaluation on PostgreSQL; a unique open key also guards persistence.
Creation is audited with rule actor, time, channel and source. Evaluation changes
retain the human review actor and Evidence reference when triggered by review.

`app.rules.PRECONDITIONS` registers rules with `applies`/`evaluate`; Flag creation,
deduplication and audit are shared. `evaluate_site(session, ...)` rechecks persisted
work Events in the caller's transaction and can be reused by #14's future scan.
It does not implement a scheduler or independently flag every scheduled Task.
SQLAlchemy Session hooks run it after new Events and human `EvidenceReview`
records are flushed, in the same transaction. #9 must validate/authorize decisions
before appending immutable reviews through this ORM contract; bulk SQL bypasses
ORM hooks and must explicitly call the evaluator. A failed transaction rolls
back Events, Flags and audit together.

A satisfied Precondition only updates the evaluation/explanation; the Flag stays
open for human closure. #9 must clear `open_key` when closing a Flag so a future
conflict can be recorded. No automatic closure, outgoing notification, Proposal
or lifecycle transition is implemented in #7. Seed reset clears Flags, source
links and audit before their referenced Site Record tables.

## Verify offline

Run the seed and `backend/demo/closing-work.json` ingestion from the README,
then load the dashboard or request `/flags`: exactly one high-severity Flag A
for 3B links `drywall-F3`, `rough-in-F3`, the drywall Crew Lead and the original
quote. Repeat ingestion and verify its ID is unchanged. The inbox remains
visible across schedule/timeline filters. Expand a Flag for source and Evidence
details. An unconfirmed inspection success does not authorize work.

From `backend`, `python -m pytest tests/test_rules.py` covers evaluation, review-triggered
rechecks, dedup, reset, read-only routes and migration parity/rollback.
