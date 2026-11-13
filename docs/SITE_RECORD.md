# Static site record — Issue #5

This is the shared schema, seed and REST contract for the static site record.
The domain glossary remains in [PLAN §2](PLAN.md). OpenAPI at `/openapi.json`
describes all request and response fields. Only `api` accesses PostgreSQL.

## Zone IDs shared with Issue #3

IDs are case-sensitive and are the exact CAD unit/room/element labels. Human
readable `name` fields are not identifiers and must not be used to join CAD data.

| Kind | ID | Parent |
|---|---|---|
| building | `B1` | null |
| floor | `F1` … `F4` | `B1` |
| unit | `1A` … `1D`, `2A` … `2D`, `3A` … `3D`, `4A` … `4D` | corresponding `F1` … `F4` |
| room | `3B-BATH` | `3B` |
| element | `3B-BATH-WALL` | `3B-BATH` |

Floors have a height of 3 m; elevations are 0, 3, 6 and 9 m respectively.
These are synthetic building metadata, not CAD geometry. Plans `A-101` … `A-104`
belong to `F1` … `F4`. Plan revision file names follow `A-103_RevC.dwg`.
Issue #3 supplies actual DWG files; this issue stores file names and zone links only.
Any additional CAD zone labels must be added to the seed using this hierarchy
and coordinated between the two issues before use.

## Initial snapshot and import/reset

The seed in `backend/seed/` represents the start of the hero scenario on day 1,
2026-11-13, before Rev D arrives. Day 3 is 2026-11-15. `Site.timezone` is
`Europe/Vienna`; timestamps in seed files are UTC with a `Z` suffix.

It contains one building, four floors, sixteen units and the hero bathroom/wall;
three crews and Crew Leads; twelve schedule Tasks with predecessor IDs; four
Rev C Plan Revisions, each acknowledged by the plumbing crew; and eight pending
Inspections. In particular, `drywall-F3` starts at 07:00 Vienna time on day 3,
`A-103-C` covers `3B`, and `rough-in-F3` is pending. Rev D arrival, inspection
postponement and subsequent state changes belong to later issues, not the initial seed.

Start Compose, then run in another terminal:

```sh
docker compose exec api python -m app.seed
```

The command validates all files and relationships before changing data, then
replaces the entire static snapshot in one transaction. Repeating it is the reset
operation: modified records revert, extra static records disappear and no duplicates
accumulate. A failed import rolls back. The schema and migration history remain.
There is no automatic seed import on API startup, so restarts preserve state.

For a different complete seed directory:

```sh
docker compose cp ./my-seed api:/tmp/my-seed
docker compose exec api python -m app.seed --directory /tmp/my-seed
```

`POST /seed/import` accepts the same complete snapshot as one JSON `Seed` body
and returns record counts. It is the REST entry point for callers needing static
reset/import, including the later replay work. The CLI parses the files and calls
the same import function inside the API service. This is static bootstrap, not
the message extraction/Events ingestion from #6. There is no separate runtime
message ingestion implementation in this issue.

**Import replaces data:** use only the intended local demo database. The endpoint
has no authentication, as in the MVP skeleton. Reset currently covers only the
static tables introduced here. When Events/Flags or other referencing tables are
added, their reset behavior must be integrated in #22; they are not implicitly
deleted by this importer. Existing foreign keys can reject an incompatible reset,
which rolls back rather than leaving a partial state.

## Seed file formats

All files use UTF-8. JSON files and the CSV header are checked against the typed
Seed contract; extra fields, duplicate IDs, invalid references/hierarchies,
cyclic task predecessors and invalid time ranges are rejected.

| File | Content |
|---|---|
| `building.json` | Object with `site`, `zones`, `plans` |
| `crews.json` | Object with `crew_leads`, `crews` |
| `revisions.json` | Object with `revisions`, `acknowledgments` |
| `inspections.json` | Array of Inspections |
| `schedule.csv` | Header `id,name,zone_id,crew_id,starts_at,ends_at,predecessor_ids`; predecessor IDs separated by `\|`, empty for none |

The combined REST `Seed` object has the keys `site`, `zones`, `plans`,
`crew_leads`, `crews`, `tasks`, `revisions`, `acknowledgments`, `inspections`.
All collections are required, even if empty; at least the building Zone is required.

| Entity | Fields |
|---|---|
| Site | `id`, `name`, `start_date` (ISO date), `timezone` (IANA name) |
| Zone | `id`, `parent_id` (null for building), `kind`, `name`, optional `elevation_m`, `height_m`; both metadata fields required for floors |
| CrewLead | `id`, `name`; synthetic names, no contact details |
| Crew | `id`, `name`, `trade`, `lead_id` |
| Plan | `id`, `name`, `floor_id`; one Plan per floor in this seed contract |
| Revision | `id`, `plan_id`, `label`, positive `sequence`, `issued_at`, `file_name`, `zone_ids` |
| RevisionAcknowledgment | `crew_id`, `revision_id`, `acknowledged_at` |
| Task | `id`, `name`, `zone_id`, `crew_id`, `starts_at`, `ends_at`, `predecessor_ids` |
| Inspection | `id`, `zone_id`, `kind`, `status`, `scheduled_at` |

Zone kinds: `building`, `floor`, `unit`, `room`, `element`. Rooms belong to units;
elements can belong to units or rooms. Inspection status: `pending`, `passed`,
`failed`; the sample kinds are `rough_in` and `insulation`. IDs use letters,
digits, hyphens and underscores, at most 64 characters. All timestamps require a
timezone offset and are normalized to UTC. A revision's zones must be within
its Plan's floor. Acknowledgments cannot predate the revision.

## REST read access

| Endpoint | Result |
|---|---|
| `GET /site` | Site or `null` before import |
| `GET /zones` | Tree with nested `children`, including floor metadata |
| `GET /tasks` | Tasks, ordered by start time then ID, with predecessor IDs |
| `GET /crews` | Crews with nested `lead` |
| `GET /plans` | Plans with `current_revision` and complete `revisions` history; each Revision includes acknowledgments |
| `GET /inspections` | Inspections with source Zone ID and status |

`/tasks` and `/inspections` accept `zone_id` and `include_descendants` (default
`true`). The scope is the selected Zone and its descendants, never ancestors.
An unknown Zone returns `404`. Empty collections return `[]`.

Tasks also accept `from_time` and `to_time`, timezone-aware ISO timestamps. They
return Tasks overlapping the half-open interval `[from_time, to_time)`; either
bound may be omitted. Invalid/reversed ranges return `422`.

```text
/tasks?zone_id=F3&from_time=2026-11-15T00:00:00Z&to_time=2026-11-16T00:00:00Z
/inspections?zone_id=F3
```

The dashboard shows the Zone tree and floor metadata, a schedule with Zone/date
filters, Crews/Leads, Plan Revisions/acknowledgments and Inspection statuses.
Displayed times use the Site's timezone; date filter boundaries are explicitly
UTC (inclusive From, exclusive Before). Inspection statuses are stored facts;
there is no inferred ancestor status, Preconditions evaluation or Flag creation.

Current Revision is the greatest `sequence` per Plan, not lexical label order.
Labels and sequences are unique per Plan. Historical acknowledgments stay attached
to the acknowledged Revision; they never become acknowledgment of a newer one.

## Schema and migrations

SQLAlchemy models are in `backend/app/models.py`. Alembic revision `0001`
creates `sites`, `zones`, `crew_leads`, `crews`, `plans`, `revisions`,
`revision_zones`, `revision_acknowledgments`, `tasks`, `task_dependencies`,
`inspections`, with foreign keys, uniqueness and range/status constraints.
The API applies `alembic upgrade head` before starting in Compose; no other
service performs migrations. Application startup does not use `create_all`.

The schema owner for this initial contract is Issue #5. Before adding a migration,
rebase on current `origin/main` and coordinate with the schema owner (PLAN §10).
Keep one Alembic head, never modify a migration already merged, and document
contract changes in PLAN/README and the PR. After model edits, generate a reviewed
migration in the API environment containing the edited checkout:

```sh
docker compose exec api alembic revision --autogenerate -m "describe change"
docker compose exec api alembic upgrade head
```

The container does not bind-mount source: rebuild it with edited models first,
then copy the generated migration back into `backend/migrations/versions/`
before committing. Do not leave migration files only inside a container.
`docker compose exec api alembic current` shows the applied revision.

Unit tests run without external credentials, using SQLite with foreign keys
enabled and the actual Alembic migration. They cover import/reset/rollback,
validation, REST filters and revision history, and migration/model agreement plus
downgrade/upgrade. PostgreSQL is the runtime database; Compose smoke checks
verify the deployed migration, import and REST/dashboard path on PostgreSQL.
