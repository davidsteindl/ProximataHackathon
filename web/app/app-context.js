"use client";

import { createContext, useContext, useMemo, useSyncExternalStore } from "react";
import { scenarioTime } from "../lib/site.mjs";

// Demo role switcher with synthetic identities. Not authentication: the API validates role and person.
const SUPERINTENDENT = "superintendent:synthetic-superintendent";
const KEY = "groundiq-demo-role";
const listeners = new Set();
let memory = SUPERINTENDENT; // used when browser storage is unavailable

function readIdentity() {
  try { return localStorage.getItem(KEY) || memory; } catch { return memory; }
}
function writeIdentity(value) {
  memory = value;
  try { localStorage.setItem(KEY, value); } catch { /* private mode: keep it for this tab only */ }
  listeners.forEach((listener) => listener());
}
function subscribe(listener) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => { listeners.delete(listener); window.removeEventListener("storage", listener); };
}

const AppContext = createContext(null);

export function AppProvider({ site, crews, children }) {
  const stored = useSyncExternalStore(subscribe, readIdentity, () => SUPERINTENDENT);
  const value = useMemo(() => {
    const leads = [...new Map((crews || []).map((crew) => [crew.lead.id, { ...crew.lead, trade: crew.trade }])).values()];
    // A stored Crew Lead who no longer exists in the site record falls back to the Superintendent.
    const identity = stored === SUPERINTENDENT || leads.some((lead) => stored === `crew_lead:${lead.id}`) ? stored : SUPERINTENDENT;
    const [role, actor] = identity.split(":");
    return { site, leads, identity, role, actor, lead: leads.find((lead) => lead.id === actor), setIdentity: writeIdentity };
  }, [site, crews, stored]);
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  return useContext(AppContext) || { site: null, leads: [], identity: SUPERINTENDENT, role: "superintendent", actor: "synthetic-superintendent", setIdentity: writeIdentity };
}

export function RoleSwitch() {
  const { identity, leads, setIdentity } = useApp();
  return (
    <label className="role-switch" title="Demo role switcher with synthetic identities, not authentication">
      <span className="sr-only">Demo role</span>
      <select value={identity} onChange={(event) => setIdentity(event.target.value)}>
        <option value={SUPERINTENDENT}>Superintendent</option>
        {leads.map((lead) => <option key={lead.id} value={`crew_lead:${lead.id}`}>Crew Lead · {lead.name}</option>)}
      </select>
    </label>
  );
}

const minute = () => Math.floor(Date.now() / 60000);
function subscribeMinute(listener) {
  const timer = setInterval(listener, 15000);
  return () => clearInterval(timer);
}

/** Current scenario time ("Day 2 · 18:10"); client-only so server and browser never disagree. */
export function ScenarioClock() {
  const { site } = useApp();
  const now = useSyncExternalStore(subscribeMinute, minute, () => null);
  const text = now === null ? null : scenarioTime(now * 60000, site);
  return <span className="clock" aria-label="Scenario time">{text || " "}</span>;
}
