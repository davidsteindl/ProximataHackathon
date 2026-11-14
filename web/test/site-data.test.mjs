import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { getSiteModel, getSiteState } from "../lib/site-data.mjs";

afterEach(() => mock.restoreAll());

const plans = [{ id: "A-103", floor_id: "F3", revisions: [
  { id: "A-103-C", sequence: 3 }, { id: "A-103-D", sequence: 4 },
] }, { id: "A-101", floor_id: "F1", revisions: [{ id: "A-101-C", sequence: 3 }] }];

test("site model loads current geometry and the previous imported revision only for revised plans", async () => {
  const urls = [];
  mock.method(globalThis, "fetch", async (url) => {
    urls.push(`${url.pathname}${url.search}`);
    if (url.pathname === "/plans") return Response.json(plans);
    if (url.pathname === "/zones") return Response.json([{ id: "B1", children: [] }]);
    if (url.search === "?revision_id=A-103-C") return Response.json([{ plan_id: "A-103", revision_id: "A-103-C", elements: [] }]);
    return Response.json([
      { plan_id: "A-103", revision_id: "A-103-D", sequence: 4, elements: [] },
      { plan_id: "A-101", revision_id: "A-101-C", sequence: 3, elements: [] },
    ]);
  });
  const { data, error } = await getSiteModel("http://api:8000");
  assert.equal(error, null);
  assert.equal(data.geometry.length, 2);
  assert.deepEqual(Object.keys(data.previous), ["A-103"]);
  assert.equal(data.previous["A-103"].revision_id, "A-103-C");
  assert.deepEqual(urls.filter((u) => u.startsWith("/geometry")).sort(), ["/geometry", "/geometry?revision_id=A-103-C"]);
});

test("a missing previous revision geometry does not break the model", async () => {
  mock.method(globalThis, "fetch", async (url) => {
    if (url.pathname === "/plans") return Response.json(plans);
    if (url.search) return new Response("{}", { status: 404 });
    return Response.json(url.pathname === "/zones" ? [] : [{ plan_id: "A-103", sequence: 4, elements: [] }]);
  });
  const { data, error } = await getSiteModel("http://api:8000");
  assert.equal(error, null);
  assert.deepEqual(data.previous, {});
});

test("site state reads only REST endpoints and reports API failure without throwing", async () => {
  const paths = [];
  mock.method(globalThis, "fetch", async (url) => { paths.push(url.pathname); return Response.json([]); });
  const ok = await getSiteState("http://api:8000");
  assert.equal(ok.error, null);
  assert.deepEqual(paths.sort(), ["/crews", "/evidence", "/flags", "/inspections", "/plans", "/site", "/tasks"]);

  mock.restoreAll();
  mock.method(globalThis, "fetch", async () => new Response("", { status: 503 }));
  const failed = await getSiteState("http://api:8000");
  assert.equal(failed.data, null);
  assert.match(failed.error, /could not be loaded/);
});
