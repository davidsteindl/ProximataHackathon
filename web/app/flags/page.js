import Link from "next/link";
import { fetchAll } from "../../lib/site-data.mjs";
import { FLAG_STATE, SEVERITY, flagTitle, isEscalated, scenarioTime } from "../../lib/site.mjs";
import { StatePanel, WorkShell } from "../shell";
import { Chip, EVALUATION } from "../site-view/zone-panel";

export const dynamic = "force-dynamic";
export const metadata = { title: "Flags" };

const STATUS = { open: "Open", closed: "Closed", all: "All" };
const isClosed = (flag) => ["resolved", "false_alarm"].includes(flag.state);

export default async function FlagsPage({ searchParams }) {
  const params = await searchParams;
  const status = STATUS[params?.status] ? params.status : "open";
  const zone = typeof params?.zone === "string" ? params.zone : "";
  const { data, error } = await fetchAll(process.env.API_BASE_URL, { flags: "/flags?status=all", site: "/site" }, "Flags could not be loaded from the API.");
  const all = data?.flags || [];
  const shown = all.filter((flag) => (status === "all" || (status === "closed") === isClosed(flag)) && (!zone || flag.zone_id === zone));
  const open = all.filter((flag) => !isClosed(flag));
  const zones = [...new Set(all.map((flag) => flag.zone_id))].sort();

  return (
    <WorkShell current="flags">
      <div className="page-head">
        <h1>Flags</h1>
        <form className="push" method="get" aria-label="Filter flags" style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <label className="field-row">Status
            <select name="status" defaultValue={status}>{Object.entries(STATUS).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select>
          </label>
          <label className="field-row">Zone
            <select name="zone" defaultValue={zone}><option value="">All zones</option>{zones.map((id) => <option key={id} value={id}>{id}</option>)}</select>
          </label>
          <button type="submit" className="btn">Apply</button>
        </form>
      </div>

      {error ? (
        <section className="panel"><StatePanel kind="error" title="Could not load flags" action={<Link className="btn btn-acc" href="/flags">Retry</Link>}>{error} Data may be stale; no action was lost.</StatePanel></section>
      ) : (
        <>
          <div className="grid-4">
            <Kpi label="Open" value={open.length} />
            <Kpi label="Critical" value={open.filter((flag) => flag.severity === "high").length} tone="crit" />
            <Kpi label="Awaiting human closure" value={open.filter((flag) => flag.awaiting_human_closure).length} tone="ok" />
            <Kpi label="Closed · false alarm" value={all.filter((flag) => flag.state === "false_alarm").length} tone="unk" />
          </div>
          <section className="panel" aria-label="Flag list">
            {shown.length === 0 ? (
              <StatePanel title={status === "open" ? "No open flags" : "No flags match"} action={<Link className="link small" href="/evidence">Evidence still awaiting review →</Link>}>
                {status === "open" ? "Nothing is blocked by a rule right now. New events and Evidence decisions are checked as they arrive." : "Change the filters to see more."}
              </StatePanel>
            ) : (
              <div className="table-scroll">
                <table className="t">
                  <thead><tr><th>Flag</th><th>Severity</th><th>Zone</th><th>Precondition</th><th>Status</th><th>Responsible</th></tr></thead>
                  <tbody>{shown.map((flag) => {
                    const severity = SEVERITY[flag.severity];
                    const evaluation = EVALUATION[flag.evaluation];
                    const state = FLAG_STATE[flag.state];
                    return (
                      <tr key={flag.id}>
                        <td>
                          <Link href={`/flags/${flag.id}`} className={isClosed(flag) ? "muted" : undefined}><strong>{flagTitle(flag)}</strong></Link>
                          <span className="mono muted" style={{ display: "block" }}>Flag {flag.type} · {scenarioTime(flag.created_at, data.site) || flag.created_at}</span>
                          {flag.awaiting_human_closure && <span className="small muted" style={{ display: "block" }}>Precondition satisfied. Stays open until a person closes it.</span>}
                          {flag.advice?.proposals.some((proposal) => proposal.status === "proposed") && <span className="small" style={{ display: "block", color: "var(--accent-text)" }}>Advisor proposal awaits a Superintendent decision</span>}
                        </td>
                        <td><Chip tone={isClosed(flag) ? "unk" : severity.tone}>{severity.text}</Chip>{isEscalated(flag) && !isClosed(flag) && <> <Chip tone="warn">Escalated</Chip></>}</td>
                        <td className="mono">{flag.zone_id}</td>
                        <td><Chip tone={evaluation.tone} glyph>{evaluation.text}</Chip></td>
                        <td><Chip tone={state.tone}>{state.text}</Chip></td>
                        <td className={isClosed(flag) ? "muted" : undefined}>{flag.responsible?.name || "Unassigned"}</td>
                      </tr>
                    );
                  })}</tbody>
                </table>
              </div>
            )}
          </section>
          <p className="small muted" style={{ margin: "10px 2px 0" }}>Flags are created by deterministic rules and closed only by people, with feedback and a reason.</p>
        </>
      )}
    </WorkShell>
  );
}

function Kpi({ label, value, tone }) {
  const colour = { crit: "var(--crit-fg)", ok: "var(--ok-fg)", unk: "var(--unk-fg)" }[tone];
  return <div className="panel pad kpi"><p className="label">{label}</p><span className="num" style={{ color: colour }}>{value}</span></div>;
}
