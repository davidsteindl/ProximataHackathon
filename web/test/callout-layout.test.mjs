import assert from "node:assert/strict";
import { test } from "node:test";
import { leaderClash, segmentHitsRect } from "../lib/callout-layout.mjs";

const card = { l: 565, t: 370, r: 810, b: 442 }; // Flag A card in the round-4 F3 overhead screenshot

test("a vertical leader through a card is detected even if sampled points would miss", () => {
  assert.equal(segmentHitsRect(687, 502, 687, 330, card), true); // Rev D leader from the review
  assert.equal(segmentHitsRect(600, 371, 600, 372, card), true);
});

test("segments beside, ending at, or along the edge of a card do not count", () => {
  assert.equal(segmentHitsRect(500, 300, 500, 500, card), false);
  assert.equal(segmentHitsRect(687, 502, 687, 442, card), false); // stops at the bottom edge
  assert.equal(segmentHitsRect(565, 300, 565, 500, card), false); // runs along the left edge
  assert.equal(segmentHitsRect(400, 300, 900, 360, card), false); // diagonal above
});

test("leaderClash checks the new leader against placed cards and the new card against placed leaders", () => {
  const placed = [{ rect: card, leader: [687, 502, 687, 442] }];
  // Rev D card above Flag A: its leader from (687,502) to its bottom edge crosses Flag A.
  assert.equal(leaderClash({ x: 687, y: 502 }, { l: 580, t: 280, r: 790, b: 330 }, placed), true);
  // Card to the right of the anchor: leader runs horizontally below Flag A.
  assert.equal(leaderClash({ x: 687, y: 502 }, { l: 720, t: 480, r: 900, b: 540 }, placed), false);
  // A new card sitting on top of Flag A's leader.
  assert.equal(leaderClash({ x: 700, y: 600 }, { l: 650, t: 450, r: 760, b: 495 }, placed), true);
});
