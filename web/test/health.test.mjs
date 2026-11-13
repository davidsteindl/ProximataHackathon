import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { getHealth } from "../lib/health.mjs";

afterEach(() => mock.restoreAll());

test("dashboard preserves database failure reported by the API", async () => {
  mock.method(globalThis, "fetch", async (url) => {
    assert.equal(url, "http://api:8000/health");
    return Response.json({ api: "ok", db: "error" }, { status: 503 });
  });
  assert.deepEqual(await getHealth("http://api:8000"), {
    api: "ok",
    db: "error",
  });
});

test("dashboard reports an unreachable API without claiming database health", async () => {
  mock.method(globalThis, "fetch", async () => {
    throw new Error("Connection refused");
  });
  assert.deepEqual(await getHealth("http://api:8000"), {
    api: "unreachable",
    db: "unknown",
  });
});
