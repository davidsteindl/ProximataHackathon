// Activity feed reads (#37). The feed is a read-only projection served by `api`.

export const FEED_POLL_MS = 5000;

/** Dashboard filters (zone id, YYYY-MM-DD dates in UTC) → REST query for GET /feed. */
export function feedQuery({ zoneId, fromDate, toDate, cursor, limit } = {}) {
  const query = new URLSearchParams();
  if (zoneId) query.set("zone_id", zoneId);
  if (fromDate) query.set("from_time", `${fromDate}T00:00:00Z`);
  if (toDate) query.set("to_time", `${toDate}T00:00:00Z`);
  if (cursor) query.set("cursor", cursor);
  if (limit) query.set("limit", String(limit));
  return query;
}

export async function getFeed(baseUrl, filters = {}) {
  try {
    const response = await fetch(new URL(`/feed?${feedQuery(filters)}`, baseUrl), {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) {
      return { data: null, error: response.status === 404 ? "Unknown zone." : "The activity feed could not be loaded." };
    }
    return { data: await response.json(), error: null };
  } catch {
    return { data: null, error: "The activity feed could not be loaded." };
  }
}

/** Reload the complete visible prefix; entries and its paging cursor form one snapshot. */
export async function readFeedPages(loadPage, pageCount = 1) {
  const entries = new Map();
  let cursor = null;
  for (let page = 0; page < pageCount; page += 1) {
    const result = await loadPage(cursor);
    if (result.error) throw new Error(result.error);
    for (const entry of result.data.entries) entries.set(entry.id, entry);
    cursor = result.data.next_cursor;
    if (!cursor) break;
  }
  return { entries: [...entries.values()], next_cursor: cursor };
}

export const kindLabels = {
  event: "Event",
  revision: "Revision",
  evidence_decision: "Evidence decision",
  task_completed: "Task completed",
  flag_change: "Flag",
  proposal: "Proposal",
};

// How much an entry can be trusted (PLAN §3.2). Unconfirmed statements never read as facts.
export const confirmationLabels = {
  unconfirmed: "Unconfirmed statement",
  confirmed: "Confirmed by a human",
  rejected: "Rejected by a human",
  deterministic: "Deterministic plan diff",
  seed: "Seed baseline",
  human: "Human action",
  system: "Rule engine",
  advice: "Agent advice, not approved",
};

const roleLabels = {
  superintendent: "Superintendent",
  crew_lead: "Crew Lead",
  crew: "Crew",
  architect: "Architect",
  inspector: "Inspector",
  system: "System",
  agent: "Agent",
  unknown: "Unknown sender",
};

/** Short provenance line: role, channel and trade. Never a person (PLAN §6). */
export function entryContext(entry) {
  return [
    roleLabels[entry.actor_role] || entry.actor_role,
    entry.channel,
    entry.trade,
    entry.zone_ids.length ? entry.zone_ids.join(", ") : "Zone unresolved",
  ].filter(Boolean).join(" · ");
}
