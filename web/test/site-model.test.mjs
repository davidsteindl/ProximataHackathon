import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ancestors, changedElements, describeChange, elementStatus, flagsForZone, floorOf, floorVisible, indexZones,
  focusBounds, inspectionConfirmedPassed, inspectionKindLabel, inspectionPass, revisionAcknowledgments, splitTasks, insetEdgeStrips, viewForZone, zoneBounds, zoneDetails, zoneStatus,
} from "../lib/site-model.mjs";

const zone = (id, kind, children = []) => ({ id, kind, name: id, children });
const tree = [zone("B1", "building", [
  zone("F2", "floor", [zone("2B", "unit")]),
  zone("F3", "floor", [
    zone("3A", "unit", [zone("3A-BATH", "room")]),
    zone("3B", "unit", [zone("3B-BATH", "room", [zone("3B-BATH-WALL", "element")]), zone("3B-LIV", "room")]),
  ]),
])];
// The API sends parent_id; derive it so the fixture stays short.
const withParents = (zones, parent = null) => zones.map((z) => ({ ...z, parent_id: parent, children: withParents(z.children, z.id) }));
const index = indexZones(withParents(tree));

const flagA = { id: "flag-a", type: "A", zone_id: "3B", state: "detected", evaluation: "contradictory" };
const roughIn = { id: "rough-in-F3", zone_id: "F3", kind: "rough_in", status: "pending" };
const evidence = (id, claim, review_status, origin = "seed_statement", inspection_id = "rough-in-F3", zone_id = "F3") => ({
  id, claim, review_status, origin, quote: id, source_ref: id,
  scope: { kind: "inspection", zone_id, inspection_id, task_id: null, crew_id: null, revision_id: null },
  history: [{ status: review_status, actor_type: review_status === "unconfirmed" ? "extractor" : origin === "seed_baseline" ? "seed_import" : "human" }],
});
const state = (overrides = {}) => ({ flags: [flagA], inspections: [roughIn], evidence: [], tasks: [], plans: [], crews: [], ...overrides });

test("zone hierarchy helpers follow parent ids, not string prefixes", () => {
  assert.deepEqual(ancestors(index, "3B-BATH-WALL"), ["3B-BATH-WALL", "3B-BATH", "3B", "F3", "B1"]);
  assert.equal(floorOf(index, "3B-BATH"), "F3");
  assert.equal(floorOf(index, "B1"), null);
  assert.deepEqual(ancestors(index, "nope"), []);
});

test("an open Flag on 3B applies to its rooms, element and floor but not to sibling units", () => {
  for (const id of ["3B", "3B-BATH", "3B-BATH-WALL", "F3", "B1"]) assert.equal(flagsForZone(index, [flagA], id).length, 1, id);
  for (const id of ["3A", "3A-BATH", "F2", "2B"]) assert.equal(flagsForZone(index, [flagA], id).length, 0, id);
  assert.equal(flagsForZone(index, [{ ...flagA, state: "resolved" }], "3B").length, 0);
  assert.equal(flagsForZone(index, [{ ...flagA, state: "false_alarm" }], "3B").length, 0);
});

test("the 3B bathroom wall is a conflict while Flag A is open and stops being one when it is gone", () => {
  const wall = { element_id: "3B-BATH-WALL", kind: "wall", zone_ids: ["3B", "3B-BATH", "3B-BATH-WALL", "B1", "F3"] };
  const plainWall = { element_id: "3B-WALL-01", kind: "wall", zone_ids: ["3B", "3B-LIV", "B1", "F3"] };
  assert.equal(elementStatus(index, state(), wall), "conflict");
  assert.equal(elementStatus(index, state(), plainWall), null, "only walls with their own element Zone are coloured");
  assert.equal(elementStatus(index, state({ flags: [] }), wall), "open", "pending rough-in keeps it open, not ok");
  assert.equal(elementStatus(index, state({ flags: [{ ...flagA, state: "resolved" }] }), wall), "open");
});

test("unconfirmed or contradicted passes never turn a zone ok", () => {
  const base = { flags: [] };
  assert.equal(zoneStatus(index, state({ ...base, evidence: [evidence("llm", "passed", "unconfirmed")] }), "3A"), "open");
  const confirmed = evidence("human", "passed", "confirmed");
  assert.equal(zoneStatus(index, state({ ...base, evidence: [confirmed] }), "3A"), "ok");
  assert.equal(zoneStatus(index, state({ ...base, evidence: [confirmed, evidence("neg", "failed", "unconfirmed")] }), "3A"), "open");
  assert.equal(zoneStatus(index, state({ ...base, evidence: [confirmed, evidence("neg", "failed", "rejected")] }), "3A"), "ok");
  assert.ok(inspectionConfirmedPassed(index, roughIn, [evidence("baseline", "pending", "confirmed", "seed_baseline"), confirmed]),
    "a synthetic pending baseline is the normal progression before a confirmed pass");
  assert.equal(zoneStatus(index, state({ ...base, inspections: [{ ...roughIn, status: "passed" }] }), "3A"), "open",
    "a recorded Inspection status alone is not proof");
  assert.equal(zoneStatus(index, state(), "missing"), "unknown");
});

test("zone details gather scoped flags, inspections with evidence, tasks and revisions", () => {
  const plans = [{ id: "A-103", floor_id: "F3", revisions: [
    { id: "A-103-C", label: "C", sequence: 3, acknowledgments: [{ crew_id: "plumbing", acknowledged_at: "2026-11-13T05:00:00Z" }] },
    { id: "A-103-D", label: "D", sequence: 4, acknowledgments: [] },
  ] }];
  const tasks = [
    { id: "drywall-F3", zone_id: "F3", crew_id: "drywall", starts_at: "2026-11-15T06:00:00Z" },
    { id: "plumbing-F3", zone_id: "F3", crew_id: "plumbing", starts_at: "2026-11-13T07:00:00Z" },
    { id: "drywall-F2", zone_id: "F2", crew_id: "drywall", starts_at: "2026-11-15T06:00:00Z" },
  ];
  const unresolved = evidence("missing-scope", "passed", "unconfirmed", "seed_statement", null);
  unresolved.scope.zone_id = null;
  const details = zoneDetails(index, state({
    plans, tasks, crews: [{ id: "plumbing", name: "Plumbing crew" }],
    evidence: [evidence("llm", "passed", "unconfirmed"), unresolved],
  }), "3B-BATH");
  assert.deepEqual(details.path.map((z) => z.id), ["B1", "F3", "3B", "3B-BATH"]);
  assert.equal(details.status, "conflict");
  assert.deepEqual(details.flags.map((f) => f.id), ["flag-a"]);
  assert.deepEqual(details.tasks.map((t) => t.id), ["plumbing-F3", "drywall-F3"]);
  assert.equal(details.inspections[0].evidence[0].review_status, "unconfirmed");
  assert.deepEqual(details.unresolvedEvidence.map((e) => e.id), ["missing-scope"]);
  assert.deepEqual(details.revisions.map((r) => r.revision.label), ["D", "C"]);
  assert.equal(details.revisions[1].acknowledgments[0].crew.name, "Plumbing crew");
  assert.equal(details.revisions[0].acknowledgments.length, 0, "no acknowledgment is invented for Rev D");
  assert.equal(zoneDetails(index, state(), "XX-404"), null);
});

const wallC = { element_id: "3B-BATH-WALL", kind: "wall", zone_ids: [], shape: { outline: [], segments: [[[22.0, 5.5], [22.0, 8.5]]], position: [22.0, 5.5] } };
const wallD = { ...wallC, shape: { outline: [], segments: [[[22.3, 5.5], [22.3, 8.5]]], position: [22.3, 5.5] } };
const unit = { element_id: "3B", kind: "unit", zone_ids: ["3B", "F3"], shape: { outline: [[12, 0], [24, 0], [24, 8.5], [12, 8.5]], segments: [] } };

test("revision comparison finds the moved bathroom wall by stable element id", () => {
  const changes = changedElements({ elements: [unit, wallD] }, { elements: [unit, wallC] });
  assert.equal(changes.length, 1);
  assert.equal(changes[0].element.element_id, "3B-BATH-WALL");
  assert.equal(changes[0].change, "moved 0.30 m");
  assert.equal(describeChange(null, wallD), "added");
  assert.deepEqual(changedElements({ elements: [unit] }, null), []);
});

test("zone bounds and route-derived view", () => {
  const plan = { floor_id: "F3", elements: [unit, { element_id: "3B-BATH", kind: "room", zone_ids: ["3B", "3B-BATH", "F3"], shape: { outline: [[19, 5.5], [22.3, 5.5], [22.3, 8.5], [19, 8.5]], segments: [] } }] };
  assert.deepEqual(zoneBounds([plan], "3B-BATH"), { minX: 19, maxX: 22.3, minY: 5.5, maxY: 8.5 });
  assert.deepEqual(zoneBounds([plan], "F3"), { minX: 12, maxX: 24, minY: 0, maxY: 8.5 });
  assert.equal(zoneBounds([plan], "2B"), null);
  assert.deepEqual(viewForZone(index, "3B-BATH"), { known: true, floorId: "F3", mode: "top", highlight: "3B-BATH" });
  assert.deepEqual(viewForZone(index, null), { known: true, floorId: null, mode: "orbit", highlight: null });
  assert.equal(viewForZone(index, "XX-404").known, false);
  assert.equal(viewForZone(index, "B1").floorId, null);
});

test("isolating a floor shows only that floor, not the floors below it", () => {
  const floors = ["F1", "F2", "F3", "F4"];
  assert.deepEqual(floors.filter((id) => floorVisible("F3", id)), ["F3"]);
  assert.deepEqual(floors.filter((id) => floorVisible("F1", id)), ["F1"]);
  assert.deepEqual(floors.filter((id) => floorVisible(null, id)), floors, "the whole building without isolation");
});

test("tasks split into running/upcoming and already ended; nothing past is called upcoming", () => {
  const now = Date.parse("2026-11-14T12:00:00Z");
  const tasks = [
    { id: "plumbing-F3", starts_at: "2026-11-13T07:00:00Z", ends_at: "2026-11-13T16:00:00Z" },
    { id: "insulation-F3", starts_at: "2026-11-14T08:00:00Z", ends_at: "2026-11-14T17:00:00Z" },
    { id: "drywall-F3", starts_at: "2026-11-15T06:00:00Z", ends_at: "2026-11-15T15:00:00Z" },
    { id: "no-end", starts_at: "2026-11-13T06:00:00Z" },
  ];
  const { current, earlier } = splitTasks(tasks, now);
  assert.deepEqual(current.map((t) => t.id), ["insulation-F3", "drywall-F3"], "a running task still counts");
  assert.deepEqual(earlier.map((t) => t.id), ["plumbing-F3", "no-end"]);
  assert.equal(inspectionKindLabel("rough_in"), "Rough-in");
});

test("inspection summaries count review states and never treat unconfirmed passes as passed", () => {
  const records = [evidence("seed", "pending", "confirmed", "seed_baseline"), evidence("llm1", "passed", "unconfirmed"), evidence("llm2", "failed", "unconfirmed"), evidence("x", "passed", "rejected")];
  const [summary] = zoneDetails(index, state({ flags: [], evidence: records }), "3A").inspections;
  assert.deepEqual(summary.counts, { confirmed: 1, unconfirmed: 2, rejected: 1 });
  assert.equal(summary.pass, "none");
  const [passed] = zoneDetails(index, state({ flags: [], evidence: [evidence("human", "passed", "confirmed")] }), "3A").inspections;
  assert.equal(passed.pass, "confirmed");
});

test("a confirmed pass is not shown as passed while a relevant counterclaim is unresolved (rules.py boundary)", () => {
  const confirmed = evidence("human", "passed", "confirmed");
  // Unconfirmed failed statement whose exact Inspection is unresolved, in the inspection's zone scope.
  const unresolvedFail = evidence("llm-fail", "failed", "unconfirmed", "llm_statement", null, "3B");
  assert.equal(inspectionPass(index, roughIn, [confirmed, unresolvedFail]), "review");
  assert.equal(zoneStatus(index, state({ flags: [], evidence: [confirmed, unresolvedFail] }), "3A"), "open");
  const [summary] = zoneDetails(index, state({ flags: [], evidence: [confirmed, unresolvedFail] }), "3A").inspections;
  assert.equal(summary.pass, "review");
  // Rejected counterclaims and unresolved claims outside the scope (sibling floor) do not block it.
  assert.equal(inspectionPass(index, roughIn, [confirmed, { ...unresolvedFail, review_status: "rejected" }]), "confirmed");
  assert.equal(inspectionPass(index, roughIn, [confirmed, evidence("f2", "failed", "unconfirmed", "llm_statement", null, "F2")]), "confirmed");
});

test("mismatched scope, invalid confirmations and unverifiable freshness never read as a confirmed pass", () => {
  assert.equal(inspectionPass(index, roughIn, [evidence("wrong-zone", "passed", "confirmed", "seed_statement", "rough-in-F3", "F2")]), "none",
    "exact inspection id but another zone is a scope mismatch");
  const noHistory = { ...evidence("no-history", "passed", "confirmed"), history: [] };
  assert.equal(inspectionPass(index, roughIn, [noHistory]), "none", "review_status alone without a recorded decision");
  const machine = { ...evidence("machine", "passed", "confirmed"), history: [{ status: "confirmed", actor_type: "extractor" }] };
  assert.equal(inspectionPass(index, roughIn, [machine]), "none", "only humans (or the seed import for a baseline) confirm");
  const reopened = { ...evidence("reopened", "passed", "unconfirmed"), history: [{ status: "confirmed", actor_type: "human" }, { status: "needs_clarification", actor_type: "human" }] };
  assert.equal(inspectionPass(index, roughIn, [reopened]), "none", "the latest decision counts");
  assert.equal(inspectionPass(index, roughIn, [evidence("llm-pass", "passed", "confirmed", "llm_statement")]), "unchecked",
    "the API does not expose the statement time here, so staleness cannot be ruled out");
  assert.equal(inspectionPass(index, roughIn, [evidence("u", "passed", "unconfirmed", "llm_statement")]), "none");
});

test("an element is framed together with its parent room", () => {
  const plan = { floor_id: "F3", elements: [
    { element_id: "3B-BATH", kind: "room", zone_ids: ["3B", "3B-BATH", "F3"], shape: { outline: [[19, 5.5], [22.3, 5.5], [22.3, 8.5], [19, 8.5]], segments: [] } },
    { ...wallD, zone_ids: ["3B", "3B-BATH", "3B-BATH-WALL", "F3"] },
  ] };
  assert.deepEqual(focusBounds(index, [plan], "3B-BATH-WALL"), { minX: 19, maxX: 22.3, minY: 5.5, maxY: 8.5 });
  assert.deepEqual(focusBounds(index, [plan], "3B-BATH"), { minX: 19, maxX: 22.3, minY: 5.5, maxY: 8.5 });
});

// Mirrors the live seed: plumbing has a confirmed baseline acknowledgment of A-103 Rev C, but Rev D is current.
const revC = { id: "A-103-C", label: "C", sequence: 3, issued_at: "2026-11-12T12:00:00Z" };
const revD = { id: "A-103-D", label: "D", sequence: 4, issued_at: "2026-11-13T09:15:00Z" };
const planF3 = { id: "A-103", floor_id: "F3", current_revision: revD, revisions: [revC, revD] };
const ack = (id, revision_id, review_status, origin = "seed_baseline", zone_id = "F3", crew_id = "plumbing") => ({
  id, claim: "acknowledged", review_status, origin,
  scope: { kind: "revision_acknowledgment", zone_id, inspection_id: null, task_id: null, crew_id, revision_id },
  history: [{ status: review_status, actor_type: review_status === "unconfirmed" ? "extractor" : origin === "seed_baseline" ? "seed_import" : "human" }],
});

test("a confirmed acknowledgment of an earlier revision is stale, never proof for the current one", () => {
  assert.deepEqual(revisionAcknowledgments(index, planF3, [ack("c", "A-103-C", "confirmed")]),
    [{ crewId: "plumbing", state: "stale", label: "C" }]);
  assert.equal(revisionAcknowledgments(index, planF3, [ack("c", "A-103-C", "confirmed"), ack("d", "A-103-D", "unconfirmed", "llm_statement")])[0].state,
    "unconfirmed", "an extracted Rev D acknowledgment awaits review");
  assert.equal(revisionAcknowledgments(index, planF3, [ack("d", "A-103-D", "confirmed", "llm_statement")])[0].state, "current",
    "a human-confirmed Rev D acknowledgment covers Rev D");
  assert.deepEqual(revisionAcknowledgments(index, planF3, [ack("d", "A-103-D", "confirmed", "seed_baseline", "F2")]), [],
    "evidence for another floor does not apply");
  assert.deepEqual(revisionAcknowledgments(index, planF3, [ack("d", "A-103-D", "rejected", "llm_statement")]), []);
  const machine = { ...ack("d", "A-103-D", "confirmed", "llm_statement"), history: [{ status: "confirmed", actor_type: "extractor" }] };
  assert.equal(revisionAcknowledgments(index, planF3, [machine])[0].state, "unconfirmed", "only a human confirms");
});

test("a confirmed pass scheduled before the current plan revision is not shown as a pass", () => {
  const passed = evidence("human", "passed", "confirmed");
  const before = { ...roughIn, scheduled_at: "2026-11-12T15:00:00Z" };
  const after = { ...roughIn, scheduled_at: "2026-11-14T15:00:00Z" };
  assert.equal(inspectionPass(index, after, [passed], [planF3]), "confirmed");
  assert.equal(inspectionPass(index, before, [passed], [planF3]), "revised");
  assert.equal(inspectionPass(index, roughIn, [passed], [planF3]), "revised", "unknown order is not a pass");
  assert.equal(zoneStatus(index, state({ flags: [], inspections: [before], evidence: [passed], plans: [planF3] }), "3A"), "open");
  assert.equal(zoneStatus(index, state({ flags: [], inspections: [after], evidence: [passed], plans: [planF3] }), "3A"), "ok");
});

test("unit boundary strips lie inside the outline whatever its winding", () => {
  const ccw = [[12, 0], [24, 0], [24, 8.5], [12, 8.5]];
  const inside = ([x, y]) => x >= 12 && x <= 24 && y >= 0 && y <= 8.5;
  for (const outline of [ccw, [...ccw].reverse()]) {
    const strips = insetEdgeStrips(outline, 0.4);
    assert.equal(strips.length, 4);
    for (const quad of strips) for (const point of quad) assert.ok(inside(point), `${point} lies outside`);
  }
  assert.deepEqual(insetEdgeStrips(ccw, 0.4)[0], [[12, 0], [24, 0], [24, 0.4], [12, 0.4]]);
});

test("callouts: a Flag anchors on its flagged wall, the floor's pending inspection is listed, changes are filterable", async () => {
  const { buildCallouts } = await import("../lib/site-model.mjs");
  const wall = { element_id: "W-1", kind: "wall", zone_ids: ["3B-BATH-WALL"] };
  const geometry = [{ floor_id: "F3", elements: [wall] }];
  const changes = [{ element: wall, change: "moved", floorId: "F3", label: "D", previousLabel: "C" }];
  const input = { state: state({ evidence: [evidence("claim", "passed", "unconfirmed")] }), geometry, index, changes };
  const callouts = buildCallouts(input);
  const flag = callouts.find((c) => c.key === "flag-flag-a");
  assert.equal(flag.anchor, "F3:W-1");
  assert.equal(flag.tone, "crit");
  assert.match(callouts.find((c) => c.key === "insp-rough-in-F3").text, /1 unconfirmed claim awaiting review/);
  assert.ok(callouts.some((c) => c.key === "rev-W-1"));
  assert.ok(!buildCallouts({ ...input, showChanges: false }).some((c) => c.key === "rev-W-1"));
  assert.ok(!buildCallouts({ ...input, route: { floorId: "F3", highlight: "3B" } }).some((c) => c.key.startsWith("insp-")), "a selected zone hides floor-level inspection callouts");
});

test("next 48 h: a task is blocked only by an open Flag naming it; an unconfirmed claim never reads as a pass", async () => {
  const { upcoming } = await import("../lib/site-model.mjs");
  const now = Date.parse("2026-11-14T17:00:00Z");
  const tasks = [
    { id: "drywall-F3", name: "Drywall closing", zone_id: "3B", starts_at: "2026-11-15T06:00:00Z" },
    { id: "later", name: "Later", zone_id: "3A", starts_at: "2026-11-20T06:00:00Z" },
  ];
  const inspections = [{ ...roughIn, scheduled_at: "2026-11-15T09:00:00Z" }];
  const items = upcoming({ tasks, inspections, flags: [{ ...flagA, task_id: "drywall-F3" }], evidence: [evidence("claim", "passed", "unconfirmed")], plans: [] }, index, now);
  assert.deepEqual(items.map((item) => [item.key, item.chip.text]), [["drywall-F3", "Blocked by Flag"], ["rough-in-F3", "Pass not confirmed"]]);
  assert.equal(upcoming({ tasks, inspections: [], flags: [], evidence: [], plans: [] }, index, now)[0].chip.text, "No open Flag");
});
