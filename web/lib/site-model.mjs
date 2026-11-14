// Pure view-model logic for the 3D site view (#16). No React, no Three.js:
// everything here is derived from REST data and unit-tested in test/site-model.test.mjs.

export function indexZones(tree) {
  const index = new Map();
  const walk = (zones) => zones.forEach((zone) => {
    index.set(zone.id, { ...zone, childIds: zone.children.map((child) => child.id) });
    walk(zone.children);
  });
  walk(tree || []);
  return index;
}

/** The zone itself followed by its parents up to the building. */
export function ancestors(index, zoneId) {
  const chain = [];
  for (let zone = index.get(zoneId); zone; zone = index.get(zone.parent_id)) chain.push(zone.id);
  return chain;
}

export function descendants(index, zoneId) {
  const zone = index.get(zoneId);
  return zone ? zone.childIds.flatMap((id) => [id, ...descendants(index, id)]) : [];
}

export function floorOf(index, zoneId) {
  return ancestors(index, zoneId).find((id) => index.get(id).kind === "floor") || null;
}

/** Zones whose records apply to `zoneId`: its ancestors (floor-level inspections, tasks) and descendants. */
function scopeOf(index, zoneId) {
  return new Set([...ancestors(index, zoneId), ...descendants(index, zoneId)]);
}

/** GET /flags already returns open Flags only; this guards data that includes closed ones. */
export function isOpenFlag(flag) {
  return flag.state !== "resolved" && flag.state !== "false_alarm";
}

/** Open Flags on the zone, an ancestor or a descendant. Sibling zones are never included. */
export function flagsForZone(index, flags, zoneId) {
  const scope = scopeOf(index, zoneId);
  return (flags || []).filter((flag) => isOpenFlag(flag) && scope.has(flag.zone_id));
}

function evidenceFor(evidence, inspection) {
  return evidence.filter((record) => record.scope.kind === "inspection" && record.scope.inspection_id === inspection.id);
}

/**
 * Coarse colour for an Inspection. Only a human-confirmed (or explicit seed-baseline confirmed) pass
 * without any unrejected counterclaim counts as done; the recorded Inspection.status alone never does.
 * This is a display hint, not a Precondition evaluation — those come from the rule engine via Flags.
 */
export function inspectionConfirmedPassed(inspection, evidence) {
  const records = evidenceFor(evidence, inspection);
  const passed = records.some((record) => record.claim === "passed" && record.review_status === "confirmed");
  const counter = records.some((record) => record.claim !== "passed" && record.review_status !== "rejected"
    && !(record.origin === "seed_baseline" && record.claim === "pending"));
  return passed && !counter;
}

/** "conflict" (open Flag) > "open" (an Inspection in scope is not confirmed passed) > "ok". */
export function zoneStatus(index, state, zoneId) {
  if (!index.has(zoneId)) return "unknown";
  if (flagsForZone(index, state.flags, zoneId).length > 0) return "conflict";
  const chain = new Set(ancestors(index, zoneId));
  const open = (state.inspections || []).some((inspection) => chain.has(inspection.zone_id)
    && !inspectionConfirmedPassed(inspection, state.evidence || []));
  return open ? "open" : "ok";
}

/** Status of a plan element: only elements with their own element Zone are coloured, e.g. 3B-BATH-WALL. */
export function elementStatus(index, state, element) {
  const own = element.zone_ids.find((id) => index.get(id)?.kind === "element");
  return own ? zoneStatus(index, state, own) : null;
}

export function elementZone(index, element) {
  return element.zone_ids.find((id) => index.get(id)?.kind === "element") || null;
}

export function zoneDetails(index, state, zoneId) {
  const zone = index.get(zoneId);
  if (!zone) return null;
  const chain = ancestors(index, zoneId);
  const scope = scopeOf(index, zoneId);
  const evidence = state.evidence || [];
  const floorId = floorOf(index, zoneId);
  const crews = Object.fromEntries((state.crews || []).map((crew) => [crew.id, crew]));
  const inspections = (state.inspections || [])
    .filter((inspection) => scope.has(inspection.zone_id))
    .map((inspection) => ({ inspection, evidence: evidenceFor(evidence, inspection) }));
  const unresolvedEvidence = evidence.filter((record) => record.scope.kind === "inspection"
    && !record.scope.inspection_id && (!record.scope.zone_id || scope.has(record.scope.zone_id)));
  const plan = (state.plans || []).find((candidate) => candidate.floor_id === floorId) || null;
  const revisions = plan ? [...plan.revisions].sort((a, b) => b.sequence - a.sequence).map((revision) => ({
    revision,
    acknowledgments: revision.acknowledgments.map((ack) => ({ ...ack, crew: crews[ack.crew_id] || null })),
    evidence: evidence.filter((record) => record.scope.kind === "revision_acknowledgment" && record.scope.revision_id === revision.id),
  })) : [];
  return {
    zone,
    path: [...chain].reverse().map((id) => index.get(id)),
    floorId,
    status: zoneStatus(index, state, zoneId),
    flags: flagsForZone(index, state.flags, zoneId),
    inspections,
    unresolvedEvidence,
    tasks: (state.tasks || []).filter((task) => scope.has(task.zone_id))
      .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
      .map((task) => ({ ...task, crew: crews[task.crew_id] || null })),
    plan,
    revisions,
  };
}

const shapeKey = (element) => JSON.stringify(element.shape);

/**
 * Elements whose stored geometry differs between two imported Revisions of the same plan, matched by
 * stable element_id. This is a view-level comparison for highlighting only; the plan diff is #17's.
 */
export function changedElements(current, previous) {
  if (!current || !previous) return [];
  const before = new Map(previous.elements.map((element) => [element.element_id, element]));
  return current.elements
    .filter((element) => !before.has(element.element_id) || shapeKey(before.get(element.element_id)) !== shapeKey(element))
    .map((element) => ({ element, previous: before.get(element.element_id) || null, change: describeChange(before.get(element.element_id), element) }));
}

export function describeChange(previous, current) {
  if (!previous) return "added";
  const [a] = previous.shape.segments;
  const [b] = current.shape.segments;
  if (a && b && previous.shape.segments.length === 1 && current.shape.segments.length === 1) {
    const [ax, ay] = [a[1][0] - a[0][0], a[1][1] - a[0][1]];
    const [bx, by] = [b[1][0] - b[0][0], b[1][1] - b[0][1]];
    const length = Math.hypot(ax, ay);
    if (length > 0 && Math.abs(ax * by - ay * bx) < 1e-9 && Math.abs(Math.hypot(bx, by) - length) < 1e-9) {
      const offset = Math.abs(((b[0][0] - a[0][0]) * ay - (b[0][1] - a[0][1]) * ax) / length);
      return `moved ${offset.toFixed(2)} m`;
    }
  }
  return "geometry changed";
}

function pointsOf(element) {
  const { outline, segments, position } = element.shape;
  if (outline?.length) return outline;
  if (segments?.length) return segments.flat();
  return position ? [position] : [];
}

/** XY bounds in plan metres of the plan elements that belong to a zone; null if none. */
export function zoneBounds(geometry, zoneId) {
  const points = (geometry || []).flatMap((plan) => {
    const own = plan.elements.filter((element) => element.element_id === zoneId);
    const elements = own.length ? own : plan.floor_id === zoneId || zoneId === undefined
      ? plan.elements.filter((element) => element.kind === "unit" || element.kind === "wall")
      : plan.elements.filter((element) => element.zone_ids.includes(zoneId) && (element.kind === "room" || element.kind === "unit"));
    return elements.flatMap(pointsOf);
  });
  if (!points.length) return null;
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
}

/** Route-derived view: the selected Zone decides isolation, camera and highlight. */
export function viewForZone(index, zoneId) {
  if (!zoneId) return { known: true, floorId: null, mode: "orbit", highlight: null };
  const zone = index.get(zoneId);
  if (!zone) return { known: false, floorId: null, mode: "orbit", highlight: null };
  if (zone.kind === "building") return { known: true, floorId: null, mode: "orbit", highlight: null };
  return { known: true, floorId: floorOf(index, zoneId), mode: "top", highlight: zoneId };
}
