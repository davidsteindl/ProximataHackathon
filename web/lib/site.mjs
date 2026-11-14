export async function getSiteOverview(baseUrl, { zoneId, fromDate, toDate } = {}) {
  const query = new URLSearchParams();
  if (zoneId) query.set("zone_id", zoneId);
  if (fromDate) query.set("from_time", `${fromDate}T00:00:00Z`);
  if (toDate) query.set("to_time", `${toDate}T00:00:00Z`);

  const paths = {
    site: "/site",
    zones: "/zones",
    crews: "/crews",
    plans: "/plans",
    inspections: "/inspections",
    evidence: "/evidence",
    flags: "/flags",
    closedFlags: "/flags?status=closed",
    tasks: `/tasks?${query}`,
    events: `/events?${query}`,
  };
  try {
    const entries = await Promise.all(
      Object.entries(paths).map(async ([key, path]) => {
        const response = await fetch(new URL(path, baseUrl), {
          cache: "no-store",
          signal: AbortSignal.timeout(5000),
        });
        if (!response.ok) throw new Error("Site data request failed");
        return [key, await response.json()];
      }),
    );
    return { data: Object.fromEntries(entries), error: null };
  } catch {
    return { data: null, error: "Site data could not be loaded. Check the service status or adjust the schedule filters and try again." };
  }
}

export function flattenZones(zones, depth = 0) {
  return zones.flatMap((zone) => [
    { ...zone, depth },
    ...flattenZones(zone.children, depth + 1),
  ]);
}

export function formatTime(value, timezone) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: timezone,
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
