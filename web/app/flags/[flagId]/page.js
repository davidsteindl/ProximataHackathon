import Link from "next/link";
import FlagInbox from "../../flag-inbox";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }) {
  const { flagId } = await params;
  return { title: `Flag ${flagId} · SiteMind` };
}

async function getFlag(flagId) {
  try {
    const response = await fetch(new URL(`/flags/${encodeURIComponent(flagId)}`, process.env.API_BASE_URL), {
      cache: "no-store", signal: AbortSignal.timeout(5000),
    });
    if (response.status === 404) return { flag: null, error: "This Flag does not exist." };
    if (!response.ok) throw new Error();
    const [flag, site] = await Promise.all([response.json(), fetch(new URL("/site", process.env.API_BASE_URL), { cache: "no-store" }).then((r) => r.json())]);
    return { flag, timezone: site?.timezone || "UTC", error: null };
  } catch {
    return { flag: null, error: "The Flag could not be loaded from the API." };
  }
}

// Read-only Flag detail; lifecycle actions (acknowledge, close) belong to #9.
export default async function FlagPage({ params }) {
  const { flagId } = await params;
  const { flag, timezone, error } = await getFlag(flagId);
  return (
    <main>
      <p><Link href="/site">← Site model</Link>{flag && <> · <Link href={`/zones/${encodeURIComponent(flag.zone_id)}`}>Zone {flag.zone_id} in 3D</Link></>}</p>
      {error ? <p role="alert">{error}</p> : <FlagInbox flags={[flag]} timezone={timezone} title={`Flag ${flag.type} · ${flag.zone_id}`} expanded />}
    </main>
  );
}
