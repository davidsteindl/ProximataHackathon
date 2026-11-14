"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { observeRightOverlay } from "../../lib/key-layout.mjs";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  buildCallouts, focusBounds, indexZones, revisionChanges, sceneStatus, viewForZone, zoneDetails, zoneStatus,
} from "../../lib/site-model.mjs";
import { flagTitle } from "../../lib/site.mjs";
import SiteNav from "./site-nav";
import { Chip, STATUS, Widget, ZonePanel } from "./zone-panel";
import "./site-view.css";

const POLL_MS = 3000;
// Until the first successful load every derivation runs on empty data; the error card says why.
const EMPTY_STATE = { site: null, flags: [], evidence: [], inspections: [], plans: [], tasks: [], crews: [] };

function zoneFromPath(pathname) {
  const match = pathname.match(/^\/zones\/([^/]+)/);
  if (!match) return null;
  try { return decodeURIComponent(match[1]); } catch { return match[1]; }
}

function useLiveState(initial) {
  const [state, setState] = useState(initial);
  const [live, setLive] = useState(() => ({ ok: Boolean(initial), at: Date.now() }));
  useEffect(() => {
    let stopped = false;
    let timer;
    const tick = async () => {
      if (document.visibilityState === "visible") {
        try {
          const response = await fetch("/api/site-state", { cache: "no-store" });
          const body = await response.json();
          if (!response.ok || !body.data) throw new Error(body.error);
          if (!stopped) { setState(body.data); setLive({ ok: true, at: Date.now() }); }
        } catch {
          if (!stopped) setLive((previous) => ({ ...previous, ok: false }));
        }
      }
      if (!stopped) timer = setTimeout(tick, POLL_MS);
    };
    timer = setTimeout(tick, POLL_MS);
    return () => { stopped = true; clearTimeout(timer); };
  }, []);
  return [state, live];
}

function LiveBadge({ live }) {
  const [, force] = useState(0);
  useEffect(() => { const t = setInterval(() => force((n) => n + 1), 1000); return () => clearInterval(t); }, []);
  // eslint-disable-next-line react-hooks/purity -- the badge re-renders every second on purpose
  const age = Math.max(0, Math.round((Date.now() - live.at) / 1000));
  return (
    <span className={`live ${live.ok ? "on" : "off"}`} role="status">
      <i aria-hidden="true" />{live.ok ? `Live · ${age < 2 ? "just now" : `${age}s ago`}` : "API unreachable · retrying"}
    </span>
  );
}

function ZoneBrowser({ zones, index, state, current }) {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const matches = (zone) => !q || zone.id.toLowerCase().includes(q) || zone.name.toLowerCase().includes(q);
  const building = zones[0];
  if (!building) return null;
  const floors = [...building.children].reverse();
  return (
    <Widget title="Zones" aside={<span className="meta">click, search or share a link</span>}>
      <label className="search">
        <span className="sr-only">Filter zones</span>
        <input type="search" placeholder="Filter, e.g. 3B or bath" value={query} onChange={(event) => setQuery(event.target.value)} />
      </label>
      <div className="zone-tree">
        {floors.map((floor) => {
          const units = floor.children.filter((unit) => matches(unit) || unit.children.some(matches));
          if (q && !matches(floor) && units.length === 0) return null;
          return (
            <div key={floor.id} className="zt-floor">
              <ZoneLink zone={floor} index={index} state={state} current={current} />
              {units.map((unit) => (
                <div key={unit.id} className="zt-unit">
                  <ZoneLink zone={unit} index={index} state={state} current={current} />
                  {(q || current?.startsWith(unit.id)) && (
                    <div className="zt-rooms">
                      {unit.children.filter((room) => !q || matches(room) || matches(unit)).map((room) => (
                        <ZoneLink key={room.id} zone={room} index={index} state={state} current={current} small />
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </Widget>
  );
}

function ZoneLink({ zone, index, state, current, small }) {
  const status = zoneStatus(index, state, zone.id);
  return (
    <Link href={`/zones/${encodeURIComponent(zone.id)}`} className={`zl${small ? " small" : ""}${current === zone.id ? " cur" : ""}`}
      aria-current={current === zone.id ? "page" : undefined}>
      <i className={`dot s-${status}`} aria-hidden="true" /><span className="mono">{zone.id}</span><span className="zl-name">{zone.name}</span>
    </Link>
  );
}

function OverviewPanel({ index, state, geometry, changes }) {
  const flags = state.flags || [];
  return (
    <div className="widgets">
      <Widget wide title="Needs attention" aside={<Chip tone={flags.length ? "crit" : "ok"}>{flags.length} open Flag{flags.length === 1 ? "" : "s"}</Chip>}>
        {flags.length === 0 ? <p className="empty">No open Flags. Rules re-check whenever work is announced or evidence is reviewed.</p> : (
          <ul className="attention">
            {flags.map((flag) => (
              <li key={flag.id}>
                <Link href={`/zones/${encodeURIComponent(flag.zone_id)}`}>
                  <span className="flag-id">Flag {flag.type}</span> {flagTitle(flag)}
                </Link>
                <p className="meta">{flag.explanation}</p>
                <Link className="flag-link" href={`/flags/${flag.id}`}>Flag detail →</Link>
              </li>
            ))}
          </ul>
        )}
      </Widget>
      <Widget title="Floors">
        <ul className="floors">
          {[...geometry].sort((a, b) => b.floor_elevation_m - a.floor_elevation_m).map((plan) => {
            const status = zoneStatus(index, state, plan.floor_id);
            return (
              <li key={plan.floor_id}>
                <Link href={`/zones/${plan.floor_id}`}>
                  <i className={`dot s-${status}`} aria-hidden="true" /><strong>{plan.floor_id}</strong>
                  <span className="meta">{plan.plan_id} · Rev {plan.label} · +{plan.floor_elevation_m.toFixed(1)} m</span>
                </Link>
              </li>
            );
          })}
        </ul>
        {changes.length > 0 && (
          <p className="meta">Rev changes: {changes.map((c) => `${c.element.element_id} ${c.change}`).join(", ")}</p>
        )}
      </Widget>
    </div>
  );
}

export default function SiteView({ model, initialState, error }) {
  const pathname = usePathname();
  const router = useRouter();
  const zoneId = zoneFromPath(pathname);
  const index = useMemo(() => indexZones(model?.zones), [model]);
  const [liveState, live] = useLiveState(initialState);
  const state = liveState || EMPTY_STATE;
  const geometry = useMemo(() => model?.geometry || [], [model]);
  const changes = useMemo(() => revisionChanges(model), [model]);

  const route = useMemo(() => viewForZone(index, zoneId), [index, zoneId]);
  const [override, setOverride] = useState({ key: null, mode: null });
  const [overviewMode, setOverviewMode] = useState("orbit");
  const mode = zoneId ? (override.key === zoneId ? override.mode : route.mode) : overviewMode;
  const setMode = (next) => (zoneId ? setOverride({ key: zoneId, mode: next }) : setOverviewMode(next));
  const [filters, setFilters] = useState({ status: true, changes: true, context: true });
  const [panelOpen, setPanelOpen] = useState(true);
  const [copied, setCopied] = useState(false);
  const [webglError, setWebglError] = useState(null);

  const stageRef = useRef(null);
  const sceneRef = useRef(null);
  const tipRef = useRef(null);
  const calloutRefs = useRef(new Map());
  const sideRef = useRef(null);

  const selectZone = useCallback((id) => {
    router.push(id ? `/zones/${encodeURIComponent(id)}` : "/site", { scroll: false });
  }, [router]);

  const [sceneReady, setSceneReady] = useState(0);
  const selectZoneRef = useRef(selectZone);
  const stateRef = useRef(state);
  useEffect(() => { selectZoneRef.current = selectZone; stateRef.current = state; });

  // Build the scene once per model. Dynamic import keeps Three.js out of the server bundle.
  useEffect(() => {
    if (!stageRef.current || !geometry.length) return undefined;
    let scene;
    let cancelled = false;
    import("./site-scene").then(({ createSiteScene }) => {
      if (cancelled || !stageRef.current) return;
      try {
        scene = createSiteScene(stageRef.current, {
          geometry, zones: index, changes,
          onSelect: (id) => selectZoneRef.current(id),
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
        setSceneReady((n) => n + 1);
      } catch (failure) {
        setWebglError(failure?.message || "WebGL is not available");
      }
    });
    return () => { cancelled = true; scene?.dispose(); sceneRef.current = null; };
  }, [geometry, index, changes]);

  // A new selection starts the panel at its Status widget. Keyed on the route only, so polling never scrolls.
  // If the selection came from inside the panel (the Zones list), focus moves to the Status heading so keyboard
  // users land on the answer instead of on a link that scrolled away.
  const lastZone = useRef(zoneId);
  useEffect(() => {
    if (lastZone.current === zoneId) return;
    lastZone.current = zoneId;
    const side = sideRef.current;
    if (!side) return;
    const fromPanel = side.contains(document.activeElement);
    side.scrollTop = 0;
    const heading = side.querySelector(".widget-head h3");
    if (fromPanel && heading) { heading.tabIndex = -1; heading.focus(); }
  }, [zoneId]);

  // Route-derived view: isolation, camera mode, highlight and focus.
  const focus = useMemo(() => (route.highlight ? focusBounds(index, geometry, route.highlight) : null), [index, route, geometry]);
  useEffect(() => {
    sceneRef.current?.setView({ floorId: route.floorId, mode, highlight: route.highlight, focus: route.floorId && route.highlight !== route.floorId ? focus : null });
  }, [route.floorId, route.highlight, mode, focus, sceneReady]);

  // Status colours follow API data.
  useEffect(() => {
    sceneRef.current?.setStatus(sceneStatus(index, state, geometry));
  }, [state, index, geometry, sceneReady]);

  useEffect(() => { sceneRef.current?.setFilters(filters); }, [filters, sceneReady]);
  // The information panel floats over the stage's right side on desktop: shift the projection so the subject
  // stays clear of it (narrow layouts put the panel below the canvas, so no shift there). Also re-lays out callouts.
  const panelRef = useRef(null);
  useEffect(() => {
    const panel = panelRef.current;
    const viewport = stageRef.current;
    if (!panel || !viewport) return;
    return observeRightOverlay(panel, viewport, (coveredRight) => {
      sceneRef.current?.setCoveredRight(coveredRight);
      sceneRef.current?.refresh();
    });
  }, [panelOpen, sceneReady]);

  // Anchored callouts: open Flags (on their flagged element if there is one), revision changes, pending inspections.
  const callouts = useMemo(() => buildCallouts({ state, geometry, index, changes, showChanges: filters.changes, route }),
    [state, geometry, index, changes, filters.changes, route]);

  useEffect(() => {
    sceneRef.current?.setOverlays(callouts.map((c) => ({ el: calloutRefs.current.get(c.key), anchor: c.anchor, floorId: c.floorId, below: c.below, target: c.target, tone: c.tone })));
  }, [callouts, sceneReady]);

  // Briefly mark Flags that appeared while the page was open.
  const [seenFlags] = useState(() => new Set((initialState?.flags || []).map((flag) => flag.id)));
  const newFlagIds = useMemo(() => new Set((state.flags || []).map((flag) => flag.id).filter((id) => !seenFlags.has(id))), [state.flags, seenFlags]);

  const details = zoneId && route.known ? zoneDetails(index, state, zoneId) : null;
  const building = model?.zones?.[0];
  const timezone = state.site?.timezone || "Europe/Vienna";
  const floorsDesc = [...geometry].sort((a, b) => b.floor_elevation_m - a.floor_elevation_m);
  const plansLabel = geometry.map((plan) => `${plan.plan_id} Rev ${plan.label}`).join(" · ");

  const copyLink = async () => {
    try { await navigator.clipboard.writeText(window.location.href); setCopied(true); setTimeout(() => setCopied(false), 1600); } catch { /* clipboard unavailable */ }
  };

  if (error || !model) return <Shell live={live}><Unavailable error={error} /></Shell>;

  const openFlags = (state.flags || []).length;
  const unconfirmed = (state.evidence || []).filter((record) => record.review_status === "unconfirmed").length;
  const context = zoneId || "Site";
  // The collapsed pill counts the Flags of the current context: the selected zone, or the whole site.
  const contextFlags = details ? details.flags.length : openFlags;

  return (
    <Shell live={live}>
      <div className={`sv-stage${panelOpen ? "" : " collapsed"}`}>
        <div className="sv-viewport">
          <div ref={stageRef} className="sv-canvas" />
          {!geometry.length && (
            <div className="sv-state panel overlay">
              <h1>No plan geometry imported yet</h1>
              <p>The 3D view is generated only from imported DXF plans. Run <code>docker compose exec api python -m app.cad_import</code>, then reload.</p>
            </div>
          )}
          {webglError && <div className="sv-state panel overlay"><h1>3D view unavailable</h1><p>{webglError}. Zone details stay available in the information panel.</p></div>}

          {route.known && <div className={`callouts${route.highlight && route.highlight !== route.floorId ? " compact" : ""}`} aria-label="Plan callouts">
            {callouts.map((c) => (
              <div key={c.key} ref={(el) => (el ? calloutRefs.current.set(c.key, el) : calloutRefs.current.delete(c.key))} className={`callout t-${c.tone}`} style={{ visibility: "hidden" }}>
                <button type="button" onClick={() => selectZone(c.target)}>
                  <strong>{c.title}</strong><span>{c.text}</span><em className="pin" aria-hidden="true">{c.short}</em>
                </button>
              </div>
            ))}
          </div>}
          <div ref={tipRef} className="hover-tip" hidden><strong /><span /></div>
          {zoneId && !route.known && (
            <div className="sv-state panel overlay" role="alert">
              <h1>Zone “{zoneId}” is not in the site record</h1>
              <p>Check the link, or choose a zone from the list. Nothing was changed.</p>
              <Link className="btn btn-acc" href="/site">Back to the building</Link>
            </div>
          )}
        </div>

        <div className="stage-card panel" data-reserve>
          {zoneId && !route.known ? (
            <>
              <p className="crumbs mono"><Link href="/site">{building?.id}</Link> / ?</p>
              <h1>Unknown zone</h1>
            </>
          ) : details ? (
            <>
              <p className="crumbs mono">
                {details.path.map((zone, i) => (
                  <span key={zone.id}>{i > 0 && " / "}{zone.id === zoneId ? zone.id : <Link href={zone.kind === "building" ? "/site" : `/zones/${zone.id}`}>{zone.id}</Link>}</span>
                ))}
              </p>
              <h1>{details.zone.name}</h1>
              <p className="meta mono">{details.plan ? `${details.plan.id} · Rev ${details.plan.current_revision?.label} · ` : ""}/zones/{zoneId}</p>
              <button type="button" className="ghost-btn" onClick={copyLink}>{copied ? "Link copied" : "Copy share link"}</button>
            </>
          ) : (
            <>
              <p className="crumbs mono">{state.site?.name || "Site"}</p>
              <h1>{building?.name || "Building"}</h1>
              <p className="meta mono">{plansLabel}</p>
            </>
          )}
        </div>

        {/* Desktop: floating glass controls on the stage. Narrow: in document flow under the canvas (no overlap). */}
        <div className="stage-dock">
          <div className="floor-rail panel" data-reserve>
            <nav aria-label="Floor isolation">
              <Link href="/site" className={!route.floorId ? "cur" : ""} aria-current={!route.floorId ? "page" : undefined} title="Whole building">All</Link>
              {floorsDesc.map((plan) => {
                const status = zoneStatus(index, state, plan.floor_id);
                return (
                  <Link key={plan.floor_id} href={`/zones/${plan.floor_id}`} className={route.floorId === plan.floor_id ? "cur" : ""}
                    aria-current={route.floorId === plan.floor_id ? "true" : undefined} title={`Isolate floor ${plan.floor_id} · ${STATUS[status].text}`}>
                    {plan.floor_id}<i className={`dot s-${status}`} aria-hidden="true" />
                  </Link>
                );
              })}
            </nav>
            <span className="rail-sep" aria-hidden="true" />
            <div role="toolbar" aria-label="Camera" className="rail-tools">
              <button type="button" className="mode" aria-pressed={mode === "top"} onClick={() => setMode("top")} title="Top-down plan view">2D</button>
              <button type="button" className="mode" aria-pressed={mode === "orbit"} onClick={() => setMode("orbit")} title="3D orbit view">3D</button>
              <span className="rail-sep" aria-hidden="true" />
              <button type="button" className="icon" aria-label="Zoom in" onClick={() => sceneRef.current?.zoom(0.7)}>+</button>
              <button type="button" className="icon" aria-label="Zoom out" onClick={() => sceneRef.current?.zoom(1.4)}>−</button>
              <button type="button" className="icon" aria-label="Recenter view" title="Recenter" onClick={() => sceneRef.current?.recenter()}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><circle cx="8" cy="8" r="2.5" /><path d="M8 1.5v3M8 11.5v3M1.5 8h3M11.5 8h3" /></svg>
              </button>
            </div>
          </div>

          <details className="legend panel" data-reserve>
            <summary>
              <span className="sw-row" aria-hidden="true"><i className="sw crit" /><i className="sw warn" /><i className="sw sel" /><i className="sw ghost" /></span>
              Layers &amp; key<span className="meta"> · scenery is decorative</span>
            </summary>
            <div className="legend-body">
              <div role="group" aria-label="Layers" className="layer-toggles">
                {[["status", "Status"], ["changes", "Rev diff"], ["context", "Context"]].map(([key, text]) => (
                  <button key={key} type="button" className="toggle" aria-pressed={filters[key]} onClick={() => setFilters((f) => ({ ...f, [key]: !f[key] }))}>{text}</button>
                ))}
              </div>
              <span><i className="sw crit" />Open Flag</span>
              <span><i className="sw warn" />Inspection not confirmed</span>
              <span><i className="sw sel" />Selected</span>
              <span><i className="sw ghost" />Previous revision</span>
              <span><i className="sw pipe" />Drain</span>
              <p>Building, walls, rooms, door openings, fixtures and drains: imported DXF geometry ({geometry.length} plans). Schematic: fixture sizes, door leaves, swing arcs, lintels, the slab edge overhang, surface textures (concrete, plaster) and contact shading. Decorative context, not plan data: crane, scaffold, fence, street, vehicles, materials, trees and neighbouring buildings.</p>
            </div>
          </details>

          <nav className="quick-dock panel" data-reserve aria-label="Quick actions">
            <Link href="/flags"><i style={{ background: "var(--crit-solid)" }} aria-hidden="true" />Open flags ({openFlags})</Link>
            <Link href="/evidence"><i style={{ background: "var(--muted)" }} aria-hidden="true" />Review evidence{unconfirmed ? ` (${unconfirmed})` : ""}</Link>
            <Link href="/chat"><i style={{ background: "var(--blue)" }} aria-hidden="true" />Ask GroundIQ</Link>
          </nav>
        </div>

        <aside ref={panelRef} className="sv-side" data-reserve aria-label="Zone information">
          {panelOpen ? (
            <div className="side-card panel">
              <div className="side-head">
                <div>
                  <p className="mono meta">{details ? details.path.slice(0, -1).map((zone) => zone.id).join(" / ") : building?.id}</p>
                  <h2>{details ? `Zone ${zoneId}` : "Site overview"}</h2>
                </div>
                <button type="button" className="collapse-btn" aria-expanded="true" aria-label="Collapse information panel" onClick={() => setPanelOpen(false)}>⟫</button>
              </div>
              <div className="side-scroll" ref={sideRef}>
                {details ? <ZonePanel details={details} timezone={timezone} changes={changes} newFlagIds={newFlagIds} now={live.at} />
                  : <OverviewPanel index={index} state={state} geometry={geometry} changes={changes} />}
                <ZoneBrowser zones={model.zones} index={index} state={state} current={zoneId} />
              </div>
            </div>
          ) : (
            <button type="button" className="side-pill panel" aria-expanded="false" onClick={() => setPanelOpen(true)}
              aria-label={`Expand information panel: ${context}, ${contextFlags} open Flag${contextFlags === 1 ? "" : "s"}`}>
              <span aria-hidden="true" className="chev">⟪</span>
              <span className={`count${contextFlags ? "" : " none"}`} aria-hidden="true">{contextFlags}</span>
              <span className="mono vertical" aria-hidden="true">{context}</span>
            </button>
          )}
        </aside>
      </div>
    </Shell>
  );
}

const RETRY_S = 10;

// First load failed: keep the product layout (empty stage, panel placeholders) and retry the server render.
function Unavailable({ error }) {
  const router = useRouter();
  const [left, setLeft] = useState(RETRY_S);
  useEffect(() => {
    const t = setInterval(() => setLeft((n) => {
      if (n > 1) return n - 1;
      router.refresh();
      return RETRY_S;
    }), 1000);
    return () => clearInterval(t);
  }, [router]);
  return (
    <div className="sv-stage sv-offline">
      <div className="sv-viewport" />
      <div className="sv-state panel overlay" role="alert">
        <p className="crumbs mono">GET /zones · /plans · /geometry</p>
        <h1>Site model unavailable</h1>
        <p>{error || "The API returned no site model."} Nothing was changed; the view only reads the site record.</p>
        <div className="retry-row">
          <button type="button" className="btn btn-acc" onClick={() => { setLeft(RETRY_S); router.refresh(); }}>Retry now</button>
          <span className="meta" aria-live="polite">Retrying automatically in {left} s</span>
        </div>
      </div>
      <aside className="sv-side" aria-label="Zone information">
        <div className="side-card panel">
          <div className="side-scroll">
            {["Needs attention", "Floors", "Zones"].map((title) => (
              <Widget key={title} title={title}><p className="empty">Waiting for the API.</p><div aria-hidden="true"><div className="skel" /><div className="skel" style={{ width: "70%" }} /></div></Widget>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}

function Shell({ live, children }) {
  return (
    <div className="sv theme-light">
      <SiteNav current="site"><LiveBadge live={live} /></SiteNav>
      {children}
    </div>
  );
}
