import Link from "next/link";
import { getHealth } from "../lib/health.mjs";
import { getSiteOverview } from "../lib/site.mjs";
import SiteOverview from "./site-overview";

export const dynamic = "force-dynamic";

export default async function Home({ searchParams }) {
  const params = await searchParams;
  const singleValue = (value) => typeof value === "string" ? value : "";
  const filters = {
    zoneId: singleValue(params?.zone),
    fromDate: singleValue(params?.from),
    toDate: singleValue(params?.to),
  };
  const [health, overview] = await Promise.all([
    getHealth(process.env.API_BASE_URL),
    getSiteOverview(process.env.API_BASE_URL, filters),
  ]);

  return (
    <main>
      <h1>SiteMind</h1>
      <p><Link href="/site">Open the 3D site model →</Link></p>
      <div className="health">
        <h2>Service health</h2>
        <dl>
          <dt>API</dt><dd>{health.api}</dd>
          <dt>Database</dt><dd>{health.db}</dd>
        </dl>
      </div>
      {overview.error ? <p role="alert">{overview.error} <Link href="/">Clear filters</Link></p> : (
        <SiteOverview data={overview.data} filters={filters} />
      )}
      <p>Reload this page to update the site record.</p>
    </main>
  );
}
