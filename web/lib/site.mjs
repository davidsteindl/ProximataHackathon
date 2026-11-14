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
    knowledge: "/site-knowledge",
    feedbackMetric: "/metrics/flag-feedback",
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

export const label = (value) => (value || "").replaceAll("_", " ");
const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);

/** Local calendar date (YYYY-MM-DD) of an instant in the site timezone. */
function localDate(value, timezone) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
}

/** Scenario day relative to the site's start date (day 1), e.g. "Day 2 · 18:10". Null without a site. */
export function scenarioTime(value, site) {
  if (!site?.start_date || !value) return null;
  const timezone = site.timezone || "UTC";
  const day = Math.round((Date.parse(localDate(value, timezone)) - Date.parse(site.start_date)) / 86400000) + 1;
  const time = new Intl.DateTimeFormat("en-GB", { timeZone: timezone, hour: "2-digit", minute: "2-digit" }).format(new Date(value));
  return `Day ${day} · ${time}`;
}

/** Human title for a Flag; type A guards work on an inspection, type B a revision receipt. */
export function flagTitle(flag) {
  if (flag.type === "B") {
    const crew = flag.context?.crew_id ? `${label(flag.context.crew_id)} crew` : "crew unresolved";
    return `Rev ${flag.context?.current_revision || "?"} receipt not confirmed: ${crew} · ${flag.zone_id}`;
  }
  return capitalize(`${label(flag.activity)} in ${flag.zone_id} before ${label(flag.precondition)}`);
}

export const SEVERITY = {
  high: { text: "Critical", tone: "crit" },
  medium: { text: "Warning", tone: "warn" },
  low: { text: "Low", tone: "unk" },
};

/** Lifecycle position for the stepper; closed states share the last step. */
export const LIFECYCLE = ["detected", "notified", "acknowledged", "in_progress", "closed"];
export function lifecycleStep(state) {
  return LIFECYCLE.indexOf(["resolved", "false_alarm"].includes(state) ? "closed" : state);
}

export const FLAG_STATE = {
  detected: { text: "Detected · awaiting notification", tone: "info" },
  notified: { text: "Notified · open", tone: "info" },
  acknowledged: { text: "Acknowledged", tone: "info" },
  in_progress: { text: "In progress", tone: "info" },
  resolved: { text: "Closed · resolved", tone: "unk" },
  false_alarm: { text: "Closed · false alarm", tone: "unk" },
};

/** Outbox message kinds (#10, #13, #14) as shown in Flag timelines. */
export const NOTIFICATION = {
  warning: "Warning",
  escalation: "Escalation to Superintendent",
  approval_request: "Approval request",
  proposal_followup: "Approved follow-up",
  compliance_reply: "Compliance reply",
};

export const isEscalated = (flag) => (flag.audit || []).some((entry) => entry.action === "escalated");

/** Morning-scan sources (#14): audit refs "schedule:<task>@<start>", one per scheduled occurrence. */
export function scheduleSources(flag) {
  const refs = new Set((flag.audit || []).map((entry) => entry.source_ref).filter((ref) => ref?.startsWith("schedule:")));
  return [...refs].map((ref) => {
    const [taskId, startsAt] = ref.slice("schedule:".length).split("@");
    return { ref, taskId, startsAt };
  });
}
