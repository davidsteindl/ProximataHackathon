import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { test } from "node:test";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const swc = require("next/dist/build/swc");

let viewer = { role: "superintendent", actor: "synthetic-superintendent" };

async function loadComponent(name) {
  await swc.loadBindings();
  const source = await readFile(new URL(`../app/${name}.js`, import.meta.url), "utf8");
  const { code } = await swc.transform(source, {
    filename: `${name}.js`,
    jsc: { parser: { syntax: "ecmascript", jsx: true }, transform: { react: { runtime: "automatic" } }, target: "es2022" },
    module: { type: "commonjs" },
  });
  const stubs = {
    "next/link": { __esModule: true, default: ({ href, children, ...rest }) => React.createElement("a", { href, ...rest }, children) },
    "../lib/site.mjs": await import("../lib/site.mjs"),
    "./actions/review": { submitReview: async () => ({}) },
    // Demo role from the app shell; tests switch it through `viewer`.
    "./app-context": { useApp: () => viewer, RoleSwitch: () => null, ScenarioClock: () => null },
    "./site-view/zone-panel": { Chip: ({ children }) => React.createElement("span", null, children), reviewTone: () => "ok" },
  };
  const component = { exports: {} };
  vm.runInThisContext(`(function (exports, require, module) {${code}\n})`)(component.exports, (id) => stubs[id] || require(id), component);
  return component.exports;
}

test("knowledge empty state does not invent a success rate", async () => {
  const { default: SiteKnowledge } = await loadComponent("site-knowledge");
  const html = renderToStaticMarkup(React.createElement(SiteKnowledge, { knowledge: [], metric: [], timezone: "UTC" }));
  assert.match(html, /No Flag feedback yet/);
  assert.match(html, /No Site Knowledge yet/);
  assert.doesNotMatch(html, /<svg/);
});

test("dashboard renders metric chart, definition and linked source-backed knowledge", async () => {
  const { default: SiteKnowledge } = await loadComponent("site-knowledge");
  const html = renderToStaticMarkup(React.createElement(SiteKnowledge, {
    timezone: "UTC",
    metric: [
      { date: "2026-11-13", confirmed_flags: 0, reviewed_flags: 1, confirmed_share: 0 },
      { date: "2026-11-14", confirmed_flags: 1, reviewed_flags: 2, confirmed_share: 0.5 },
    ],
    knowledge: [{
      id: "knowledge-1", flag_id: "flag-1", feedback_id: 42, feedback: "false_alarm",
      reason: "A question, not planned work <script>", recorded_at: "2026-11-14T08:00:00Z",
      source_ids: ["source-original"], correction_event_id: "event-original", correction: "planned_work → question",
    }],
  }));
  assert.match(html, /50% · 1 of 2 reviewed Flags confirmed/);
  assert.match(html, /<svg[^>]+role="img"/);
  assert.match(html, /Daily metric values/);
  assert.match(html, /unreviewed Flags are excluded/);
  assert.match(html, /id="knowledge-knowledge-1"/);
  assert.match(html, /href="\/flags\/flag-1"/);
  assert.match(html, /Feedback: 42/);
  assert.match(html, /Sources: source-original/);
  assert.match(html, /Corrected Event: event-original/);
  assert.match(html, /&lt;script&gt;/);
});

test("human feedback offers explicit correction only for linked planned work", async () => {
  const { FlagDecisions } = await loadComponent("decisions");
  const render = (sources) => renderToStaticMarkup(React.createElement(FlagDecisions, { flag: { id: "flag-1", state: "notified", sources } }));
  const html = render([{ id: "event-1", intent: "planned_work", quote: "A question?" }]);
  assert.match(html, /name="correction_event_id"/);
  assert.match(html, /No extraction correction/);
  assert.match(html, /Question, not planned work: A question\?/);
  assert.match(html, /Never confirms Evidence or changes safety rules/);
  assert.doesNotMatch(render([{ id: "event-2", intent: "inspection_result", quote: "Passed" }]), /name="correction_event_id"/);
});

test("corrected timeline Event visibly links back to knowledge, feedback and original source", async () => {
  const { default: EventTimeline } = await loadComponent("event-timeline");
  const html = renderToStaticMarkup(React.createElement(EventTimeline, {
    site: { start_date: "2026-11-13", timezone: "UTC" }, crewNames: {}, events: [{
      id: "replayed-event", intent: "question", zone_ids: ["3B"], unresolved_zones: [],
      quote: "A question?", evidence: [],
      source: { sent_at: "2026-11-14T08:00:00Z", channel: "replay", sender_role: "crew_lead", text: "A question?", attachments: [] },
      details: { learning: { knowledge_id: "known-1", feedback_id: 42, source_message_id: "original-source" } },
    }],
  }));
  assert.match(html, /href="\/activity#knowledge-known-1"/);
  assert.match(html, /Extraction corrected: planned work → question/);
  assert.match(html, /Feedback: 42/);
  assert.match(html, /Original source: original-source/);
});

test("Proposal decisions: Superintendent only, approval only after acknowledgment, decided ones are read-only", async () => {
  const { ProposalDecision } = await loadComponent("decisions");
  const proposal = { id: "proposal-1", status: "proposed" };
  const render = (flag, item = proposal) => renderToStaticMarkup(React.createElement(ProposalDecision, { flag, proposal: item }));
  const notified = render({ id: "flag-1", state: "notified" });
  assert.match(notified, /value="rejected"/);
  assert.doesNotMatch(notified, /value="approved"/);
  assert.match(notified, /Acknowledge the Flag before approving/);
  assert.match(render({ id: "flag-1", state: "acknowledged" }), /value="approved"/);
  assert.equal(render({ id: "flag-1", state: "acknowledged" }, { ...proposal, status: "approved" }), "");
  assert.equal(render({ id: "flag-1", state: "false_alarm" }), "");
  viewer = { role: "crew_lead", actor: "lead-drywall" };
  try {
    assert.match(render({ id: "flag-1", state: "acknowledged" }), /Only the Superintendent decides on Proposals/);
  } finally {
    viewer = { role: "superintendent", actor: "synthetic-superintendent" };
  }
});

test("the work-view sidebar exposes Proposals and marks it as the current page there", async () => {
  const { WorkShell } = await loadComponent("shell");
  const html = renderToStaticMarkup(React.createElement(WorkShell, { current: "proposals" }, "content"));
  assert.match(html, /href="\/proposals"/);
  assert.match(html, /<a href="\/proposals" class="nav-item cur" aria-current="page">/);
  assert.equal((html.match(/aria-current="page"/g) || []).length, 1, "only the current page is marked");
});
