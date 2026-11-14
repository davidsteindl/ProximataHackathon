// Decorative site context for the 3D view: ground, fence, scaffold, tower cranes, containers,
// material stacks, trees and neighbouring blocks. NONE of this comes from plan data; the UI labels it
// as decorative and every object carries userData.decorative. Repeated parts are instanced.
import * as THREE from "three";

const mat = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.92, metalness: 0, flatShading: true, ...extra });

function rng(seed) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) - 1) / 2147483646;
}

/** Instanced boxes from {x,y,z,sx,sy,sz,ry} descriptors. */
function boxes(items, material, { cast = true, receive = true } = {}) {
  const mesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), material, items.length);
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  items.forEach((b, i) => {
    q.setFromEuler(new THREE.Euler(b.rx || 0, b.ry || 0, b.rz || 0));
    m.compose(new THREE.Vector3(b.x, b.y, b.z), q, new THREE.Vector3(b.sx, b.sy, b.sz));
    mesh.setMatrixAt(i, m);
  });
  mesh.castShadow = cast;
  mesh.receiveShadow = receive;
  return mesh;
}

/** A thin box spanning two points (scaffold tubes, crane lattice). */
function bar(a, b, t) {
  const d = new THREE.Vector3().subVectors(b, a);
  const len = d.length();
  const mid = new THREE.Vector3().addVectors(a, b).multiplyScalar(0.5);
  const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
  const e = new THREE.Euler().setFromQuaternion(q);
  return { x: mid.x, y: mid.y, z: mid.z, sx: t, sy: len, sz: t, rx: e.x, ry: e.y, rz: e.z };
}

function crane({ x, z, height, jib, counter, angle }, steel, dark) {
  const g = new THREE.Group();
  const w = 1.6;
  const parts = [];
  const lattice = [];
  const corners = [[-w / 2, -w / 2], [w / 2, -w / 2], [w / 2, w / 2], [-w / 2, w / 2]];
  corners.forEach(([cx, cz]) => parts.push(bar(new THREE.Vector3(cx, 0, cz), new THREE.Vector3(cx, height, cz), 0.14)));
  for (let y = 0; y < height; y += 2) {
    for (let i = 0; i < 4; i++) {
      const [ax, az] = corners[i];
      const [bx, bz] = corners[(i + 1) % 4];
      lattice.push(bar(new THREE.Vector3(ax, y, az), new THREE.Vector3(bx, y + 2, bz), 0.05));
      lattice.push(bar(new THREE.Vector3(ax, y, az), new THREE.Vector3(bx, y, bz), 0.06));
    }
  }
  // Jib and counter-jib: triangular lattice along +X, rotated by `angle`.
  const top = height;
  const jibParts = [];
  const chord = (x0, x1, y, z0) => jibParts.push(bar(new THREE.Vector3(x0, y, z0), new THREE.Vector3(x1, y, z0), 0.12));
  chord(-counter, jib, top, -0.55);
  chord(-counter, jib, top, 0.55);
  chord(0, jib, top + 1.3, 0);
  for (let s = 0; s < jib; s += 1.5) {
    jibParts.push(bar(new THREE.Vector3(s, top, -0.55), new THREE.Vector3(s + 0.75, top + 1.3, 0), 0.05));
    jibParts.push(bar(new THREE.Vector3(s + 0.75, top + 1.3, 0), new THREE.Vector3(s + 1.5, top, 0.55), 0.05));
    jibParts.push(bar(new THREE.Vector3(s, top, -0.55), new THREE.Vector3(s, top, 0.55), 0.05));
  }
  for (let s = -counter; s < 0; s += 1.5) jibParts.push(bar(new THREE.Vector3(s, top, -0.55), new THREE.Vector3(s, top, 0.55), 0.06));
  // Apex and tie bars.
  jibParts.push(bar(new THREE.Vector3(-0.6, top, 0), new THREE.Vector3(0, top + 5, 0), 0.14));
  jibParts.push(bar(new THREE.Vector3(0.6, top, 0), new THREE.Vector3(0, top + 5, 0), 0.14));
  jibParts.push(bar(new THREE.Vector3(0, top + 5, 0), new THREE.Vector3(jib * 0.66, top + 1.3, 0), 0.04));
  jibParts.push(bar(new THREE.Vector3(0, top + 5, 0), new THREE.Vector3(-counter, top + 0.3, 0), 0.04));
  const head = new THREE.Group();
  head.add(boxes(jibParts, steel));
  head.add(boxes([
    { x: -counter + 1.6, y: top - 0.6, z: 0, sx: 2.6, sy: 1.6, sz: 1.6 }, // counterweight
    { x: 1.4, y: top - 0.9, z: 1.1, sx: 1.6, sy: 1.6, sz: 1.2 }, // cab
  ], dark));
  const trolley = jib * 0.55;
  const hookDrop = top - 9;
  head.add(boxes([
    { x: trolley, y: top - 0.15, z: 0, sx: 1, sy: 0.3, sz: 1.2 },
    bar(new THREE.Vector3(trolley, top - 0.2, -0.1), new THREE.Vector3(trolley, hookDrop, -0.1), 0.03),
    bar(new THREE.Vector3(trolley, top - 0.2, 0.1), new THREE.Vector3(trolley, hookDrop, 0.1), 0.03),
    { x: trolley, y: hookDrop - 0.3, z: 0, sx: 0.5, sy: 0.6, sz: 0.4 },
  ], dark));
  head.rotation.y = angle;
  g.add(boxes(parts, steel), boxes(lattice, steel, { receive: false }), head);
  g.add(boxes([{ x: 0, y: 0.4, z: 0, sx: 4.5, sy: 0.8, sz: 4.5 }], dark));
  g.position.set(x, 0, z);
  return g;
}

/**
 * @param bounds world-space building bounds {minX,maxX,minZ,maxZ,height}
 * @returns {{ group: THREE.Group, tall: THREE.Group }} `tall` is hidden in top-down mode.
 */
export function buildSiteContext(bounds) {
  const group = new THREE.Group();
  const tall = new THREE.Group();
  group.userData.decorative = true;
  tall.userData.decorative = true;
  group.add(tall);
  const random = rng(42);
  const { minX, maxX, minZ, maxZ, height } = bounds;
  // Scenery stays desaturated and darker than the building so plan geometry and status colours lead.
  const steel = mat(0x9E998B);
  const craneSteel = mat(0xC9B98F);
  const dark = mat(0x45473F);
  const wood = mat(0x8F7A5A);

  // Ground, gravel site pad, road with lane marks.
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(600, 600), mat(0x23261F, { flatShading: false }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.08;
  ground.receiveShadow = true;
  const pad = { minX: minX - 14, maxX: maxX + 16, minZ: minZ - 12, maxZ: maxZ + 13 };
  const gravel = new THREE.Mesh(new THREE.PlaneGeometry(pad.maxX - pad.minX, pad.maxZ - pad.minZ), mat(0x4A463C, { flatShading: false }));
  gravel.rotation.x = -Math.PI / 2;
  gravel.position.set((pad.minX + pad.maxX) / 2, -0.04, (pad.minZ + pad.maxZ) / 2); // below the F1 slab top: no z-fighting
  gravel.receiveShadow = true;
  const roadZ = pad.maxZ + 6;
  const road = new THREE.Mesh(new THREE.PlaneGeometry(600, 9), mat(0x24261F, { flatShading: false }));
  road.rotation.x = -Math.PI / 2;
  road.position.set(0, 0.01, roadZ);
  road.receiveShadow = true;
  const lanes = [];
  for (let x = -150; x < 150; x += 6) lanes.push({ x, y: 0.02, z: roadZ, sx: 3, sy: 0.01, sz: 0.15 });
  group.add(ground, gravel, road, boxes(lanes, mat(0x77756A), { cast: false }));

  // Site fence with a gate gap facing the road.
  const posts = [];
  const panels = [];
  const gateX = (pad.minX + pad.maxX) / 2 + 6;
  const edge = (ax, az, bx, bz) => {
    const len = Math.hypot(bx - ax, bz - az);
    const n = Math.ceil(len / 3.5);
    for (let i = 0; i < n; i++) {
      const t0 = i / n;
      const t1 = (i + 1) / n;
      const x0 = ax + (bx - ax) * t0;
      const z0 = az + (bz - az) * t0;
      const x1 = ax + (bx - ax) * t1;
      const z1 = az + (bz - az) * t1;
      const cx = (x0 + x1) / 2;
      if (az === bz && az === pad.maxZ && Math.abs(cx - gateX) < 5) continue;
      posts.push({ x: x0, y: 1, z: z0, sx: 0.08, sy: 2, sz: 0.08 });
      panels.push({ x: cx, y: 1.05, z: (z0 + z1) / 2, sx: Math.hypot(x1 - x0, z1 - z0), sy: 1.9, sz: 0.03, ry: -Math.atan2(z1 - z0, x1 - x0) });
    }
  };
  edge(pad.minX, pad.minZ, pad.maxX, pad.minZ);
  edge(pad.maxX, pad.minZ, pad.maxX, pad.maxZ);
  edge(pad.maxX, pad.maxZ, pad.minX, pad.maxZ);
  edge(pad.minX, pad.maxZ, pad.minX, pad.minZ);
  group.add(boxes(posts, steel), boxes(panels, mat(0xBDB8A8, { transparent: true, opacity: 0.32, depthWrite: false }), { cast: false }));

  // Scaffold on the north and west facades only: the default camera looks from the south-east,
  // so scaffold never sits between the viewer and the building.
  const tubes = [];
  const planks = [];
  const top = height + 1;
  const runs = [
    { ax: minX - 0.4, az: minZ - 0.4, bx: maxX + 0.4, bz: minZ - 0.4, out: [0, -1] }, // north
    { ax: minX - 0.4, az: minZ - 0.4, bx: minX - 0.4, bz: maxZ + 0.4, out: [-1, 0] }, // west
  ];
  runs.forEach(({ ax, az, bx, bz, out }) => {
    const len = Math.hypot(bx - ax, bz - az);
    const ux = (bx - ax) / len;
    const uz = (bz - az) / len;
    const bays = Math.round(len / 2.4);
    for (const depth of [0.25, 1.05]) {
      const ox = out[0] * depth;
      const oz = out[1] * depth;
      for (let i = 0; i <= bays; i++) {
        const px = ax + ux * (len * i / bays) + ox;
        const pz = az + uz * (len * i / bays) + oz;
        tubes.push(bar(new THREE.Vector3(px, 0, pz), new THREE.Vector3(px, top, pz), 0.045));
      }
      for (let y = 1; y <= top; y += 2) {
        tubes.push(bar(new THREE.Vector3(ax + ox, y, az + oz), new THREE.Vector3(bx + ox, y, bz + oz), 0.035));
      }
    }
    for (let i = 0; i < bays; i += 2) {
      const p0 = new THREE.Vector3(ax + ux * (len * i / bays) + out[0] * 1.05, 0, az + uz * (len * i / bays) + out[1] * 1.05);
      const p1 = new THREE.Vector3(ax + ux * (len * (i + 1) / bays) + out[0] * 1.05, top - 1, az + uz * (len * (i + 1) / bays) + out[1] * 1.05);
      tubes.push(bar(p0, p1, 0.035));
    }
    for (let y = 0; y <= height; y += 3) {
      planks.push({
        x: (ax + bx) / 2 + out[0] * 0.65, y: y + 0.02, z: (az + bz) / 2 + out[1] * 0.65,
        sx: Math.abs(ux) * len + Math.abs(out[0]) * 0.8 + 0.01, sy: 0.05, sz: Math.abs(uz) * len + Math.abs(out[1]) * 0.8 + 0.01,
      });
    }
  });
  tall.add(boxes(tubes, steel, { receive: false }), boxes(planks, wood));

  // One tower crane behind the building, jib swung over the site.
  tall.add(crane({ x: maxX + 6, z: minZ - 6, height: height + 16, jib: 30, counter: 9, angle: Math.PI * 0.84 }, craneSteel, dark));

  // Container site office stack and toilets at the back-left corner, material laydown on the east side.
  const ox = minX - 12;
  const oz = minZ + 7;
  const containers = [];
  const trims = [];
  for (let i = 0; i < 3; i++) containers.push({ x: ox + 3.1, y: 1.3, z: oz - i * 2.6, sx: 6, sy: 2.55, sz: 2.4 });
  for (let i = 0; i < 2; i++) containers.push({ x: ox + 3.1, y: 3.88, z: oz - i * 2.6, sx: 6, sy: 2.55, sz: 2.4 });
  containers.forEach((c) => {
    trims.push({ x: c.x - 1.2, y: c.y + 0.25, z: c.z, sx: 2.2, sy: 0.9, sz: 2.44 });
    trims.push({ x: c.x + 2.1, y: c.y - 0.15, z: c.z, sx: 0.9, sy: 2, sz: 2.44 });
  });
  group.add(boxes(containers, mat(0x8A8574)), boxes(trims, dark, { cast: false }));
  group.add(boxes([
    { x: ox + 8, y: 1.2, z: oz + 1, sx: 1.2, sy: 2.4, sz: 1.2 },
    { x: ox + 9.4, y: 1.2, z: oz + 1, sx: 1.2, sy: 2.4, sz: 1.2 },
  ], mat(0x6F7A68)));
  const stacks = [];
  for (let i = 0; i < 4; i++) stacks.push({ x: maxX + 3 + i * 1.6, y: 0.45, z: (minZ + maxZ) / 2 + 2, sx: 1.25, sy: 0.9, sz: 2.6 });
  for (let i = 0; i < 6; i++) stacks.push({ x: minX - 6 - (i % 2) * 1.5, y: 0.2 + Math.floor(i / 2) * 0.25, z: minZ + 4 + i * 0.1, sx: 1.2, sy: 0.2, sz: 1.2 });
  group.add(boxes(stacks, mat(0x9C978A)));
  const rebar = [];
  for (let i = 0; i < 8; i++) rebar.push({ x: maxX + 4 + (i % 4) * 0.3, y: 0.15 + Math.floor(i / 4) * 0.2, z: minZ + 3, sx: 0.18, sy: 0.18, sz: 9 });
  group.add(boxes(rebar, mat(0x7A5642)));

  // Trees outside the fence (instanced, varied scale and tint).
  const count = 64;
  const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.12, 0.18, 1, 5), mat(0x4B4237), count);
  const crown = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1, 2), mat(0xFFFFFF, { flatShading: false }), count);
  const m = new THREE.Matrix4();
  const color = new THREE.Color();
  for (let i = 0, placed = 0; placed < count && i < 2000; i++) {
    const x = (random() - 0.5) * 170;
    const z = (random() - 0.5) * 150;
    const inPad = x > pad.minX - 4 && x < pad.maxX + 4 && z > pad.minZ - 4 && z < pad.maxZ + 4;
    const onRoad = Math.abs(z - roadZ) < 7;
    const inBlock = z < pad.minZ - 16 && Math.abs(x) < 50 && z > pad.minZ - 36;
    if (inPad || onRoad || inBlock) continue;
    const s = 1.1 + random() * 1.2;
    m.makeScale(1, s * 1.4, 1).setPosition(x, s * 0.7, z);
    trunk.setMatrixAt(placed, m);
    m.makeScale(s * 1.15, s * 1.35, s * 1.15).setPosition(x, s * 1.4 + s * 1.1, z);
    crown.setMatrixAt(placed, m);
    crown.setColorAt(placed, color.setHSL(0.21 + random() * 0.05, 0.14 + random() * 0.08, 0.12 + random() * 0.05));
    placed++;
  }
  trunk.castShadow = crown.castShadow = true;
  group.add(trunk, crown);

  // Neighbouring blocks across the north side, with window bands.
  const blocks = [
    { x: -32, z: pad.minZ - 26, sx: 22, sy: 9, sz: 14 },
    { x: -4, z: pad.minZ - 24, sx: 16, sy: 12, sz: 12 },
    { x: 24, z: pad.minZ - 27, sx: 26, sy: 7, sz: 15 },
  ];
  const windows = [];
  blocks.forEach((b) => {
    for (let y = 2; y < b.sy - 1; y += 3) {
      windows.push({ x: b.x, y, z: b.z + b.sz / 2 + 0.02, sx: b.sx - 2, sy: 1.1, sz: 0.04 });
      windows.push({ x: b.x - b.sx / 2 - 0.02, y, z: b.z, sx: 0.04, sy: 1.1, sz: b.sz - 2 });
    }
  });
  group.add(boxes(blocks.map((b) => ({ ...b, y: b.sy / 2 })), mat(0x3A3C35)), boxes(windows, mat(0x2A2C26), { cast: false }));

  group.traverse((object) => { object.userData.decorative = true; });
  return { group, tall };
}
