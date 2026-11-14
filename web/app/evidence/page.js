import Link from "next/link";
import { fetchAll } from "../../lib/site-data.mjs";
import { flagTitle, formatTime, label, scenarioTime } from "../../lib/site.mjs";
import { EvidenceDecision } from "../decisions";
import { StatePanel, WorkShell } from "../shell";
import { Chip, reviewTone } from "../site-view/zone-panel";

export const dynamic = "force-dynamic";
export const metadata = { title: "Evidence review" };

const ORDER = { unconfirmed: 0, confirmed: 1, rejected: 2 };
const ORIGIN = {
  seed_baseline: "Synthetic seed baseline (seed provenance, not a human confirmation)",
  seed_statement: "Synthetic statement example",
  llm_statement: "Extracted from a message by the LLM",
};

// Scope fields that must be resolved for each Evidence kind; other kinds' fields are irrelevant.
const REQUIRED = { inspection: ["zone_id", "inspection_id"], task_completion: ["zone_id", "task_id"], revision_acknowledgment: ["crew_id", "revision_id"] };

function scopeText(scope) {
  if (scope.kind === "inspection") return `inspection ${scope.inspection_id || "unresolved"}`;
  if (scope.kind === "task_completion") return `task ${scope.task_id || "unresolved"}`;
  return `crew ${scope.crew_id || "unresolved"} · revision ${scope.revision_id || "unresolved"}`;
}

export default async function EvidencePage({ searchParams }) {
  const params = await searchParams;
  const { data, error } = await fetchAll(process.env.API_BASE_URL, {
    evidence: "/evidence", events: "/events", flags: "/flags?status=all", crews: "/crews", tasks: "/tasks", site: "/site",
  }, "Evidence could not be loaded from the API.");
  const records = [...(data?.evidence || [])].sort((a, b) => ORDER[a.review_status] - ORDER[b.review_status]);
  const selected = records.find((record) => record.id === params?.id) || records[0];
  return (
    <WorkShell current="evidence">
      <div className="page-head">
        <h1>Evidence review</h1>
        <span className="muted small">Independent of Flags: a decision re-runs the rule checks, nothing more.</span>
      </div>
      {error ? (
        <section className="panel"><StatePanel kind="error" title="Could not load Evidence" action={<Link className="btn btn-acc" href="/evidence">Retry</Link>}>{error} No decision was lost.</StatePanel></section>
      ) : records.length === 0 ? (
        <section className="panel"><StatePanel title="No Evidence recorded yet">Claims extracted from messages and seed baselines appear here for human review.</StatePanel></section>
      ) : (
        <div className="split">
          <section className="panel" style={{ flex: "1 1 340px", minWidth: 280, maxWidth: 460 }} aria-labelledby="evl-h">
            <h2 id="evl-h">Evidence <span className="muted small" style={{ marginLeft: "auto" }}>{records.filter((r) => r.review_status === "unconfirmed").length} unconfirmed</span></h2>
            <nav aria-label="Evidence records">
              {records.map((record) => (
                <Link key={record.id} href={`/evidence?id=${encodeURIComponent(record.id)}`} scroll={false}
                  className={`ev-link${record.id === selected.id ? " sel" : ""}`} aria-current={record.id === selected.id ? "true" : undefined}>
                  <Chip tone={reviewTone(record.review_status)}>{label(record.review_status)}</Chip>{" "}
                  <strong className="small">{label(record.claim)} · {record.scope.zone_id || "zone unresolved"}</strong>
                  <span className="mono muted" style={{ display: "block", marginTop: 2 }}>{scopeText(record.scope)}</span>
                </Link>
              ))}
            </nav>
          </section>
          <EvidenceDetail key={selected.id} record={selected} data={data} />
        </div>
      )}
    </WorkShell>
  );
}

function EvidenceDetail({ record, data }) {
  const { site, events, flags, crews, tasks } = data;
  const timezone = site?.timezone || "UTC";
  const event = events.find((item) => item.evidence.some((evidence) => evidence.id === record.id));
  const related = flags.filter((flag) => flag.evidence.some((evidence) => evidence.id === record.id));
  const { scope } = record;
  return (
    <section className="panel" style={{ flex: "999 1 460px", minWidth: 0 }} aria-labelledby="evd-h">
      <h2 id="evd-h">Claim: {label(record.claim)}</h2>
      <div className="pad stack">
        <div className="small">
          <Chip tone={reviewTone(record.review_status)}>{label(record.review_status)}</Chip>
          <p className="muted" style={{ margin: "6px 0 0" }}>
            {ORIGIN[record.origin] || label(record.origin)}
            {event && record.origin === "llm_statement" && <> (confidence {event.confidence.toFixed(2)}): confidence is not confirmation.</>}
          </p>
        </div>
        <div className="small">
          <blockquote className="q">{record.quote}</blockquote>
          {event ? (
            <span className="mono" style={{ color: "var(--accent-text)" }}>{scenarioTime(event.source.sent_at, site)} · {event.source.channel} · {label(event.source.sender_role)}</span>
          ) : <span className="mono muted">Source {record.source_ref}</span>}
          {event && (
            <details style={{ marginTop: 6 }}>
              <summary>Original source message</summary>
              <blockquote className="q">{event.source.text}</blockquote>
            </details>
          )}
        </div>
        <div className="small">
          <strong>Scope</strong>
          <p style={{ margin: "4px 0 0" }}>
            Zone {scope.zone_id ? <Link className="mono link" href={`/zones/${encodeURIComponent(scope.zone_id)}`}>{scope.zone_id}</Link> : <span className="muted">unresolved</span>}
            {" · "}<span className="mono muted">{scopeText(scope)}</span>
          </p>
          {(REQUIRED[scope.kind] || []).some((key) => !scope[key]) && <p className="meta warn-text">Part of the scope is unresolved, so this claim cannot satisfy a Precondition as it stands.</p>}
        </div>
        <div className="small">
          <strong>History</strong>
          <ul className="timeline" style={{ padding: 0 }}>
            {record.history.map((entry) => (
              <li key={entry.sequence}>
                <span className="when">{scenarioTime(entry.decided_at || entry.recorded_at, site) || formatTime(entry.recorded_at, timezone)}</span>
                <span>{label(entry.status)} · {entry.actor_type === "human" ? `${entry.reviewer_id} (${label(entry.reviewer_role)})` : label(entry.actor_type)}
                  {entry.reason && <span className="muted" style={{ display: "block" }}>{entry.reason}</span>}</span>
              </li>
            ))}
          </ul>
        </div>
        <div style={{ borderTop: "1px solid var(--line-soft)", paddingTop: 14 }} className="stack">
          <EvidenceDecision evidence={record} crews={crews} tasks={tasks} />
          <p className="form-note">Recorded with person, time and source. Does not close any Flag or approve a Proposal. MCP and chat cannot review Evidence.</p>
        </div>
        {related.length > 0 && (
          <p className="small" style={{ margin: 0 }}>Used by: {related.map((flag, i) => <span key={flag.id}>{i > 0 && " · "}<Link className="link" href={`/flags/${flag.id}`}>{flagTitle(flag)}</Link></span>)}</p>
        )}
      </div>
    </section>
  );
}
