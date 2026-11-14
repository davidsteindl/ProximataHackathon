import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { postHumanAction } from "../lib/review.mjs";

afterEach(() => mock.restoreAll());

function form(values) {
  const data = new FormData();
  for (const [key, value] of Object.entries(values)) data.set(key, value);
  return data;
}

const human = { actor: "synthetic-superintendent", role: "superintendent", reason: "Reviewed source" };

test("an explicit extraction correction is sent only with false-alarm feedback", async () => {
  const payloads = [];
  mock.method(globalThis, "fetch", async (_url, options) => {
    payloads.push(JSON.parse(options.body));
    return Response.json({});
  });
  for (const action of ["false_alarm", "acknowledge", "resolved"]) {
    await postHumanAction("http://api:8000", "flag", "flag-1", form({
      ...human, action, expected_state: "notified", correction_event_id: "event-question",
    }));
  }
  assert.equal(payloads[0].correction_event_id, "event-question");
  assert.equal(payloads[1].correction_event_id, undefined);
  assert.equal(payloads[2].correction_event_id, undefined);
});

test("human Flag feedback uses the fixed dashboard channel and includes stale-state protection", async () => {
  let request;
  mock.method(globalThis, "fetch", async (url, options) => {
    request = { url, payload: JSON.parse(options.body) };
    return Response.json({});
  });
  const result = await postHumanAction("http://api:8000", "flag", "flag-1", form({
    ...human, action: "acknowledge", expected_state: "notified", channel: "mcp",
  }));
  assert.equal(result.error, null);
  assert.equal(request.url.pathname, "/flags/flag-1/actions");
  assert.equal(request.payload.channel, "dashboard");
  assert.equal(request.payload.feedback, "confirmed");
  assert.equal(request.payload.expected_state, "notified");
});

test("Evidence review sends a decision and sequence, independent of any Flag action", async () => {
  let request;
  mock.method(globalThis, "fetch", async (url, options) => {
    request = { url, payload: JSON.parse(options.body) };
    return Response.json({});
  });
  const result = await postHumanAction("http://api:8000", "evidence", "evidence-1", form({
    ...human, decision: "rejected", expected_sequence: "3",
  }));
  assert.equal(result.error, null);
  assert.equal(request.url.pathname, "/evidence/evidence-1/reviews");
  assert.equal(request.payload.expected_sequence, 3);
  assert.equal(request.payload.decision, "rejected");
  assert.equal(request.payload.action, undefined);
  assert.equal(request.payload.feedback, undefined);
});

test("system signals and undecided Proposals cannot be sent through the dashboard adapter", async () => {
  const fetchMock = mock.method(globalThis, "fetch", async () => { throw new Error("unexpected request"); });
  for (const action of ["action_approved", "notified", "escalated"]) {
    assert.ok((await postHumanAction("http://api:8000", "flag", "flag-1", form({ ...human, action }))).error);
  }
  assert.ok((await postHumanAction("http://api:8000", "proposal", "proposal-1", form(human))).error);
  assert.ok((await postHumanAction("http://api:8000", "proposal", "proposal-1", form({ ...human, decision: "confirmed" }))).error);
  assert.equal(fetchMock.mock.callCount(), 0);
});

test("Proposal decisions go to the decision endpoint via the dashboard channel only", async () => {
  let request;
  mock.method(globalThis, "fetch", async (url, options) => {
    request = { url, payload: JSON.parse(options.body) };
    return Response.json({});
  });
  const result = await postHumanAction("http://api:8000", "proposal", "proposal-1", form({
    ...human, decision: "approved", channel: "mcp",
  }));
  assert.equal(result.error, null);
  assert.equal(request.url.pathname, "/proposals/proposal-1/decisions");
  assert.deepEqual(request.payload, { ...human, channel: "dashboard", decision: "approved" });
});

test("rejected or failed writes remain visible and never report success", async () => {
  const data = form({ ...human, decision: "confirmed", expected_sequence: "1" });
  mock.method(globalThis, "fetch", async () => Response.json({ detail: "Evidence changed; inspect the current review history" }, { status: 409 }));
  assert.match((await postHumanAction("http://api:8000", "evidence", "evidence-1", data)).error, /Evidence changed/);
  mock.method(globalThis, "fetch", async () => Response.json({ detail: [] }, { status: 422 }));
  assert.match((await postHumanAction("http://api:8000", "evidence", "evidence-1", data)).error, /Decision rejected/);
  mock.method(globalThis, "fetch", async () => { throw new Error("timeout"); });
  const failed = await postHumanAction("http://api:8000", "evidence", "evidence-1", data);
  assert.match(failed.error, /Reload/);
  assert.equal(failed.message, undefined);
});
