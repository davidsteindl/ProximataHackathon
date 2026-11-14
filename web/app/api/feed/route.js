import { getFeed } from "../../../lib/feed.mjs";

export const dynamic = "force-dynamic";

/** Polled by the activity feed so new entries appear without a reload. */
export async function GET(request) {
  const params = new URL(request.url).searchParams;
  const result = await getFeed(process.env.API_BASE_URL, {
    zoneId: params.get("zone") || "",
    fromDate: params.get("from") || "",
    toDate: params.get("to") || "",
    cursor: params.get("cursor") || "",
  });
  return Response.json(result, { status: result.error ? 502 : 200, headers: { "cache-control": "no-store" } });
}
