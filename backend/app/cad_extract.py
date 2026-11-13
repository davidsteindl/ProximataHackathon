"""Documented DXF layer extraction. No CAD conversion, plan diff or domain actions."""

import math
import tempfile
from collections import Counter
from pathlib import Path

import ezdxf

from app.cad_schemas import Element, IgnoredLayer, Shape

EPS = 1e-8  # metres
AREA_LAYERS = {"A-AREA-UNIT": ("unit", "A-AREA-UNIT-IDEN"), "A-AREA": ("room", "A-AREA-IDEN")}
KNOWN_LAYERS = set(AREA_LAYERS) | {value[1] for value in AREA_LAYERS.values()} | {
    "A-WALL", "A-WALL-EXTR", "A-DOOR", "P-FIXT", "P-SANR", "A-ANNO-TTLB",
}


class InvalidPlan(ValueError):
    pass


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def sub(a, b):
    return a[0] - b[0], a[1] - b[1]


def on_segment(point, a, b):
    direction, offset = sub(b, a), sub(point, a)
    return abs(cross(direction, offset)) <= EPS and all(
        min(a[i], b[i]) - EPS <= point[i] <= max(a[i], b[i]) + EPS for i in (0, 1)
    )


def contains(point, polygon):
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if on_segment(point, a, b):
            return True
        if (a[1] > point[1]) != (b[1] > point[1]):
            x = a[0] + (point[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if point[0] < x:
                inside = not inside
    return inside


def line_overlaps_polygon(a, b, polygon):
    """Positive-length overlap, including shared walls but excluding corner-only contact."""
    direction = sub(b, a)
    length2 = sum(value * value for value in direction)
    if length2 <= EPS * EPS:
        return False
    cuts = {0.0, 1.0}
    for c, d in zip(polygon, polygon[1:] + polygon[:1]):
        edge, offset = sub(d, c), sub(c, a)
        denominator = cross(direction, edge)
        if abs(denominator) > EPS:
            t, u = cross(offset, edge) / denominator, cross(offset, direction) / denominator
            if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS:
                cuts.add(min(1.0, max(0.0, t)))
        elif abs(cross(offset, direction)) <= EPS:
            for point in (c, d):
                t = sum(x * y for x, y in zip(sub(point, a), direction)) / length2
                cuts.add(min(1.0, max(0.0, t)))
    ordered = sorted(cuts)
    return any(
        (hi - lo) * math.sqrt(length2) > EPS and contains(
            tuple(a[i] + (hi + lo) * 0.5 * direction[i] for i in (0, 1)), polygon,
        )
        for lo, hi in zip(ordered, ordered[1:])
    )


def stable_id(entity):
    if entity.has_xdata("SITEMIND"):
        values = [tag.value for tag in entity.get_xdata("SITEMIND") if tag.code == 1000]
        if len(values) != 1 or not values[0] or len(values[0]) > 200:
            raise InvalidPlan("Invalid SITEMIND element ID")
        return values[0]
    return f"handle:{entity.dxf.handle}"


def polyline(entity, closed=False):
    if entity.dxftype() != "LWPOLYLINE":
        raise InvalidPlan(f"Expected LWPOLYLINE on {entity.dxf.layer}")
    if any(abs(bulge) > EPS for _, _, bulge in entity.get_points("xyb")):
        raise InvalidPlan("Curved polylines are outside the documented straight-segment convention")
    extrusion = tuple(entity.dxf.extrusion)
    if extrusion != (0.0, 0.0, 1.0) or abs(entity.dxf.elevation) > EPS:
        raise InvalidPlan("Plans must use the floor's local XY plane at z=0")
    points = [(float(x) / 1000, float(y) / 1000) for x, y in entity.get_points("xy")]
    if not all(math.isfinite(value) for point in points for value in point):
        raise InvalidPlan("Non-finite coordinates")
    if len(points) < (3 if closed else 2) or (closed and not entity.closed):
        raise InvalidPlan("Invalid or open area outline")
    if closed:
        area2 = sum(cross(a, b) for a, b in zip(points, points[1:] + points[:1]))
        if abs(area2) <= EPS:
            raise InvalidPlan("Area outline must have a nonzero area")
    return points


def extract_dxf(source: bytes, zones, floor_id):
    # readfile handles the DXF codepage and encoding. Keep the original bytes
    # separately; parsing never rewrites the source.
    try:
        with tempfile.TemporaryDirectory(prefix="sitemind-dxf-") as directory:
            path = Path(directory) / "plan.dxf"
            path.write_bytes(source)
            doc = ezdxf.readfile(path)
    except (ezdxf.DXFError, UnicodeError, ValueError, OSError) as error:
        raise InvalidPlan("Unreadable DXF file") from error
    if doc.dxfversion != "AC1015" or doc.units != ezdxf.units.MM:
        raise InvalidPlan("Expected DXF R2000 (AC1015) in millimetres")
    entities = list(doc.modelspace())
    ignored = Counter(entity.dxf.layer for entity in entities if entity.dxf.layer not in KNOWN_LAYERS)
    by_id = {zone.id: zone for zone in zones}

    def ancestors(zone_id):
        result = []
        while zone_id is not None:
            result.append(zone_id)
            zone_id = by_id[zone_id].parent_id
        return result

    areas, elements = [], []
    used_stamps = set()
    for entity in entities:
        if entity.dxf.layer not in AREA_LAYERS:
            continue
        kind, stamp_layer = AREA_LAYERS[entity.dxf.layer]
        points = polyline(entity, closed=True)
        stamps = [stamp for stamp in entities if stamp.dxf.layer == stamp_layer and stamp.dxftype() == "TEXT" and contains(
            (stamp.get_placement()[1].x / 1000, stamp.get_placement()[1].y / 1000), points,
        )]
        if len(stamps) != 1:
            raise InvalidPlan("Every unit/room outline needs exactly one matching label")
        stamp = stamps[0]
        zone_id = stamp.dxf.text.strip()
        if zone_id not in by_id or by_id[zone_id].kind != kind or floor_id not in ancestors(zone_id):
            raise InvalidPlan(f"Unknown, wrong-kind or wrong-floor zone label: {zone_id}")
        if zone_id in {area[0] for area in areas} or stamp.dxf.handle in used_stamps:
            raise InvalidPlan(f"Duplicate zone outline: {zone_id}")
        if entity.has_xdata("SITEMIND") and stable_id(entity) != zone_id:
            raise InvalidPlan("Area XDATA ID must match its zone label")
        used_stamps.add(stamp.dxf.handle)
        areas.append((zone_id, kind, points))
        elements.append(Element(
            element_id=zone_id, kind=kind, layer=entity.dxf.layer,
            shape=Shape(outline=points), zone_ids=ancestors(zone_id),
        ))
    if not areas:
        raise InvalidPlan("No labelled unit/room outlines found")
    if any(entity.dxf.layer in {"A-AREA-IDEN", "A-AREA-UNIT-IDEN"} and entity.dxf.handle not in used_stamps for entity in entities):
        raise InvalidPlan("Unmatched unit/room label")

    for entity in entities:
        layer = entity.dxf.layer
        if layer not in {"A-WALL", "A-WALL-EXTR", "A-DOOR", "P-FIXT", "P-SANR"}:
            continue
        element_id = stable_id(entity)
        shape = Shape()
        if layer in {"A-WALL", "A-WALL-EXTR"} or (layer == "P-SANR" and entity.dxftype() == "LWPOLYLINE"):
            points = polyline(entity)
            shape.segments = list(zip(points, points[1:] + (points[:1] if entity.closed else [])))
            shape.position = points[0]
            kind = "drain" if layer == "P-SANR" else "wall"
            if kind == "wall":
                shape.thickness_m = float(entity.dxf.const_width) / 1000
                if not math.isfinite(shape.thickness_m) or shape.thickness_m <= 0:
                    raise InvalidPlan("Wall thickness must be a positive constant width")
        else:
            if entity.dxftype() != "INSERT":
                raise InvalidPlan(f"Expected block INSERT on {layer}")
            name = entity.dxf.name
            allowed = {"A-DOOR": {"DOOR"}, "P-FIXT": {"WC", "SINK", "SHOWER"}, "P-SANR": {"STACK"}}
            if name not in allowed[layer] or name not in doc.blocks:
                raise InvalidPlan(f"Unknown block {name} on {layer}")
            if abs(entity.dxf.insert.z) > EPS or tuple(entity.dxf.extrusion) != (0.0, 0.0, 1.0):
                raise InvalidPlan("Block insert must be on the local XY plane")
            shape.position = (float(entity.dxf.insert.x) / 1000, float(entity.dxf.insert.y) / 1000)
            shape.rotation_deg = float(entity.dxf.rotation)
            shape.scale = (float(entity.dxf.xscale), float(entity.dxf.yscale))
            if not all(math.isfinite(value) for value in (*shape.position, shape.rotation_deg, *shape.scale)) or min(shape.scale) <= 0:
                raise InvalidPlan("Invalid block position, rotation or scale")
            shape.block_name = name
            kind = {"A-DOOR": "door", "P-FIXT": "plumbing_fixture", "P-SANR": "drain"}[layer]
            if kind == "door":
                shape.width_m = shape.scale[0] / 1000
                angle = math.radians(shape.rotation_deg)
                end = (shape.position[0] + math.cos(angle) * shape.width_m, shape.position[1] + math.sin(angle) * shape.width_m)
                shape.segments = [(shape.position, end)]
        associated = set(ancestors(floor_id))
        for zone_id, _, outline in areas:
            hit = any(line_overlaps_polygon(a, b, outline) for a, b in shape.segments) if shape.segments else contains(shape.position, outline)
            if hit:
                associated.update(ancestors(zone_id))
        if element_id in by_id and by_id[element_id].kind == "element":
            if floor_id not in ancestors(element_id) or by_id[element_id].parent_id not in associated:
                raise InvalidPlan("Element zone is outside its labelled parent/floor")
            associated.update(ancestors(element_id))
        elements.append(Element(element_id=element_id, kind=kind, layer=layer, shape=shape, zone_ids=sorted(associated)))
    ids = [element.element_id for element in elements]
    if len(ids) != len(set(ids)):
        raise InvalidPlan("Duplicate element identifiers")
    return elements, [IgnoredLayer(layer=layer, entity_count=count) for layer, count in sorted(ignored.items())]
