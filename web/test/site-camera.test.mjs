import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";
import { cameraFrame, cameraViewport } from "../lib/site-camera.mjs";

// Dimensions from the synthetic DXF plans: 24 x 17 m, four 3 m floors.
const buildingBounds = { minX: 0, maxX: 24, minY: 0, maxY: 17 };
const unit = { minX: 12, maxX: 24, minY: 0, maxY: 8.5 };
const bath = { minX: 19, maxX: 22.3, minY: 5.5, maxY: 8.5 };

function assertFits(options, bounds = buildingBounds, bottom = 0, top = 12) {
  const goal = cameraFrame({ buildingBounds, buildingHeight: 12, elevation: 4.56, mode: "orbit", ...options });
  const { width, height, offsetX } = cameraViewport(options.width, options.height, options.coveredRight);
  const camera = new THREE.PerspectiveCamera(goal.fov, width / height, 0.5, Math.max(1200, goal.position.distanceTo(goal.target) * 3));
  camera.position.copy(goal.position);
  camera.lookAt(goal.target);
  camera.setViewOffset(width, height, offsetX, 0, width, height);
  camera.updateMatrixWorld();
  for (const x of [bounds.minX, bounds.maxX]) for (const y of [bounds.minY, bounds.maxY]) for (const z of [bottom, top]) {
    const p = new THREE.Vector3(x - 12, z, -(y - 8.5)).project(camera);
    const px = (p.x + 1) * width / 2, py = (1 - p.y) * height / 2;
    assert.ok(px >= 0 && px <= width - (options.coveredRight || 0), `subject x=${px} outside free canvas at width ${width}`);
    assert.ok(py >= 0 && py <= height, `subject y=${py} outside height ${height}`);
    assert.ok(p.z >= -1 && p.z <= 1, "subject outside camera depth range");
  }
}

test("the whole building fits beside an open Key at narrow and wide desktop sizes", () => {
  for (const width of [465, 480, 588, 844, 1004, 1484]) for (const coveredRight of [0, 276]) {
    assertFits({ width, height: 650, coveredRight });
  }
});

test("isolated floors fit beside the Key in orbit and top-down modes", () => {
  for (const mode of ["orbit", "top"]) for (const width of [465, 588, 1004]) {
    assertFits({ width, height: 800, coveredRight: 276, mode, floorId: "F3", elevation: 6 }, buildingBounds, 6, 8.75);
  }
});

test("selected unit and bathroom remain inside the free top-down view", () => {
  for (const bounds of [unit, bath]) for (const width of [465, 588, 1004]) {
    assertFits({ width, height: 650, coveredRight: 276, mode: "top", floorId: "F3", elevation: 6, bounds }, bounds, 6, 8.75);
  }
});

test("mobile without an overlaid Key uses the full canvas and its centre", () => {
  for (const width of [320, 390, 768]) {
    assert.equal(cameraViewport(width, 440).offsetX, 0);
    assertFits({ width, height: 440 });
  }
});
