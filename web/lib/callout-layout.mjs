// Pure geometry for the 3D view's callout layout (screen space, y down).

/** True if the segment (x1,y1)-(x2,y2) passes through the interior of rect {l,t,r,b} (Liang–Barsky clip). */
export function segmentHitsRect(x1, y1, x2, y2, rect) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  let t0 = 0;
  let t1 = 1;
  for (const [p, q] of [[-dx, x1 - rect.l], [dx, rect.r - x1], [-dy, y1 - rect.t], [dy, rect.b - y1]]) {
    if (p === 0) { if (q <= 0) return false; continue; }
    const t = q / p;
    if (p < 0) { if (t > t0) t0 = t; } else if (t < t1) t1 = t;
    if (t0 >= t1) return false;
  }
  return true;
}

/** True if a card's leader (anchor to the card's nearest point) or the card itself clashes with placed ones. */
export function leaderClash(anchor, rect, placed) {
  const lx = Math.min(Math.max(anchor.x, rect.l), rect.r);
  const ly = Math.min(Math.max(anchor.y, rect.t), rect.b);
  return placed.some((p) => segmentHitsRect(anchor.x, anchor.y, lx, ly, p.rect)
    || (p.leader && segmentHitsRect(...p.leader, rect)));
}
