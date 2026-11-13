# Synthetic floor plans (issue #3)

Synthetic plans of the fictional building from the hero scenario (PLAN §7):
1 building, 4 floors, units A–D per floor. They are the input for the CAD
pipeline (#15), the plan diff (#17) and the 3D view (#16).

| File | Sheet | Floor | Revision |
|---|---|---|---|
| `plans/A-101_RevC.dxf` | A-101 | F1 | C |
| `plans/A-102_RevC.dxf` | A-102 | F2 | C |
| `plans/A-103_RevC.dxf` | A-103 | F3 | C |
| `plans/A-103_RevD.dxf` | A-103 | F3 | D: unit 3B bathroom wall moved 300 mm east, shower drain rerouted |
| `plans/A-104_RevC.dxf` | A-104 | F4 | C |
| `plans/manifest.json` | sheets, floors (elevation, height), zone hierarchy, layers | | |

**Format:** DXF R2000 (AC1015), units millimetres. DXF is our internal format
(PLAN §3.5) and opens in free viewers (e.g. LibreCAD, ODA Viewer). A DWG export
is a follow-up; until then the hero mail attaches `A-103_RevD.dxf` and the
pipeline uses its direct-DXF path.

## Regenerate

```sh
pip install ezdxf==1.4.5
python cad/generate_plans.py        # writes cad/plans/
python -m pytest backend/tests/test_synthetic_plans.py
```

The generator is the single source. Do not edit the DXF files by hand: a test
fails if the committed files differ from the generator output.

## Zone IDs

These IDs are shared with the seed (#5).

| Kind | Pattern | Example |
|---|---|---|
| Building | `BLDG` | `BLDG` |
| Floor | `F<n>` | `F3` |
| Unit | `<floor><letter>` | `3B` |
| Room | `<unit>-<code>`, codes `LIV BED KIT HALL BATH STOR` | `3B-BATH` |
| Common area (corridor) | `F<n>-CORE` | `F3-CORE` |

The full list with parents and names is in `plans/manifest.json` (`zones`).
Floor `F<n>` is drawn on sheet `A-10<n>`; elevation `(n-1) × 3000 mm`, storey
height 3000 mm (not in the DXF, metadata only).

## Layer convention

Based on the AIA / US National CAD Standard layer names.

| Layer | Element type | Representation |
|---|---|---|
| `A-WALL-EXTR` | Exterior wall | LWPOLYLINE on the wall centreline, `const_width` = thickness (300) |
| `A-WALL` | Interior, party and corridor walls | LWPOLYLINE on the centreline, `const_width` = thickness (100 / 200). Door openings are gaps |
| `A-DOOR` | Door | INSERT of block `DOOR` at the hinge; opening runs along the rotated +x axis; `xscale` = leaf width |
| `A-AREA-UNIT` | Unit outline | Closed LWPOLYLINE on wall centrelines |
| `A-AREA-UNIT-IDEN` | Unit label | TEXT = unit zone ID, inside its outline |
| `A-AREA` | Room / common area outline | Closed LWPOLYLINE on wall centrelines |
| `A-AREA-IDEN` | Room label (Raumstempel) | TEXT = room zone ID, inside its outline |
| `P-FIXT` | Plumbing fixture | INSERT of block `WC`, `SINK` or `SHOWER` at its centre |
| `P-SANR` | Sanitary drain | LWPOLYLINE = pipe run; INSERT of block `STACK` = stack |
| `A-ANNO-TTLB` | Title block | TEXT `SHEET: …`, `FLOOR: …`, `REV: …` and revision notes. Not geometry; ignore for parsing and plan diff |

Rules:

- **Labels map outlines to zones:** every closed polyline on `A-AREA` /
  `A-AREA-UNIT` contains exactly one TEXT on the matching `-IDEN` layer, and
  that text is the zone ID. Elements are linked to a zone by position (inside the
  outline).
- **Stable element IDs:** every geometry entity carries XDATA of application
  `SITEMIND` with one string (group 1000), e.g. `3B-WALL-09`, `3B-DOOR-04`,
  `3B-SANR-03`, `F3-WALL-01` (floor-level walls). Outlines carry their zone ID.
  The same element keeps its ID in every revision, so a diff can report it as
  moved rather than removed + added.
- **Block contents** are on layer `0` with colour BYBLOCK; the element type
  comes from the INSERT's layer and block name.
- Any other layer is unknown and should be ignored and reported (#15).

## Rev C → Rev D

Only these elements change (all in unit 3B; tested):

| Element | Change |
|---|---|
| `3B-WALL-09` | bathroom/storage wall moved from x = 22000 to 22300 (+300 mm) |
| `3B-BATH`, `3B-STOR` | room outlines follow the wall |
| `3B-SANR-03` | shower drain rerouted along the new wall |

Plus one extra revision-note line on `A-ANNO-TTLB`.
