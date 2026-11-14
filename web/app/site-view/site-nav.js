import Link from "next/link";

/** Dark top bar shared by the site model and the Flag detail page. */
export default function SiteNav({ current, children }) {
  return (
    <header className="sv-nav">
      <Link href="/site" className="brand" aria-label="Site model home">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/groundiq-logo-white.svg" alt="GroundIQ" />
      </Link>
      <nav aria-label="Main">
        <Link href="/">Dashboard</Link>
        <Link href="/site" className={current === "site" ? "cur" : undefined} aria-current={current === "site" ? "page" : undefined}>Site model</Link>
      </nav>
      <div className="nav-right">
        {children}
        <span className="demo">Synthetic demo data</span>
      </div>
    </header>
  );
}
