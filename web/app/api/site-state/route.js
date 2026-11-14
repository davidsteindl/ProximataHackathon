import { getSiteState } from "../../../lib/site-data.mjs";

export const dynamic = "force-dynamic";

/** Polled by the 3D view so status colours follow Flag changes without a reload. */
export async function GET() {
  const result = await getSiteState(process.env.API_BASE_URL);
  return Response.json(result, { status: result.error ? 502 : 200, headers: { "cache-control": "no-store" } });
}
