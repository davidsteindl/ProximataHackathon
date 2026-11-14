import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { test } from "node:test";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const swc = require("next/dist/build/swc");
const flag = {
  id: "sequence-flag", type: "C", zone_id: "F1", task_id: "drywall-F1", activity: "drywall",
  precondition: "predecessors_completed", inspection_id: null, severity: "high", state: "detected",
  evaluation: "not_satisfied", explanation: "Insulation F1 is not complete.",
  created_at: "2026-11-14T17:05:00Z", updated_at: "2026-11-14T17:05:00Z",
  context: { predecessors: [{ task_id: "insulation-F1", evaluation: "not_satisfied" }] },
  sources: [], audit: [], evidence: [{
    id: "proof", claim: "not_completed", review_status: "confirmed", quote: "Synthetic incomplete insulation.",
    origin: "seed_baseline", source_ref: "seed:schedule.csv#insulation-F1",
    scope: { task_id: "insulation-F1", zone_id: "F1" },
  }],
};

async function loadPage() {
  await swc.loadBindings();
  const source = await readFile(new URL("../app/flags/[flagId]/page.js", import.meta.url), "utf8");
  const { code } = await swc.transform(source, {
    filename: "page.js",
    jsc: { parser: { syntax: "ecmascript", jsx: true }, transform: { react: { runtime: "automatic" } }, target: "es2022" },
    module: { type: "commonjs" },
  });
  const stubs = {
    "next/link": { __esModule: true, default: ({ href, children }) => React.createElement("a", { href }, children) },
    "../../../lib/site.mjs": await import("../lib/site.mjs"),
    "../../../lib/site-data.mjs": { fetchAll: async () => ({ data: { site: { timezone: "UTC" } } }) },
    "../../advice": { __esModule: true, default: () => null },
    "../../decisions": { FlagDecisions: () => null },
    "../../shell": { WorkShell: ({ children }) => React.createElement("main", null, children), StatePanel: () => null },
    "../../site-view/zone-panel": {
      Chip: ({ children }) => React.createElement("span", null, children),
      EVALUATION: { not_satisfied: { text: "Not satisfied", tone: "crit", note: "" } },
      EvidenceItem: ({ record }) => React.createElement("li", null, record.quote),
    },
  };
  const component = { exports: {} };
  vm.runInNewContext(code, {
    exports: component.exports, module: component, require: (id) => stubs[id] || require(id),
    URL, AbortSignal, process: { env: { API_BASE_URL: "http://api.test" } },
    fetch: async () => ({ status: 200, ok: true, json: async () => flag }),
  });
  return component.exports.default;
}

test("Flag C detail lists required predecessors and Task-scoped completion Evidence", async () => {
  const FlagPage = await loadPage();
  const html = renderToStaticMarkup(await FlagPage({ params: Promise.resolve({ flagId: flag.id }) }));
  assert.match(html, /Required predecessors/);
  assert.match(html, /insulation-F1/);
  assert.match(html, /Predecessor completion Evidence/);
  assert.match(html, /Synthetic incomplete insulation\./);
  assert.doesNotMatch(html, /Required inspection|Inspection Evidence|Revision receipt Evidence|required Rev/);
});
