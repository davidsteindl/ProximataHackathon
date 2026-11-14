// Decorative site context for the 3D view: ground, street, fence and hoarding, scaffold, tower crane,
// site office, vehicles, material stacks, vegetation and neighbouring blocks. NONE of this comes from plan
// data; the UI labels it as decorative and every object carries userData.decorative. Repeated parts are
// instanced, textures are generated on a canvas (no assets, no extra dependencies).
import * as THREE from "three";
import { mergeVertices } from "three/addons/utils/BufferGeometryUtils.js";

const mat = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.9, metalness: 0, ...extra });

function rng(seed) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) - 1) / 2147483646;
}

const BOX = new THREE.BoxGeometry(1, 1, 1);
const CYL = new THREE.CylinderGeometry(0.5, 0.5, 1, 12);
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

/** Tileable fractal value noise in [0, 1] (smoothstep-interpolated lattice octaves, wrapping at the edges). */
function fbm(size, seed, octaves = 5, base = 4) {
  const random = rng(seed);
  const out = new Float32Array(size * size);
  let amp = 1;
  let total = 0;
  for (let o = 0; o < octaves; o++) {
    const n = base << o;
    const lattice = Float32Array.from({ length: n * n }, random);
    const step = n / size;
    for (let y = 0; y < size; y++) {
      const fy = y * step;
      const y0 = Math.floor(fy);
      const ty = fy - y0;
      const sy = ty * ty * (3 - 2 * ty);
      const y1 = (y0 + 1) % n;
      for (let x = 0; x < size; x++) {
        const fx = x * step;
        const x0 = Math.floor(fx);
        const tx = fx - x0;
        const sx = tx * tx * (3 - 2 * tx);
        const x1 = (x0 + 1) % n;
        const top = lattice[y0 * n + x0] + (lattice[y0 * n + x1] - lattice[y0 * n + x0]) * sx;
        const bottom = lattice[y1 * n + x0] + (lattice[y1 * n + x1] - lattice[y1 * n + x0]) * sx;
        out[y * size + x] += amp * (top + (bottom - top) * sy);
      }
    }
    total += amp;
    amp *= 0.5;
  }
  for (let i = 0; i < out.length; i++) out[i] /= total;
  return out;
}

/**
 * Tileable surface texture: base colour, low-frequency staining (fbm), fine grain, then `paint` marks (joints,
 * tracks). The red channel doubles as a bump map, so stains and joints also shade under the low sun.
 */
export function surfaceTexture({ size = 256, color, stain = 18, grain = 8, seed = 1, octaves = 5, base = 4, repeat = 1, paint }) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  const random = rng(seed + 101);
  const noise = fbm(size, seed, octaves, base);
  const [r, g, b] = color;
  const img = ctx.createImageData(size, size);
  for (let i = 0; i < size * size; i++) {
    const n = (noise[i] - 0.5) * 2 * stain + (random() - 0.5) * grain;
    img.data[i * 4] = r + n;
    img.data[i * 4 + 1] = g + n;
    img.data[i * 4 + 2] = b + n * 0.92;
    img.data[i * 4 + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  paint?.(ctx, size, random);
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(repeat, repeat);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}

/**
 * Samples a material's map/bumpMap in world space (metres / `tile`), picking the projection plane from the
 * world normal. Shared unit boxes are scaled per wall, so their own UVs would stretch the texture; this keeps
 * the material's detail at true scale on every wall, slab and facade (instanced meshes included).
 */
export function worldUV(material, tile) {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uWorldTile = { value: 1 / tile };
    shader.vertexShader = `varying vec3 vWPos;
varying vec3 vWNrm;
${shader.vertexShader.replace("#include <worldpos_vertex>", `#include <worldpos_vertex>
      mat4 wMat = modelMatrix;
      #ifdef USE_INSTANCING
        wMat = modelMatrix * instanceMatrix;
      #endif
      vWPos = (wMat * vec4(transformed, 1.0)).xyz;
      vWNrm = normalize(mat3(wMat) * objectNormal);`)}`;
    shader.fragmentShader = `uniform float uWorldTile;
varying vec3 vWPos;
varying vec3 vWNrm;
vec2 wUv() { vec3 n = abs(vWNrm); return (n.y > n.x && n.y > n.z ? vWPos.xz : n.x > n.z ? vWPos.zy : vWPos.xy) * uWorldTile; }
${shader.fragmentShader.replace(/(?<!vec2 )vMapUv/g, "wUv()").replace(/(?<!vec2 )vBumpMapUv/g, "wUv()")}`;
  };
  material.customProgramCacheKey = () => `world-uv-${tile}`;
  return material;
}

/** Cast-in-place concrete, 3.6 m tile: staining, grain, faint formwork panel joints and tie holes. */
export function concreteTexture(seed = 21, color = [150, 147, 139]) {
  return surfaceTexture({
    size: 512, color, stain: 14, grain: 10, seed, octaves: 6, base: 3,
    paint(ctx, size, r) {
      const m = size / 3.6; // px per metre
      ctx.strokeStyle = "rgba(40,38,34,0.16)";
      ctx.lineWidth = 1.2;
      for (let x = 0; x <= 3.6; x += 1.2) { ctx.beginPath(); ctx.moveTo(x * m, 0); ctx.lineTo(x * m, size); ctx.stroke(); }
      for (const y of [0, 1.8]) { ctx.beginPath(); ctx.moveTo(0, y * m); ctx.lineTo(size, y * m); ctx.stroke(); }
      ctx.fillStyle = "rgba(30,28,25,0.35)";
      for (let x = 0.3; x < 3.6; x += 0.6) for (let y = 0.45; y < 3.6; y += 0.9) { ctx.beginPath(); ctx.arc(x * m, y * m, 1.6, 0, Math.PI * 2); ctx.fill(); }
      // Darker run-off streaks under the joints.
      for (let i = 0; i < 14; i++) {
        const x = r() * size;
        const grad = ctx.createLinearGradient(0, 0, 0, size * 0.5);
        grad.addColorStop(0, "rgba(60,56,50,0.10)");
        grad.addColorStop(1, "rgba(60,56,50,0)");
        ctx.fillStyle = grad;
        ctx.fillRect(x, 0, 2 + r() * 5, size * 0.5);
      }
    },
  });
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
 * Organic foliage clump: a jittered, lobed icosphere with a flattened underside and vertex shading that darkens
 * toward the bottom (baked self-occlusion). Faceted on purpose: the facets catch the low sun like leaf masses.
 */
function crownGeometry(seed) {
  const random = rng(seed);
  let g = new THREE.IcosahedronGeometry(1, 2);
  g.deleteAttribute("normal");
  g.deleteAttribute("uv");
  g = mergeVertices(g);
  const p = g.attributes.position;
  const lobes = Array.from({ length: 6 }, () => new THREE.Vector3(random() - 0.5, random() * 0.8 - 0.2, random() - 0.5).normalize());
  const v = new THREE.Vector3();
  const colors = [];
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i);
    const lobe = Math.max(...lobes.map((l) => l.dot(v)));
    v.multiplyScalar(0.78 + 0.3 * Math.max(0, lobe) ** 2 + (random() - 0.5) * 0.18);
    v.y *= 0.82;
    if (v.y < -0.3) v.y = -0.3 + (v.y + 0.3) * 0.35;
    p.setXYZ(i, v.x, v.y, v.z);
    const shade = 0.42 + 0.58 * THREE.MathUtils.clamp((v.y + 0.45) / 1.2, 0, 1);
    colors.push(shade, shade, shade);
  }
  g.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  g.computeVertexNormals();
  return g;
}

/** Facade tile, 6 m x 6 m (two 3 m storeys, two bays): rendered wall, recessed glazing with a sky sheen, sills. */
function facadeTexture() {
  return surfaceTexture({
    size: 256, color: [206, 203, 195], stain: 8, grain: 6, seed: 31,
    paint(ctx, size) {
      const m = size / 6;
      for (const fy of [0, 3]) {
        ctx.fillStyle = "rgba(60,58,54,0.10)";
        ctx.fillRect(0, (fy + 2.95) * m, size, 0.12 * m); // floor joint
        for (const bx of [0.75, 3.75]) {
          const x = bx * m;
          const y = (fy + 0.6) * m;
          const w = 1.3 * m;
          const h = 1.4 * m;
          const glass = ctx.createLinearGradient(0, y, 0, y + h);
          glass.addColorStop(0, "rgb(128,134,138)");
          glass.addColorStop(1, "rgb(92,98,104)");
          ctx.fillStyle = "rgba(40,38,34,0.35)";
          ctx.fillRect(x - 2, y - 2, w + 4, h + 4); // reveal shadow
          ctx.fillStyle = glass;
          ctx.fillRect(x, y, w, h);
          ctx.fillStyle = "rgba(230,228,220,0.55)";
          ctx.fillRect(x + w / 2 - 1, y, 2, h); // mullion
          ctx.fillRect(x - 4, y + h + 2, w + 8, 3); // sill
        }
      }
    },
  });
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
  // Surroundings: dark charcoal earth with a faint olive cast, so the site and the building lead.
  const earth = worldUV(mat(0xFFFFFF, { map: surfaceTexture({ color: [48, 49, 43], stain: 9, grain: 5, seed: 7, base: 3 }) }), 34);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(700, 700), earth);
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.1;
  ground.receiveShadow = true;
  const tracks = (alpha, count) => (ctx, size, r) => {
    for (let i = 0; i < count; i++) { // paired tyre tracks
      const y = r() * size;
      const bend = (r() - 0.5) * size * 0.4;
      for (const off of [0, 9 + r() * 4]) {
        ctx.strokeStyle = `rgba(34,31,27,${alpha * (0.6 + r() * 0.5)})`;
        ctx.lineWidth = 2.5 + r() * 2;
        ctx.beginPath();
        ctx.moveTo(0, y + off);
        ctx.bezierCurveTo(size * 0.33, y + off + bend, size * 0.66, y + off - bend, size, y + off);
        ctx.stroke();
      }
    }
  };
  // Compacted site gravel: warm grey, stained, with tyre tracks; its texture also shades as bump.
  const gravelMap = surfaceTexture({ size: 512, color: [94, 90, 82], stain: 15, grain: 16, seed: 3, base: 3, paint: tracks(0.16, 7) });
  const gravel = new THREE.Mesh(new THREE.PlaneGeometry(pad.maxX - pad.minX, pad.maxZ - pad.minZ), worldUV(mat(0xFFFFFF, { map: gravelMap, bumpMap: gravelMap, bumpScale: 1.2, roughness: 0.97 }), 16));
  gravel.rotation.x = -Math.PI / 2;
  gravel.position.set((pad.minX + pad.maxX) / 2, -0.05, (pad.minZ + pad.maxZ) / 2); // below the F1 slab top
  gravel.receiveShadow = true;

  // Street in front (south), with kerbs, pavement and lane marks; haul road from the gate to the building.
  const roadZ = pad.maxZ + 8;
  const asphalt = surfaceTexture({ color: [52, 53, 51], stain: 6, grain: 12, seed: 11 });
  const road = new THREE.Mesh(new THREE.PlaneGeometry(700, 8), worldUV(mat(0xFFFFFF, { map: asphalt, roughness: 0.9 }), 9));
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
  const haul = surfaceTexture({ color: [108, 102, 90], stain: 12, grain: 14, seed: 5, paint: tracks(0.2, 3) });
  const haulRoad = new THREE.Mesh(new THREE.PlaneGeometry(6, pad.maxZ - maxZ + 1), worldUV(mat(0xFFFFFF, { map: haul, bumpMap: haul, bumpScale: 1 }), 8));
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
  const towerCrane = crane({ x: maxX + 5.5, z: minZ - 5.5, height: height + 17, jib: 31, counter: 10, angle: Math.PI * 0.9 }, craneSteel, dark, concrete);
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

  // ---------- neighbouring blocks: distant, low-contrast, varied massing with a facade texture ----------
  // Stepped and L-shaped massing breaks the repeated-box read; fog and muted tints keep them behind the site.
  const neighbours = [
    { x: -40, z: pad.minZ - 48, sx: 22, sy: 9, sz: 12, color: 0x7E7C76 },
    { x: -44, z: pad.minZ - 48, sx: 9, sy: 3, sz: 7, base: 9, color: 0x75736D },
    { x: -8, z: pad.minZ - 58, sx: 16, sy: 14, sz: 11, color: 0x73726D },
    { x: 26, z: pad.minZ - 50, sx: 24, sy: 9, sz: 11, color: 0x827E76 },
    { x: 34, z: pad.minZ - 39, sx: 8, sy: 9, sz: 12, color: 0x827E76 },
    { x: pad.maxX + 44, z: -6, sx: 12, sy: 11, sz: 26, color: 0x7A7873 },
    { x: pad.minX - 34, z: -6, sx: 11, sy: 6, sz: 18, roof: "pitch", color: 0x8E8980 },
    { x: pad.minX - 34, z: 22, sx: 11, sy: 6, sz: 14, roof: "pitch", color: 0x878279 },
  ];
  const facade = worldUV(mat(0xFFFFFF, { map: facadeTexture(), roughness: 0.92 }), 6);
  const roofMat = mat(0x5E5C56, { roughness: 0.95 });
  group.add(instanced(BOX, neighbours.map((b) => ({ x: b.x, y: (b.base || 0) + b.sy / 2, z: b.z, sx: b.sx, sy: b.sy, sz: b.sz, color: b.color })),
    [facade, facade, roofMat, roofMat, facade, facade]));
  const flatRoofs = neighbours.filter((b) => b.roof !== "pitch");
  const parapets = flatRoofs.map((b) => ({ x: b.x, y: (b.base || 0) + b.sy + 0.2, z: b.z, sx: b.sx + 0.25, sy: 0.4, sz: b.sz + 0.25 }));
  const plant = flatRoofs.filter((b) => b.sx > 12).map((b) => ({ x: b.x + b.sx * 0.22, y: b.sy + 0.75, z: b.z - b.sz * 0.15, sx: 2.6, sy: 1.1, sz: 1.8 }));
  // Pitched roof: a triangular prism along the block's long (z) axis.
  const prism = new THREE.CylinderGeometry(0.5, 0.5, 1, 3);
  prism.rotateX(Math.PI / 2);
  prism.rotateZ(Math.PI / 2);
  const pitched = neighbours.filter((b) => b.roof === "pitch").map((b) => ({ x: b.x, y: b.sy + 1.0, z: b.z, sx: b.sx * 1.15, sy: 2.6, sz: b.sz + 0.6 }));
  group.add(boxes([...parapets, ...plant], mat(0x7D7B75)), instanced(prism, pitched, mat(0x4F4A45, { roughness: 0.85 })));
  neighbours.forEach((b) => shadows.push({ x: b.x, z: b.z, sx: b.sx + 5, sz: b.sz + 5 }));

  // ---------- vegetation: groves of lobed deciduous crowns, conifers, hedges; dark and desaturated ----------
  const crownVariants = [crownGeometry(5), crownGeometry(9), crownGeometry(13)];
  const crowns = crownVariants.map(() => []);
  const trunks = [];
  const conifers = [];
  const shrubs = [];
  const inPad = (x, z, m) => x > pad.minX - m && x < pad.maxX + m && z > pad.minZ - m && z < pad.maxZ + m;
  const onStreet = (z) => Math.abs(z - roadZ) < 7.5;
  const inBlock = (x, z) => neighbours.some((b) => Math.abs(x - b.x) < b.sx / 2 + 3 && Math.abs(z - b.z) < b.sz / 2 + 3);
  const free = (x, z) => !inPad(x, z, 4) && !onStreet(z) && !inBlock(x, z);
  const foliage = (l) => new THREE.Color().setHSL(0.2 + random() * 0.08, 0.16 + random() * 0.12, l).getHex();
  const tree = (x, z, s) => {
    trunks.push({ x, y: s * 0.9, z, sx: 0.26 * s, sy: s * 1.8, sz: 0.26 * s });
    const light = 0.2 + random() * 0.07;
    const clumps = 3 + Math.floor(random() * 3);
    for (let k = 0; k < clumps; k++) {
      const a = random() * Math.PI * 2;
      const rr = k === 0 ? 0 : s * (0.45 + random() * 0.35);
      const size = s * (k === 0 ? 1.15 : 0.7 + random() * 0.35);
      crowns[Math.floor(random() * crowns.length)].push({
        x: x + Math.cos(a) * rr, y: s * (2.4 + random() * 0.6) + (k === 0 ? s * 0.35 : 0), z: z + Math.sin(a) * rr,
        sx: size, sy: size * (0.85 + random() * 0.3), sz: size, ry: random() * 6.3, color: foliage(light + (random() - 0.5) * 0.04),
      });
    }
    shadows.push({ x: x + 0.8, z: z + 0.5, sx: s * 3.6, sz: s * 3.6 });
  };
  const conifer = (x, z, s) => {
    for (let k = 0; k < 3; k++) conifers.push({ x, y: s * (1.2 + k * 1.05), z, sx: s * (1.15 - k * 0.3), sy: s * 2, sz: s * (1.15 - k * 0.3), ry: random() * 3, color: foliage(0.11 + random() * 0.03) });
    shadows.push({ x, z, sx: s * 2.6, sz: s * 2.6 });
  };
  // Groves: tight clusters read as tree lines and canopy masses, not scattered balls.
  for (let g = 0, groves = 0; groves < 16 && g < 500; g++) {
    const gx = (random() - 0.5) * 200;
    const gz = (random() - 0.5) * 180;
    if (!free(gx, gz)) continue;
    groves++;
    const n = 3 + Math.floor(random() * 6);
    const pine = random() < 0.3;
    for (let i = 0; i < n; i++) {
      const x = gx + (random() - 0.5) * 12;
      const z = gz + (random() - 0.5) * 10;
      if (!free(x, z)) continue;
      if (pine) conifer(x, z, 1.1 + random() * 1.1); else tree(x, z, 1.1 + random() * 1.2);
    }
  }
  // Street trees in a loose row on the far pavement.
  for (let x = -90; x < 90; x += 10 + random() * 4) tree(x + random() * 2, roadZ + 6.2, 1 + random() * 0.4);
  // Hedges along the outside of the fence.
  const hedge = (x, z, sx, sz) => shrubs.push({ x, y: 0.4, z, sx, sy: 0.55 + random() * 0.3, sz, ry: random() * 6.3, color: foliage(0.14 + random() * 0.04) });
  for (let x = pad.minX - 2; x < pad.maxX + 2; x += 1.4) hedge(x, pad.minZ - 1.5 - random() * 0.5, 1 + random() * 0.4, 0.8);
  for (let z = pad.minZ; z < pad.maxZ; z += 1.5) {
    hedge(pad.minX - 1.5, z, 0.8, 1 + random() * 0.4);
    if (random() < 0.6) hedge(pad.maxX + 1.6, z, 0.9, 1);
  }
  const leaf = mat(0xFFFFFF, { roughness: 0.95, vertexColors: true, flatShading: true });
  const needles = mat(0xFFFFFF, { roughness: 1, flatShading: true });
  group.add(instanced(CYL, trunks, mat(0x3E352C)), instanced(CONE, conifers, needles), instanced(crownVariants[0], shrubs, leaf, { cast: false }));
  crownVariants.forEach((geometry, i) => group.add(instanced(geometry, crowns[i], leaf)));

  // ---------- baked soft contact shadows (under the building too) ----------
  shadows.push({ x: (minX + maxX) / 2, z: (minZ + maxZ) / 2, sx: maxX - minX + 7, sz: maxZ - minZ + 7 });
  const blobs = instanced(new THREE.PlaneGeometry(1, 1), shadows.map((s) => ({ x: s.x, y: -0.02, z: s.z, sx: s.sx, sy: s.sz, sz: 1, rx: -Math.PI / 2, rz: s.ry || 0 })), contact, { cast: false, receive: false });
  blobs.renderOrder = -1;
  group.add(blobs);

  group.traverse((object) => { object.userData.decorative = true; });
  const focus = new THREE.Box3(V(minX - 4, 0, minZ - 8), V(maxX + 4, height + 2, maxZ + 6));
  focus.expandByPoint(V(maxX + 5.5, height + 17 + 6, minZ - 5.5));
  // Jib tip at its initial slew angle, so the overview opens on the complete crane.
  const slewAngle = Math.PI * 0.9;
  focus.expandByPoint(V(maxX + 5.5 + Math.cos(slewAngle) * 31, height + 18, minZ - 5.5 - Math.sin(slewAngle) * 31));
  return { group, tall, slew: towerCrane.slew, focus };
}
