import assert from "node:assert/strict";
import { test } from "node:test";
import { observeKeyLayout } from "../lib/key-layout.mjs";
import { cameraViewport } from "../lib/site-camera.mjs";

test("an open Key follows desktop/mobile changes, width changes and cleanup", (t) => {
  const originals = Object.fromEntries(["ResizeObserver", "getComputedStyle", "window"].map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  t.after(() => {
    for (const [key, descriptor] of Object.entries(originals)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  });
  let notify, disconnected = false;
  const observed = [];
  const events = new EventTarget();
  globalThis.window = events;
  globalThis.getComputedStyle = (element) => ({ position: element.position });
  globalThis.ResizeObserver = class {
    constructor(callback) { notify = callback; }
    observe(element) { observed.push(element); }
    disconnect() { disconnected = true; }
  };
  const legend = { open: true, offsetWidth: 260, position: "absolute" };
  const viewport = {};
  const reservations = [];
  const stop = observeKeyLayout(legend, viewport, (right) => reservations.push(right));
  assert.deepEqual(observed, [legend, viewport]);
  assert.equal(reservations.at(-1), 276);

  // The same open Key moves below the canvas; no toggle or remount occurs.
  legend.position = "relative";
  events.dispatchEvent(new Event("resize"));
  assert.equal(reservations.at(-1), 0);
  assert.equal(cameraViewport(390, 440, reservations.at(-1)).offsetX, 0);

  // Back to desktop, including the case where the observed sizes stay equal.
  legend.position = "absolute";
  events.dispatchEvent(new Event("resize"));
  assert.equal(reservations.at(-1), 276);
  legend.offsetWidth = 230;
  notify();
  assert.equal(reservations.at(-1), 246);

  legend.open = false;
  notify();
  assert.equal(reservations.at(-1), 0);
  stop();
  assert.equal(disconnected, true);
  const count = reservations.length;
  events.dispatchEvent(new Event("resize"));
  assert.equal(reservations.length, count, "unmounted scene must not retain a resize listener");
});
