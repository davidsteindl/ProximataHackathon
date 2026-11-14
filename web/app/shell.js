import Link from "next/link";
import { RoleSwitch, ScenarioClock } from "./app-context";

const svg = { width: 16, height: 16, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true };
export const ICONS = {
  overview: <svg {...svg}><path d="M2.5 8.2 8 3l5.5 5.2M4.2 7.4V13h7.6V7.4" /></svg>,
  site: <svg {...svg}><rect x="2.5" y="2.5" width="11" height="11" rx="1.5" /><path d="M8 2.5V8h5.5M2.5 10.8H8V8" /></svg>,
  flags: <svg {...svg}><path d="M4.2 13.5V2.8h8l-1.8 2.7 1.8 2.7h-8" /></svg>,
  evidence: <svg {...svg}><rect x="3" y="2.2" width="10" height="11.6" rx="1.5" /><path d="m5.6 8.4 1.8 1.8 3.2-3.6" /></svg>,
  proposals: <svg {...svg}><path d="M8 2.2a4 4 0 0 1 2.4 7.2c-.5.4-.8.9-.8 1.5v.6H6.4v-.6c0-.6-.3-1.1-.8-1.5A4 4 0 0 1 8 2.2zM6.4 13.8h3.2" /></svg>,
  activity: <svg {...svg}><path d="M1.8 8.5h2.7l1.8-4.6 3.2 8.2 1.8-3.6h2.9" /></svg>,
};

export const NAV = [
  { key: "overview", href: "/", text: "Overview" },
  { key: "site", href: "/site", text: "Site plan" },
  { key: "flags", href: "/flags", text: "Flags" },
  { key: "evidence", href: "/evidence", text: "Evidence" },
  { key: "proposals", href: "/proposals", text: "Proposals" },
  { key: "activity", href: "/activity", text: "Activity" },
];

/** Dark work-view chrome: sidebar navigation, scenario clock and demo role switcher. */
export function WorkShell({ current, narrow, children }) {
  return (
    <div className="app theme-dark">
      <aside className="side">
        <Link href="/" aria-label="GroundIQ overview">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="logo" src="/groundiq-logo-white.svg" alt="GroundIQ" />
        </Link>
        <nav aria-label="Main">
          {NAV.map((item) => (
            <Link key={item.key} href={item.href} className={`nav-item${current === item.key ? " cur" : ""}`} aria-current={current === item.key ? "page" : undefined}>
              {ICONS[item.key]}{item.text}
            </Link>
          ))}
        </nav>
        <div className="side-foot">
          <ScenarioClock />
          <RoleSwitch />
          <span className="mono muted demo-note">synthetic demo data</span>
        </div>
      </aside>
      <main className={`main${narrow ? " narrow" : ""}`}>{children}</main>
    </div>
  );
}

const STATE_ICONS = {
  empty: <svg className="state-icon" width="34" height="34" viewBox="0 0 34 34" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="17" cy="17" r="13" /><path d="m11.5 17.5 4 4 7-8" /></svg>,
  error: <svg className="state-icon" width="34" height="34" viewBox="0 0 34 34" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M17 4 31 29H3z" /><path d="M17 13v7M17 24v.5" /></svg>,
  unavailable: <svg className="state-icon" width="34" height="34" viewBox="0 0 34 34" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="17" cy="17" r="13" /><path d="M10 17h14" /></svg>,
};

/** Shared empty / error / unavailable state. Errors are announced; nothing is ever implied to have changed. */
export function StatePanel({ kind = "empty", title, children, action, heading = "h2" }) {
  const Heading = heading;
  return (
    <div className={`state t-${kind}`} role={kind === "error" ? "alert" : undefined}>
      {STATE_ICONS[kind]}
      <Heading>{title}</Heading>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Skeleton({ rows = 4, label = "Loading" }) {
  return (
    <div role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skel" style={{ width: `${[70, 85, 60, 80][i % 4]}%` }} />)}
    </div>
  );
}
