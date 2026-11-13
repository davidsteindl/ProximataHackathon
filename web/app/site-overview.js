import Link from "next/link";
import { flattenZones, formatTime } from "../lib/site.mjs";

function ZoneTree({ zones }) {
  return (
    <ul>
      {zones.map((zone) => (
        <li key={zone.id}>
          <strong>{zone.id}</strong> — {zone.name} <small>({zone.kind})</small>
          {zone.kind === "floor" && (
            <span> · elevation {zone.elevation_m} m · height {zone.height_m} m</span>
          )}
          {zone.children.length > 0 && <ZoneTree zones={zone.children} />}
        </li>
      ))}
    </ul>
  );
}

export default function SiteOverview({ data, filters }) {
  const { site, zones, tasks, crews, plans, inspections } = data;
  if (!site) return <p>No site data has been loaded yet.</p>;

  const crewNames = Object.fromEntries(crews.map((crew) => [crew.id, crew.name]));
  return (
    <>
      <section aria-labelledby="site-title">
        <h2 id="site-title">{site.name}</h2>
        <p>Scenario day 1: {site.start_date}. Schedule times: {site.timezone}.</p>
        <h3>Zones</h3>
        <ZoneTree zones={zones} />
      </section>

      <section aria-labelledby="schedule-title">
        <h2 id="schedule-title">Schedule</h2>
        <form method="get">
          <label>
            Zone and descendants
            <select name="zone" defaultValue={filters.zoneId || ""}>
              <option value="">All zones</option>
              {flattenZones(zones).map((zone) => (
                <option key={zone.id} value={zone.id}>
                  {"— ".repeat(zone.depth)}{zone.id} · {zone.name}
                </option>
              ))}
            </select>
          </label>
          <label>From date (UTC, inclusive)<input name="from" type="date" defaultValue={filters.fromDate || ""} /></label>
          <label>Before date (UTC, exclusive)<input name="to" type="date" defaultValue={filters.toDate || ""} /></label>
          <button type="submit">Filter schedule</button>
          <Link href="/">Clear filters</Link>
        </form>
        {tasks.length === 0 ? <p>No tasks in this zone and time range.</p> : (
          <div className="table-scroll">
            <table>
              <thead><tr><th>Task</th><th>Zone</th><th>Crew</th><th>Start</th><th>End</th><th>Predecessors</th></tr></thead>
              <tbody>{tasks.map((task) => (
                <tr key={task.id}>
                  <td>{task.name}<small className="record-id">{task.id}</small></td>
                  <td>{task.zone_id}</td><td>{crewNames[task.crew_id] || task.crew_id}</td>
                  <td>{formatTime(task.starts_at, site.timezone)}</td>
                  <td>{formatTime(task.ends_at, site.timezone)}</td>
                  <td>{task.predecessor_ids.join(", ") || "—"}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-labelledby="crews-title">
        <h2 id="crews-title">Crews</h2>
        <ul>{crews.map((crew) => (
          <li key={crew.id}>{crew.name} · {crew.trade} · Crew Lead: {crew.lead.name}</li>
        ))}</ul>
      </section>

      <section aria-labelledby="plans-title">
        <h2 id="plans-title">Plans and revisions</h2>
        {plans.map((plan) => (
          <article key={plan.id}>
            <h3>{plan.id} · {plan.name} · {plan.floor_id}</h3>
            <p>Current revision: {plan.current_revision?.label || "None"}</p>
            <ul>{plan.revisions.map((revision) => (
              <li key={revision.id}>
                Rev {revision.label} · {revision.file_name} · zones: {revision.zone_ids.join(", ")}
                <ul>{revision.acknowledgments.map((ack) => (
                  <li key={ack.crew_id}>{crewNames[ack.crew_id]} acknowledged {formatTime(ack.acknowledged_at, site.timezone)}</li>
                ))}</ul>
                {revision.acknowledgments.length === 0 && <span> · No crew acknowledgment</span>}
              </li>
            ))}</ul>
          </article>
        ))}
      </section>

      <section aria-labelledby="inspections-title">
        <h2 id="inspections-title">Inspections</h2>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Zone</th><th>Inspection</th><th>Status</th><th>Scheduled</th></tr></thead>
            <tbody>{inspections.map((inspection) => (
              <tr key={inspection.id}>
                <td>{inspection.zone_id}</td><td>{inspection.kind.replaceAll("_", " ")}</td>
                <td>{inspection.status}</td><td>{formatTime(inspection.scheduled_at, site.timezone)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>
    </>
  );
}
