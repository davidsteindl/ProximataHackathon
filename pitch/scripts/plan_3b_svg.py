"""Render unit 3B from the synthetic DXF plans as one SVG: Rev D, with Rev C changes dashed.

Usage (needs ezdxf, same as backend): python pitch/scripts/plan_3b_svg.py > pitch/public/plan-3b.svg
Changed elements are found by their stable SITEMIND id, like the plan diff (#17).
"""
import math
import sys
from pathlib import Path

import ezdxf

PLANS = Path(__file__).resolve().parents[2] / "cad" / "plans"
X0, X1, Y0, Y1 = 12000, 24000, 0, 8500  # unit 3B outline in mm
PAD = 900
INK, MUTED, RED, BLUE = "#171A1F", "#8A93A1", "#E2492F", "#176AC6"
LAYERS = {"A-WALL", "A-WALL-EXTR", "A-DOOR", "P-FIXT", "P-SANR"}


def sid(e):
    return e.get_xdata("SITEMIND")[0].value if e.has_xdata("SITEMIND") else None


def y(v):
    return Y1 - v  # DXF y up -> SVG y down


def svg(e, stroke, width, dash=""):
    t, extra = e.dxftype(), f' stroke="{stroke}" stroke-width="{width}" fill="none"{dash}'
    if t == "LWPOLYLINE":
        pts = " ".join(f"{x:.0f},{y(v):.0f}" for x, v in e.get_points("xy"))
        tag = "polygon" if e.closed else "polyline"
        return f'<{tag} points="{pts}"{extra} stroke-linejoin="miter"/>'
    if t == "LINE":
        s, n = e.dxf.start, e.dxf.end
        return f'<line x1="{s.x:.0f}" y1="{y(s.y):.0f}" x2="{n.x:.0f}" y2="{y(n.y):.0f}"{extra}/>'
    if t == "CIRCLE":
        c = e.dxf.center
        return f'<circle cx="{c.x:.0f}" cy="{y(c.y):.0f}" r="{e.dxf.radius:.0f}"{extra}/>'
    if t == "ARC":
        c, r = e.dxf.center, e.dxf.radius
        a0, a1 = math.radians(e.dxf.start_angle), math.radians(e.dxf.end_angle)
        sweep = (e.dxf.end_angle - e.dxf.start_angle) % 360
        p0 = (c.x + r * math.cos(a0), y(c.y + r * math.sin(a0)))
        p1 = (c.x + r * math.cos(a1), y(c.y + r * math.sin(a1)))
        return (f'<path d="M{p0[0]:.0f},{p0[1]:.0f} A{r:.0f},{r:.0f} 0 {int(sweep > 180)} 0 '
                f'{p1[0]:.0f},{p1[1]:.0f}"{extra}/>')
    if t == "INSERT":
        return "".join(svg(v, stroke, width, dash) for v in e.virtual_entities())
    return ""


def elements(name):
    return {sid(e): e for e in ezdxf.readfile(PLANS / name).modelspace()
            if e.dxf.layer in LAYERS and sid(e)}


def same(a, b):
    if a.dxftype() == "LWPOLYLINE":
        return list(a.get_points("xy")) == list(b.get_points("xy"))
    return a.dxf.insert == b.dxf.insert and a.dxf.rotation == b.dxf.rotation


def stroke_width(e):
    return max(getattr(e.dxf, "const_width", 0) or 0, 30 if e.dxf.layer.startswith("P-") else 25)


def main():
    rev_c, rev_d = elements("A-103_RevC.dxf"), elements("A-103_RevD.dxf")
    changed = {k for k in rev_d if k in rev_c and not same(rev_c[k], rev_d[k])}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{X0 - PAD} {-PAD} '
           f'{X1 - X0 + 2 * PAD} {Y1 - Y0 + 2 * PAD}" font-family="JetBrains Mono, monospace">',
           f'<clipPath id="u"><rect x="{X0 - 60}" y="-60" width="{X1 - X0 + 120}" height="{Y1 + 120}"/></clipPath>',
           f'<rect x="19000" y="{y(8500)}" width="3300" height="3000" fill="{RED}" fill-opacity=".07"/>',
           '<g clip-path="url(#u)">']
    for k, e in rev_d.items():
        if k not in changed:
            out.append(svg(e, INK if e.dxf.layer.startswith("A-") else BLUE, stroke_width(e)))
    for k in sorted(changed):  # old position dashed grey, new position red, like the product
        out.append(svg(rev_c[k], MUTED, stroke_width(rev_c[k]), ' stroke-dasharray="120 90"'))
        out.append(svg(rev_d[k], RED, stroke_width(rev_d[k])))
    out.append("</g>")
    for label, x, v in [("LIV", 15500, 2750), ("BED", 21500, 2750), ("KIT", 13500, 7000),
                        ("HALL", 17000, 6600), ("BATH", 20300, 6900), ("STOR", 23150, 7000)]:
        out.append(f'<text x="{x}" y="{y(v)}" font-size="300" fill="{MUTED}" text-anchor="middle">3B-{label}</text>')
    # dimension line Rev C -> Rev D above the unit
    dy = y(8500) - 450
    out.append(f'<g stroke="{RED}" stroke-width="20"><line x1="22000" y1="{dy}" x2="22300" y2="{dy}"/>'
               f'<line x1="22000" y1="{dy - 150}" x2="22000" y2="{dy + 150}"/>'
               f'<line x1="22300" y1="{dy - 150}" x2="22300" y2="{dy + 150}"/></g>'
               f'<text x="22150" y="{dy - 200}" font-size="300" fill="{RED}" text-anchor="middle">300</text>')
    out.append("</svg>")
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
