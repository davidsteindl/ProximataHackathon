"""Generate the synthetic SiteMind floor plans (issue #3).

One DXF per storey (sheets A-101 .. A-104, Rev C) plus A-103 Rev D, which moves
the bathroom wall of unit 3B by 300 mm and reroutes the shower drain. Every
element follows the layer convention in ``cad/README.md`` (PLAN §3.5) and carries
a stable element ID as XDATA (application ``SITEMIND``).

The plans are delivered as DXF (the internal format, PLAN §3.5). A DWG export is
a follow-up; the CAD pipeline accepts DXF directly.

Usage::

    python cad/generate_plans.py [--out DIR]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

APPID = "SITEMIND"
DXF_VERSION = "R2000"  # AC1015: widest viewer and converter support
DEFAULT_OUT = Path(__file__).resolve().parent / "plans"

# --- Layer convention (AIA / US National CAD Standard style) -----------------
# name: (ACI colour, element type, description)
LAYERS: dict[str, tuple[int, str, str]] = {
    "A-WALL-EXTR": (7, "wall", "Exterior wall, centreline polyline, width = thickness"),
    "A-WALL": (7, "wall", "Interior / party / corridor wall, centreline polyline, width = thickness"),
    "A-DOOR": (3, "door", "Door, INSERT of block DOOR at the hinge, scale = leaf width"),
    "A-AREA-UNIT": (5, "unit", "Unit outline, closed polyline on wall centrelines"),
    "A-AREA-UNIT-IDEN": (5, "unit_label", "Unit stamp, TEXT = unit zone ID (e.g. 3B)"),
    "A-AREA": (8, "room", "Room outline, closed polyline on wall centrelines"),
    "A-AREA-IDEN": (2, "room_label", "Room stamp, TEXT = room zone ID (e.g. 3B-BATH)"),
    "P-FIXT": (4, "plumbing_fixture", "Plumbing fixture, INSERT of block WC / SINK / SHOWER"),
    "P-SANR": (6, "drain", "Sanitary drain: polyline = pipe run, INSERT of block STACK = stack"),
    "A-ANNO-TTLB": (7, "annotation", "Title block text (sheet, floor, revision); ignored by parsing and diff"),
}

# --- Building metadata --------------------------------------------------------
# Zone IDs, floor heights and plan -> floor live in the seed (#5,
# backend/seed/building.json). Every stamp below must exist there (tested).
FLOORS = [1, 2, 3, 4]
SHEET_REVISIONS = {1: ["C"], 2: ["C"], 3: ["C", "D"], 4: ["C"]}
REVISION_NOTES = {
    "C": "Rev C: issued for construction.",
    "D": "Rev D: unit 3B bathroom wall moved 300 mm east, shower drain rerouted along the new wall.",
}

BUILDING_W, BUILDING_D = 24000, 20000
UNIT_W, UNIT_D = 12000, 8500
CORRIDOR_Y0, CORRIDOR_Y1 = 8500, 11500
EXT_WALL, PARTY_WALL, INT_WALL = 300, 200, 100

# Unit placement: (x offset, y offset, rotated 180°). A/B face south, C/D north.
UNIT_PLACEMENT = {
    "A": (0, 0, False),
    "B": (12000, 0, False),
    "C": (0, CORRIDOR_Y1, True),
    "D": (12000, CORRIDOR_Y1, True),
}

HERO_UNIT = "3B"
HERO_REVISION = "D"


def sheet_id(floor: int) -> str:
    return f"A-10{floor}"


def plan_filename(floor: int, rev: str) -> str:
    return f"{sheet_id(floor)}_Rev{rev}.dxf"


# --- Element model ------------------------------------------------------------
Point = tuple[float, float]


@dataclass(frozen=True)
class Polyline:
    id: str
    layer: str
    points: tuple[Point, ...]
    closed: bool = False
    width: float = 0


@dataclass(frozen=True)
class Stamp:
    layer: str
    text: str
    at: Point
    height: float


@dataclass(frozen=True)
class Insert:
    id: str
    layer: str
    block: str
    at: Point
    rotation: float = 0
    scale: float = 1


Element = Polyline | Stamp | Insert


def _rect(x0: float, y0: float, x1: float, y1: float) -> tuple[Point, ...]:
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def unit_template(unit: str, moved_bath_wall: bool) -> list[Element]:
    """Unit layout in local coordinates (0..12000 x 0..8500, corridor at the top).

    Walls on the unit boundary (exterior, party, corridor) belong to the floor.
    """
    bath_x = 10300 if moved_bath_wall else 10000
    els: list[Element] = []

    walls = [
        ((0, 5500), (4500, 5500)),
        ((5400, 5500), (10900, 5500)),
        ((11700, 5500), (12000, 5500)),
        ((7000, 0), (7000, 4300)),
        ((7000, 5200), (7000, 6200)),
        ((7000, 7000), (7000, 8500)),
        ((3000, 5500), (3000, 6500)),
        ((3000, 7400), (3000, 8500)),
        ((bath_x, 5500), (bath_x, 8500)),  # bathroom wall: moved in Rev D
    ]
    for n, pts in enumerate(walls, 1):
        wall_id = f"{unit}-WALL-{n:02d}"
        if unit == HERO_UNIT and n == len(walls):
            wall_id = f"{unit}-BATH-WALL"  # seed element zone of the hero wall
        els.append(Polyline(wall_id, "A-WALL", pts, width=INT_WALL))

    els.append(Polyline(unit, "A-AREA-UNIT", _rect(0, 0, UNIT_W, UNIT_D), closed=True))
    els.append(Stamp("A-AREA-UNIT-IDEN", unit, (5000, 7600), 400))

    rooms = {
        "LIV": (_rect(0, 0, 7000, 5500), (3500, 2750)),
        "BED": (_rect(7000, 0, 12000, 5500), (9500, 2750)),
        "KIT": (_rect(0, 5500, 3000, 8500), (1500, 7000)),
        "HALL": (_rect(3000, 5500, 7000, 8500), (5000, 6600)),
        "BATH": (_rect(7000, 5500, bath_x, 8500), (8300, 6900)),
        "STOR": (_rect(bath_x, 5500, 12000, 8500), (11150, 7000)),
    }
    for code, (outline, stamp_at) in rooms.items():
        zone = f"{unit}-{code}"
        els.append(Polyline(zone, "A-AREA", outline, closed=True))
        els.append(Stamp("A-AREA-IDEN", zone, stamp_at, 250))

    doors = [  # hinge, rotation, leaf width
        ((5500, 8500), 180, 1000),  # entrance from corridor
        ((5400, 5500), 180, 900),  # hall -> living
        ((7000, 4300), 90, 900),  # living -> bedroom
        ((7000, 7000), 270, 800),  # hall -> bathroom
        ((3000, 6500), 90, 900),  # hall -> kitchen
        ((10900, 5500), 0, 800),  # bedroom -> storage
    ]
    for n, (at, rot, width) in enumerate(doors, 1):
        els.append(Insert(f"{unit}-DOOR-{n:02d}", "A-DOOR", "DOOR", at, rot, width))

    fixtures = [
        ("WC", (9550, 5900), 0),
        ("SINK", (7600, 8200), 0),
        ("SHOWER", (9450, 7950), 0),
        ("SINK", (1500, 8200), 0),  # kitchen sink
    ]
    for n, (block, at, rot) in enumerate(fixtures, 1):
        els.append(Insert(f"{unit}-FIXT-{n:02d}", "P-FIXT", block, at, rot))

    els.append(Insert(f"{unit}-SANR-01", "P-SANR", "STACK", (9850, 5650)))
    els.append(Polyline(f"{unit}-SANR-02", "P-SANR", ((7600, 8200), (7600, 5650), (9850, 5650))))
    if moved_bath_wall:  # rerouted along the relocated wall
        shower_drain = ((9450, 7950), (10200, 7950), (10200, 5650), (9850, 5650))
    else:
        shower_drain = ((9450, 7950), (9850, 7950), (9850, 5650))
    els.append(Polyline(f"{unit}-SANR-03", "P-SANR", shower_drain))
    return els


def _place(el: Element, dx: float, dy: float, rotated: bool) -> Element:
    def p(pt: Point) -> Point:
        x, y = pt
        if rotated:
            x, y = UNIT_W - x, UNIT_D - y
        return (x + dx, y + dy)

    if isinstance(el, Polyline):
        return Polyline(el.id, el.layer, tuple(p(q) for q in el.points), el.closed, el.width)
    if isinstance(el, Stamp):
        return Stamp(el.layer, el.text, p(el.at), el.height)
    rotation = (el.rotation + (180 if rotated else 0)) % 360
    return Insert(el.id, el.layer, el.block, p(el.at), rotation, el.scale)


def floor_elements(floor: int, rev: str) -> list[Element]:
    fid = f"F{floor}"
    els: list[Element] = []

    # Floor-level walls: exterior, corridor, party walls. Gaps = unit entrances.
    els.append(
        Polyline(f"{fid}-WALL-01", "A-WALL-EXTR", _rect(0, 0, BUILDING_W, BUILDING_D), closed=True, width=EXT_WALL)
    )
    floor_walls: list[tuple[str, tuple[Point, ...], int]] = [
        ("A-WALL", ((0, CORRIDOR_Y0), (4500, CORRIDOR_Y0)), PARTY_WALL),
        ("A-WALL", ((5500, CORRIDOR_Y0), (16500, CORRIDOR_Y0)), PARTY_WALL),
        ("A-WALL", ((17500, CORRIDOR_Y0), (BUILDING_W, CORRIDOR_Y0)), PARTY_WALL),
        ("A-WALL", ((0, CORRIDOR_Y1), (6500, CORRIDOR_Y1)), PARTY_WALL),
        ("A-WALL", ((7500, CORRIDOR_Y1), (18500, CORRIDOR_Y1)), PARTY_WALL),
        ("A-WALL", ((19500, CORRIDOR_Y1), (BUILDING_W, CORRIDOR_Y1)), PARTY_WALL),
        ("A-WALL", ((12000, 0), (12000, CORRIDOR_Y0)), PARTY_WALL),
        ("A-WALL", ((12000, CORRIDOR_Y1), (12000, BUILDING_D)), PARTY_WALL),
    ]
    for n, (layer, pts, width) in enumerate(floor_walls, 2):
        els.append(Polyline(f"{fid}-WALL-{n:02d}", layer, pts, width=width))

    for letter, (dx, dy, rotated) in UNIT_PLACEMENT.items():
        unit = f"{floor}{letter}"
        moved = unit == HERO_UNIT and rev == HERO_REVISION
        els.extend(_place(e, dx, dy, rotated) for e in unit_template(unit, moved))
    return els


def manifest() -> dict:
    return {
        "units": "mm",
        "zones_source": "backend/seed/building.json",
        "sheets": [
            {
                "sheet": sheet_id(floor),
                "floor": f"F{floor}",
                "title": f"Floor plan level {floor}",
                "revisions": [
                    {
                        "rev": rev,
                        "file": plan_filename(floor, rev),
                        "note": REVISION_NOTES[rev],
                    }
                    for rev in SHEET_REVISIONS[floor]
                ],
            }
            for floor in FLOORS
        ],
        "layers": {name: {"type": t, "description": d} for name, (_, t, d) in LAYERS.items()},
    }


# --- DXF writing --------------------------------------------------------------
def _define_blocks(doc: ezdxf.document.Drawing) -> None:
    attrs = {"layer": "0", "color": 0}  # BYBLOCK: inherit the insert's layer
    door = doc.blocks.new("DOOR")  # hinge at origin, opening along +x, scale = width
    door.add_line((0, 0), (0, 1), dxfattribs=attrs)
    door.add_arc((0, 0), 1, 0, 90, dxfattribs=attrs)

    wc = doc.blocks.new("WC")  # cistern against the wall at -y
    wc.add_lwpolyline(_rect(-200, -350, 200, -150), close=True, dxfattribs=attrs)
    wc.add_circle((0, 100), 180, dxfattribs=attrs)

    sink = doc.blocks.new("SINK")
    sink.add_lwpolyline(_rect(-300, -225, 300, 225), close=True, dxfattribs=attrs)
    sink.add_circle((0, 0), 150, dxfattribs=attrs)

    shower = doc.blocks.new("SHOWER")
    shower.add_lwpolyline(_rect(-450, -450, 450, 450), close=True, dxfattribs=attrs)
    shower.add_line((-450, -450), (450, 450), dxfattribs=attrs)
    shower.add_line((-450, 450), (450, -450), dxfattribs=attrs)
    shower.add_circle((0, 0), 40, dxfattribs=attrs)

    stack = doc.blocks.new("STACK")
    stack.add_circle((0, 0), 75, dxfattribs=attrs)
    stack.add_circle((0, 0), 40, dxfattribs=attrs)


def _write_title_block(msp, floor: int, rev: str) -> None:
    lines = [
        "SITEMIND SYNTHETIC PLAN - NOT FOR CONSTRUCTION",
        f"SHEET: {sheet_id(floor)}",
        f"TITLE: Floor plan level {floor}",
        f"FLOOR: F{floor}",
        f"REV: {rev}",
        *(REVISION_NOTES[r] for r in SHEET_REVISIONS[floor] if r <= rev),
    ]
    for i, text in enumerate(lines):
        msp.add_text(text, height=300, dxfattribs={"layer": "A-ANNO-TTLB"}).set_placement(
            (0, -1500 - i * 500)
        )


def build_document(floor: int, rev: str) -> ezdxf.document.Drawing:
    doc = ezdxf.new(DXF_VERSION, setup=False)
    doc.units = ezdxf.units.MM
    doc.header["$MEASUREMENT"] = 1
    doc.appids.new(APPID)
    for name, (color, _, _) in LAYERS.items():
        doc.layers.add(name, color=color)
    _define_blocks(doc)

    msp = doc.modelspace()
    for el in floor_elements(floor, rev):
        if isinstance(el, Stamp):
            msp.add_text(el.text, height=el.height, dxfattribs={"layer": el.layer}).set_placement(
                el.at, align=TextEntityAlignment.MIDDLE_CENTER
            )
            continue
        if isinstance(el, Polyline):
            entity = msp.add_lwpolyline(
                el.points, close=el.closed, dxfattribs={"layer": el.layer, "const_width": el.width}
            )
        else:
            entity = msp.add_blockref(
                el.block,
                el.at,
                dxfattribs={"layer": el.layer, "rotation": el.rotation, "xscale": el.scale, "yscale": el.scale},
            )
        entity.set_xdata(APPID, [(1000, el.id)])
    _write_title_block(msp, floor, rev)
    return doc


def generate(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ezdxf.options.write_fixed_meta_data_for_testing = True  # reproducible output
    written = []
    for floor in FLOORS:
        for rev in SHEET_REVISIONS[floor]:
            path = out_dir / plan_filename(floor, rev)
            build_document(floor, rev).saveas(path)
            written.append(path)
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest(), indent=2) + "\n", encoding="utf-8")
    written.append(manifest_path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    for path in generate(args.out):
        print(path)


if __name__ == "__main__":
    main()
