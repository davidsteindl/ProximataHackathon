# DXF geometry contract — Issue #15

The API extracts the [documented CAD layers](../cad/README.md) from DXF R2000
(AC1015) in millimetres. No DWG conversion, plan diff, conflict evaluation or
3D frontend is implemented here. Both the future 3D view and agent query the
same stored geometry through REST; no MCP tool is introduced by this issue.

## Import the supplied plans

Start Compose and import the static Site record before the geometry:

```sh
docker compose up --build -d
docker compose exec api python -m app.seed
docker compose exec api python -m app.cad_import
```

The second command is the existing **destructive demo reset**, not a prerequisite
on every subsequent import. The third command imports all five files from #3
without per-file manual steps. `cad/` is mounted read-only at `/cad` in the API
service. PostgreSQL stores the original bytes, SHA-256, filename, floor metadata,
extracted elements and their Zone associations for each Revision.

`cad/import-metadata.json` supplies the input metadata separately from the drawing
generator's manifest. Every entry has `file` (relative to this metadata file) and
`metadata`: `plan_id` (sheet), `floor_id`, `revision_id`, `label`, numeric `sequence`,
timezone-aware `issued_at`. The sample C entries match the seed exactly; A-103 D
is sequence 4, issued on scenario day 1 at 10:15 Vienna time. The generator and its
committed DXFs are unchanged. A different batch can be provided with:

```sh
docker compose exec api python -m app.cad_import --metadata /cad/import-metadata.json
```

Each file is an atomic import. A batch reports each result and stops on a failed
entry; already successful entries remain stored. Repeating an identical import is
idempotent, so the batch can be retried. Changed bytes for an existing Revision
return a conflict rather than silently changing its original source. Supply new
Revision metadata for a changed plan. Source filenames are preserved as basenames.

The Plan must already exist and belong to the supplied floor. Known Revision
metadata must match. A new Revision is registered from explicit input metadata,
without inferring label order or an issue timestamp from the DXF. Registration
updates what `/plans` considers the current Revision by its sequence, but creates
no Crew acknowledgment, Evidence, Event or Flag. Existing acknowledgment/history
records are left intact. `Revision.zone_ids` is left untouched for existing
Revisions and is initially empty for a new one: changed/affected Zones are #17's
responsibility. Geometry coverage uses its own associations below, not that field.
Accordingly `/plans` can return a Revision with `zone_ids: []`; this means that
affected-zone information has not been supplied, not that a diff found no changes.

## REST import and source retrieval

`POST /geometry/import` accepts multipart form fields:

| Field | Content |
|---|---|
| `file` | Original `.dxf` file bytes |
| `plan_id`, `floor_id` | Seeded sheet and floor IDs, e.g. `A-103`, `F3` |
| `revision_id`, `label`, `sequence` | e.g. `A-103-D`, `D`, `4` |
| `issued_at` | Explicit timezone-aware ISO timestamp |

Example (Bash; API port defaults to 8000):

```sh
curl http://localhost:8000/geometry/import \
  -F file=@cad/plans/A-103_RevD.dxf \
  -F plan_id=A-103 -F floor_id=F3 -F revision_id=A-103-D \
  -F label=D -F sequence=4 -F issued_at=2026-11-13T09:15:00Z
```

The result contains `revision_id`, `element_count`, `source_sha256` and
`ignored_layers` (`layer`, `entity_count`). Invalid format, units, labels or
floor metadata return `422`; conflicting metadata or changed source content
return `409`. The previous stored data remains unchanged. All import metadata,
query parameters and output shapes are described by OpenAPI at `/docs`.

`GET /geometry/revisions/{revision_id}/source` retrieves the exact original DXF
bytes as an attachment. It returns `404` when no source was imported. Only the API
accesses PostgreSQL. Source retention is independent of the read-only sample mount:
already imported files can still be retrieved if their sample file is removed.

## Geometry reads

`GET /geometry` returns one result per Plan: its highest-sequence **imported**
Revision. Revisions registered without geometry do not hide existing geometry.
Supply `revision_id` to request an exact historical Revision. Also supported:

```text
/geometry?floor_id=F3
/geometry?zone_id=3B
/geometry?zone_id=3B-BATH&revision_id=A-103-C
/geometry?zone_id=3B-BATH-WALL&revision_id=A-103-D
```

Filters combine with AND. `zone_id` includes descendants by default;
`include_descendants=false` uses that exact association. Unknown floor/Zone/Revision
IDs return `404`, while a known selection with no imported geometry returns `[]`.
The result includes Revision/sheet/floor identity, label, sequence, issue timestamp,
`units: "m"`, `floor_height_m`, `floor_elevation_m`, source filename/hash,
ignored-layer report, and `elements` with:

| Field | Meaning |
|---|---|
| `element_id` | Stable XDATA ID when present; unit/room ID from its label; otherwise explicit `handle:<DXF handle>` fallback |
| `kind`, `layer` | `unit`, `room`, `wall`, `door`, `plumbing_fixture`, `drain`, and original layer |
| `zone_ids` | Matching Zones and their ancestors, including the floor/building |
| `shape.outline` | Unit/room XY polygon; implicitly closed, without requiring the first vertex to be repeated |
| `shape.segments` | Wall/pipe centreline segments, or door opening segment |
| `shape.position` | Insert position for doors/MEP; first vertex for line elements |
| `shape.thickness_m` | Wall thickness from constant polyline width |
| `shape.rotation_deg`, `shape.width_m` | Door/insert rotation (counterclockwise in XY); door opening width in metres |
| `shape.block_name`, `shape.scale` | MEP subtype (`WC`, `SINK`, `SHOWER`, `STACK`) or `DOOR`, and original dimensionless XY insert scale |

Unused shape fields are null/empty. All positions, polygon vertices, segment
endpoints, thicknesses and door widths are in **metres**. XY uses the original
plan axes shared by the supplied floor plans. For 3D, use `floor_elevation_m` as
base Z and `floor_height_m` as wall extrusion height. No arbitrary fixture meshes,
door heights or building dimensions are invented by the extractor.

### Association and supported entities

Unit and room outlines must be closed LWPOLYLINEs with exactly one matching
`TEXT` stamp on the corresponding `-IDEN` layer. Labels must match an existing
Zone of the right kind/floor. XDATA area IDs, when present, must match the label.
Parent relations come from the Site model, not from string-prefix guesses.

Line entities are associated with every labelled unit/room they overlap by a
positive length, including shared boundaries. A corner-only touch does not claim
a neighbouring Zone. Doors use their opening segment, so a hinge on a room/unit
boundary still associates correctly. MEP point inserts use inclusive point-in-
polygon tests. Room matches include their parent unit; shared walls can belong to
multiple rooms/units. The explicit seed element Zone `3B-BATH-WALL` is linked by
its stable XDATA ID, with its parent/floor checked. Corridors have no room Zone and
retain their floor/building association. Filtering returns complete elements;
it does not clip long shared walls to a selected room.

Supported geometry follows #3: straight planar LWPOLYLINEs, constant positive
wall widths, and planar positive-scale `DOOR`/`WC`/`SINK`/`SHOWER`/`STACK` INSERTs.
Arbitrary CAD layouts and curved polylines are not supported by this MVP contract.
Title-block annotations are ignored. Unknown modelspace layers are ignored and
reported with entity counts rather than aborting the import. Unsupported geometry
on a **known** required layer, missing/duplicate labels or element IDs, wrong units
and invalid required outlines are rejected rather than silently losing geometry.
Block definitions' inherited layer `0` is not an unknown modelspace layer.

XDATA IDs keep their identity across C/D, including `3B-BATH-WALL` and the drain.
Without XDATA, handles are only stable if the drawing editor preserves them;
geometry-based identity matching is not implemented here. No plan diff is computed.

## Persistence and reset

Alembic `0003` adds `plan_geometry`, `geometry_elements`, `geometry_element_zones`
after `0002`, retaining one migration head. Floor height/elevation are captured
at import. The original source and extracted geometry are stored independently
per Revision. The existing seed reset deletes the Revision snapshot; explicit
database cascades remove its derived geometry, associations and source bytes.
After a demo reset, rerun `python -m app.cad_import` to populate geometry again.
Reset does not leave orphan geometry pointing at removed Zones or Revisions.

Tests use all five #3 plans and the real migrations, covering metre scaling,
Zone/room/element associations, shared walls/doors, source-byte retention,
stable C/D IDs, selection semantics, unknown layers, malformed input, atomic
failure/idempotency, no fabricated confirmations and cleanup on seed reset.

## Plan diff (#17)

`GET /geometry/revisions/{revision_id}/diff` compares the revision with the
immediately preceding `Revision.sequence` of the same Plan. Both geometries must
be imported (`409` otherwise; unknown revision: `404`). The response contains
`revision_id`, `previous_revision_id`, `origin: deterministic_plan_diff`,
`affected_zone_ids` and `zones: [{zone_id, changes}]`. Each change has an
`element_id`, `change` (`added`, `removed`, `moved`) and full `before`/`after`
elements (null for an absent side). `moved` includes shape, layer, kind and zone
membership changes of the same stable ID. Unchanged elements are omitted.

Changes are grouped by affected unit Zone from both revisions. Building/floor
coverage is excluded to avoid flagging unrelated apartments. Stable SITEMIND IDs
are preferred; handle-based IDs can only match when handles persist across files.
Identical extracted geometry yields an empty diff, regardless of DXF metadata.
The comparison never creates Evidence or certifies any Precondition.
