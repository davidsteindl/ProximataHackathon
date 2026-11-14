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

/** True floor isolation: with a floor isolated, only that floor is shown (no stack below it). */
export function floorVisible(isolatedFloorId, floorId) {
  return !isolatedFloorId || isolatedFloorId === floorId;
}

/** Tasks that have not ended yet (running or upcoming) versus tasks that ended before `now`. */
export function splitTasks(tasks, now) {
  const ended = (task) => Date.parse(task.ends_at || task.starts_at) < now;
  return { current: tasks.filter((task) => !ended(task)), earlier: tasks.filter(ended) };
}

/** "rough_in" -> "Rough-in". */
export function inspectionKindLabel(kind) {
  const text = (kind || "inspection").replaceAll("_", "-");
  return text[0].toUpperCase() + text.slice(1);
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

/** Last review decision counts only from a human, or from the seed import for an explicit seed baseline. */
function validConfirmation(record) {
  const review = record.history?.at(-1);
  return review?.status === "confirmed"
    && (review.actor_type === "human" || (record.origin === "seed_baseline" && review.actor_type === "seed_import"));
}

/**
 * Conservative display state of an Inspection's pass, mirroring the boundary of backend/app/rules.py without
 * re-implementing it (Flags carry the authoritative evaluation):
 * - "confirmed": an exact-scope (inspection + zone) pass with a valid human/seed confirmation and no relevant
 *   counterclaim. Relevant = exact-scope or unresolved-scope (no inspection_id) claims in the inspection's zone
 *   scope; the client cannot see a statement's inspection kind, so every such claim counts.
 * - "review": a confirmed pass exists but an unrejected counterclaim is still open.
 * - "unchecked": the only confirmed passes are extracted statements whose source time (staleness) the API
 *   does not expose here, so the view never calls them a pass.
 * - "revised": a pass that would otherwise read "confirmed", but the floor's current plan Revision was issued
 *   after the inspection was scheduled (or the order cannot be established). Inspection Evidence carries no
 *   revision_id in the API, so the view cannot tell whether the pass covers the current geometry; it says so
 *   instead of showing a pass. Flags remain the authoritative evaluation.
 * - "none": no valid confirmed pass. The recorded Inspection.status alone never counts.
 */
export function inspectionPass(index, inspection, evidence, plans = []) {
  const scope = scopeOf(index, inspection.zone_id);
  const relevant = (evidence || []).filter((record) => record.scope.kind === "inspection" && record.review_status !== "rejected" && (
    record.scope.inspection_id === inspection.id ? record.scope.zone_id === inspection.zone_id
      : !record.scope.inspection_id && record.scope.zone_id && scope.has(record.scope.zone_id)));
  const positives = relevant.filter((record) => record.claim === "passed" && record.scope.inspection_id === inspection.id && validConfirmation(record));
  if (!positives.length) return "none";
  const counter = relevant.some((record) => record.claim !== "passed" && !(record.origin === "seed_baseline" && record.claim === "pending"));
  if (counter) return "review";
  if (positives.every((record) => record.origin === "llm_statement")) return "unchecked";
  const plan = planForZone(index, plans, inspection.zone_id);
  const issued = Date.parse(plan?.current_revision?.issued_at);
  const scheduled = Date.parse(inspection.scheduled_at);
  if (plan?.current_revision && !(issued <= scheduled)) return "revised"; // NaN (unknown order) also lands here
  return "confirmed";
}

export function inspectionConfirmedPassed(index, inspection, evidence, plans) {
  return inspectionPass(index, inspection, evidence, plans) === "confirmed";
}

function planForZone(index, plans, zoneId) {
  const floorId = floorOf(index, zoneId);
  return (plans || []).find((plan) => plan.floor_id === floorId) || null;
}

/**
 * Crew acknowledgments of the floor plan's current Revision, from Evidence (the plan's acknowledgment list is
 * only context). Per crew with acknowledgment Evidence in the plan's floor scope:
 * - "current": a valid confirmed (human, or seed import for a seed baseline) record for exactly the current revision
 * - "unconfirmed": records for the current revision exist, none validly confirmed
 * - "stale": only an earlier revision is validly confirmed (`label` names it); not proof for the current one
 * - "none": nothing validly confirmed for any revision
 * Rejected records and records outside the floor's zone scope never count.
 */
export function revisionAcknowledgments(index, plan, evidence) {
  if (!plan?.current_revision) return [];
  const revisions = new Map(plan.revisions.map((revision) => [revision.id, revision]));
  const scope = new Set([plan.floor_id, ...descendants(index, plan.floor_id)]);
  const records = (evidence || []).filter((record) => record.scope.kind === "revision_acknowledgment"
    && revisions.has(record.scope.revision_id) && scope.has(record.scope.zone_id) && record.review_status !== "rejected");
  return [...new Set(records.map((record) => record.scope.crew_id))].map((crewId) => {
    const own = records.filter((record) => record.scope.crew_id === crewId);
    const current = own.filter((record) => record.scope.revision_id === plan.current_revision.id);
    if (current.some(validConfirmation)) return { crewId, state: "current", label: plan.current_revision.label };
    if (current.length) return { crewId, state: "unconfirmed", label: plan.current_revision.label };
    const latest = own.filter(validConfirmation).map((record) => revisions.get(record.scope.revision_id))
      .sort((a, b) => b.sequence - a.sequence)[0];
    return latest ? { crewId, state: "stale", label: latest.label } : { crewId, state: "none", label: null };
  });
}

/** "conflict" (open Flag) > "open" (an Inspection in scope is not confirmed passed) > "ok". */
export function zoneStatus(index, state, zoneId) {
  if (!index.has(zoneId)) return "unknown";
  if (flagsForZone(index, state.flags, zoneId).length > 0) return "conflict";
  const chain = new Set(ancestors(index, zoneId));
  const open = (state.inspections || []).some((inspection) => chain.has(inspection.zone_id)
    && !inspectionConfirmedPassed(index, inspection, state.evidence, state.plans));
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
    .map((inspection) => {
      const records = evidenceFor(evidence, inspection);
      const counts = { confirmed: 0, unconfirmed: 0, rejected: 0 };
      for (const record of records) counts[record.review_status] = (counts[record.review_status] || 0) + 1;
      return { inspection, evidence: records, counts, pass: inspectionPass(index, inspection, evidence, state.plans) };
    });
  const unresolvedEvidence = evidence.filter((record) => record.scope.kind === "inspection"
    && !record.scope.inspection_id && (!record.scope.zone_id || scope.has(record.scope.zone_id)));
  const plan = planForZone(index, state.plans, zoneId);
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
    acknowledgments: revisionAcknowledgments(index, plan, evidence).map((ack) => ({ ...ack, crew: crews[ack.crewId] || null })),
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

/** Camera focus: an element (e.g. a wall) is framed together with its parent room, so it has context. */
export function focusBounds(index, geometry, zoneId) {
  const own = zoneBounds(geometry, zoneId);
  const zone = index.get(zoneId);
  const parent = own && zone?.kind === "element" ? zoneBounds(geometry, zone.parent_id) : null;
  if (!parent) return own;
  return {
    minX: Math.min(own.minX, parent.minX), maxX: Math.max(own.maxX, parent.maxX),
    minY: Math.min(own.minY, parent.minY), maxY: Math.max(own.maxY, parent.maxY),
  };
}

/** Route-derived view: the selected Zone decides isolation, camera and highlight. */
export function viewForZone(index, zoneId) {
  if (!zoneId) return { known: true, floorId: null, mode: "orbit", highlight: null };
  const zone = index.get(zoneId);
  if (!zone) return { known: false, floorId: null, mode: "orbit", highlight: null };
  if (zone.kind === "building") return { known: true, floorId: null, mode: "orbit", highlight: null };
  return { known: true, floorId: floorOf(index, zoneId), mode: "top", highlight: zoneId };
}
