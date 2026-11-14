import Link from "next/link";
import { getHealth } from "../../lib/health.mjs";
import { flattenZones, getSiteOverview, label, scenarioTime } from "../../lib/site.mjs";
import EventTimeline from "../event-timeline";
import SiteKnowledge from "../site-knowledge";
import { StatePanel, WorkShell } from "../shell";

export const dynamic = "force-dynamic";
export const metadata = { title: "Activity" };

export default async function ActivityPage({ searchParams }) {
  const params = await searchParams;
  const single = (value) => (typeof value === "string" ? value : "");
  const filters = { zoneId: single(params?.zone), fromDate: single(params?.from), toDate: single(params?.to) };
  const [health, overview] = await Promise.all([
    getHealth(process.env.API_BASE_URL),
    getSiteOverview(process.env.API_BASE_URL, filters),
  ]);
  const data = overview.data;
  return (
    <WorkShell current="activity">
      <div className="page-head">
        <h1>Activity</h1>
        <span className="muted small">Events, schedule, plans and inspections from the site record.</span>
        <span className="push mono muted">API {health.api} · DB {health.db}</span>
      </div>
      {overview.error ? (
        <section className="panel"><StatePanel kind="error" title="Site data unavailable" action={<Link className="btn btn-acc" href="/activity">Clear filters and retry</Link>}>{overview.error}</StatePanel></section>
      ) : !data.site ? (
        <section className="panel"><StatePanel title="No site data loaded yet">Run the seed import, then reload.</StatePanel></section>
      ) : <Activity data={data} filters={filters} />}
    </WorkShell>
  );
}

function Activity({ data, filters }) {
  const { site, zones, tasks, crews, plans, inspections, events } = data;
  const crewNames = Object.fromEntries(crews.map((crew) => [crew.id, crew.name]));
  const at = (value) => scenarioTime(value, site);
  return (
    <div className="stack" style={{ gap: 16 }}>
      <form method="get" className="panel pad" aria-label="Schedule and timeline filters" style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label className="field">Zone and descendants
          <select name="zone" defaultValue={filters.zoneId}>
            <option value="">All zones</option>
            {flattenZones(zones).map((zone) => <option key={zone.id} value={zone.id}>{"— ".repeat(zone.depth)}{zone.id} · {zone.name}</option>)}
          </select>
        </label>
        <label className="field">From date (UTC, inclusive)<input name="from" type="date" defaultValue={filters.fromDate} /></label>
        <label className="field">Before date (UTC, exclusive)<input name="to" type="date" defaultValue={filters.toDate} /></label>
        <button type="submit" className="btn btn-acc">Apply filters</button>
        <Link className="link small" href="/activity" style={{ alignSelf: "center" }}>Clear filters</Link>
        <p className="form-note" style={{ flexBasis: "100%" }}>Filters apply to the schedule and the event timeline. Timeline dates refer to source message times. Scenario day 1: {site.start_date} ({site.timezone}).</p>
      </form>

      <div className="grid-main">
        <EventTimeline events={events} site={site} crewNames={crewNames} />
        <section className="panel" aria-labelledby="schedule-title">
          <h2 id="schedule-title">Schedule</h2>
          {tasks.length === 0 ? <p className="pad small muted" style={{ margin: 0 }}>No tasks in this zone and time range.</p> : tasks.map((task) => (
            <div key={task.id} className="row">
              <span className="small"><strong>{task.name}</strong><br /><span className="mono muted">{at(task.starts_at)} – {at(task.ends_at)}</span></span>
              <span className="small muted" style={{ textAlign: "right" }}><span className="mono">{task.zone_id}</span><br />{crewNames[task.crew_id] || task.crew_id}</span>
            </div>
          ))}
        </section>
      </div>

      <SiteKnowledge knowledge={data.knowledge} metric={data.feedbackMetric} timezone={site.timezone} />

      <div className="grid-main">
        <section className="panel" aria-labelledby="plans-title">
          <h2 id="plans-title">Plans and revisions</h2>
          <p className="pad small muted" style={{ margin: 0, paddingBottom: 0 }}>Revision-note zones are unconfirmed; DXF plan diffs determine affected zones geometrically. Neither confirms crew receipt.</p>
          {plans.map((plan) => (
            <div key={plan.id} className="pad" style={{ borderBottom: "1px solid var(--line-soft)" }}>
              <h3 style={{ fontSize: 14 }}>{plan.id} · {plan.name} · <span className="mono">{plan.floor_id}</span> <span className="muted small">current Rev {plan.current_revision?.label || "none"}</span></h3>
              <ul className="ev-list" style={{ marginTop: 8 }}>{plan.revisions.map((revision) => (
                <li key={revision.id} className="small">
                  <strong>Rev {revision.label}</strong> · <span className="mono muted">{revision.file_name || "revision note, no drawing imported"}</span> · zones {revision.zone_ids.join(", ") || "none"}
                  {revision.acknowledgments.length === 0 ? <span className="muted"> · no crew acknowledgment</span>
                    : revision.acknowledgments.map((ack) => <span key={ack.crew_id} className="muted"> · {crewNames[ack.crew_id]} acknowledged {at(ack.acknowledged_at)}</span>)}
                </li>
              ))}</ul>
            </div>
          ))}
        </section>
        <div className="stack" style={{ gap: 16 }}>
          <section className="panel" aria-labelledby="inspections-title">
            <h2 id="inspections-title">Inspections</h2>
            {inspections.map((inspection) => (
              <div key={inspection.id} className="row">
                <span className="small"><strong>{label(inspection.kind)}</strong> · <span className="mono">{inspection.zone_id}</span><br /><span className="mono muted">{at(inspection.scheduled_at)}</span></span>
                <span className="small muted">recorded {inspection.status}</span>
              </div>
            ))}
            <p className="pad form-note">A recorded result is separate from the Evidence review status.</p>
          </section>
          <section className="panel" aria-labelledby="crews-title">
            <h2 id="crews-title">Crews</h2>
            {crews.map((crew) => <div key={crew.id} className="row small"><span>{crew.name} · {crew.trade}</span><span className="muted">Crew Lead: {crew.lead.name}</span></div>)}
          </section>
        </div>
      </div>
    </div>
  );
}
