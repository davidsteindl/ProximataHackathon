# Dashboard design brief

Tracked in [issue #35](https://github.com/davidsteindl/ProximataHackathon/issues/35).
This directory is the shared handoff for the mockup; the mockup has not been
created yet. Production implementation stays in its existing feature issues.

## Direction and layout

Simple and functional, with enough character to feel designed. Make the plan
the visual focus; use clear typography, consistent spacing and restrained
status colours. Keep the controls easy to scan.

- **Left:** the large 3D plan view, including floor isolation, a top-down view
  and Zone selection. A static plan representation is sufficient for the mockup.
- **Right:** a collapsible information widget with relevant Site/Zone data,
  current revision, conflicts, blockers and pending human decisions. Use the
  existing Flag/Precondition model for conflicts and blockers.
- Show both expanded and collapsed widget states, with a visible reopen
  control. Collapsing it gives the plan more space and preserves the selection.
- Selecting a Zone, especially 3B, updates the context shown on the right.
  Keep the selected Zone and its relationship to the plan clear.

## Workflow and shared artifact

David will create the mockup with Claude's `/design` workflow, then use the
repo-local `/unslop` skill to review and refine it. Run Claude in the checkout
containing `.claude/skills/unslop/`. That skill is separate from `/design`.

Save the resulting artifact as `design/mockup/index.html` with any supporting
HTML/CSS/JavaScript and assets under `design/mockup/`. Keep the source readable,
use local assets and document how to open it. A Claude artifact link may be
included, but the repository copy is the handoff other agents must be able to
inspect and use without access to David's Claude session.

Add `design/HANDOFF.md` when delivering the mockup: describe navigation,
components, typography, spacing, status colours, synthetic fixtures and the
mapping to existing APIs or implementation issues. Record open decisions.
Include screenshots of the right widget expanded and collapsed as references.

## Domain constraints

Use the synthetic Site record and hero scenario from `docs/PLAN.md`, with the
DXF plans in `cad/plans/`. Label mock data. Keep Evidence review, Flag
acknowledgment, Proposal approval and Flag closure as distinct human actions;
Evidence review must also work without a Flag. Show unconfirmed Evidence and
uncertain or contradictory Preconditions accurately.

Gmail/Telegram notifications link into the dashboard. Human decisions happen
through dashboard controls; the Outbox sends external notifications. Chat
cannot confirm Evidence, approve Proposals or close Flags.

Issue #35 contains the complete workflow, role and accessibility criteria.
