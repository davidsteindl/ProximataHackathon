// Imperative Three.js scene for the 3D site view. React owns data and selection; this module owns
// meshes, camera animation and per-frame overlay placement (kept out of React state on purpose).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { buildSiteContext } from "./site-context";

const C = {
  bg: 0x22251F,
  chalk: 0xEDEAE0,
  shell: 0xE4E0D3,
  slab: 0xCFC9BA,
  line: 0x191813,
  conflict: 0xFF5C49,
  open: 0xE8B04B,
  ok: 0x55B97D,
  selected: 0xFF8A4A,
  pipe: 0x62A8D8,
  fixture: 0xFAF8F2,
  ghost: 0xF2EEE2,
};
const SLAB = 0.25;
const EASE = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

function planBounds(geometry) {
  const pts = geometry.flatMap((plan) => plan.elements.flatMap((e) => (e.shape.outline?.length ? e.shape.outline : e.shape.segments.flat())));
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
}

export function createSiteScene(container, { geometry, zones, changes, onHover, onSelect }) {
  const kindOf = (id) => zones.get(id)?.kind;
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.domElement.setAttribute("aria-hidden", "true");
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(C.bg);
  scene.fog = new THREE.Fog(C.bg, 110, 260);
  const camera = new THREE.PerspectiveCamera(32, 1, 0.3, 700);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.09;
  controls.maxPolarAngle = Math.PI * 0.47;
  controls.minDistance = 4;
  controls.maxDistance = 190;
  controls.screenSpacePanning = true;

  const pb = planBounds(geometry);
  const cx = (pb.minX + pb.maxX) / 2;
  const cy = (pb.minY + pb.maxY) / 2;
  const P = (x, y, h = 0) => new THREE.Vector3(x - cx, h, -(y - cy));
  const floors = [...geometry].sort((a, b) => a.floor_elevation_m - b.floor_elevation_m);
  const topElevation = floors.length ? Math.max(...floors.map((f) => f.floor_elevation_m + f.floor_height_m)) : 3;

  // Lights.
  scene.add(new THREE.HemisphereLight(0xF6F0E2, 0x2A2C25, 1.25));
  const sun = new THREE.DirectionalLight(0xFFF0DA, 2.3);
  sun.position.set(-34, 52, 30);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -55, right: 55, top: 55, bottom: -55, near: 1, far: 160 });
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.03;
  scene.add(sun, new THREE.DirectionalLight(0xB8C6D4, 0.45).translateX(30).translateY(20).translateZ(-30));

  // Shared materials.
  const std = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0, ...extra });
  const M = {
    wall: std(C.chalk),
    shell: std(C.shell, { transparent: true, opacity: 0.3, depthWrite: false }),
    shellSolid: std(C.shell),
    slab: std(C.slab),
    conflict: std(C.conflict, { emissive: C.conflict, emissiveIntensity: 0.35 }),
    selectedWall: std(C.selected, { emissive: C.selected, emissiveIntensity: 0.3 }),
    fixture: std(C.fixture, { roughness: 0.4 }),
    pipe: std(C.pipe, { roughness: 0.5, emissive: C.pipe, emissiveIntensity: 0.15 }),
    threshold: std(0x8E897C),
    ghost: new THREE.MeshBasicMaterial({ color: C.ghost, transparent: true, opacity: 0.1, depthWrite: false }),
    ghostLine: new THREE.LineDashedMaterial({ color: C.ghost, dashSize: 0.18, gapSize: 0.12, transparent: true, opacity: 0.9 }),
    edges: new THREE.LineBasicMaterial({ color: C.line, transparent: true, opacity: 0.28 }),
    unitLine: new THREE.LineBasicMaterial({ color: 0x5F5B52, transparent: true, opacity: 0.75 }),
    highlight: new THREE.MeshBasicMaterial({ color: C.selected }),
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

  for (const plan of floors) {
    const group = new THREE.Group();
    const elev = plan.floor_elevation_m;
    const wallHeight = plan.floor_height_m - SLAB;
    group.userData = { floorId: plan.floor_id, elevation: elev };
    edgePositions.length = 0;

    // Slab (from the plan's extent) with the floor top at the floor elevation.
    const slab = new THREE.Mesh(boxGeom, M.slab);
    slab.scale.set(pb.maxX - pb.minX + 0.5, SLAB, pb.maxY - pb.minY + 0.5);
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
            mesh.castShadow = true;
            shellWalls.push(mesh);
          } else {
            pickables.push(mesh);
          }
          if (zoneId) {
            mesh.userData.zoneId = zoneId;
            zoneWalls.push({ mesh, zoneId, key, base: mesh.material });
          }
          pushEdges(mesh.geometry, mesh.matrix);
          group.add(mesh);
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
          group.add(line);
        }
      } else if (element.kind === "door") {
        for (const [a, b] of shape.segments) {
          const pa = P(a[0], a[1]);
          const pbb = P(b[0], b[1]);
          const mesh = new THREE.Mesh(boxGeom, M.threshold);
          mesh.scale.set(pa.distanceTo(pbb), 0.03, 0.16);
          mesh.position.set((pa.x + pbb.x) / 2, elev + 0.015, (pa.z + pbb.z) / 2);
          mesh.rotation.y = -Math.atan2(pbb.z - pa.z, pbb.x - pa.x);
          group.add(mesh);
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

    // Revision ghost: the previous position of changed elements, dashed.
    for (const change of changes.filter((c) => c.floorId === plan.floor_id && c.previous?.kind === "wall")) {
      for (const segment of change.previous.shape.segments) {
        const ghost = wallBox(segment, change.previous.shape.thickness_m || 0.1, elev, wallHeight);
        ghost.material = M.ghost;
        ghost.castShadow = ghost.receiveShadow = false;
        const lines = new THREE.LineSegments(new THREE.EdgesGeometry(boxGeom), M.ghostLine);
        lines.applyMatrix4(ghost.matrix);
        lines.computeLineDistances();
        group.add(ghost, lines);
      }
    }

    const edgeGeom = new THREE.BufferGeometry();
    edgeGeom.setAttribute("position", new THREE.Float32BufferAttribute(edgePositions, 3));
    group.add(new THREE.LineSegments(edgeGeom, M.edges));
    floorGroups.set(plan.floor_id, group);
    anchors.set(plan.floor_id, P(pb.minX + 6, pb.minY + 2, elev + 1.5));
    building.add(group);
  }

  const half = { x: (pb.maxX - pb.minX) / 2, z: (pb.maxY - pb.minY) / 2 };
  const context = buildSiteContext({ minX: -half.x, maxX: half.x, minZ: -half.z, maxZ: half.z, height: topElevation });
  scene.add(context.group);
  const highlightGroup = new THREE.Group();
  scene.add(highlightGroup);

  // ---------- state ----------
  let dirty = true;
  let tween = null;
  let view = { floorId: null, mode: "orbit", highlight: null, focus: null };
  let status = { rooms: new Map(), walls: new Map() };
  let filters = { status: true, context: true, changes: true };
  let hovered = null;
  let overlays = [];
  const invalidate = () => { dirty = true; };
  controls.addEventListener("change", invalidate);

  function floorVisible(floorId) {
    if (!view.floorId) return true;
    const iso = floorGroups.get(view.floorId)?.userData.elevation ?? Infinity;
    return (floorGroups.get(floorId)?.userData.elevation ?? 0) <= iso;
  }

  function rebuildHighlight() {
    highlightGroup.clear();
    const target = view.highlight;
    if (!target) return;
    const outline = outlines.get(target);
    const wall = zoneWalls.find((w) => w.zoneId === target);
    const ribbon = (a, b, y, width = 0.14) => {
      const mesh = new THREE.Mesh(boxGeom, M.highlight);
      mesh.scale.set(a.distanceTo(b) + width, 0.04, width);
      mesh.position.set((a.x + b.x) / 2, y, (a.z + b.z) / 2);
      mesh.rotation.y = -Math.atan2(b.z - a.z, b.x - a.x);
      highlightGroup.add(mesh);
    };
    if (outline) {
      const elev = floorGroups.get(outline.floorId).userData.elevation + 0.05;
      outline.points.forEach((p, i) => {
        const q = outline.points[(i + 1) % outline.points.length];
        ribbon(P(p[0], p[1], elev), P(q[0], q[1], elev), elev);
      });
    } else if (wall) {
      const box = new THREE.Box3().setFromObject(wall.mesh);
      const helper = new THREE.Box3Helper(box.expandByScalar(0.06), C.selected);
      highlightGroup.add(helper);
    }
  }

  function applyMaterials() {
    for (const [floorId, group] of floorGroups) group.visible = floorVisible(floorId);
    const isolated = Boolean(view.floorId);
    for (const mesh of shellWalls) mesh.material = isolated ? M.shellSolid : M.shell;
    context.group.visible = filters.context;
    context.tall.visible = filters.context && view.mode !== "top";
    const selectedUnit = view.highlight && outlines.has(view.highlight) ? view.highlight : null;
    for (const plate of roomPlates) {
      const s = filters.status ? status.rooms.get(plate.zoneId) : null;
      let color = C.open;
      let opacity = 0;
      if (s === "conflict") { color = C.conflict; opacity = 0.3; }
      else if (s === "open") { color = C.open; opacity = 0.16; }
      else if (s === "ok") { color = C.ok; opacity = 0.16; }
      if (plate.zoneId === view.highlight) { color = C.selected; opacity = 0.5; }
      else if (selectedUnit && plate.unitId === selectedUnit) { color = C.selected; opacity = Math.max(opacity, 0.26); }
      if (plate.zoneId === hovered) opacity = Math.min(0.75, opacity + 0.22) || 0.18;
      plate.mesh.material.color.setHex(color);
      plate.mesh.material.opacity = opacity;
    }
    for (const wall of zoneWalls) {
      const s = filters.status ? status.walls.get(wall.key) : null;
      wall.mesh.material = s === "conflict" ? M.conflict
        : wall.zoneId === view.highlight || wall.zoneId === hovered ? M.selectedWall
          : wall.base === M.shell ? (isolated ? M.shellSolid : M.shell) : M.wall;
    }
    scene.traverse((o) => {
      if (o.material === M.ghost || o.material === M.ghostLine) o.visible = filters.changes;
    });
    invalidate();
  }

  // ---------- camera ----------
  function frame(bounds, elevation, mode) {
    const w = container.clientWidth || 1;
    const h = container.clientHeight || 1;
    const aspect = w / h;
    const min = P(bounds.minX, bounds.maxY);
    const max = P(bounds.maxX, bounds.minY);
    const center = new THREE.Vector3((min.x + max.x) / 2, elevation, (min.z + max.z) / 2);
    const sx = Math.max(max.x - min.x, 14);
    const sz = Math.max(max.z - min.z, 10);
    if (mode === "top") {
      const fov = 16; // narrow FOV from far away reads almost like an orthographic plan
      const needed = Math.max(sz, sx / aspect) * 1.3;
      const dist = needed / 2 / Math.tan(THREE.MathUtils.degToRad(fov / 2));
      return { target: center, position: center.clone().add(new THREE.Vector3(0, dist, 0.001)), fov };
    }
    const fov = 32;
    const radius = Math.max(Math.hypot(sx, sz), 8) * (aspect < 1 ? 1.8 : 1.3) / Math.tan(THREE.MathUtils.degToRad(fov / 2)) * 0.62;
    const polar = THREE.MathUtils.degToRad(view.floorId ? 50 : 62);
    const azimuth = THREE.MathUtils.degToRad(38);
    const offset = new THREE.Vector3().setFromSphericalCoords(radius, polar, azimuth);
    return { target: center, position: center.clone().add(offset), fov };
  }

  function animateCamera() {
    const iso = view.floorId ? floorGroups.get(view.floorId) : null;
    const bounds = view.focus || pb;
    const elevation = iso ? iso.userData.elevation : topElevation * 0.38;
    const goal = frame(bounds, elevation, view.mode);
    tween = {
      start: performance.now(), duration: 950,
      from: { position: camera.position.clone(), target: controls.target.clone(), fov: camera.fov },
      to: goal,
    };
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
    const hit = raycaster.intersectObjects(pickables, false).find((h) => visibleChain(h.object));
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
  const resize = () => {
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    invalidate();
  };
  const ro = new ResizeObserver(resize);
  ro.observe(container);
  resize();

  const v = new THREE.Vector3();
  function placeOverlays() {
    const w = container.clientWidth;
    const h = container.clientHeight;
    for (const o of overlays) {
      const pos = anchors.get(o.anchor);
      if (!pos || !o.el) continue;
      v.copy(pos).project(camera);
      const shown = v.z < 1 && Math.abs(v.x) < 1.05 && Math.abs(v.y) < 1.05 && (!o.floorId || floorVisible(o.floorId));
      o.el.style.visibility = shown ? "visible" : "hidden";
      if (shown) o.el.style.transform = `translate(${((v.x + 1) / 2) * w}px, ${((1 - v.y) / 2) * h}px)`;
    }
  }

  let lastPointer = null;
  let raf = 0;
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
      dirty = true;
    }
    controls.update();
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
    placeOverlays();
  };

  // Initial camera without animation.
  const initial = frame(pb, topElevation * 0.38, "orbit");
  camera.position.copy(initial.position);
  controls.target.copy(initial.target);
  camera.fov = initial.fov;
  camera.updateProjectionMatrix();
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
    setOverlays(next) { overlays = next; invalidate(); },
    hasAnchor: (key) => anchors.has(key),
    zoom(factor) {
      const offset = camera.position.clone().sub(controls.target).multiplyScalar(factor);
      tween = { start: performance.now(), duration: 350, from: { position: camera.position.clone(), target: controls.target.clone(), fov: camera.fov },
        to: { position: controls.target.clone().add(offset), target: controls.target.clone(), fov: camera.fov } };
    },
    recenter() { animateCamera(); },
    changedKeys,
    dispose() {
      cancelAnimationFrame(raf);
      ro.disconnect();
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
