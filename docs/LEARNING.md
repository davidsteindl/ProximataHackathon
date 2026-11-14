# Learning loop (#21)

The API owns feedback knowledge. No other service accesses the database. Feedback
never changes safety rules, Evidence status, scope or human review requirements.
No LLM call is used to interpret free-text feedback as executable instructions.

## REST and storage contract

- Every successful human Flag feedback action creates one `site_knowledge` row
  linked by unique `feedback_id` to the append-only Flag audit. The audit retains
  actor, role, time, reason, decision and Flag; the Flag retains original sources.
- `GET /site-knowledge`: entries with `id`, `flag_id`, `feedback_id`, `feedback`,
  `reason`, `recorded_at`, `source_ids`, `correction_event_id` and `correction`.
- Optional `correction_event_id` on `POST /flags/{id}/actions` explicitly means
  “this planned-work extraction was a question”. Only `false_alarm` feedback can
  select a linked `planned_work` Event. It has the same human dashboard/role,
  stale-state and lifecycle checks as existing feedback. Invalid requests do not
  close the Flag or create knowledge. MCP/chat cannot submit this human decision.
- On subsequent ingestion, after advisory extraction and quote validation, the
  API applies a deterministic correction to `question` **only** for identical
  full source text, Site, sender role, Crew, Event ordinal, quote and original
  `planned_work` intent. Only that Event changes. Other claims in the same batch
  remain unconfirmed and all existing rules still run. Historical Events and
  Evidence are not rewritten. Corrected Event `details.learning` exposes the
  knowledge, feedback, original source/Event and Flag references for explanations.
- Feedback without this explicit correction is viewable context, not a reason to
  suppress any future Flag. Corrections do not generalize to similar messages,
  other Crews or roles. Free-text reasons and identities are not sent to the LLM.
- `GET /metrics/flag-feedback`: daily UTC cumulative series of `date`,
  `confirmed_flags`, `reviewed_flags`, `confirmed_share`. Each assessed Flag
  counts once; its latest feedback as of each day wins. `confirmed` and `resolved`
  are positive; `false_alarm` is negative. No feedback means exclusion, not a
  presumed false alarm. Empty history returns `[]`, not a misleading 0%.
- Seed import/reset deletes knowledge before its referenced records. No learned
  state is silently carried into a fresh demo baseline.

## Synthetic offline demo (handoff for #5 / #22)

Use the README seed/import procedure and `LLM_PROVIDER=cached`. The cache includes
an **intentionally incorrect synthetic extraction** for the following question;
its 0.98 confidence is neither truth nor confirmed Evidence.

1. Submit the fixture through the normal ingestion endpoint:

   ```sh
   curl -fsS http://localhost:8000/ingestion/messages \
     -H 'Content-Type: application/json' \
     --data-binary @backend/demo/false-alarm-question.json
   ```

   Substitute your configured API host port if different. Open the dashboard at
   `/`. The question “Können wir morgen früh 3B zumachen?” is initially extracted
   as planned work and raises a deterministic inspection Flag.
2. Let the configured worker deliver its notification (as required by the existing
   Flag lifecycle). For a completely offline **synthetic development stack only**,
   leave Gmail/Telegram disabled and use a local-file mock transport instead:

   ```sh
   api=http://localhost:8000
   delivery=$(curl -fsS -X POST "$api/outbox/claim")
   printf '%s' "$delivery" | jq -er '.content' > /tmp/sitemind-synthetic-warning.txt
   message_id=$(printf '%s' "$delivery" | jq -er '.id')
   printf '%s' "$delivery" | jq '{lease_token, status: "sent", provider_message_id: ("synthetic-local:" + .id)}' \
     | curl -fsS "$api/outbox/$message_id/result" \
       -H 'Content-Type: application/json' --data-binary @-
   ```

   This requires `jq`, a fresh seeded stack with this single pending warning, and
   explicitly records a synthetic local delivery, **not** a Gmail/Telegram send
   or a human Evidence confirmation. It uses the existing worker REST contract;
   #22 can replace this manual mock with its replay adapter.
   In the dashboard select **Close · false alarm**, give the
   reason “A question, not an announcement”, and explicitly select this Event in
   **Optional extraction correction**. This is not an Evidence decision.
3. Site Knowledge now shows source/feedback/knowledge references and the metric.
   Replay the same payload with a **new `external_id`**, e.g.
   `learning-question-replay`. An unchanged external ID is ingestion deduplication,
   not a new extraction. Do not reset between these two submissions.
4. The new Event is a **question**, linked visibly in the timeline to its learned
   correction; no repeat work Flag is created. The old Flag remains human-closed
   and its original source/extraction/audit is preserved.
5. Submit `backend/demo/closing-work.json`. This is a real work announcement,
   not the learned question. Without confirmed applicable inspection Evidence it
   still raises a Flag. High-confidence and verbal-OK claims remain unconfirmed.
6. Seed reset removes all learned state; the question again reproduces the
   original synthetic extraction error. This makes the demo repeatable offline.

Verification: `PYTHONPATH=backend python -m pytest backend/tests/test_learning.py`;
frontend tests cover the optional correction payload, API loading, metric chart,
empty state and rendered knowledge/feedback/source references.
