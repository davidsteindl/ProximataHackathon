import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { confirmationLabels, entryContext, feedQuery, getFeed, readFeedPages } from "../lib/feed.mjs";

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

function pagedFeed(entries) {
  return async (cursor) => {
    const offset = Number(cursor || 0);
    const next = offset + 50;
    return { data: {
      entries: entries.slice(offset, next),
      next_cursor: next < entries.length ? String(next) : null,
    }, error: null };
  };
}

const observations = (count) => Array.from({ length: count }, (_, index) => ({ id: `event:${index}` }));

test("refresh updates an older completion after rejection, including loaded older pages", async () => {
  const completed = { id: "review:confirmed", kind: "task_completed", confirmation: "confirmed", title: "Task completed" };
  const newer = observations(60);
  const initial = await readFeedPages(pagedFeed([...newer, completed]), 2);
  assert.equal(initial.entries.at(-1).kind, "task_completed");

  const rejected = { id: "review:rejected", kind: "evidence_decision", confirmation: "rejected" };
  const superseded = { ...completed, kind: "evidence_decision", title: "Evidence confirmed", summary: "Later rejected." };
  const refreshed = await readFeedPages(pagedFeed([rejected, ...newer, superseded]), 2);
  assert.equal(refreshed.entries.length, 62);
  assert.equal(refreshed.entries.some((entry) => entry.kind === "task_completed"), false);
  assert.equal(refreshed.entries.at(-1).summary, "Later rejected.");
  assert.equal(refreshed.entries[0].confirmation, "rejected");
});

test("a burst of 60 new entries leaves a usable cursor and no pagination gap", async () => {
  const original = { id: "original" };
  const initial = await readFeedPages(pagedFeed([original]));
  assert.equal(initial.next_cursor, null);
  const source = pagedFeed([...observations(60), original]);
  const refreshed = await readFeedPages(source);
  assert.equal(refreshed.entries.length, 50);
  assert.equal(refreshed.next_cursor, "50");
  const expanded = await readFeedPages(source, 2);
  assert.deepEqual(expanded.entries, [...observations(60), original]);
  assert.equal(expanded.next_cursor, null);
});

test("a reset removes old visible entries and clears the old paging cursor", async () => {
  const initial = await readFeedPages(pagedFeed(observations(120)), 2);
  assert.equal(initial.next_cursor, "100");
  const baseline = [{ id: "revision:seed" }];
  const refreshed = await readFeedPages(pagedFeed(baseline), 2);
  assert.deepEqual(refreshed, { entries: baseline, next_cursor: null });
});

test("an error loading an older page fails the whole refresh rather than returning a partial feed", async () => {
  const source = pagedFeed(observations(60));
  await assert.rejects(readFeedPages(async (cursor) => cursor
    ? { data: null, error: "Older page unavailable" } : source(cursor), 2), /Older page unavailable/);
});

test("context names roles and trades, never people, and unconfirmed is explicit", () => {
  const entry = { actor_role: "crew_lead", channel: "telegram", trade: "drywall", zone_ids: ["3B"] };
  assert.equal(entryContext(entry), "Crew Lead · telegram · drywall · 3B");
  assert.equal(entryContext({ actor_role: null, channel: null, trade: null, zone_ids: [] }), "Zone unresolved");
  assert.equal(confirmationLabels.unconfirmed, "Unconfirmed statement");
});
