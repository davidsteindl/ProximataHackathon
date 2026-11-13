"""Tests for the synthetic floor plans and their layer convention (issue #3)."""

import importlib.util
import json
import sys
from pathlib import Path

import ezdxf
import pytest

REPO = Path(__file__).resolve().parents[2]
PLANS = REPO / "cad" / "plans"
MANIFEST = json.loads((PLANS / "manifest.json").read_text(encoding="utf-8"))

_spec = importlib.util.spec_from_file_location("generate_plans", REPO / "cad" / "generate_plans.py")
gen = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gen  # dataclasses look up their module during class creation
_spec.loader.exec_module(gen)

PLAN_FILES = [rev["file"] for sheet in MANIFEST["sheets"] for rev in sheet["revisions"]]
SEED = json.loads((REPO / "backend" / "seed" / "building.json").read_text(encoding="utf-8"))
ZONES = {z["id"]: z for z in SEED["zones"]}
SEED_PLAN_FLOOR = {plan["id"]: plan["floor_id"] for plan in SEED["plans"]}
AREA_STAMP_LAYER = {"A-AREA": "A-AREA-IDEN", "A-AREA-UNIT": "A-AREA-UNIT-IDEN"}


def xy(v):
    return (round(v.x, 3), round(v.y, 3))


def element_id(entity):
    if entity.has_xdata(gen.APPID):
        return entity.get_xdata(gen.APPID)[0].value
    return None


def snapshot(path):
    """Plan content keyed by element ID (stamps by their text); title block ignored."""
    out = {}
    for e in ezdxf.readfile(path).modelspace():
        layer = e.dxf.layer
        if layer == "A-ANNO-TTLB":
            continue
        if e.dxftype() == "TEXT":
            key = ("stamp", layer, e.dxf.text)
            value = xy(e.dxf.align_point)
        elif e.dxftype() == "LWPOLYLINE":
            key = element_id(e)
            pts = tuple((round(x, 3), round(y, 3)) for x, y in e.get_points("xy"))
            value = (layer, pts, e.closed, e.dxf.const_width)
        else:
            key = element_id(e)
            value = (layer, e.dxf.name, xy(e.dxf.insert), e.dxf.rotation, e.dxf.xscale)
        assert key not in out, f"duplicate element {key} in {path.name}"
        out[key] = value
    return out


def inside(point, polygon):
    x, y = point
    hit = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def floor_of(zone_id):
    while ZONES[zone_id]["kind"] != "floor":
        zone_id = ZONES[zone_id]["parent_id"]
    return zone_id


def test_one_plan_per_seed_plan_with_rev_c_and_d_for_a103():
    sheets = {s["sheet"]: s for s in MANIFEST["sheets"]}
    assert {sheet: s["floor"] for sheet, s in sheets.items()} == SEED_PLAN_FLOOR
    assert [r["rev"] for r in sheets["A-103"]["revisions"]] == ["C", "D"]
    for name in PLAN_FILES:
        assert (PLANS / name).is_file(), name


def test_committed_plans_match_generator(tmp_path):
    gen.generate(tmp_path)
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8")) == MANIFEST
    for name in PLAN_FILES:
        assert snapshot(tmp_path / name) == snapshot(PLANS / name), f"{name} is stale: run cad/generate_plans.py"


@pytest.mark.parametrize("name", PLAN_FILES)
def test_plan_uses_only_convention_layers_and_mm(name):
    doc = ezdxf.readfile(PLANS / name)
    assert doc.dxfversion == "AC1015"
    assert doc.units == ezdxf.units.MM
    used = {e.dxf.layer for e in doc.modelspace()}
    assert used <= set(MANIFEST["layers"])


@pytest.mark.parametrize("name", PLAN_FILES)
def test_every_area_has_exactly_one_stamp_matching_a_seed_zone(name):
    msp = ezdxf.readfile(PLANS / name).modelspace()
    floor = next(s["floor"] for s in MANIFEST["sheets"] if any(r["file"] == name for r in s["revisions"]))
    stamps = [(e.dxf.layer, e.dxf.text, xy(e.dxf.align_point)) for e in msp.query("TEXT")]

    labelled = []
    for area in msp.query("LWPOLYLINE"):
        if area.dxf.layer not in AREA_STAMP_LAYER:
            continue
        assert area.closed
        outline = [tuple(p) for p in area.get_points("xy")]
        hits = [t for layer, t, at in stamps if layer == AREA_STAMP_LAYER[area.dxf.layer] and inside(at, outline)]
        assert hits == [element_id(area)], f"{element_id(area)} has stamps {hits}"
        labelled.append(hits[0])

    expected = {z for z, d in ZONES.items() if d["kind"] in ("unit", "room") and floor_of(z) == floor}
    assert sorted(labelled) == sorted(expected)


def test_seed_element_zone_is_the_hero_wall():
    for rev in ("C", "D"):
        ids = {element_id(e): e for e in ezdxf.readfile(PLANS / f"A-103_Rev{rev}.dxf").modelspace()}
        assert ids["3B-BATH-WALL"].dxf.layer == "A-WALL"
        assert all(z in ids for z, d in ZONES.items() if d["kind"] in ("room", "element") and floor_of(z) == "F3")


def test_unit_3b_elements_lie_inside_unit_3b():
    for rev in ("C", "D"):
        msp = ezdxf.readfile(PLANS / f"A-103_Rev{rev}.dxf").modelspace()
        unit = next(e for e in msp.query("LWPOLYLINE") if element_id(e) == "3B")
        outline = [tuple(p) for p in unit.get_points("xy")]
        for e in msp:
            eid = element_id(e) or ""
            if not eid.startswith("3B-"):
                continue
            points = e.get_points("xy") if e.dxftype() == "LWPOLYLINE" else [xy(e.dxf.insert)]
            for x, y in points:  # boundary counts: nudge towards the unit centre
                cx, cy = 18000, 4250
                assert inside((x + (cx - x) * 1e-6, y + (cy - y) * 1e-6), outline), eid


def test_rev_d_differs_from_rev_c_only_by_the_3b_bathroom_change():
    rev_c = snapshot(PLANS / "A-103_RevC.dxf")
    rev_d = snapshot(PLANS / "A-103_RevD.dxf")
    assert rev_c.keys() == rev_d.keys()
    changed = {k for k in rev_c if rev_c[k] != rev_d[k]}
    assert changed == {"3B-BATH-WALL", "3B-BATH", "3B-SANR-03"}

    (c_start, c_end), (d_start, d_end) = rev_c["3B-BATH-WALL"][1], rev_d["3B-BATH-WALL"][1]
    assert d_start[0] - c_start[0] == pytest.approx(300) and d_end[0] - c_end[0] == pytest.approx(300)
    assert (c_start[1], c_end[1]) == (d_start[1], d_end[1])
    assert rev_c["3B-SANR-03"][1] != rev_d["3B-SANR-03"][1]


@pytest.mark.parametrize("name", [n for n in PLAN_FILES if n != "A-103_RevD.dxf"])
def test_every_floor_has_the_same_drawn_layout(name):
    """Same layout on every floor: element counts per geometry layer match A-103 Rev C."""

    def counts(path):
        result = {}
        for e in ezdxf.readfile(path).modelspace():
            if e.dxf.layer in ("A-AREA", "A-AREA-IDEN", "A-ANNO-TTLB"):
                continue  # room labels exist only where the seed has room zones
            result[e.dxf.layer] = result.get(e.dxf.layer, 0) + 1
        return result

    assert counts(PLANS / name) == counts(PLANS / "A-103_RevC.dxf")
