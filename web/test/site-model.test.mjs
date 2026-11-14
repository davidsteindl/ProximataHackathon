import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ancestors, changedElements, describeChange, elementStatus, flagsForZone, floorOf, floorVisible, indexZones,
  inspectionConfirmedPassed, inspectionKindLabel, splitTasks, viewForZone, zoneBounds, zoneDetails, zoneStatus,
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
const evidence = (id, claim, review_status, origin = "seed_statement", inspection_id = "rough-in-F3") => ({
  id, claim, review_status, origin, quote: id, source_ref: id,
  scope: { kind: "inspection", zone_id: "F3", inspection_id, task_id: null, crew_id: null, revision_id: null },
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
  assert.ok(inspectionConfirmedPassed(roughIn, [evidence("baseline", "pending", "confirmed", "seed_baseline"), confirmed]),
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
  assert.equal(summary.confirmedPassed, false);
  const [passed] = zoneDetails(index, state({ flags: [], evidence: [evidence("human", "passed", "confirmed")] }), "3A").inspections;
  assert.equal(passed.confirmedPassed, true);
});
