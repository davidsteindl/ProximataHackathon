import Link from "next/link";
import { fetchAll } from "../../../lib/site-data.mjs";
import { FLAG_STATE, LIFECYCLE, NOTIFICATION, SEVERITY, flagTitle, formatTime, isEscalated, label, lifecycleStep, scenarioTime, scheduleSources } from "../../../lib/site.mjs";
import Advice from "../../advice";
import { FlagDecisions } from "../../decisions";
import { StatePanel, WorkShell } from "../../shell";
import { Chip, EVALUATION, EvidenceItem } from "../../site-view/zone-panel";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }) {
  const { flagId } = await params;
  return { title: `Flag ${decodeURIComponent(flagId).slice(0, 8)}` };
}

async function getFlag(flagId) {
  const base = process.env.API_BASE_URL;
  try {
    const response = await fetch(new URL(`/flags/${encodeURIComponent(flagId)}`, base), { cache: "no-store", signal: AbortSignal.timeout(5000) });
    if (response.status === 404) return { error: "This Flag does not exist.", missing: true };
    if (!response.ok) throw new Error();
    const flag = await response.json();
    const { data } = await fetchAll(base, { site: "/site" });
    return { flag, site: data?.site || null };
  } catch {
    return { error: "The Flag could not be loaded from the API." };
  }
}

const STEP_TEXT = { detected: "Detected", notified: "Notified", acknowledged: "Acknowledged", in_progress: "In progress", closed: "Closed" };

export default async function FlagPage({ params }) {
  const { flagId } = await params;
  const { flag, site, error, missing } = await getFlag(flagId);
  return (
    <WorkShell current="flags" narrow>
      {error ? (
        <section className="panel">
          <StatePanel kind="error" heading="h1" title={error}
            action={<Link className="btn btn-acc" href={missing ? "/flags" : `/flags/${encodeURIComponent(flagId)}`}>{missing ? "Back to the flag inbox" : "Retry"}</Link>}>
            {missing ? "Check the link. Nothing was changed." : "Data may be stale. No decision was recorded."}
          </StatePanel>
        </section>
      ) : <FlagDetail flag={flag} site={site} />}
    </WorkShell>
  );
}

function When({ value, site }) {
  const timezone = site?.timezone || "UTC";
  return <time className="when" dateTime={value} title={formatTime(value, timezone)}>{scenarioTime(value, site) || formatTime(value, timezone)}</time>;
}

function FlagDetail({ flag, site }) {
  const severity = SEVERITY[flag.severity];
  const evaluation = EVALUATION[flag.evaluation];
  const step = lifecycleStep(flag.state);
  const zoneHref = `/zones/${encodeURIComponent(flag.zone_id)}`;
  const timezone = site?.timezone || "UTC";
  return (
    <>
      <p className="crumbs mono"><Link href="/flags">Flags</Link> / Flag {flag.type} · {flag.id.slice(0, 8)}</p>
      <div className="page-head" style={{ alignItems: "flex-start", marginBottom: 8 }}>
        <Chip tone={severity.tone}>{severity.text}</Chip>
        {isEscalated(flag) && <Chip tone="warn">Escalated</Chip>}
        <h1 style={{ fontSize: 21, maxWidth: 720 }}>{flagTitle(flag)}</h1>
      </div>
      <div className="small muted" style={{ display: "flex", gap: 18, flexWrap: "wrap", marginBottom: 14 }}>
        <span>Zone: <Link href={zoneHref} className="mono link">{flag.zone_id}</Link></span>
        <span>Work: <span className="mono">{flag.task_id || "no matching task"}</span> · {label(flag.activity)}</span>
        <span>Responsible: {flag.responsible?.name || "Unassigned, needs clarification"}</span>
      </div>

      <p className="sr-only" role="status">State: {FLAG_STATE[flag.state].text}</p>
      <ol className="panel pad steps" aria-label="Lifecycle">
        {LIFECYCLE.map((key, i) => (
          <li key={key} className={i < step ? "done" : i === step ? "cur" : undefined} aria-current={i === step ? "step" : undefined}>
            <span className="dot" aria-hidden="true" />{key === "closed" && step === 4 ? FLAG_STATE[flag.state].text : STEP_TEXT[key]}
          </li>
        ))}
      </ol>

      <div className="split">
        <div className="grow">
          <section className="panel" aria-labelledby="why-h">
            <h2 id="why-h">Why this flag exists</h2>
            <div className="pad stack">
              <p style={{ margin: 0 }}>{flag.explanation}</p>
              <div className="small"><Chip tone={evaluation.tone} glyph>{evaluation.text}</Chip> <span className="muted">{evaluation.note}</span></div>
              {flag.awaiting_human_closure && <p className="small" style={{ margin: 0 }}><Chip tone="ok">Awaiting closure</Chip> The Precondition is satisfied, but only a person closes this Flag.</p>}
              <dl className="facts small">
                {flag.type === "A" ? <><dt>Required inspection</dt><dd className="mono">{flag.inspection_id || "missing or ambiguous"}</dd></> : flag.type === "C" ? (
                  <><dt>Required predecessors</dt><dd>{(flag.context.predecessors || []).map((task) => (
                    <span key={task.task_id} style={{ display: "block" }}><span className="mono">{task.task_id}</span> · {label(task.evaluation)}</span>
                  ))}</dd></>
                ) : (
                  <>
                    <dt>Crew</dt><dd>{flag.context.crew_id || "Unresolved"}</dd>
                    <dt>Plan</dt><dd className="mono">{flag.context.plan_id} · required Rev {flag.context.current_revision} · confirmed receipt Rev {flag.context.acknowledged_revision || "unknown"}</dd>
                    <dt>Affected zones</dt><dd>{flag.context.affected_zones_origin === "deterministic_plan_diff" ? "Determined by DXF plan diff."
                      : flag.context.diff_status === "failed" ? `Plan diff failed (${flag.context.diff_error}); using the unconfirmed revision note.` : "From an unconfirmed revision note."}</dd>
                  </>
                )}
                <dt>Detected</dt><dd><When value={flag.created_at} site={site} /></dd>
                <dt>Last updated</dt><dd><When value={flag.updated_at} site={site} /></dd>
              </dl>
              {flag.type === "B" && <p className="small muted" style={{ margin: 0 }}>Receipt confirms that the revision was received; implementation needs separate Evidence.</p>}
            </div>
          </section>

          <Advice flag={flag} site={site} />

          <section className="panel" aria-labelledby="src-h">
            <h2 id="src-h">Sources <span className="muted small" style={{ marginLeft: "auto" }}>{flag.sources.length + scheduleSources(flag).length}</span></h2>
            <div className="pad stack">
              {scheduleSources(flag).map((source) => (
                <div key={source.ref} className="small">
                  <span className="mono" style={{ color: "var(--accent-text)" }}>morning scan · schedule</span>
                  <p style={{ margin: "4px 0 0" }}>Task <span className="mono">{source.taskId}</span> starts {scenarioTime(source.startsAt, site) || source.startsAt}. No message was received; the rule checked the scheduled work itself.</p>
                </div>
              ))}
              {flag.sources.length === 0 && scheduleSources(flag).length === 0 && <p className="small muted" style={{ margin: 0 }}>No source message linked.</p>}
              {flag.sources.map((event) => (
                <div key={event.id} className="small">
                  <span className="mono" style={{ color: "var(--accent-text)" }}>{scenarioTime(event.source.sent_at, site)} · {event.source.channel} · {label(event.source.sender_role)}</span>
                  <blockquote className="q">{event.quote}</blockquote>
                  <details>
                    <summary>Original source message</summary>
                    <blockquote className="q">{event.source.text}</blockquote>
                    <span className="mono muted">Source {event.source.id} · message {event.source.external_id}</span>
                  </details>
                </div>
              ))}
            </div>
          </section>

          <section className="panel" aria-labelledby="ev-h">
            <h2 id="ev-h">{flag.type === "C" ? "Predecessor completion Evidence" : flag.type === "B" ? "Revision receipt Evidence" : "Inspection Evidence"} <Link className="link small" href="/evidence" style={{ marginLeft: "auto" }}>Review evidence →</Link></h2>
            <div className="pad">
              {flag.evidence.length === 0 ? <p className="small muted" style={{ margin: 0 }}>No matching Evidence.</p> : (
                <ul className="ev-list">{flag.evidence.map((record) => <EvidenceItem key={record.id} record={record} timezone={timezone} href={`/evidence?id=${encodeURIComponent(record.id)}`} />)}</ul>
              )}
            </div>
          </section>

          <section className="panel" aria-labelledby="audit-h">
            <h2 id="audit-h">Timeline</h2>
            <ul className="timeline">
              {flag.audit.map((entry, i) => (
                <li key={i}>
                  <When value={entry.recorded_at} site={site} />
                  <span>
                    <strong>{label(entry.action)}</strong>{entry.from_state && <span className="muted"> · {label(entry.from_state)} → {label(entry.to_state)}</span>}
                    <span className="muted" style={{ display: "block" }}>{entry.actor}{entry.actor_role && ` (${label(entry.actor_role)})`} · {entry.channel}</span>
                    {entry.feedback && <span style={{ display: "block" }}>Feedback: {label(entry.feedback)} · {entry.reason}</span>}
                  </span>
                </li>
              ))}
              {(flag.notifications || []).map((message) => (
                <li key={message.id} role={message.status === "failed" ? "alert" : undefined}>
                  <span className="when">outbox</span>
                  <span>{NOTIFICATION[message.kind] || label(message.kind)} ({message.channel}): {message.status} · attempts {message.attempts}
                    {message.status === "failed" && message.error_code ? ` · ${label(message.error_code)} · retry scheduled` : ""}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <div className="aside">
          <FlagDecisions flag={flag} />
          <Link className="btn" href={zoneHref}>Show {flag.zone_id} in the site model</Link>
        </div>
      </div>
    </>
  );
}
