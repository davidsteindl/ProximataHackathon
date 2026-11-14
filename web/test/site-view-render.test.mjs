// Renders the real SiteView component with React's server renderer. The JSX is transpiled with the SWC
// binary that ships with Next; only next/navigation, next/link and the CSS import are stubbed.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { test } from "node:test";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const React = require("react");
const { renderToString } = require("react-dom/server");

const swc = require("next/dist/build/swc");

async function compile(name) {
  await swc.loadBindings();
  const source = await readFile(new URL(`../app/site-view/${name}.js`, import.meta.url), "utf8");
  const { code } = await swc.transform(source, {
    filename: `${name}.js`,
    jsc: { parser: { syntax: "ecmascript", jsx: true }, transform: { react: { runtime: "automatic" } }, target: "es2022" },
    module: { type: "commonjs" },
  });
  return code;
}

async function loadSiteView(pathname) {
  return (await loadLocal(pathname))("./site-view").default;
}

async function loadLocal(pathname) {
  const local = Object.fromEntries(await Promise.all(["site-view", "site-nav", "zone-panel"].map(async (name) => [`./${name}`, await compile(name)])));
  const stubs = {
    "next/navigation": { usePathname: () => pathname, useRouter: () => ({ push() {} }) },
    "next/link": { __esModule: true, default: ({ href, children, ...rest }) => React.createElement("a", { href, ...rest }, children) },
    // The pure view model is ESM; import it up front so the CommonJS output can require it synchronously.
    "../../lib/site-model.mjs": await import("../lib/site-model.mjs"),
    "../../lib/site.mjs": await import("../lib/site.mjs"),
    "./site-view.css": {},
  };
  const loaded = new Map();
  const load = (id) => {
    if (stubs[id]) return stubs[id];
    if (!local[id]) return require(id);
    if (!loaded.has(id)) {
      const cjs = { exports: {} };
      loaded.set(id, cjs);
      vm.runInThisContext(`(function (exports, require, module) {${local[id]}\n})`)(cjs.exports, load, cjs);
    }
    return loaded.get(id).exports;
  };
  return load;
}

test("an initial API failure renders the error card instead of crashing (site state data:null)", async () => {
  const SiteView = await loadSiteView("/zones/3B-BATH");
  const html = renderToString(React.createElement(SiteView, {
    model: { zones: [], geometry: [], previous: {} }, initialState: null, error: "Site status could not be loaded from the API.",
  }));
  assert.match(html, /Site model unavailable/);
  assert.match(html, /Site status could not be loaded from the API/);
  assert.match(html, /API unreachable/);
});

test("a failed model load (data:null for both) also renders the error card", async () => {
  const SiteView = await loadSiteView("/site");
  const html = renderToString(React.createElement(SiteView, { model: null, initialState: null, error: "Zones and plan geometry could not be loaded from the API." }));
  assert.match(html, /Site model unavailable/);
});

test("with data the stage, floor rail and key render (sanity check of the harness)", async () => {
  const SiteView = await loadSiteView("/site");
  const zones = [{ id: "B1", kind: "building", name: "Building B1", parent_id: null, children: [] }];
  const html = renderToString(React.createElement(SiteView, {
    model: { zones, geometry: [], previous: {} },
    initialState: { site: { name: "Synthetic site" }, flags: [], evidence: [], inspections: [], plans: [], tasks: [], crews: [] },
    error: null,
  }));
  assert.match(html, /Building B1/);
  assert.match(html, /scenery is decorative/);
  assert.doesNotMatch(html, /Site model unavailable/);
});

test("a confirmation of a superseded revision is never shown in the positive green", async () => {
  const { reviewTone } = (await loadLocal("/site"))("./zone-panel");
  assert.equal(reviewTone("confirmed"), "ok");
  assert.equal(reviewTone("confirmed", true), "unk", "historical decision kept, but neutral");
  assert.equal(reviewTone("unconfirmed", true), "warn");
  assert.equal(reviewTone("rejected", true), "unk");
});
