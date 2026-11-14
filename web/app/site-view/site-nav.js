import Link from "next/link";
import { RoleSwitch, ScenarioClock } from "../app-context";

const PILLS = [
  { key: "overview", href: "/", text: "Overview" },
  { key: "site", href: "/site", text: "Site plan" },
  { key: "flags", href: "/flags", text: "Flags" },
  { key: "evidence", href: "/evidence", text: "Evidence" },
];

/** Light plan-view top bar: logo, pill navigation, live status, scenario clock and demo role. */
export default function SiteNav({ current, children }) {
  return (
    <header className="sv-nav">
      <Link href="/" className="brand" aria-label="GroundIQ overview">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/groundiq-logo.svg" alt="GroundIQ" />
      </Link>
      <nav aria-label="Main" className="pills">
        {PILLS.map((pill) => (
          <Link key={pill.key} href={pill.href} className={`pill${current === pill.key ? " cur" : ""}`} aria-current={current === pill.key ? "page" : undefined}>{pill.text}</Link>
        ))}
      </nav>
      <div className="nav-right">
        {children}
        <ScenarioClock />
        <RoleSwitch />
      </div>
    </header>
  );
}
