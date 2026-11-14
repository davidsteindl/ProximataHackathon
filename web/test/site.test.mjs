import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { flattenZones, formatTime, getSiteOverview } from "../lib/site.mjs";

afterEach(() => mock.restoreAll());

test("schedule and timeline filtering reach REST while other overview data remains unfiltered", async () => {
  const urls = [];
  mock.method(globalThis, "fetch", async (url) => {
    urls.push(url);
    return Response.json(url.pathname === "/site" ? { id: "SITE-DEMO" } : []);
  });
  const result = await getSiteOverview("http://api:8000", {
    zoneId: "F3", fromDate: "2026-11-15", toDate: "2026-11-16",
  });
  assert.equal(result.error, null);
  assert.equal(result.data.site.id, "SITE-DEMO");
  assert.ok(urls.some((url) => url.pathname === "/evidence"));
  assert.ok(urls.some((url) => url.pathname === "/site-knowledge"));
  assert.ok(urls.some((url) => url.pathname === "/metrics/flag-feedback"));
  assert.ok(urls.some((url) => url.pathname === "/flags" && url.search === ""));
  assert.deepEqual(result.data.flags, []);
  assert.ok(urls.some((url) => url.pathname === "/flags" && url.searchParams.get("status") === "closed"));
  const tasks = urls.find((url) => url.pathname === "/tasks");
  assert.equal(tasks.searchParams.get("zone_id"), "F3");
  assert.equal(tasks.searchParams.get("from_time"), "2026-11-15T00:00:00Z");
  assert.equal(tasks.searchParams.get("to_time"), "2026-11-16T00:00:00Z");
  const events = urls.find((url) => url.pathname === "/events");
  assert.equal(events.search, tasks.search);
  assert.deepEqual(result.data.events, []);
  assert.ok(urls.filter((url) => !["/tasks", "/events", "/flags"].includes(url.pathname)).every((url) => url.search === ""));
});

test("unavailable or invalid REST responses are shown as errors, not an empty site", async () => {
  mock.method(globalThis, "fetch", async () => Response.json({ detail: "Invalid filter" }, { status: 422 }));
  const result = await getSiteOverview("http://api:8000");
  assert.equal(result.data, null);
  assert.ok(result.error);
});

test("network failures remain visible", async () => {
  mock.method(globalThis, "fetch", async () => { throw new Error("Connection refused"); });
  assert.ok((await getSiteOverview("http://api:8000")).error);
});

test("an unseeded site is distinct from a failed request", async () => {
  mock.method(globalThis, "fetch", async (url) => Response.json(url.pathname === "/site" ? null : []));
  const result = await getSiteOverview("http://api:8000");
  assert.equal(result.error, null);
  assert.equal(result.data.site, null);
});

test("zone choices retain hierarchy and task timestamps use the site's time zone", () => {
  assert.deepEqual(flattenZones([{ id: "B1", children: [{ id: "F3", children: [] }] }]).map(({ id, depth }) => ({ id, depth })), [
    { id: "B1", depth: 0 }, { id: "F3", depth: 1 },
  ]);
  assert.match(formatTime("2026-11-15T06:00:00Z", "Europe/Vienna"), /07:00/);
});

test("scenario time counts days from the site start date in the site timezone", async () => {
  const { scenarioTime } = await import("../lib/site.mjs");
  const site = { start_date: "2026-11-13", timezone: "Europe/Vienna" };
  assert.equal(scenarioTime("2026-11-14T17:10:00Z", site), "Day 2 · 18:10");
  assert.equal(scenarioTime("2026-11-13T23:30:00Z", site), "Day 2 · 00:30", "local midnight, not UTC, starts a day");
  assert.equal(scenarioTime("2026-11-14T17:10:00Z", null), null);
});

test("Flag titles, severity and lifecycle steps", async () => {
  const { flagTitle, lifecycleStep } = await import("../lib/site.mjs");
  assert.equal(flagTitle({ type: "A", zone_id: "3B", activity: "closing_work", precondition: "inspection_passed" }), "Closing work in 3B before inspection passed");
  assert.equal(flagTitle({ type: "B", zone_id: "3B", context: { crew_id: "drywall", current_revision: "D" } }), "Rev D receipt not confirmed: drywall crew · 3B");
  assert.equal(lifecycleStep("notified"), 1);
  assert.equal(lifecycleStep("false_alarm"), 4);
  assert.equal(lifecycleStep("resolved"), lifecycleStep("false_alarm"));
});

test("morning-scan sources come from schedule audit refs; escalation is read from the audit", async () => {
  const { isEscalated, scheduleSources } = await import("../lib/site.mjs");
  const audit = [
    { action: "detected", source_ref: "schedule:drywall-F3@2026-11-15T06:00:00+00:00" },
    { action: "morning_scan", source_ref: "schedule:drywall-F3@2026-11-15T06:00:00+00:00" },
    { action: "escalated", source_ref: "outbox:abc" },
  ];
  assert.deepEqual(scheduleSources({ audit }), [{ ref: "schedule:drywall-F3@2026-11-15T06:00:00+00:00", taskId: "drywall-F3", startsAt: "2026-11-15T06:00:00+00:00" }]);
  assert.equal(isEscalated({ audit }), true);
  assert.equal(isEscalated({ audit: audit.slice(0, 2) }), false);
});
