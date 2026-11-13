import { getHealth } from "../lib/health.mjs";

export const dynamic = "force-dynamic";

export default async function Home() {
  const health = await getHealth(process.env.API_BASE_URL);

  return (
    <main>
      <h1>SiteMind</h1>
      <h2>Service health</h2>
      <dl>
        <dt>API</dt>
        <dd>{health.api}</dd>
        <dt>Database</dt>
        <dd>{health.db}</dd>
      </dl>
      <p>Reload this page to check again.</p>
    </main>
  );
}
