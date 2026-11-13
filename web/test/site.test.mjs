import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { flattenZones, formatTime, getSiteOverview } from "../lib/site.mjs";

afterEach(() => mock.restoreAll());

test("schedule filtering reaches REST and other overview data remains unfiltered", async () => {
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
  const tasks = urls.find((url) => url.pathname === "/tasks");
  assert.equal(tasks.searchParams.get("zone_id"), "F3");
  assert.equal(tasks.searchParams.get("from_time"), "2026-11-15T00:00:00Z");
  assert.equal(tasks.searchParams.get("to_time"), "2026-11-16T00:00:00Z");
  assert.ok(urls.filter((url) => url.pathname !== "/tasks").every((url) => url.search === ""));
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
