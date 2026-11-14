import Link from "next/link";
import { getHealth } from "../lib/health.mjs";
import { getFeed } from "../lib/feed.mjs";
import { flattenZones, getSiteOverview } from "../lib/site.mjs";
import ActivityFeed from "./activity-feed";
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
  const feedFilters = {
    zoneId: singleValue(params?.feed_zone),
    fromDate: singleValue(params?.feed_from),
    toDate: singleValue(params?.feed_to),
  };
  const [health, overview, feed] = await Promise.all([
    getHealth(process.env.API_BASE_URL),
    getSiteOverview(process.env.API_BASE_URL, filters),
    getFeed(process.env.API_BASE_URL, feedFilters),
  ]);
  const site = overview.data?.site;

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
      {feed.error ? <p role="alert">{feed.error} <Link href="/">Clear filters</Link></p> : site && (
        <ActivityFeed key={JSON.stringify(feedFilters)} initial={feed.data} filters={feedFilters}
          timezone={site.timezone} zones={flattenZones(overview.data.zones)} />
      )}
      {overview.error ? <p role="alert">{overview.error} <Link href="/">Clear filters</Link></p> : (
        <SiteOverview data={overview.data} filters={filters} />
      )}
      <p>The activity feed updates automatically; reload this page to update the rest of the site record.</p>
    </main>
  );
}
