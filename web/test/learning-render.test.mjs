import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { test } from "node:test";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const swc = require("next/dist/build/swc");

async function loadComponent(name) {
  await swc.loadBindings();
  const source = await readFile(new URL(`../app/${name}.js`, import.meta.url), "utf8");
  const { code } = await swc.transform(source, {
    filename: `${name}.js`,
    jsc: { parser: { syntax: "ecmascript", jsx: true }, transform: { react: { runtime: "automatic" } }, target: "es2022" },
    module: { type: "commonjs" },
  });
  const stubs = {
    "next/link": { __esModule: true, default: ({ href, children }) => React.createElement("a", { href }, children) },
    "../lib/site.mjs": await import("../lib/site.mjs"),
    "./actions/review": { submitReview: async () => ({}) },
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
  const { FlagActions, HumanReview } = await loadComponent("human-review");
  const render = (sources) => renderToStaticMarkup(React.createElement(HumanReview, { crews: [] },
    React.createElement(FlagActions, { flag: { id: "flag-1", state: "notified", sources } })));
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
    timezone: "UTC", crewNames: {}, events: [{
      id: "replayed-event", intent: "question", zone_ids: ["3B"], unresolved_zones: [],
      quote: "A question?", evidence: [],
      source: { sent_at: "2026-11-14T08:00:00Z", channel: "replay", sender_role: "crew_lead", text: "A question?", attachments: [] },
      details: { learning: { knowledge_id: "known-1", feedback_id: 42, source_message_id: "original-source" } },
    }],
  }));
  assert.match(html, /href="\/#knowledge-known-1"/);
  assert.match(html, /Extraction corrected: planned work → question/);
  assert.match(html, /Feedback: 42/);
  assert.match(html, /Original source: original-source/);
});
