// Imperative Three.js scene for the 3D site view. React owns data and selection; this module owns
// meshes, camera animation and per-frame overlay placement (kept out of React state on purpose).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { leaderClash } from "../../lib/callout-layout.mjs";
import { floorVisible as isFloorVisible, insetEdgeStrips } from "../../lib/site-model.mjs";
import { buildSiteContext, concreteTexture, surfaceTexture, worldUV } from "./site-context";

const C = {
  bg: 0x1D1F1A,
  chalk: 0xEFEBE1,
  shell: 0xDCE3E2,
  slab: 0xC9C2B1,
  line: 0x191813,
  conflict: 0xFF5C49,
  open: 0xE8B04B,
  ok: 0x55B97D,
  selected: 0xFF8A4A,
  pipe: 0x62A8D8,
  fixture: 0xFAF8F2,
  ghost: 0x2FC4BC, // previous revision: teal, distinct from status reds/ambers, selection orange and drain blue
  door: 0xB9A585,
};
const SLAB = 0.25;
const EASE = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

function planBounds(geometry) {
  const pts = geometry.flatMap((plan) => plan.elements.flatMap((e) => (e.shape.outline?.length ? e.shape.outline : e.shape.segments.flat())));
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
}

/** Alpha gradient, opaque at the wall foot (u = 0) fading out: alpha map for the contact-occlusion strips. */
function aoTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 4;
  const ctx = canvas.getContext("2d");
  const grad = ctx.createLinearGradient(0, 0, 64, 0);
  grad.addColorStop(0, "#fff");
  grad.addColorStop(0.35, "#777");
  grad.addColorStop(1, "#000");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 64, 4);
  return new THREE.CanvasTexture(canvas);
}

export function createSiteScene(container, { geometry, zones, changes, onHover, onSelect }) {
  const kindOf = (id) => zones.get(id)?.kind;
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.domElement.setAttribute("aria-hidden", "true");
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  // Graphite sky with a slightly lighter, warmer haze at the horizon; fog fades the far scenery into it.
  const sky = document.createElement("canvas");
  sky.width = 2;
  sky.height = 256;
  const skyCtx = sky.getContext("2d");
  const skyGrad = skyCtx.createLinearGradient(0, 0, 0, 256);
  skyGrad.addColorStop(0, "#161814");
  skyGrad.addColorStop(0.62, "#2A2C26");
  skyGrad.addColorStop(1, "#3A3A33");
  skyCtx.fillStyle = skyGrad;
  skyCtx.fillRect(0, 0, 2, 256);
  scene.background = new THREE.CanvasTexture(sky);
  scene.background.colorSpace = THREE.SRGBColorSpace;
  scene.fog = new THREE.Fog(0x33342D, 110, 260); // near/far follow the camera distance, see loop()
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  pmrem.dispose();
  scene.environmentIntensity = 0.4;
  const camera = new THREE.PerspectiveCamera(32, 1, 0.5, 1200);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.09;
  controls.maxPolarAngle = Math.PI * 0.47;
  controls.minDistance = 4;
  controls.maxDistance = 520; // the narrow-FOV overhead plan view sits far away
  controls.screenSpacePanning = true;

  const pb = planBounds(geometry);
  const cx = (pb.minX + pb.maxX) / 2;
  const cy = (pb.minY + pb.maxY) / 2;
  const P = (x, y, h = 0) => new THREE.Vector3(x - cx, h, -(y - cy));
  const floors = [...geometry].sort((a, b) => a.floor_elevation_m - b.floor_elevation_m);
  const topElevation = floors.length ? Math.max(...floors.map((f) => f.floor_elevation_m + f.floor_height_m)) : 3;

  // Lights.
  // Low warm key from the south-west for long shadows, cool sky fill.
  scene.add(new THREE.HemisphereLight(0xDCE4EA, 0x26231D, 0.8));
  const sun = new THREE.DirectionalLight(0xFFE0BC, 3.2);
  sun.position.set(-50, 36, 34);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -62, right: 62, top: 62, bottom: -62, near: 1, far: 190 });
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.03;
  sun.shadow.radius = 4;
  scene.add(sun, new THREE.DirectionalLight(0xB8C6D4, 0.45).translateX(30).translateY(20).translateZ(-30));

  // Shared materials.
  const std = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0, ...extra });
  // Surface detail only (staining, grain, formwork joints, plaster texture): material dressing, not plan data.
  const concrete = concreteTexture(21);
  const slabTex = concreteTexture(44, [138, 135, 128]);
  const plaster = surfaceTexture({ size: 256, color: [236, 232, 222], stain: 6, grain: 5, seed: 17 });
  const M = {
    wall: worldUV(std(0xFFFFFF, { map: plaster, bumpMap: plaster, bumpScale: 0.6, roughness: 0.9 }), 2.5),
    shell: worldUV(std(0xFFFFFF, { map: concrete, bumpMap: concrete, bumpScale: 1.4, roughness: 0.88 }), 3.6),
    slab: worldUV(std(0xB4B0A8, { map: slabTex, bumpMap: slabTex, bumpScale: 1.2, roughness: 0.92 }), 3.6),
    // Contact occlusion strips along wall feet: a baked gradient decal, no post-processing pass.
    ao: new THREE.MeshBasicMaterial({ color: 0x000000, alphaMap: aoTexture(), transparent: true, opacity: 0.42, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -1 }),
    conflict: std(C.conflict, { emissive: C.conflict, emissiveIntensity: 0.9, roughness: 0.6 }),
    // Flag markers: drawn on top so the flagged element is never hidden behind slabs or scenery.
    xray: new THREE.MeshBasicMaterial({ color: C.conflict, transparent: true, opacity: 0.85, depthTest: false, depthWrite: false }),
    halo: new THREE.MeshBasicMaterial({ color: C.conflict, transparent: true, opacity: 0.5, depthWrite: false }),
    volume: new THREE.MeshBasicMaterial({ color: C.conflict, transparent: true, opacity: 0.22, depthTest: false, depthWrite: false, side: THREE.DoubleSide }),
    volumeBar: new THREE.MeshBasicMaterial({ color: C.conflict, transparent: true, opacity: 0.7 }),
    selectedWall: std(C.selected, { emissive: C.selected, emissiveIntensity: 0.3 }),
    keyline: new THREE.MeshBasicMaterial({ color: 0x141410, depthTest: false, depthWrite: false }),
    frame: new THREE.MeshBasicMaterial({ color: C.selected, depthTest: false, depthWrite: false }),
    door: std(C.door, { roughness: 0.7 }),
    lintel: std(C.chalk),
    swing: new THREE.LineBasicMaterial({ color: 0x6F6A5E, transparent: true, opacity: 0.7 }),
    fixture: std(C.fixture, { roughness: 0.4 }),
    pipe: std(C.pipe, { roughness: 0.5, emissive: C.pipe, emissiveIntensity: 0.15 }),
    threshold: std(0x8E897C),
    ghost: new THREE.MeshBasicMaterial({ color: C.ghost, transparent: true, opacity: 0.34, depthWrite: false }),
    ghostLine: new THREE.LineDashedMaterial({ color: C.ghost, dashSize: 0.22, gapSize: 0.14 }),
    edges: new THREE.LineBasicMaterial({ color: C.line, transparent: true, opacity: 0.16 }),
    // Previous-revision overlay drawn above status fills, so the old position reads even over a red wall.
    ghostTop: new THREE.MeshBasicMaterial({ color: C.ghost, transparent: true, opacity: 0.55, depthTest: false, depthWrite: false }),
    ghostDash: new THREE.MeshBasicMaterial({ color: 0x0E6E69, depthTest: false, depthWrite: false }),
    volumeIso: new THREE.MeshBasicMaterial({ color: C.conflict, transparent: true, opacity: 0.16, depthWrite: false, side: THREE.DoubleSide }),
    unitLine: new THREE.LineBasicMaterial({ color: 0x5F5B52, transparent: true, opacity: 0.75 }),
    highlight: new THREE.MeshBasicMaterial({ color: C.selected, polygonOffset: true, polygonOffsetFactor: -2 }),
    hit: new THREE.MeshBasicMaterial({ visible: false, side: THREE.DoubleSide }), // raycast-only surfaces
  };

  const building = new THREE.Group();
  scene.add(building);
  const floorGroups = new Map();
  const roomPlates = []; // { mesh, zoneId, unitId, floorId }
  const zoneWalls = []; // { mesh, zoneId, key }
  const shellWalls = [];
  const pickables = [];
  const anchors = new Map(); // zoneId / element key -> Vector3
  const outlines = new Map(); // zoneId -> { floorId, points: [[x,y]...] }
  const changedKeys = new Set(changes.map((c) => `${c.floorId}:${c.element.element_id}`));

  const edgePositions = [];
  const pushEdges = (geom, matrix) => {
    const edges = new THREE.EdgesGeometry(geom);
    const pos = edges.attributes.position;
    const v = new THREE.Vector3();
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i).applyMatrix4(matrix);
      edgePositions.push(v.x, v.y, v.z);
    }
    edges.dispose();
  };

  const boxGeom = new THREE.BoxGeometry(1, 1, 1);
  const wallBox = ([a, b], thickness, base, height) => {
    const pa = P(a[0], a[1]);
    const pbb = P(b[0], b[1]);
    const len = pa.distanceTo(pbb);
    const mesh = new THREE.Mesh(boxGeom, M.wall);
    mesh.scale.set(len + thickness, height, thickness);
    mesh.position.set((pa.x + pbb.x) / 2, base + height / 2, (pa.z + pbb.z) / 2);
    mesh.rotation.y = -Math.atan2(pbb.z - pa.z, pbb.x - pa.x);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.updateMatrix();
    return mesh;
  };

  const fixtureSize = { WC: [0.4, 0.42, 0.62], SINK: [0.55, 0.85, 0.42], SHOWER: [0.9, 0.06, 0.9] };

  const aoGeom = new THREE.PlaneGeometry(1, 1);
  aoGeom.rotateX(-Math.PI / 2);
  const AO_WIDTH = 0.55;
  let aoStrips = [];
  for (const plan of floors) {
    aoStrips = [];
    const group = new THREE.Group();
    const elev = plan.floor_elevation_m;
    const wallHeight = plan.floor_height_m - SLAB;
    group.userData = { floorId: plan.floor_id, elevation: elev, wallHeight };
    edgePositions.length = 0;

    // Slab (from the plan's extent) with the floor top at the floor elevation.
    const slab = new THREE.Mesh(boxGeom, M.slab);
    slab.scale.set(pb.maxX - pb.minX + 0.8, SLAB, pb.maxY - pb.minY + 0.8); // schematic slab edge, 0.4 m past the plan
    slab.position.set(0, elev - SLAB / 2, 0);
    slab.castShadow = slab.receiveShadow = true;
    slab.userData.zoneId = plan.floor_id;
    slab.updateMatrix();
    pushEdges(slab.geometry, slab.matrix);
    group.add(slab);
    pickables.push(slab);

    for (const element of plan.elements) {
      const { shape } = element;
      const zoneId = element.zone_ids.find((id) => kindOf(id) === "element") || null;
      const key = `${plan.floor_id}:${element.element_id}`;
      if (element.kind === "wall") {
        const exterior = (shape.thickness_m || 0) >= 0.3;
        for (const segment of shape.segments) {
          const mesh = wallBox(segment, shape.thickness_m || 0.1, elev, wallHeight);
          if (exterior) {
            mesh.material = M.shell;
            shellWalls.push(mesh);
          } else {
            pickables.push(mesh);
          }
          if (zoneId) {
            mesh.userData.zoneId = zoneId;
            zoneWalls.push({ mesh, zoneId, key, base: mesh.material, floorId: plan.floor_id, segment, thickness: shape.thickness_m || 0.1 });
          }
          pushEdges(mesh.geometry, mesh.matrix);
          group.add(mesh);
          const t = (shape.thickness_m || 0.1) / 2;
          for (const side of [-1, 1]) aoStrips.push({ mesh, side, t, elev });
        }
        const [a, b] = shape.segments[0];
        anchors.set(key, P((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, elev + wallHeight + 0.1));
      } else if (element.kind === "room" || element.kind === "unit") {
        const pts = shape.outline;
        outlines.set(element.element_id, { floorId: plan.floor_id, points: pts });
        const centroid = pts.reduce((acc, p) => [acc[0] + p[0] / pts.length, acc[1] + p[1] / pts.length], [0, 0]);
        anchors.set(element.element_id, P(centroid[0], centroid[1], elev + 0.2));
        if (element.kind === "room") {
          const s = new THREE.Shape(pts.map(([x, y]) => new THREE.Vector2(x - cx, y - cy)));
          const g = new THREE.ShapeGeometry(s);
          g.rotateX(-Math.PI / 2);
          const material = new THREE.MeshBasicMaterial({ color: C.open, transparent: true, opacity: 0, depthWrite: false });
          const plate = new THREE.Mesh(g, material);
          plate.position.y = elev + 0.015;
          plate.renderOrder = 1;
          plate.userData.zoneId = element.element_id;
          const unitId = element.zone_ids.find((id) => kindOf(id) === "unit") || null;
          roomPlates.push({ mesh: plate, zoneId: element.element_id, unitId, floorId: plan.floor_id });
          pickables.push(plate);
          group.add(plate);
        } else {
          const line = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts.map(([x, y]) => P(x, y, elev + 0.03))), M.unitLine);
          // Rooms tile the unit, so the unit gets invisible hit strips 0.45 m inside its outline (above the room
          // plates): clicks along a unit's edge select the unit, clicks inside a room still select the room.
          const quads = insetEdgeStrips(pts, 0.45);
          const g = new THREE.BufferGeometry().setFromPoints(quads.flatMap(([a, b, c, d]) => [a, b, c, a, c, d].map(([x, y]) => P(x, y, elev + 0.03))));
          const hit = new THREE.Mesh(g, M.hit);
          hit.userData.zoneId = element.element_id;
          pickables.push(hit);
          group.add(line, hit);
        }
      } else if (element.kind === "door") {
        // The opening and hinge point come from the DXF door block. Leaf angle, swing side, swing arc and the
        // 2.1 m lintel are schematic dressing (disclosed in the Key), not plan data.
        for (const [a, b] of shape.segments) {
          const pa = P(a[0], a[1]);
          const pbb = P(b[0], b[1]);
          const width = pa.distanceTo(pbb);
          const along = Math.atan2(pbb.z - pa.z, pbb.x - pa.x);
          const mesh = new THREE.Mesh(boxGeom, M.threshold);
          mesh.scale.set(width, 0.03, 0.16);
          mesh.position.set((pa.x + pbb.x) / 2, elev + 0.015, (pa.z + pbb.z) / 2);
          mesh.rotation.y = -along;
          const lintel = new THREE.Mesh(boxGeom, M.lintel);
          lintel.scale.set(width, wallHeight - 2.1, 0.1);
          lintel.position.set(mesh.position.x, elev + 2.1 + (wallHeight - 2.1) / 2, mesh.position.z);
          lintel.rotation.y = -along;
          lintel.castShadow = lintel.receiveShadow = true;
          lintel.updateMatrix();
          pushEdges(lintel.geometry, lintel.matrix);
          const open = along - THREE.MathUtils.degToRad(70);
          const leaf = new THREE.Mesh(boxGeom, M.door);
          leaf.scale.set(width - 0.04, 2.05, 0.04);
          leaf.position.set(pa.x + Math.cos(open) * width / 2, elev + 1.04, pa.z + Math.sin(open) * width / 2);
          leaf.rotation.y = -open;
          leaf.castShadow = true;
          const arc = [];
          for (let i = 0; i <= 12; i++) {
            const t = along - THREE.MathUtils.degToRad(70) * (i / 12);
            arc.push(new THREE.Vector3(pa.x + Math.cos(t) * width, elev + 0.02, pa.z + Math.sin(t) * width));
          }
          group.add(mesh, lintel, leaf, new THREE.Line(new THREE.BufferGeometry().setFromPoints(arc), M.swing));
        }
      } else if (element.kind === "plumbing_fixture" && shape.position) {
        const [w, h, d] = fixtureSize[shape.block_name] || [0.4, 0.4, 0.4];
        const mesh = new THREE.Mesh(boxGeom, M.fixture);
        mesh.scale.set(w, h, d);
        mesh.position.copy(P(shape.position[0], shape.position[1], elev + h / 2));
        mesh.rotation.y = THREE.MathUtils.degToRad(shape.rotation_deg || 0);
        mesh.castShadow = true;
        group.add(mesh);
      } else if (element.kind === "drain") {
        if (shape.segments.length) {
          for (const [a, b] of shape.segments) {
            const pa = P(a[0], a[1], elev + 0.07);
            const pbb = P(b[0], b[1], elev + 0.07);
            const pipe = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, pa.distanceTo(pbb), 8), M.pipe);
            pipe.position.copy(pa).add(pbb).multiplyScalar(0.5);
            pipe.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), pbb.clone().sub(pa).normalize());
            group.add(pipe);
          }
        } else if (shape.position) {
          const stack = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, plan.floor_height_m, 10), M.pipe);
          stack.position.copy(P(shape.position[0], shape.position[1], elev + plan.floor_height_m / 2 - SLAB));
          group.add(stack);
        }
      }
    }

    // Contact occlusion: a dark gradient strip on the slab along both faces of every wall (one instanced draw).
    const ao = new THREE.InstancedMesh(aoGeom, M.ao, aoStrips.length || 1);
    ao.count = aoStrips.length;
    const aoMatrix = new THREE.Matrix4();
    const aoQ = new THREE.Quaternion();
    aoStrips.forEach(({ mesh, side, t, elev: y }, i) => {
      const along = mesh.rotation.y;
      const offset = new THREE.Vector3(0, 0, side * (t + AO_WIDTH / 2)).applyAxisAngle(new THREE.Vector3(0, 1, 0), along);
      // Rotate the strip so its u axis (dark edge at u = 0) points away from the wall.
      aoQ.setFromAxisAngle(new THREE.Vector3(0, 1, 0), along + (side > 0 ? -Math.PI / 2 : Math.PI / 2));
      aoMatrix.compose(new THREE.Vector3(mesh.position.x + offset.x, y + 0.012, mesh.position.z + offset.z), aoQ, new THREE.Vector3(AO_WIDTH, 1, mesh.scale.x));
      ao.setMatrixAt(i, aoMatrix);
    });
    ao.renderOrder = 0;
    group.add(ao);

    // Revision ghost: the previous position of changed elements, dashed.
    for (const change of changes.filter((c) => c.floorId === plan.floor_id && c.previous?.kind === "wall")) {
      for (const segment of change.previous.shape.segments) {
        const ghost = wallBox(segment, change.previous.shape.thickness_m || 0.1, elev, wallHeight);
        ghost.material = M.ghost;
        ghost.castShadow = ghost.receiveShadow = false;
        const lines = new THREE.LineSegments(new THREE.EdgesGeometry(boxGeom), M.ghostLine);
        lines.applyMatrix4(ghost.matrix);
        lines.computeLineDistances();
        // Footprint on the slab, so the previous position also reads from straight above.
        const foot = ghost.clone();
        foot.scale.y = 0.02;
        foot.position.y = elev + 0.03;
        foot.updateMatrix();
        group.add(ghost, lines, foot);
        const [ga, gb] = segment;
        const pa = P(ga[0], ga[1]);
        const pbb = P(gb[0], gb[1]);
        const along = new THREE.Vector3().subVectors(pbb, pa).setY(0).normalize();
        const across = new THREE.Vector3(-along.z, 0, along.x);
        const len = pa.distanceTo(pbb);
        const half = (change.previous.shape.thickness_m || 0.1) / 2 + 0.04;
        const y = elev + wallHeight + 0.12;
        const mid = pa.clone().add(pbb).multiplyScalar(0.5).setY(y);
        const top = new THREE.Mesh(boxGeom, M.ghostTop);
        top.scale.set(len, 0.02, half * 2);
        top.position.copy(mid);
        top.rotation.y = -Math.atan2(along.z, along.x);
        top.renderOrder = 29;
        group.add(top);
        // Dashes along both long edges of the previous footprint.
        for (const sideSign of [-1, 1]) {
          for (let d = 0; d < len; d += 0.32) {
            const dash = new THREE.Mesh(boxGeom, M.ghostDash);
            const l = Math.min(0.2, len - d);
            dash.scale.set(l, 0.03, 0.05);
            dash.position.copy(pa).setY(y + 0.01).addScaledVector(along, d + l / 2).addScaledVector(across, sideSign * half);
            dash.rotation.y = top.rotation.y;
            dash.renderOrder = 29;
            group.add(dash);
          }
        }
      }
    }

    const edgeGeom = new THREE.BufferGeometry();
    edgeGeom.setAttribute("position", new THREE.Float32BufferAttribute(edgePositions, 3));
    group.add(new THREE.LineSegments(edgeGeom, M.edges));
    floorGroups.set(plan.floor_id, group);
    anchors.set(plan.floor_id, P(pb.minX + 6, pb.minY + 2, elev + 1.5));
    building.add(group);
  }

  const extent = { x: (pb.maxX - pb.minX) / 2, z: (pb.maxY - pb.minY) / 2 };
  const context = buildSiteContext({ minX: -extent.x, maxX: extent.x, minZ: -extent.z, maxZ: extent.z, height: topElevation });
  scene.add(context.group);
  const highlightGroup = new THREE.Group();
  const markerGroup = new THREE.Group();
  scene.add(highlightGroup, markerGroup);

  // ---------- state ----------
  let dirty = true;
  let layoutDirty = true;
  let tween = null;
  let view = { floorId: null, mode: "orbit", highlight: null, focus: null };
  let status = { rooms: new Map(), walls: new Map(), flagZones: new Set() };
  let filters = { status: true, context: true, changes: true };
  let hovered = null;
  let overlays = [];
  let measureDirty = true; // callout sizes per mode are re-measured after the card set or stage size changes
  // `dirty` re-renders; `layoutDirty` also re-places the callouts (camera, stage or card changes only).
  const invalidate = () => { dirty = true; layoutDirty = true; };
  controls.addEventListener("change", invalidate);

  const floorVisible = (floorId) => isFloorVisible(view.floorId, floorId);

  // Open-Flag markers: the flagged element gets a solid red wall, an x-ray copy (overview) and a glow band;
  // the flagged unit gets a restrained red volume outline from its plan outline and floor height.
  function rebuildMarkers() {
    for (const child of markerGroup.children) if (child.geometry !== boxGeom) child.geometry.dispose();
    markerGroup.clear();
    if (!filters.status) return;
    const overview = !view.floorId;
    for (const wall of zoneWalls) {
      if (status.walls.get(wall.key) !== "conflict" || !floorVisible(wall.floorId)) continue;
      const { elevation, wallHeight } = floorGroups.get(wall.floorId).userData;
      if (overview) {
        const xray = new THREE.Mesh(boxGeom, M.xray);
        xray.matrixAutoUpdate = false;
        xray.matrix.copy(wall.mesh.matrix);
        xray.renderOrder = 30;
        markerGroup.add(xray);
      }
      const [a, b] = wall.segment;
      const pa = P(a[0], a[1]);
      const pbb = P(b[0], b[1]);
      const halo = new THREE.Mesh(new THREE.PlaneGeometry(pa.distanceTo(pbb) + 0.7, wall.thickness + 0.7), M.halo);
      halo.rotation.set(-Math.PI / 2, 0, -Math.atan2(pbb.z - pa.z, pbb.x - pa.x));
      halo.position.set((pa.x + pbb.x) / 2, elevation + wallHeight + 0.03, (pa.z + pbb.z) / 2);
      halo.renderOrder = 25;
      markerGroup.add(halo);
    }
    for (const zoneId of status.flagZones) {
      const outline = outlines.get(zoneId);
      if (!outline || !floorVisible(outline.floorId)) continue;
      const { elevation, wallHeight } = floorGroups.get(outline.floorId).userData;
      const shape = new THREE.Shape(outline.points.map(([x, y]) => new THREE.Vector2(x - cx, y - cy)));
      const solid = new THREE.ExtrudeGeometry(shape, { depth: wallHeight, bevelEnabled: false });
      solid.rotateX(-Math.PI / 2);
      solid.translate(0, elevation, 0);
      // From straight above the volume's top face would only double the room tint, so top-down skips it.
      if (overview || view.mode !== "top") {
        const fill = new THREE.Mesh(solid, overview ? M.volume : M.volumeIso);
        fill.renderOrder = 22;
        markerGroup.add(fill);
      } else solid.dispose();
      // Edges as thin bars (WebGL lines are 1px): readable at overview distance.
      const edges = new THREE.EdgesGeometry(solid);
      const pos = edges.attributes.position;
      const a = new THREE.Vector3();
      const b = new THREE.Vector3();
      for (let i = 0; i < pos.count; i += 2) {
        a.fromBufferAttribute(pos, i);
        b.fromBufferAttribute(pos, i + 1);
        const bar = new THREE.Mesh(boxGeom, overview ? M.xray : M.volumeBar);
        bar.position.copy(a).add(b).multiplyScalar(0.5);
        bar.quaternion.setFromUnitVectors(new THREE.Vector3(1, 0, 0), b.clone().sub(a).normalize());
        const w = overview ? 0.08 : 0.13;
        bar.scale.set(a.distanceTo(b) + w, w, w);
        bar.renderOrder = 24;
        markerGroup.add(bar);
      }
      edges.dispose();
    }
  }

  function rebuildHighlight() {
    highlightGroup.clear();
    const target = view.highlight;
    if (!target) return;
    const outline = outlines.get(target);
    const wall = zoneWalls.find((w) => w.zoneId === target);
    const ribbon = (a, b, y, width) => {
      const mesh = new THREE.Mesh(boxGeom, M.highlight);
      mesh.renderOrder = 26;
      mesh.scale.set(a.distanceTo(b) + width, 0.04, width);
      mesh.position.set((a.x + b.x) / 2, y, (a.z + b.z) / 2);
      mesh.rotation.y = -Math.atan2(b.z - a.z, b.x - a.x);
      highlightGroup.add(mesh);
    };
    if (outline) {
      // Along the wall tops, so the outline reads from above and is not hidden inside the walls.
      const { elevation, wallHeight } = floorGroups.get(outline.floorId).userData;
      const y = elevation + wallHeight + 0.05;
      outline.points.forEach((p, i) => {
        const q = outline.points[(i + 1) % outline.points.length];
        ribbon(P(p[0], p[1], y), P(q[0], q[1], y), y, 0.1);
      });
    } else if (wall) {
      // Selected element: an orange frame with a dark keyline, drawn on top and outside the red conflict halo,
      // plus orange corner posts, so selection stays distinct whatever status colour the wall has.
      const { elevation, wallHeight } = floorGroups.get(wall.floorId).userData;
      const [a, b] = wall.segment;
      const pa = P(a[0], a[1]);
      const pbb = P(b[0], b[1]);
      const along = new THREE.Vector3().subVectors(pbb, pa).setY(0).normalize();
      const across = new THREE.Vector3(-along.z, 0, along.x);
      const hl = pa.distanceTo(pbb) / 2 + 0.3;
      const hw = wall.thickness / 2 + 0.3;
      const mid = pa.clone().add(pbb).multiplyScalar(0.5);
      const corner = (sa, sc, y) => mid.clone().addScaledVector(along, sa * hl).addScaledVector(across, sc * hw).setY(y);
      const ring = [[-1, -1], [1, -1], [1, 1], [-1, 1]];
      for (const [y, width] of [[elevation + wallHeight + 0.08, 0.06]]) {
        ring.forEach((c, i) => {
          const n = ring[(i + 1) % 4];
          const p0 = corner(c[0], c[1], y);
          const p1 = corner(n[0], n[1], y);
          const back = new THREE.Mesh(boxGeom, M.keyline);
          back.scale.set(p0.distanceTo(p1) + width + 0.05, 0.04, width + 0.05);
          back.position.copy(p0).add(p1).multiplyScalar(0.5);
          back.rotation.y = -Math.atan2(p1.z - p0.z, p1.x - p0.x);
          back.renderOrder = 27;
          const front = back.clone();
          front.material = M.frame;
          front.scale.set(p0.distanceTo(p1) + width, 0.05, width);
          front.renderOrder = 28;
          highlightGroup.add(back, front);
        });
      }
      ring.forEach((c) => {
        const post = new THREE.Mesh(boxGeom, M.highlight);
        post.scale.set(0.04, wallHeight, 0.04);
        post.position.copy(corner(c[0], c[1], elevation + wallHeight / 2));
        post.renderOrder = 28;
        highlightGroup.add(post);
      });
    }
  }

  function applyMaterials() {
    for (const [floorId, group] of floorGroups) group.visible = floorVisible(floorId);
    const isolated = Boolean(view.floorId);
    for (const mesh of shellWalls) if (!zoneWalls.some((w) => w.mesh === mesh)) mesh.material = M.shell;
    context.group.visible = filters.context;
    context.tall.visible = filters.context && view.mode !== "top";
    const selectedUnit = view.highlight && outlines.has(view.highlight) ? view.highlight : null;
    for (const plate of roomPlates) {
      const s = filters.status ? status.rooms.get(plate.zoneId) : null;
      let color = C.open;
      let opacity = 0;
      if (s === "conflict") { color = C.conflict; opacity = isolated ? 0.26 : 0.14; }
      else if (s === "open") { color = C.open; opacity = 0.12; }
      else if (s === "ok") { color = C.ok; opacity = 0.14; }
      // Selection is carried by the orange outline; a conflicting room keeps its red fill so it still reads flagged.
      if (plate.zoneId === view.highlight) { if (s === "conflict") opacity = 0.34; else { color = C.selected; opacity = 0.42; } }
      else if (selectedUnit && plate.unitId === selectedUnit && s !== "conflict") { color = C.selected; opacity = Math.max(opacity, 0.22); }
      if (plate.zoneId === hovered || plate.unitId === hovered) opacity = Math.min(0.75, opacity + 0.22) || 0.18; // hovering a unit edge lights its rooms
      plate.mesh.material.color.setHex(color);
      plate.mesh.material.opacity = opacity;
    }
    for (const wall of zoneWalls) {
      const s = filters.status ? status.walls.get(wall.key) : null;
      wall.mesh.material = s === "conflict" ? M.conflict
        : wall.zoneId === view.highlight || wall.zoneId === hovered ? M.selectedWall
          : wall.base;
    }
    scene.traverse((o) => {
      if ([M.ghost, M.ghostLine, M.ghostTop, M.ghostDash].includes(o.material)) o.visible = filters.changes;
    });
    rebuildMarkers();
    invalidate();
  }

  // ---------- camera ----------
  // Reduced motion: camera moves jump to their goal, damping is off and ambient animation never starts.
  const motion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  let reduced = Boolean(motion?.matches);
  const onMotion = () => { reduced = Boolean(motion?.matches); controls.enableDamping = !reduced; invalidate(); };
  motion?.addEventListener?.("change", onMotion);
  controls.enableDamping = !reduced;

  const half = (box) => ({ x: (box.maxX - box.minX) / 2, z: (box.maxY - box.minY) / 2 });
  function frame(bounds, elevation, mode) {
    const w = container.clientWidth || 1;
    const h = container.clientHeight || 1;
    const aspect = w / h;
    if (bounds === pb && !view.floorId && mode !== "top") {
      // Overview: a three-quarter view framed on the building itself (the subject, with its Flag volume);
      // the decorative crane and scenery may crop at the edges.
      const sphere = new THREE.Box3(new THREE.Vector3(-extent.x, 0, -extent.z), new THREE.Vector3(extent.x, topElevation, extent.z))
        .getBoundingSphere(new THREE.Sphere());
      const fov = 30;
      const vfov = THREE.MathUtils.degToRad(fov / 2);
      const hfov = Math.atan(Math.tan(vfov) * aspect);
      // ponytail: fixed fill factor, tuned by screenshots at 1280/1440/390; desktop leaves room for the chrome cards.
      const radius = (sphere.radius / Math.sin(Math.min(vfov, hfov))) * (aspect < 1 ? 1.2 : 1.3);
      const target = sphere.center.clone().setY(topElevation * 0.42);
      return { target, position: target.clone().add(new THREE.Vector3().setFromSphericalCoords(radius, THREE.MathUtils.degToRad(57), THREE.MathUtils.degToRad(36))), fov };
    }
    const focused = bounds !== pb;
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
      const hb = half(pb);
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
    const radius = Math.max(Math.hypot(sx, sz), 8) * (aspect < 1 ? 1.6 : 1.25) / Math.tan(THREE.MathUtils.degToRad(fov / 2)) * (focused ? 0.62 : 0.55);
    const polar = THREE.MathUtils.degToRad(view.floorId ? 50 : 62);
    const azimuth = THREE.MathUtils.degToRad(36);
    const offset = new THREE.Vector3().setFromSphericalCoords(radius, polar, azimuth);
    return { target: center, position: center.clone().add(offset), fov };
  }

  function applyGoal(goal) {
    camera.position.copy(goal.position);
    controls.target.copy(goal.target);
    camera.fov = goal.fov;
    camera.updateProjectionMatrix();
    invalidate();
  }

  function animateCamera() {
    const iso = view.floorId ? floorGroups.get(view.floorId) : null;
    const bounds = view.focus || pb;
    const elevation = iso ? iso.userData.elevation : topElevation * 0.38;
    const goal = frame(bounds, elevation, view.mode);
    // Flush leftover damping momentum so the camera ends exactly on the goal (no drift off true overhead).
    controls.enableDamping = false;
    controls.update();
    controls.enableDamping = !reduced;
    if (reduced) { tween = null; applyGoal(goal); } else {
      tween = {
        start: performance.now(), duration: 950,
        from: { position: camera.position.clone(), target: controls.target.clone(), fov: camera.fov },
        to: goal,
      };
    }
    const top = view.mode === "top";
    controls.enableRotate = !top;
    controls.mouseButtons = { LEFT: top ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };
    controls.touches = { ONE: top ? THREE.TOUCH.PAN : THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN };
  }

  // ---------- picking ----------
  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  let pointer = null;
  let down = null;
  const visibleChain = (o) => { for (let n = o; n; n = n.parent) if (!n.visible) return false; return true; };
  function pick(clientX, clientY) {
    const rect = renderer.domElement.getBoundingClientRect();
    ndc.set(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
    // Unzoned partition walls pass the click through to the room or unit surface beneath them.
    const hit = raycaster.intersectObjects(pickables, false).find((h) => h.object.userData.zoneId && visibleChain(h.object));
    return hit?.object.userData.zoneId || null;
  }
  const onMove = (event) => { pointer = { x: event.clientX, y: event.clientY }; };
  const onLeave = () => { pointer = null; if (hovered) { hovered = null; onHover(null); applyMaterials(); } };
  const onDown = (event) => { down = { x: event.clientX, y: event.clientY }; };
  const onUp = (event) => {
    if (down && Math.hypot(event.clientX - down.x, event.clientY - down.y) < 5) onSelect(pick(event.clientX, event.clientY));
    down = null;
  };
  const el = renderer.domElement;
  el.addEventListener("pointermove", onMove);
  el.addEventListener("pointerleave", onLeave);
  el.addEventListener("pointerdown", onDown);
  el.addEventListener("pointerup", onUp);

  // ---------- loop ----------
  // Horizontal shift of the projection centre (px): an expanded desktop Key covers the stage's right side,
  // so the framed subject moves into the uncovered part instead of sitting under the Key.
  let insetX = 0;
  const resize = () => {
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    if (insetX) camera.setViewOffset(w, h, insetX, 0, w, h); else camera.clearViewOffset();
    camera.updateProjectionMatrix();
    measureDirty = true;
    invalidate();
  };
  const ro = new ResizeObserver(resize);
  ro.observe(container);
  resize();

  // Callout layout. Hard constraints: a card stays inside the stage and never overlaps another card or the
  // floating chrome ([data-reserve]). Within those, it avoids the protected subject (selected room/element, or
  // the flagged unit) and anchor dots. Cards are placed in priority order (the selected subject's card, then
  // Flags, then the rest). If no full card fits without covering the subject, the card degrades to a title-only
  // "compact" card, then to a small "pin" that expands on hover/focus; if even a pin cannot fit, it goes
  // "offstage" (visually hidden, still in the accessibility tree; the side panel carries the same facts).
  // Candidates sit in eight directions at four distances; a leader line joins the anchor to the card.
  const v = new THREE.Vector3();
  const EDGE = 8;
  const MODES = ["full", "compact", "pin"];
  const overlap = (a, b) => Math.max(0, Math.min(a.r, b.r) - Math.max(a.l, b.l)) * Math.max(0, Math.min(a.b, b.b) - Math.max(a.t, b.t));
  const DIRS = [[0, -1], [0.71, -0.71], [-0.71, -0.71], [1, 0], [-1, 0], [0.71, 0.71], [-0.71, 0.71], [0, 1]];
  const DIRS_BELOW = [[0, 1], [0.71, 0.71], [-0.71, 0.71], [1, 0], [-1, 0], [0.71, -0.71], [-0.71, -0.71], [0, -1]];
  // Screen rect of a zone's volume (room/unit outline or element wall), padded; null if it has no geometry.
  function zoneRect(target, w, h) {
    const outline = outlines.get(target);
    const wall = zoneWalls.find((item) => item.zoneId === target);
    const corners = [];
    if (outline) {
      const { elevation, wallHeight } = floorGroups.get(outline.floorId).userData;
      for (const [x, y] of outline.points) corners.push(P(x, y, elevation), P(x, y, elevation + wallHeight));
    } else if (wall) {
      const box = new THREE.Box3().setFromObject(wall.mesh).expandByScalar(0.6);
      for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) corners.push(new THREE.Vector3(x, y, z));
    }
    if (!corners.length) return null;
    const xs = [];
    const ys = [];
    for (const c of corners) {
      c.project(camera);
      xs.push(((c.x + 1) / 2) * w);
      ys.push(((1 - c.y) / 2) * h);
    }
    return { l: Math.min(...xs) - 12, t: Math.min(...ys) - 12, r: Math.max(...xs) + 12, b: Math.max(...ys) + 12 };
  }
  // Protected subjects: the selected room/element; without one, the visible flagged units (the hero).
  function subjectRects(w, h) {
    const target = view.highlight && view.highlight !== view.floorId ? view.highlight : null;
    if (target) return [zoneRect(target, w, h)].filter(Boolean);
    if (!filters.status) return [];
    return [...status.flagZones].filter((id) => outlines.has(id) && floorVisible(outlines.get(id).floorId))
      .map((id) => zoneRect(id, w, h)).filter(Boolean);
  }
  function placeOverlays() {
    const w = container.clientWidth;
    const h = container.clientHeight;
    const stage = container.getBoundingClientRect();
    const scope = container.closest(".sv-stage") || container.parentElement;
    const taken = [...(scope?.querySelectorAll("[data-reserve]") || [])].map((el) => {
      const r = el.getBoundingClientRect();
      return { l: r.left - stage.left - 6, t: r.top - stage.top - 6, r: r.right - stage.left + 6, b: r.bottom - stage.top + 6 };
    }).filter((r) => r.r > r.l && r.b > 0 && r.t < h && r.r > 0 && r.l < w);
    const subjects = subjectRects(w, h);
    // Exposed for layout checks: callouts must never cover these rects.
    container.dataset.subject = subjects.map((r) => [r.l, r.t, r.r, r.b].map(Math.round).join(",")).join(";");
    const live = overlays.filter((o) => o.el && anchors.has(o.anchor));
    // Card sizes per mode change only with the card set or the stage size: measure them once, not per frame.
    if (measureDirty) {
      measureDirty = false;
      for (const o of live) {
        o.sizes = {};
        for (const mode of MODES) {
          o.el.dataset.mode = mode;
          o.sizes[mode] = [o.el.firstElementChild.offsetWidth, o.el.firstElementChild.offsetHeight];
        }
      }
    }
    const items = live.filter((o) => o.sizes).map((o) => {
      v.copy(anchors.get(o.anchor)).project(camera);
      const x = ((v.x + 1) / 2) * w;
      const y = ((1 - v.y) / 2) * h;
      const shown = v.z < 1 && x > EDGE && x < w - EDGE && y > EDGE && y < h - EDGE && (!o.floorId || floorVisible(o.floorId));
      return { o, x, y, button: o.el.firstElementChild, shown };
    });
    const rank = (it) => (view.highlight && it.o.target === view.highlight ? 0 : it.o.tone === "crit" ? 1 : 2);
    items.sort((a, b) => rank(a) - rank(b)); // stable: keeps the given order within a rank
    // Anchor dots are small no-go zones for every card.
    const dots = items.filter((it) => it.shown).map((it) => ({ l: it.x - 9, t: it.y - 9, r: it.x + 9, b: it.y + 9 }));
    const cards = [];
    for (const it of items) {
      const { el } = it.o;
      if (!it.shown) { el.style.visibility = "hidden"; continue; }
      let chosen = null;
      let fallback = null;
      for (const mode of MODES) {
        const [bw, bh] = it.o.sizes[mode];
        let best = null;
        (it.o.below ? DIRS_BELOW : DIRS).forEach(([dx, dy], order) => {
          for (const gap of [26, 60, 110, 170]) {
            const l = THREE.MathUtils.clamp(it.x + dx * (gap + bw / 2) - bw / 2, EDGE, Math.max(EDGE, w - bw - EDGE));
            const t = it.y + dy * (gap + bh / 2) - bh / 2;
            const rect = { l, t, r: l + bw, b: t + bh };
            if (rect.t < EDGE || rect.b > h - EDGE || taken.some((r) => overlap(rect, r) > 0)) continue; // hard
            const subject = subjects.reduce((sum, r) => sum + overlap(rect, r), 0);
            // A leader through another card (or a card over another leader) is avoided ahead of everything
            // except the hard limits; if no candidate avoids it, the card keeps its place without a leader.
            const clash = leaderClash(it, rect, cards);
            const cost = (clash ? 1e9 : 0) + subject * 40 + dots.reduce((sum, r) => sum + overlap(rect, r) * 20, 0) + gap * 3 + order * 40;
            if (!best || cost < best.cost) best = { cost, rect, subject, mode, clash };
          }
        });
        if (best && best.subject === 0 && !best.clash) { chosen = best; break; }
        if (best && (!fallback || best.clash < fallback.clash || (best.clash === fallback.clash && best.subject < fallback.subject))) fallback = best;
      }
      chosen ||= fallback;
      el.style.visibility = "visible";
      if (!chosen) { el.dataset.mode = "offstage"; continue; }
      el.dataset.mode = chosen.mode;
      const { rect } = chosen;
      taken.push({ l: rect.l - 4, t: rect.t - 4, r: rect.r + 4, b: rect.b + 4 });
      const nx = THREE.MathUtils.clamp(it.x, rect.l, rect.r);
      const ny = THREE.MathUtils.clamp(it.y, rect.t, rect.b);
      cards.push({ rect, leader: chosen.clash ? null : [it.x, it.y, nx, ny] });
      el.style.transform = `translate(${it.x}px, ${it.y}px)`;
      el.style.setProperty("--len", `${chosen.clash ? 0 : Math.hypot(nx - it.x, ny - it.y)}px`);
      el.style.setProperty("--ang", `${Math.atan2(ny - it.y, nx - it.x)}rad`);
      it.button.style.transform = `translate(${rect.l - it.x}px, ${rect.t - it.y}px)`;
    }
  }

  // Ambient motion (decorative crane slew, pulsing Flag halo) runs only without reduced motion, while the
  // crane or a Flag marker is visible; otherwise the scene renders on demand. Capped at ~30 fps.
  let lastPointer = null;
  let raf = 0;
  let lastAmbient = 0;
  const ambientActive = () => !reduced && !tween && ((filters.context && view.mode !== "top") || markerGroup.children.length > 0);
  const loop = (now) => {
    raf = requestAnimationFrame(loop);
    if (tween) {
      const t = Math.min(1, (now - tween.start) / tween.duration);
      const k = EASE(t);
      camera.position.lerpVectors(tween.from.position, tween.to.position, k);
      controls.target.lerpVectors(tween.from.target, tween.to.target, k);
      camera.fov = tween.from.fov + (tween.to.fov - tween.from.fov) * k;
      camera.updateProjectionMatrix();
      if (t === 1) tween = null;
      invalidate();
    }
    controls.update();
    if (ambientActive()) {
      if (now - lastAmbient > 33) {
        const dt = lastAmbient ? Math.min(now - lastAmbient, 100) / 1000 : 0;
        lastAmbient = now;
        context.slew.rotation.y += dt * 0.045;
        M.halo.opacity = 0.3 + 0.3 * (0.5 + 0.5 * Math.sin(now / 420));
        dirty = true;
      }
    } else {
      lastAmbient = 0;
      if (M.halo.opacity !== 0.5) { M.halo.opacity = 0.5; dirty = true; }
    }
    const distance = camera.position.distanceTo(controls.target);
    // Aerial haze: the far side of the site and the scenery fade into the graphite horizon.
    scene.fog.near = distance * 0.9;
    scene.fog.far = distance * 1.9 + 10;
    if (pointer && pointer !== lastPointer && !down) {
      lastPointer = pointer;
      const id = pick(pointer.x, pointer.y);
      if (id !== hovered) {
        hovered = id;
        onHover(id ? { zoneId: id, x: pointer.x, y: pointer.y } : null);
        applyMaterials();
      } else if (id) onHover({ zoneId: id, x: pointer.x, y: pointer.y });
    }
    if (!dirty) return;
    dirty = false;
    renderer.render(scene, camera);
    if (layoutDirty) { layoutDirty = false; placeOverlays(); }
  };

  // Initial camera without animation.
  applyGoal(frame(pb, topElevation * 0.38, "orbit"));
  raf = requestAnimationFrame(loop);

  return {
    setView(next) {
      const cameraChanged = next.floorId !== view.floorId || next.mode !== view.mode || JSON.stringify(next.focus) !== JSON.stringify(view.focus);
      view = next;
      rebuildHighlight();
      applyMaterials();
      if (cameraChanged) animateCamera();
    },
    setStatus(next) { status = next; applyMaterials(); },
    setFilters(next) { filters = next; applyMaterials(); },
    setOverlays(next) { overlays = next; measureDirty = true; invalidate(); },
    setInset(px) { if (px !== insetX) { insetX = px; resize(); } },
    refresh: invalidate,
    hasAnchor: (key) => anchors.has(key),
    zoom(factor) {
      const offset = camera.position.clone().sub(controls.target).multiplyScalar(factor);
      const to = { position: controls.target.clone().add(offset), target: controls.target.clone(), fov: camera.fov };
      if (reduced) { applyGoal(to); return; }
      tween = { start: performance.now(), duration: 350, from: { position: camera.position.clone(), target: controls.target.clone(), fov: camera.fov }, to };
    },
    recenter() { animateCamera(); },
    changedKeys,
    dispose() {
      cancelAnimationFrame(raf);
      ro.disconnect();
      motion?.removeEventListener?.("change", onMotion);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointerup", onUp);
      controls.dispose();
      scene.traverse((o) => {
        o.geometry?.dispose();
        const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
        mats.forEach((m) => m.dispose());
      });
      renderer.dispose();
      el.remove();
    },
  };
}
