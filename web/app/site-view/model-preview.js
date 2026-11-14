"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { buildCallouts, indexZones, revisionChanges, sceneStatus, zoneStatus } from "../../lib/site-model.mjs";
import { STATUS } from "./zone-panel";
import "./site-view.css";

/**
 * Dashboard model: the same Three.js scene as /site, isolated to one floor, with the shared callouts as markers.
 * Markers and clicks open the zone's site view. State arrives as props (the dashboard refreshes itself).
 */
export default function ModelPreview({ model: initialModel, state, floorId, title }) {
  const router = useRouter();
  // ponytail: geometry is pinned for the page lifetime so a dashboard refresh never rebuilds the scene; a reload picks up new CAD imports.
  const [model] = useState(initialModel);
  const index = useMemo(() => indexZones(model?.zones), [model]);
  const geometry = useMemo(() => model?.geometry || [], [model]);
  const changes = useMemo(() => revisionChanges(model), [model]);
  const [mode, setMode] = useState("orbit");
  const [failure, setFailure] = useState(null);
  const [ready, setReady] = useState(0);
  const stageRef = useRef(null);
  const sceneRef = useRef(null);
  const tipRef = useRef(null);
  const calloutRefs = useRef(new Map());
  const stateRef = useRef(state);
  useEffect(() => { stateRef.current = state; });

  const open = (id) => router.push(id ? `/zones/${encodeURIComponent(id)}` : "/site");
  const openRef = useRef(open);
  useEffect(() => { openRef.current = open; });

  useEffect(() => {
    if (!stageRef.current || !geometry.length) return undefined;
    let scene;
    let cancelled = false;
    import("./site-scene").then(({ createSiteScene }) => {
      if (cancelled || !stageRef.current) return;
      try {
        scene = createSiteScene(stageRef.current, {
          geometry, zones: index, changes, theme: "dark",
          onSelect: (id) => id && openRef.current(id),
          onHover: (hover) => {
            const tip = tipRef.current;
            const stage = stageRef.current;
            if (!tip || !stage) return;
            if (!hover) { tip.hidden = true; stage.style.removeProperty("cursor"); return; }
            const rect = stage.getBoundingClientRect();
            tip.hidden = false;
            tip.style.transform = `translate(${hover.x - rect.left + 14}px, ${hover.y - rect.top + 14}px)`;
            tip.firstChild.textContent = hover.zoneId;
            tip.lastChild.textContent = `${index.get(hover.zoneId)?.name || ""} · ${STATUS[zoneStatus(index, stateRef.current, hover.zoneId)].text}`;
            stage.style.cursor = "pointer";
          },
        });
        sceneRef.current = scene;
        setReady((n) => n + 1);
      } catch (error) {
        setFailure(error?.message || "WebGL is not available");
      }
    });
    return () => { cancelled = true; scene?.dispose(); sceneRef.current = null; };
  }, [geometry, index, changes]);

  useEffect(() => { sceneRef.current?.setView({ floorId, mode, highlight: floorId, focus: null }); }, [floorId, mode, ready]);
  useEffect(() => { sceneRef.current?.setStatus(sceneStatus(index, state, geometry)); }, [index, state, geometry, ready]);
  const callouts = useMemo(() => buildCallouts({ state, geometry, index, changes, route: { floorId, highlight: floorId } }), [state, geometry, index, changes, floorId]);
  useEffect(() => {
    sceneRef.current?.setOverlays(callouts.map((c) => ({ el: calloutRefs.current.get(c.key), anchor: c.anchor, floorId: c.floorId, below: c.below, target: c.target, tone: c.tone })));
  }, [callouts, ready]);

  const expandHref = floorId ? `/zones/${encodeURIComponent(floorId)}` : "/site";
  return (
    <section className="panel" aria-labelledby="model-h">
      <div className="panel-head">
        <h2 id="model-h">{title}</h2>
        <span className="mono muted">{geometry.filter((plan) => !floorId || plan.floor_id === floorId).map((plan) => `${plan.plan_id} · Rev ${plan.label}`).join(" · ")}</span>
        <div role="toolbar" aria-label="Model view" style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          <button type="button" className={`vbtn${mode === "orbit" ? " cur" : ""}`} aria-pressed={mode === "orbit"} onClick={() => setMode("orbit")}>3D</button>
          <button type="button" className={`vbtn${mode === "top" ? " cur" : ""}`} aria-pressed={mode === "top"} onClick={() => setMode("top")}>2D</button>
          <Link className="vbtn" href={expandHref} aria-label="Open the full site model">⤢</Link>
        </div>
      </div>
      <div className="model-stage">
        <div ref={stageRef} className="sv-canvas" />
        {!geometry.length && <p className="model-note">No plan geometry imported yet. Run the CAD import, then reload.</p>}
        {failure && <p className="model-note" role="alert">3D view unavailable: {failure}. The panels beside it carry the same facts.</p>}
        <div className="callouts" aria-label="Model markers">
          {callouts.map((c) => (
            <div key={c.key} ref={(el) => (el ? calloutRefs.current.set(c.key, el) : calloutRefs.current.delete(c.key))} className={`callout t-${c.tone}`} style={{ visibility: "hidden" }}>
              <button type="button" onClick={() => open(c.target)}>
                <strong>{c.title}</strong><span>{c.text}</span><em className="pin" aria-hidden="true">{c.short}</em>
              </button>
            </div>
          ))}
        </div>
        <div ref={tipRef} className="hover-tip" hidden><strong /><span /></div>
      </div>
      <p className="small muted" style={{ margin: 0, padding: "8px 16px 14px" }}>Live model from imported DXF geometry. Markers and zones open the site view.</p>
    </section>
  );
}
