// Decorative site context for the 3D view: ground, street, fence and hoarding, scaffold, tower crane,
// site office, vehicles, material stacks, vegetation and neighbouring blocks. NONE of this comes from plan
// data; the UI labels it as decorative and every object carries userData.decorative. Repeated parts are
// instanced, textures are generated on a canvas (no assets, no extra dependencies).
import * as THREE from "three";

const mat = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.9, metalness: 0, ...extra });

function rng(seed) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) - 1) / 2147483646;
}

const BOX = new THREE.BoxGeometry(1, 1, 1);
const CYL = new THREE.CylinderGeometry(0.5, 0.5, 1, 12);
const BLOB = new THREE.IcosahedronGeometry(1, 2);
const CONE = new THREE.ConeGeometry(1, 1, 8);

/** Instanced copies of one unit geometry from {x,y,z,sx,sy,sz,rx,ry,rz,color} descriptors. */
function instanced(geometry, items, material, { cast = true, receive = true } = {}) {
  const mesh = new THREE.InstancedMesh(geometry, material, Math.max(items.length, 1));
  mesh.count = items.length;
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const e = new THREE.Euler();
  const color = new THREE.Color();
  items.forEach((b, i) => {
    q.setFromEuler(e.set(b.rx || 0, b.ry || 0, b.rz || 0));
    m.compose(new THREE.Vector3(b.x, b.y, b.z), q, new THREE.Vector3(b.sx, b.sy, b.sz));
    mesh.setMatrixAt(i, m);
    if (b.color !== undefined) mesh.setColorAt(i, color.set(b.color));
  });
  mesh.castShadow = cast;
  mesh.receiveShadow = receive;
  return mesh;
}
const boxes = (items, material, options) => instanced(BOX, items, material, options);

/** A thin box spanning two points (tubes, lattice members). */
function bar(a, b, t) {
  const d = new THREE.Vector3().subVectors(b, a);
  const len = d.length();
  const mid = new THREE.Vector3().addVectors(a, b).multiplyScalar(0.5);
  const e = new THREE.Euler().setFromQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize()));
  return { x: mid.x, y: mid.y, z: mid.z, sx: t, sy: len, sz: t, rx: e.x, ry: e.y, rz: e.z };
}
const V = (x, y, z) => new THREE.Vector3(x, y, z);

/** Tileable value-noise texture; `paint` adds marks (tracks, lines) on top. */
function noiseTexture({ size = 256, base, spread, seed, repeat = 1, paint }) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  const random = rng(seed);
  const [r, g, b] = base;
  const img = ctx.createImageData(size, size);
  for (let i = 0; i < size * size; i++) {
    const n = (random() - 0.5) * spread;
    img.data[i * 4] = r + n;
    img.data[i * 4 + 1] = g + n;
    img.data[i * 4 + 2] = b + n * 0.9;
    img.data[i * 4 + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  // Soft blotches break up the uniform noise.
  for (let i = 0; i < 40; i++) {
    const x = random() * size;
    const y = random() * size;
    const rad = 10 + random() * 40;
    const grad = ctx.createRadialGradient(x, y, 0, x, y, rad);
    const shade = random() < 0.5 ? "0,0,0" : "255,255,255";
    grad.addColorStop(0, `rgba(${shade},${0.05 + random() * 0.06})`);
    grad.addColorStop(1, `rgba(${shade},0)`);
    ctx.fillStyle = grad;
    ctx.fillRect(x - rad, y - rad, rad * 2, rad * 2);
  }
  paint?.(ctx, size, random);
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(repeat, repeat);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

/** Radial dark blob: cheap baked contact shadow under objects. */
function contactTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 128;
  const ctx = canvas.getContext("2d");
  const grad = ctx.createRadialGradient(64, 64, 8, 64, 64, 64);
  grad.addColorStop(0, "rgba(0,0,0,0.75)");
  grad.addColorStop(0.55, "rgba(0,0,0,0.35)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(canvas);
}

/** Mesh-fence texture with alpha: frame plus wire grid. */
function fenceTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 64;
  const ctx = canvas.getContext("2d");
  ctx.strokeStyle = "rgba(205,205,195,0.85)";
  ctx.lineWidth = 1;
  for (let x = 0; x <= 128; x += 6) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 64); ctx.stroke(); }
  for (let y = 0; y <= 64; y += 6) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(128, y); ctx.stroke(); }
  ctx.lineWidth = 4;
  ctx.strokeRect(2, 2, 124, 60);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/**
 * Tower crane with a full lattice jib. Returns the group and its slewing part (rotated by the scene's
 * ambient animation unless the user prefers reduced motion).
 */
function crane({ x, z, height, jib, counter, angle }, steel, dark, weight) {
  const g = new THREE.Group();
  const w = 1.7;
  const mast = [];
  const corners = [[-w / 2, -w / 2], [w / 2, -w / 2], [w / 2, w / 2], [-w / 2, w / 2]];
  corners.forEach(([cx, cz]) => mast.push(bar(V(cx, 0.9, cz), V(cx, height, cz), 0.16)));
  for (let y = 0.9; y < height - 0.1; y += 1.9) {
    for (let i = 0; i < 4; i++) {
      const [ax, az] = corners[i];
      const [bx, bz] = corners[(i + 1) % 4];
      mast.push(bar(V(ax, y, az), V(bx, Math.min(y + 1.9, height), bz), 0.06));
      mast.push(bar(V(ax, y, az), V(bx, y, bz), 0.07));
    }
  }
  // Concrete ballast base with a few blocks.
  g.add(boxes([{ x: 0, y: 0.45, z: 0, sx: 5, sy: 0.9, sz: 5 }], weight));
  g.add(boxes(mast, steel, { receive: false }));

  const slew = new THREE.Group();
  const top = height;
  const parts = [];
  // Slewing ring and turntable.
  parts.push({ x: 0, y: top + 0.25, z: 0, sx: 2.4, sy: 0.5, sz: 2.4 });
  // Jib: triangular lattice (two bottom chords, one top chord) along +X.
  const half = 0.6;
  const rise = 1.5;
  const lattice = [];
  lattice.push(bar(V(0, top + 0.5, -half), V(jib, top + 0.5, -half), 0.13));
  lattice.push(bar(V(0, top + 0.5, half), V(jib, top + 0.5, half), 0.13));
  lattice.push(bar(V(0, top + 0.5 + rise, 0), V(jib - 1, top + 0.5 + rise * 0.4, 0), 0.12));
  for (let s = 0; s < jib - 1.6; s += 1.6) {
    const yTop = top + 0.5 + rise * (1 - 0.6 * (s / jib));
    const yNext = top + 0.5 + rise * (1 - 0.6 * ((s + 0.8) / jib));
    lattice.push(bar(V(s, top + 0.5, -half), V(s + 0.8, yNext, 0), 0.05));
    lattice.push(bar(V(s + 0.8, yNext, 0), V(s + 1.6, top + 0.5, half), 0.05));
    lattice.push(bar(V(s, top + 0.5, half), V(s + 0.8, yNext, 0), 0.05));
    lattice.push(bar(V(s + 0.8, yNext, 0), V(s + 1.6, top + 0.5, -half), 0.05));
    lattice.push(bar(V(s, top + 0.5, -half), V(s, top + 0.5, half), 0.05));
    if (s === 0) lattice.push(bar(V(0, top + 0.5, 0), V(0, yTop, 0), 0.08));
  }
  // Counter-jib: flat frame with walkway and stacked ballast.
  lattice.push(bar(V(-counter, top + 0.5, -half * 1.3), V(0, top + 0.5, -half * 1.3), 0.14));
  lattice.push(bar(V(-counter, top + 0.5, half * 1.3), V(0, top + 0.5, half * 1.3), 0.14));
  for (let s = -counter; s < 0; s += 1.4) lattice.push(bar(V(s, top + 0.5, -half * 1.3), V(s, top + 0.5, half * 1.3), 0.07));
  // A-frame apex and pendant ties to jib and counter-jib.
  lattice.push(bar(V(-0.8, top + 0.5, -0.6), V(0, top + 6, 0), 0.15));
  lattice.push(bar(V(-0.8, top + 0.5, 0.6), V(0, top + 6, 0), 0.15));
  lattice.push(bar(V(0.8, top + 0.5, 0), V(0, top + 6, 0), 0.15));
  const ties = [
    bar(V(0, top + 6, 0), V(jib * 0.45, top + 0.5 + rise * 0.75, 0), 0.035),
    bar(V(0, top + 6, 0), V(jib * 0.8, top + 0.5 + rise * 0.5, 0), 0.035),
    bar(V(0, top + 6, 0), V(-counter + 0.5, top + 0.6, -0.4), 0.035),
    bar(V(0, top + 6, 0), V(-counter + 0.5, top + 0.6, 0.4), 0.035),
  ];
  slew.add(boxes(lattice, steel, { receive: false }));
  slew.add(boxes(ties, dark, { cast: false }));
  slew.add(boxes([
    ...parts,
    { x: -counter + 1.2, y: top - 0.3, z: 0, sx: 1.4, sy: 1.9, sz: 2.2 }, // ballast blocks
    { x: -counter + 2.7, y: top - 0.3, z: 0, sx: 1.4, sy: 1.9, sz: 2.2 },
  ], weight));
  // Cab with a dark glazed front, machinery house on the counter-jib.
  slew.add(boxes([{ x: 1.2, y: top - 0.55, z: 1.25, sx: 1.7, sy: 1.8, sz: 1.3 }], steel));
  slew.add(boxes([
    { x: 2.08, y: top - 0.45, z: 1.25, sx: 0.04, sy: 1.1, sz: 1.1 },
    { x: -counter + 4.6, y: top + 1.1, z: 0, sx: 2, sy: 1.2, sz: 1.6 },
  ], dark, { cast: false }));
  // Trolley, hoist ropes and hook block on a load of formwork panels.
  const trolley = jib * 0.62;
  const hook = height * 0.42;
  slew.add(boxes([
    { x: trolley, y: top + 0.25, z: 0, sx: 1.2, sy: 0.35, sz: 1.4 },
    bar(V(trolley, top + 0.1, -0.12), V(trolley, hook + 0.6, -0.12), 0.025),
    bar(V(trolley, top + 0.1, 0.12), V(trolley, hook + 0.6, 0.12), 0.025),
    { x: trolley, y: hook + 0.3, z: 0, sx: 0.45, sy: 0.7, sz: 0.45 },
    bar(V(trolley, hook, 0), V(trolley - 1, hook - 1.6, -0.6), 0.02),
    bar(V(trolley, hook, 0), V(trolley + 1, hook - 1.6, 0.6), 0.02),
  ], dark));
  slew.add(boxes([{ x: trolley, y: hook - 1.8, z: 0, sx: 2.6, sy: 0.35, sz: 1.4 }], mat(0xB79E6A)));
  slew.rotation.y = angle;
  g.add(slew);
  g.position.set(x, 0, z);
  return { group: g, slew };
}

/**
 * @param bounds world-space building bounds {minX,maxX,minZ,maxZ,height}
 * @returns {{ group, tall, slew, focus: THREE.Box3 }} `tall` is hidden in top-down mode; `slew` is the
 *   crane's rotating part; `focus` is what the overview camera should frame (building plus crane).
 */
export function buildSiteContext(bounds) {
  const group = new THREE.Group();
  const tall = new THREE.Group();
  group.add(tall);
  const random = rng(42);
  const { minX, maxX, minZ, maxZ, height } = bounds;
  // Scenery stays desaturated so plan geometry and status colours lead; one restrained crane yellow.
  const steel = mat(0x9A978C, { roughness: 0.6, metalness: 0.3 });
  const craneSteel = mat(0xC9A23C, { roughness: 0.55, metalness: 0.2 });
  const dark = mat(0x34352F);
  const concrete = mat(0x8D8A80);
  const wood = mat(0x9A7E55);
  const contact = new THREE.MeshBasicMaterial({ map: contactTexture(), transparent: true, depthWrite: false, opacity: 0.55 });
  const shadows = []; // {x,z,sx,sz,ry}

  // ---------- ground ----------
  const pad = { minX: minX - 16, maxX: maxX + 18, minZ: minZ - 13, maxZ: maxZ + 15 };
  const grass = noiseTexture({ base: [44, 50, 36], spread: 26, seed: 7, repeat: 40 });
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(700, 700), mat(0xFFFFFF, { map: grass }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.1;
  ground.receiveShadow = true;
  const gravelMap = noiseTexture({
    base: [104, 98, 86], spread: 34, seed: 3, repeat: 3,
    paint(ctx, size, r) { // tyre tracks
      ctx.strokeStyle = "rgba(40,36,30,0.18)";
      for (let i = 0; i < 6; i++) {
        ctx.lineWidth = 3 + r() * 3;
        ctx.beginPath();
        const y = r() * size;
        ctx.moveTo(0, y);
        ctx.bezierCurveTo(size * 0.3, y + (r() - 0.5) * 80, size * 0.6, y + (r() - 0.5) * 80, size, y);
        ctx.stroke();
      }
    },
  });
  const gravel = new THREE.Mesh(new THREE.PlaneGeometry(pad.maxX - pad.minX, pad.maxZ - pad.minZ), mat(0xFFFFFF, { map: gravelMap }));
  gravel.rotation.x = -Math.PI / 2;
  gravel.position.set((pad.minX + pad.maxX) / 2, -0.05, (pad.minZ + pad.maxZ) / 2); // below the F1 slab top
  gravel.receiveShadow = true;

  // Street in front (south), with kerbs, pavement and lane marks; haul road from the gate to the building.
  const roadZ = pad.maxZ + 8;
  const asphalt = noiseTexture({ base: [46, 47, 44], spread: 18, seed: 11, repeat: 30 });
  const road = new THREE.Mesh(new THREE.PlaneGeometry(700, 8), mat(0xFFFFFF, { map: asphalt, roughness: 0.95 }));
  road.rotation.x = -Math.PI / 2;
  road.position.set(0, -0.06, roadZ);
  road.receiveShadow = true;
  const flat = [];
  for (let x = -200; x < 200; x += 7) flat.push({ x, y: -0.04, z: roadZ, sx: 3.2, sy: 0.02, sz: 0.14 });
  const kerbs = [];
  for (const side of [-1, 1]) {
    kerbs.push({ x: 0, y: 0.02, z: roadZ + side * 4.1, sx: 700, sy: 0.2, sz: 0.25 });
    kerbs.push({ x: 0, y: -0.01, z: roadZ + side * 5.6, sx: 700, sy: 0.14, sz: 2.8 });
  }
  const gateX = (pad.minX + pad.maxX) / 2 + 9;
  const haul = noiseTexture({ base: [122, 114, 98], spread: 30, seed: 5, repeat: 2 });
  const haulRoad = new THREE.Mesh(new THREE.PlaneGeometry(6, pad.maxZ - maxZ + 1), mat(0xFFFFFF, { map: haul }));
  haulRoad.rotation.x = -Math.PI / 2;
  haulRoad.position.set(gateX, -0.035, (pad.maxZ + maxZ) / 2 + 0.5);
  haulRoad.receiveShadow = true;
  group.add(ground, gravel, road, haulRoad, boxes(flat, mat(0xB9B6AA), { cast: false }), boxes(kerbs, mat(0x8A887F), { cast: false }));

  // ---------- perimeter: mesh fence on three sides, solid hoarding to the street with an open gate ----------
  const fenceMat = new THREE.MeshStandardMaterial({ map: fenceTexture(), transparent: true, alphaTest: 0.15, side: THREE.DoubleSide, roughness: 0.6, metalness: 0.4 });
  const fence = [];
  const feet = [];
  const hoard = [];
  const run = (ax, az, bx, bz, solid) => {
    const len = Math.hypot(bx - ax, bz - az);
    const n = Math.ceil(len / 3.5);
    for (let i = 0; i < n; i++) {
      const x0 = ax + ((bx - ax) * i) / n;
      const z0 = az + ((bz - az) * i) / n;
      const x1 = ax + ((bx - ax) * (i + 1)) / n;
      const z1 = az + ((bz - az) * (i + 1)) / n;
      const cx = (x0 + x1) / 2;
      if (solid && Math.abs(cx - gateX) < 4) continue;
      const panel = { x: cx, y: 1.05, z: (z0 + z1) / 2, sx: Math.hypot(x1 - x0, z1 - z0), sy: 2, sz: solid ? 0.08 : 1, ry: -Math.atan2(z1 - z0, x1 - x0) };
      (solid ? hoard : fence).push(panel);
      feet.push({ x: x0, y: 0.08, z: z0, sx: 0.7, sy: 0.16, sz: 0.25, ry: panel.ry });
    }
  };
  run(pad.minX, pad.minZ, pad.maxX, pad.minZ);
  run(pad.maxX, pad.minZ, pad.maxX, pad.maxZ);
  run(pad.minX, pad.maxZ, pad.minX, pad.minZ);
  run(pad.maxX, pad.maxZ, pad.minX, pad.maxZ, true);
  const fenceMesh = instanced(new THREE.PlaneGeometry(1, 1), fence, fenceMat, { receive: false });
  group.add(fenceMesh, boxes(feet, concrete, { cast: false }));
  group.add(boxes(hoard, mat(0xD8D4C8)), boxes(hoard.map((h) => ({ ...h, y: 0.35, sy: 0.7, sz: 0.1 })), mat(0x3F4A3E), { cast: false }));
  // Open gate leaves.
  group.add(instanced(new THREE.PlaneGeometry(1, 1), [
    { x: gateX - 4 + 0.6, y: 1.05, z: pad.maxZ + 1.6, sx: 3.4, sy: 2, sz: 1, ry: Math.PI / 2.4 },
    { x: gateX + 4 - 0.6, y: 1.05, z: pad.maxZ + 1.6, sx: 3.4, sy: 2, sz: 1, ry: -Math.PI / 2.4 },
  ], fenceMat, { receive: false }));

  // ---------- scaffold on the north and west facades (behind the building from the default camera) ----------
  const tubes = [];
  const decks = [];
  const toe = [];
  const nets = [];
  const top = height + 1.2;
  const runs = [
    { ax: minX - 0.5, az: minZ - 0.5, bx: maxX + 0.5, bz: minZ - 0.5, out: [0, -1] },
    { ax: minX - 0.5, az: minZ - 0.5, bx: minX - 0.5, bz: maxZ + 0.5, out: [-1, 0] },
  ];
  runs.forEach(({ ax, az, bx, bz, out }) => {
    const len = Math.hypot(bx - ax, bz - az);
    const ux = (bx - ax) / len;
    const uz = (bz - az) / len;
    const bays = Math.round(len / 2.5);
    const at = (i, depth, y) => V(ax + ux * (len * i / bays) + out[0] * depth, y, az + uz * (len * i / bays) + out[1] * depth);
    for (let i = 0; i <= bays; i++) {
      for (const depth of [0.2, 1.1]) tubes.push(bar(at(i, depth, 0), at(i, depth, top), 0.048));
      for (let y = 2; y <= top; y += 2) tubes.push(bar(at(i, 0.2, y), at(i, 1.1, y), 0.04)); // transoms
    }
    for (let y = 2; y <= top; y += 2) {
      for (const depth of [0.2, 1.1]) tubes.push(bar(at(0, depth, y), at(bays, depth, y), 0.04)); // ledgers
      tubes.push(bar(at(0, 1.1, y + 1), at(bays, 1.1, y + 1), 0.035)); // guard rail
      const mid = at(bays / 2, 0.65, y + 0.03);
      const along = Math.abs(ux) > 0.5;
      decks.push({ x: mid.x, y: mid.y, z: mid.z, sx: along ? len : 0.95, sy: 0.05, sz: along ? 0.95 : len });
      const edge = at(bays / 2, 1.12, y + 0.12);
      toe.push({ x: edge.x, y: edge.y, z: edge.z, sx: along ? len : 0.03, sy: 0.18, sz: along ? 0.03 : len });
    }
    // Zig-zag face bracing every other bay.
    for (let i = 0; i < bays; i += 2) for (let y = 0; y < top - 1; y += 4) tubes.push(bar(at(i, 1.15, y), at(i + 1, 1.15, Math.min(y + 4, top)), 0.035));
    // Debris netting on the outer face.
    const n = at(bays / 2, 1.2, top / 2);
    nets.push({ x: n.x, y: n.y, z: n.z, sx: Math.abs(ux) > 0.5 ? len : 1, sy: top, sz: 1, ry: Math.abs(ux) > 0.5 ? 0 : Math.PI / 2 });
  });
  const netMat = new THREE.MeshStandardMaterial({ color: 0x8FA39B, transparent: true, opacity: 0.16, depthWrite: false, side: THREE.DoubleSide });
  tall.add(boxes(tubes, steel, { receive: false }), boxes(decks, wood), boxes(toe, mat(0xB08A4E), { cast: false }),
    instanced(new THREE.PlaneGeometry(1, 1), nets, netMat, { cast: false, receive: false }));

  // ---------- tower crane behind the building; full jib swings over the site ----------
  const towerCrane = crane({ x: maxX + 5.5, z: minZ - 5.5, height: height + 17, jib: 38, counter: 11, angle: Math.PI * 0.9 }, craneSteel, dark, concrete);
  tall.add(towerCrane.group);
  shadows.push({ x: maxX + 5.5, z: minZ - 5.5, sx: 8, sz: 8 });

  // ---------- site office: two-storey container stack with stair and walkway, toilets, skip ----------
  const ox = minX - 10.5;
  const oz = maxZ + 2;
  const units = [];
  const glazing = [];
  for (let i = 0; i < 3; i++) units.push({ x: ox, y: 1.3, z: oz - i * 2.55, sx: 6.05, sy: 2.6, sz: 2.45, color: i === 1 ? 0xC8CCC6 : 0xE2E1DA });
  for (let i = 0; i < 2; i++) units.push({ x: ox, y: 3.92, z: oz - i * 2.55, sx: 6.05, sy: 2.6, sz: 2.45, color: 0x9DA7A6 });
  units.forEach((u) => {
    glazing.push({ x: u.x + 3.04, y: u.y + 0.2, z: u.z - 0.3, sx: 0.04, sy: 0.9, sz: 1.1 });
    glazing.push({ x: u.x + 3.04, y: u.y - 0.15, z: u.z + 0.75, sx: 0.04, sy: 2, sz: 0.8 });
  });
  group.add(boxes(units, mat(0xFFFFFF)), boxes(glazing, mat(0x23282A, { roughness: 0.25, metalness: 0.3 }), { cast: false }));
  const stair = [];
  for (let i = 0; i < 9; i++) stair.push({ x: ox + 3.7, y: 0.3 + i * 0.29, z: oz + 2.1 - i * 0.3, sx: 1, sy: 0.05, sz: 0.3 });
  stair.push({ x: ox + 3.7, y: 2.62, z: oz - 2.6, sx: 1, sy: 0.06, sz: 6.6 });
  stair.push(bar(V(ox + 4.2, 3.6, oz + 0.7), V(ox + 4.2, 3.6, oz - 5.8), 0.05));
  for (let z = oz + 0.7; z > oz - 6; z -= 1.6) stair.push(bar(V(ox + 4.2, 2.6, z), V(ox + 4.2, 3.6, z), 0.05));
  group.add(boxes(stair, steel));
  group.add(boxes([
    { x: ox - 1.5, y: 1.2, z: oz + 2.6, sx: 1.2, sy: 2.4, sz: 1.2 },
    { x: ox, y: 1.2, z: oz + 2.6, sx: 1.2, sy: 2.4, sz: 1.2 },
  ], mat(0x4E7A63)));
  // Waste skip (tapered) by the haul road.
  const skip = new THREE.Mesh(new THREE.CylinderGeometry(1.6, 1.15, 1.3, 4, 1, true), mat(0x6E5B3F, { side: THREE.DoubleSide }));
  skip.scale.set(1.6, 1, 0.9);
  skip.rotation.y = Math.PI / 4;
  skip.position.set(gateX - 6, 0.65, maxZ + 6);
  skip.castShadow = true;
  group.add(skip);
  shadows.push({ x: ox, z: oz - 2.5, sx: 9, sz: 10 }, { x: gateX - 6, z: maxZ + 6, sx: 5, sz: 3.5 });

  // ---------- vehicles: concrete mixer at the gate, two vans parked by the office ----------
  const mixer = new THREE.Group();
  mixer.add(boxes([
    { x: 0, y: 0.75, z: 0, sx: 7.6, sy: 0.5, sz: 2.3 }, // chassis
    { x: 3, y: 1.75, z: 0, sx: 1.8, sy: 1.9, sz: 2.4 }, // cab
  ], mat(0xD6D3CA)));
  mixer.add(boxes([{ x: 3.92, y: 2.05, z: 0, sx: 0.04, sy: 0.85, sz: 2 }], mat(0x1E2224, { roughness: 0.2 }), { cast: false }));
  const drum = new THREE.Mesh(new THREE.CylinderGeometry(1.15, 0.7, 4.2, 14), mat(0xC56A3A));
  drum.rotation.z = Math.PI / 2 - 0.22;
  drum.position.set(-1.2, 2.25, 0);
  drum.castShadow = true;
  mixer.add(drum);
  const wheels = [-2.8, -1.6, 2.9].flatMap((wx) => [-1, 1].map((s) => ({ x: wx, y: 0.5, z: s * 1.05, sx: 1, sy: 0.4, sz: 1, rx: Math.PI / 2 })));
  mixer.add(instanced(CYL, wheels, dark));
  mixer.position.set(gateX + 1, 0, maxZ + 9.5);
  mixer.rotation.y = Math.PI / 2 + 0.15;
  group.add(mixer);
  shadows.push({ x: gateX + 1, z: maxZ + 9.5, sx: 3.5, sz: 8.5, ry: 0.15 });
  const vans = [];
  const vanWheels = [];
  [[ox + 8.5, maxZ + 10], [ox + 11.3, maxZ + 10.3]].forEach(([vx, vz], i) => {
    vans.push({ x: vx, y: 1.15, z: vz, sx: 2, sy: 1.7, sz: 5, color: i ? 0xB9BDC0 : 0xE6E4DE });
    vans.push({ x: vx, y: 1.6, z: vz - 2.2, sx: 1.9, sy: 0.7, sz: 0.6, color: 0x222629 });
    for (const [wx, wz] of [[-0.95, -1.6], [0.95, -1.6], [-0.95, 1.6], [0.95, 1.6]]) vanWheels.push({ x: vx + wx, y: 0.35, z: vz + wz, sx: 0.7, sy: 0.25, sz: 0.7, rz: Math.PI / 2 });
    shadows.push({ x: vx, z: vz, sx: 3, sz: 6.2 });
  });
  group.add(boxes(vans, mat(0xFFFFFF, { roughness: 0.5 })), instanced(CYL, vanWheels, dark));

  // ---------- laydown: block pallets, formwork panels, rebar bundles, pipes, sand ----------
  const pallets = [];
  const blocks = [];
  for (let i = 0; i < 8; i++) {
    const px = maxX + 4 + (i % 4) * 1.6;
    const pz = maxZ - 2 - Math.floor(i / 4) * 1.6;
    pallets.push({ x: px, y: 0.07, z: pz, sx: 1.2, sy: 0.14, sz: 1.2 });
    blocks.push({ x: px, y: 0.14 + 0.45, z: pz, sx: 1.1, sy: 0.9 - (i % 3) * 0.2, sz: 1.1 });
  }
  group.add(boxes(pallets, wood), boxes(blocks, mat(0xB3AEA2)));
  shadows.push({ x: maxX + 6.4, z: maxZ - 2.8, sx: 8, sz: 4.5 });
  const formwork = [];
  for (let i = 0; i < 7; i++) formwork.push({ x: maxX + 9.5, y: 0.1 + i * 0.12, z: minZ + 5, sx: 2.6, sy: 0.1, sz: 1.3, color: i % 2 ? 0xC9A35E : 0xB58D49 });
  group.add(boxes(formwork, mat(0xFFFFFF)));
  const rebar = [];
  for (let i = 0; i < 10; i++) rebar.push({ x: maxX + 4.5 + (i % 5) * 0.28, y: 0.2 + Math.floor(i / 5) * 0.22, z: minZ + 1.5, sx: 0.22, sy: 0.2, sz: 8, color: 0x7A5642 });
  group.add(boxes([...rebar, { x: maxX + 5.1, y: 0.06, z: minZ - 1.5, sx: 2, sy: 0.12, sz: 0.3 }, { x: maxX + 5.1, y: 0.06, z: minZ + 4.5, sx: 2, sy: 0.12, sz: 0.3 }], mat(0xFFFFFF)));
  const pipes = [];
  for (let i = 0; i < 6; i++) pipes.push({ x: minX - 6.5 + (i % 3) * 0.55, y: 0.28 + Math.floor(i / 3) * 0.48, z: minZ + 2, sx: 0.5, sy: 6, sz: 0.5, rx: Math.PI / 2 });
  group.add(instanced(CYL, pipes, mat(0x7F8A8E, { roughness: 0.5 })));
  const sand = new THREE.Mesh(CONE, mat(0xA48D69));
  sand.scale.set(2.6, 1.4, 2.6);
  sand.position.set(minX - 7, 0.6, minZ - 4);
  sand.receiveShadow = sand.castShadow = true;
  group.add(sand);
  shadows.push({ x: minX - 6, z: minZ + 2, sx: 4, sz: 7.5 }, { x: maxX + 9.5, z: minZ + 5, sx: 4, sz: 3 });

  // ---------- vegetation: layered deciduous trees, conifers and hedges outside the fence ----------
  const crowns = [];
  const trunks = [];
  const conifers = [];
  const shrubs = [];
  const inPad = (x, z, m) => x > pad.minX - m && x < pad.maxX + m && z > pad.minZ - m && z < pad.maxZ + m;
  const onStreet = (z) => Math.abs(z - roadZ) < 7.5;
  const inBlock = (x, z) => neighbours.some((b) => Math.abs(x - b.x) < b.sx / 2 + 3 && Math.abs(z - b.z) < b.sz / 2 + 3);
  const neighbours = [
    { x: -34, z: pad.minZ - 30, sx: 22, sy: 12, sz: 13, color: 0x6F6E67 },
    { x: -2, z: pad.minZ - 34, sx: 18, sy: 15, sz: 12, color: 0x67665F },
    { x: 32, z: pad.minZ - 30, sx: 24, sy: 12, sz: 14, color: 0x75746C },
    { x: pad.maxX + 26, z: 4, sx: 14, sy: 12, sz: 24, color: 0x7B7A72 },
    { x: pad.minX - 26, z: -4, sx: 13, sy: 9, sz: 20, color: 0x6C6B64 },
  ];
  const tree = (x, z, s) => {
    trunks.push({ x, y: s * 0.9, z, sx: 0.32 * s, sy: s * 1.8, sz: 0.32 * s });
    const hue = random();
    const base = new THREE.Color().setHSL(0.2 + hue * 0.07, 0.22 + random() * 0.12, 0.17 + random() * 0.07);
    for (let k = 0; k < 4; k++) {
      const a = random() * Math.PI * 2;
      const rr = k === 0 ? 0 : s * 0.55;
      const c = base.clone().offsetHSL(0, 0, (random() - 0.4) * 0.06);
      crowns.push({ x: x + Math.cos(a) * rr, y: s * (2.3 + random() * 0.5 + (k === 0 ? 0.4 : 0)), z: z + Math.sin(a) * rr, sx: s * (0.95 + random() * 0.3), sy: s * (0.85 + random() * 0.25), sz: s * (0.95 + random() * 0.3), color: c.getHex() });
    }
    shadows.push({ x: x + 0.6, z: z + 0.4, sx: s * 3.4, sz: s * 3.4 });
  };
  for (let i = 0, placed = 0; placed < 70 && i < 3000; i++) {
    const x = (random() - 0.5) * 190;
    const z = (random() - 0.5) * 170;
    if (inPad(x, z, 4) || onStreet(z) || inBlock(x, z)) continue;
    if (random() < 0.3) {
      const s = 1.2 + random() * 1.3;
      conifers.push({ x, y: s * 1.6, z, sx: s * 1.1, sy: s * 3.2, sz: s * 1.1, color: new THREE.Color().setHSL(0.3 + random() * 0.04, 0.2, 0.13 + random() * 0.04).getHex() });
      conifers.push({ x, y: s * 2.8, z, sx: s * 0.8, sy: s * 2.2, sz: s * 0.8, color: new THREE.Color().setHSL(0.3, 0.2, 0.16).getHex() });
      shadows.push({ x, z, sx: s * 2.6, sz: s * 2.6 });
    } else tree(x, z, 1 + random() * 1.1);
    placed++;
  }
  // Street trees in a regular row on the far pavement.
  for (let x = -90; x < 90; x += 11) tree(x + random() * 2, roadZ + 6.2, 1.15);
  // Hedges and shrubs along the outside of the fence.
  for (let x = pad.minX - 2; x < pad.maxX + 2; x += 1.6) shrubs.push({ x, y: 0.45, z: pad.minZ - 1.4 - random() * 0.6, sx: 1.1 + random() * 0.5, sy: 0.7 + random() * 0.4, sz: 0.9, color: new THREE.Color().setHSL(0.24, 0.25, 0.16 + random() * 0.05).getHex() });
  for (let z = pad.minZ; z < pad.maxZ; z += 1.7) {
    shrubs.push({ x: pad.minX - 1.5, y: 0.45, z, sx: 0.9, sy: 0.7 + random() * 0.4, sz: 1.2, color: new THREE.Color().setHSL(0.23, 0.22, 0.15 + random() * 0.05).getHex() });
    if (random() < 0.6) shrubs.push({ x: pad.maxX + 1.6, y: 0.4, z, sx: 1, sy: 0.6 + random() * 0.3, sz: 1.1, color: new THREE.Color().setHSL(0.25, 0.2, 0.17).getHex() });
  }
  const leaf = mat(0xFFFFFF, { roughness: 1 });
  group.add(instanced(CYL, trunks, mat(0x4A3F33)), instanced(BLOB, crowns, leaf), instanced(CONE, conifers, leaf), instanced(BLOB, shrubs, leaf, { cast: false }));

  // ---------- neighbouring blocks: facades with window grids, a few lit windows, parapets ----------
  const facadeItems = [];
  const windows = [];
  const lit = [];
  const parapets = [];
  neighbours.forEach((b) => {
    facadeItems.push({ x: b.x, y: b.sy / 2, z: b.z, sx: b.sx, sy: b.sy, sz: b.sz, color: b.color });
    parapets.push({ x: b.x, y: b.sy + 0.25, z: b.z, sx: b.sx + 0.3, sy: 0.5, sz: b.sz + 0.3 });
    parapets.push({ x: b.x + b.sx * 0.2, y: b.sy + 0.9, z: b.z, sx: 2.4, sy: 1.3, sz: 1.8 }); // roof plant
    const faces = [
      { n: [0, 1], len: b.sx }, { n: [0, -1], len: b.sx }, { n: [1, 0], len: b.sz }, { n: [-1, 0], len: b.sz },
    ];
    faces.forEach(({ n, len }) => {
      for (let y = 1.6; y < b.sy - 1; y += 3) {
        for (let t = -len / 2 + 1.6; t < len / 2 - 1; t += 2.6) {
          const w = {
            x: b.x + (n[0] ? n[0] * (b.sx / 2 + 0.02) : t), y, z: b.z + (n[1] ? n[1] * (b.sz / 2 + 0.02) : t),
            sx: n[0] ? 0.05 : 1.4, sy: 1.5, sz: n[1] ? 0.05 : 1.4,
          };
          (random() < 0.04 ? lit : windows).push(w);
        }
      }
    });
    shadows.push({ x: b.x, z: b.z, sx: b.sx + 6, sz: b.sz + 6 });
  });
  group.add(boxes(facadeItems, mat(0xFFFFFF, { roughness: 0.95 })), boxes(parapets, mat(0x7C7B74)),
    boxes(windows, mat(0x2B3033, { roughness: 0.3, metalness: 0.2 }), { cast: false }),
    boxes(lit, mat(0x8A7A5C, { emissive: 0xE8B878, emissiveIntensity: 0.35 }), { cast: false }));

  // ---------- baked soft contact shadows (under the building too) ----------
  shadows.push({ x: (minX + maxX) / 2, z: (minZ + maxZ) / 2, sx: maxX - minX + 7, sz: maxZ - minZ + 7 });
  const blobs = instanced(new THREE.PlaneGeometry(1, 1), shadows.map((s) => ({ x: s.x, y: -0.02, z: s.z, sx: s.sx, sy: s.sz, sz: 1, rx: -Math.PI / 2, rz: s.ry || 0 })), contact, { cast: false, receive: false });
  blobs.renderOrder = -1;
  group.add(blobs);

  group.traverse((object) => { object.userData.decorative = true; });
  const focus = new THREE.Box3(V(minX - 4, 0, minZ - 8), V(maxX + 4, height + 2, maxZ + 6));
  focus.expandByPoint(V(maxX + 5.5, height + 17 + 6, minZ - 5.5));
  return { group, tall, slew: towerCrane.slew, focus };
}
