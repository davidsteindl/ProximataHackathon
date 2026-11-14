// REST reads for the 3D site view. Only `api` touches the database; web reads through it.

async function getJson(baseUrl, path) {
  const response = await fetch(new URL(path, baseUrl), { cache: "no-store", signal: AbortSignal.timeout(5000) });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

const STATE_PATHS = ["site", "flags", "evidence", "inspections", "plans", "tasks", "crews"];

/** Mutable site status, polled by the browser through /api/site-state. */
export async function getSiteState(baseUrl) {
  try {
    const values = await Promise.all(STATE_PATHS.map((path) => getJson(baseUrl, `/${path}`)));
    return { data: Object.fromEntries(STATE_PATHS.map((path, i) => [path, values[i]])), error: null };
  } catch {
    return { data: null, error: "Site status could not be loaded from the API." };
  }
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
