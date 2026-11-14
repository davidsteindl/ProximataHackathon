// REST reads for the 3D site view. Only `api` touches the database; web reads through it.

async function getJson(baseUrl, path) {
  const response = await fetch(new URL(path, baseUrl), { cache: "no-store", signal: AbortSignal.timeout(5000) });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

/** Parallel REST reads keyed like `paths`; any failure yields one honest error instead of partial data. */
export async function fetchAll(baseUrl, paths, error = "Site data could not be loaded from the API.") {
  try {
    const entries = await Promise.all(Object.entries(paths).map(async ([key, path]) => [key, await getJson(baseUrl, path)]));
    return { data: Object.fromEntries(entries), error: null };
  } catch {
    return { data: null, error };
  }
}

const STATE_PATHS = ["site", "flags", "evidence", "inspections", "plans", "tasks", "crews"];

/** Mutable site status, polled by the browser through /api/site-state. */
export function getSiteState(baseUrl) {
  return fetchAll(baseUrl, Object.fromEntries(STATE_PATHS.map((path) => [path, `/${path}`])), "Site status could not be loaded from the API.");
}

/**
 * Zones plus imported plan geometry: the latest imported Revision per plan and, for highlighting
 * revision changes, the next-lower Revision of that plan when its geometry was imported too.
 */
export async function getSiteModel(baseUrl) {
  try {
    const [zones, plans, current] = await Promise.all([
      getJson(baseUrl, "/zones"), getJson(baseUrl, "/plans"), getJson(baseUrl, "/geometry"),
    ]);
    const previous = {};
    await Promise.all(current.map(async (geometry) => {
      const plan = plans.find((candidate) => candidate.id === geometry.plan_id);
      const earlier = plan?.revisions.filter((revision) => revision.sequence < geometry.sequence)
        .sort((a, b) => b.sequence - a.sequence)[0];
      if (!earlier) return;
      const [match] = await getJson(baseUrl, `/geometry?revision_id=${encodeURIComponent(earlier.id)}`).catch(() => []);
      if (match) previous[geometry.plan_id] = match;
    }));
    return { data: { zones, geometry: current, previous }, error: null };
  } catch {
    return { data: null, error: "Zones and plan geometry could not be loaded from the API." };
  }
}
