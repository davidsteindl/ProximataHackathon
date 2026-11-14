import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { confirmationLabels, entryContext, feedQuery, getFeed, mergeNewest } from "../lib/feed.mjs";

afterEach(() => mock.restoreAll());

test("feed filters map to the REST query", () => {
  const query = feedQuery({ zoneId: "3B", fromDate: "2026-11-13", toDate: "2026-11-15", cursor: "abc", limit: 20 });
  assert.equal(query.get("zone_id"), "3B");
  assert.equal(query.get("from_time"), "2026-11-13T00:00:00Z");
  assert.equal(query.get("to_time"), "2026-11-15T00:00:00Z");
  assert.equal(query.get("cursor"), "abc");
  assert.equal(query.get("limit"), "20");
  assert.equal(feedQuery({}).toString(), "");
});

test("getFeed reads /feed and reports errors without throwing", async () => {
  const urls = [];
  mock.method(globalThis, "fetch", async (url) => {
    urls.push(url);
    return Response.json({ entries: [], next_cursor: null });
  });
  const result = await getFeed("http://api:8000", { zoneId: "F3" });
  assert.deepEqual(result, { data: { entries: [], next_cursor: null }, error: null });
  assert.equal(urls[0].pathname, "/feed");
  assert.equal(urls[0].searchParams.get("zone_id"), "F3");

  mock.method(globalThis, "fetch", async () => new Response("", { status: 404 }));
  assert.equal((await getFeed("http://api:8000", { zoneId: "nowhere" })).error, "Unknown zone.");
  mock.method(globalThis, "fetch", async () => { throw new Error("offline"); });
  assert.equal((await getFeed("http://api:8000")).data, null);
});

test("polled entries go on top without duplicates and refresh known ones", () => {
  const current = [{ id: "b", title: "old" }, { id: "a", title: "A" }];
  const merged = mergeNewest(current, [{ id: "c", title: "C" }, { id: "b", title: "new" }]);
  assert.deepEqual(merged.map((entry) => entry.id), ["c", "b", "a"]);
  assert.equal(merged[1].title, "new");
});

test("context names roles and trades, never people, and unconfirmed is explicit", () => {
  const entry = { actor_role: "crew_lead", channel: "telegram", trade: "drywall", zone_ids: ["3B"] };
  assert.equal(entryContext(entry), "Crew Lead · telegram · drywall · 3B");
  assert.equal(entryContext({ actor_role: null, channel: null, trade: null, zone_ids: [] }), "Zone unresolved");
  assert.equal(confirmationLabels.unconfirmed, "Unconfirmed statement");
});
