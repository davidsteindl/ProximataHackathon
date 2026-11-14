import * as THREE from "three";

/** The Key reserves the right edge; projection and framing use the same free area. */
export function cameraViewport(width, height, coveredRight = 0) {
  width = Math.max(1, width);
  height = Math.max(1, height);
  const right = THREE.MathUtils.clamp(coveredRight, 0, width - 1);
  return { width, height, aspect: (width - right) / height, offsetX: right / 2 };
}

/** Camera goal for the current building/floor/Zone, without DOM or renderer state. */
export function cameraFrame({ width, height, coveredRight = 0, buildingBounds, bounds = buildingBounds,
                              buildingHeight, elevation, floorId, mode }) {
  const { aspect } = cameraViewport(width, height, coveredRight);
  const half = (box) => ({ x: (box.maxX - box.minX) / 2, z: (box.maxY - box.minY) / 2 });
  const extent = half(buildingBounds);
  const cx = (buildingBounds.minX + buildingBounds.maxX) / 2;
  const cy = (buildingBounds.minY + buildingBounds.maxY) / 2;
  const P = (x, y, h) => new THREE.Vector3(x - cx, h, -(y - cy));
  if (bounds === buildingBounds && !floorId && mode !== "top") {
    // Overview: a three-quarter view framed on the building itself (the subject, with its Flag volume);
    // the decorative crane and scenery may crop at the edges.
    const sphere = new THREE.Box3(new THREE.Vector3(-extent.x, 0, -extent.z), new THREE.Vector3(extent.x, buildingHeight, extent.z))
      .getBoundingSphere(new THREE.Sphere());
    const fov = 30;
    const vfov = THREE.MathUtils.degToRad(fov / 2);
    const hfov = Math.atan(Math.tan(vfov) * aspect);
    // Preserve the overview fill while fitting the area left uncovered by the Key.
    const radius = (sphere.radius / Math.sin(Math.min(vfov, hfov))) * (aspect < 1 ? 1.2 : 1.3);
    const target = sphere.center.clone().setY(buildingHeight * 0.42);
    return { target, position: target.clone().add(new THREE.Vector3().setFromSphericalCoords(radius, THREE.MathUtils.degToRad(57), THREE.MathUtils.degToRad(36))), fov };
  }
  const focused = bounds !== buildingBounds;
  // A room or element keeps a modest minimum frame so its neighbours give context and callouts fit beside it.
  const portrait = aspect < 1;
  const sx = Math.max(bounds.maxX - bounds.minX, focused ? (portrait ? 5 : 8) : 14);
  const sz = Math.max(bounds.maxY - bounds.minY, focused ? (portrait ? 5 : 6) : 10);
  const center = P((bounds.minX + bounds.maxX) / 2, (bounds.minY + bounds.maxY) / 2, elevation);
  const pad = focused ? (portrait ? 1.45 : 1.7) : 1.35;
  const chrome = aspect < 1 ? 1.5 : 2; // floating cards on desktop; mobile controls sit below the canvas
  if (mode === "top") {
    // Straight down with a very narrow FOV: reads as an orthographic plan, wall sides stay hidden.
    const fov = 8;
    const needed = Math.max(sz * pad, (sx * pad) / aspect) + chrome;
    // Keep the frame on the building: shift the centre inward instead of showing empty ground beside it.
    const hb = half(buildingBounds);
    const visible = { x: (needed * aspect) / 2, z: needed / 2 };
    const margin = 2;
    for (const axis of ["x", "z"]) {
      const room = hb[axis] + margin - visible[axis];
      center[axis] = room > 0 ? THREE.MathUtils.clamp(center[axis], -room, room) : 0;
    }
    const dist = needed / 2 / Math.tan(THREE.MathUtils.degToRad(fov / 2));
    return { target: center, position: center.clone().add(new THREE.Vector3(0, dist, 0.0001)), fov };
  }
  const fov = 32;
  const radius = Math.max(1, (width / height) / aspect) * Math.max(Math.hypot(sx, sz), 8) * (aspect < 1 ? 1.6 : 1.25) / Math.tan(THREE.MathUtils.degToRad(fov / 2)) * (focused ? 0.62 : 0.55);
  const polar = THREE.MathUtils.degToRad(floorId ? 50 : 62);
  const azimuth = THREE.MathUtils.degToRad(36);
  const offset = new THREE.Vector3().setFromSphericalCoords(radius, polar, azimuth);
  return { target: center, position: center.clone().add(offset), fov };
}
