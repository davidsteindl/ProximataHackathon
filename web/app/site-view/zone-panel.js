import Link from "next/link";
import { formatTime } from "../../lib/site.mjs";
import { inspectionKindLabel, splitTasks } from "../../lib/site-model.mjs";

const label = (value) => (value || "").replaceAll("_", " ");

export const STATUS = {
  conflict: { text: "Open Flag", tone: "crit" },
  open: { text: "Inspection not confirmed", tone: "warn" },
  ok: { text: "No open issues", tone: "ok" },
  unknown: { text: "Unknown zone", tone: "unk" },
};

export const EVALUATION = {
  satisfied: { text: "Satisfied", tone: "ok", note: "Precondition satisfied. The Flag stays open until a person closes it." },
  not_satisfied: { text: "Not satisfied", tone: "crit", note: "Confirmed evidence says the precondition is not met." },
  unknown: { text: "Unknown", tone: "unk", note: "Proof is missing, unconfirmed, stale or mismatched." },
  contradictory: { text: "Contradictory", tone: "vio", note: "Statements disagree. A person has to review the counterclaims." },
};

export function Chip({ tone, children }) {
  return <span className={`chip t-${tone}`}>{children}</span>;
}

export function reviewTone(status) {
  return status === "confirmed" ? "ok" : status === "rejected" ? "unk" : "warn";
}

const ORIGIN = {
  seed_baseline: "Synthetic seed baseline",
  seed_statement: "Synthetic statement example",
  llm_statement: "Extracted statement",
};

function lastDecision(record, timezone) {
  const entry = record.history?.at(-1);
  if (!entry) return null;
  const who = entry.actor_type === "human" ? `${entry.reviewer_id} (${label(entry.reviewer_role)})` : label(entry.actor_type);
  return `${label(entry.status)} by ${who} · ${formatTime(entry.decided_at || entry.recorded_at, timezone)}`;
}

export function EvidenceItem({ record, timezone }) {
  return (
    <li className="ev">
      <div className="ev-head">
        <Chip tone={reviewTone(record.review_status)}>{record.review_status}</Chip>
        <span className="ev-claim">claims <strong>{label(record.claim)}</strong></span>
      </div>
      <blockquote>{record.quote}</blockquote>
      <p className="meta">{ORIGIN[record.origin] || label(record.origin)} · <span className="mono">{record.source_ref}</span></p>
      {record.review_status === "unconfirmed" && <p className="meta warn-text">Unconfirmed — not proof, whatever its confidence.</p>}
      <p className="meta">{lastDecision(record, timezone)}</p>
    </li>
  );
}

function FlagCard({ flag, timezone, isNew }) {
  const evaluation = EVALUATION[flag.evaluation] || { text: label(flag.evaluation), tone: "unk" };
  const announcement = flag.sources[0];
  return (
    <article className={`flag-card${isNew ? " is-new" : ""}`}>
      <header>
        <span className="flag-id">Flag {flag.type}</span>
        <Chip tone={flag.severity === "high" ? "crit" : "warn"}>{flag.severity} severity</Chip>
        <span className="meta">{label(flag.state)}</span>
      </header>
      <h4>{label(flag.activity)} in {flag.zone_id} before {label(flag.precondition)}</h4>
      <div className="precondition">
        <span className="meta">Precondition · inspection <span className="mono">{flag.inspection_id || "missing or ambiguous"}</span></span>
        <Chip tone={evaluation.tone}>{evaluation.text}</Chip>
      </div>
      <p>{flag.explanation}</p>
      {announcement && (
        <figure className="source">
          <blockquote>{announcement.quote}</blockquote>
          <figcaption className="meta">{announcement.source.channel} · {label(announcement.source.sender_role)} · {formatTime(announcement.source.sent_at, timezone)}</figcaption>
        </figure>
      )}
      <p className="meta">Responsible: <strong>{flag.responsible?.name || "Unassigned — needs clarification"}</strong>{flag.task_id && <> · Task <span className="mono">{flag.task_id}</span></>}</p>
      {flag.evidence.length > 0 && (
        <details>
          <summary>{flag.evidence.length} evidence record{flag.evidence.length === 1 ? "" : "s"} for this precondition</summary>
          <ul className="ev-list">{flag.evidence.map((record) => <EvidenceItem key={record.id} record={record} timezone={timezone} />)}</ul>
        </details>
      )}
      <Link className="flag-link" href={`/flags/${flag.id}`}>Open flag detail <span aria-hidden="true">→</span></Link>
    </article>
  );
}

export function Widget({ title, aside, wide, children }) {
  return (
    <section className={`widget${wide ? " wide" : ""}`} aria-label={title}>
      <header className="widget-head"><h3>{title}</h3>{aside}</header>
      {children}
    </section>
  );
}

function InspectionRow({ summary }) {
  const { inspection, counts, confirmedPassed } = summary;
  return (
    <li className="pc-row">
      <div className="pc-main">
        <strong>{inspectionKindLabel(inspection.kind)} inspection</strong>
        <span className="meta mono">{inspection.id} · recorded {label(inspection.status)}</span>
      </div>
      <div className="pc-chips">
        {counts.confirmed > 0 && <Chip tone="ok">{counts.confirmed} confirmed</Chip>}
        {counts.unconfirmed > 0 && <Chip tone="warn">{counts.unconfirmed} unconfirmed</Chip>}
        {counts.rejected > 0 && <Chip tone="unk">{counts.rejected} rejected</Chip>}
        {!counts.confirmed && !counts.unconfirmed && !counts.rejected && <Chip tone="unk">no evidence</Chip>}
        <Chip tone={confirmedPassed ? "ok" : "warn"}>{confirmedPassed ? "confirmed pass" : "pass not confirmed"}</Chip>
      </div>
    </li>
  );
}

function TaskList({ tasks, flags, timezone }) {
  return (
    <ol className="tasks">
      {tasks.map((task) => {
        const flagged = flags.find((flag) => flag.task_id === task.id);
        return (
          <li key={task.id}>
            <div className="task-name">{task.name}{flagged && <Chip tone="crit">Flag {flagged.type}</Chip>}</div>
            <p className="meta"><span className="mono">{formatTime(task.starts_at, timezone)}</span> · {task.crew?.name || task.crew_id}</p>
            {task.predecessor_ids.length > 0 && <p className="meta">after {task.predecessor_ids.join(", ")}</p>}
          </li>
        );
      })}
    </ol>
  );
}

export function ZonePanel({ details, timezone, changes, newFlagIds, now }) {
  const { zone, flags, tasks, inspections, unresolvedEvidence, plan, revisions } = details;
  const status = STATUS[details.status];
  const floorChanges = changes.filter((change) => change.floorId === details.floorId);
  const { current, earlier } = splitTasks(tasks, now);
  return (
    <div className="widgets">
      <Widget wide title="Status" aside={<Chip tone={status.tone}>{status.text}</Chip>}>
        {flags.map((flag) => <FlagCard key={flag.id} flag={flag} timezone={timezone} isNew={newFlagIds.has(flag.id)} />)}
        {flags.length === 0 && (
          <p className="empty">No open Flag for {zone.id}, its parents or its rooms. That is not a pass: rules evaluate a Precondition when work is announced, and only confirmed evidence can satisfy it.</p>
        )}
        {inspections.length > 0 && (
          <div className="pc">
            <h4>Inspection evidence in scope</h4>
            <ul>{inspections.map((summary) => <InspectionRow key={summary.inspection.id} summary={summary} />)}</ul>
          </div>
        )}
        <p className="fineprint">Evidence review, Flag acknowledgment and Flag closure are separate human decisions. This view only reads them.</p>
      </Widget>

      <Widget title="Tasks" aside={<span className="meta">{current.length} current or upcoming</span>}>
        {current.length === 0 ? <p className="empty">No running or upcoming task in this zone.</p> : <TaskList tasks={current} flags={flags} timezone={timezone} />}
        {earlier.length > 0 && (
          <details className="earlier">
            <summary>{earlier.length} ended task{earlier.length === 1 ? "" : "s"}</summary>
            <TaskList tasks={earlier} flags={flags} timezone={timezone} />
          </details>
        )}
      </Widget>

      <Widget title="Plan & inspections" aside={plan && <span className="mono meta">{plan.id}</span>}>
        {!plan ? <p className="empty">No plan sheet covers this zone.</p> : (
          <>
            <ul className="revs">
              {revisions.map(({ revision, acknowledgments, evidence }) => (
                <li key={revision.id} className={revision.id === plan.current_revision?.id ? "current" : ""}>
                  <div className="rev-head">
                    <strong>Rev {revision.label}</strong>
                    {revision.id === plan.current_revision?.id && <Chip tone="info">current</Chip>}
                    <span className="meta mono">{formatTime(revision.issued_at, timezone)}</span>
                  </div>
                  <p className="meta mono">{revision.file_name}</p>
                  {acknowledgments.length === 0
                    ? <p className={revision.id === plan.current_revision?.id ? "warn-text meta" : "meta"}>No crew acknowledgment recorded.</p>
                    : acknowledgments.map((ack) => (
                      <p className="meta" key={ack.crew_id}>{ack.crew?.name || ack.crew_id} acknowledged · {formatTime(ack.acknowledged_at, timezone)}</p>
                    ))}
                  {evidence.map((record) => (
                    <p className="meta" key={record.id}><Chip tone={reviewTone(record.review_status)}>{record.review_status}</Chip> {ORIGIN[record.origin]} · <span className="mono">{record.source_ref}</span></p>
                  ))}
                </li>
              ))}
            </ul>
            {floorChanges.length > 0 && (
              <div className="changes">
                <h4>Geometry changed since the previous revision</h4>
                <ul>{floorChanges.map((change) => (
                  <li key={change.element.element_id}><span className="mono">{change.element.element_id}</span> · {change.change}</li>
                ))}</ul>
              </div>
            )}
          </>
        )}
        {inspections.map(({ inspection, evidence }) => (
          <div className="insp" key={inspection.id}>
            <div className="rev-head">
              <strong>{inspectionKindLabel(inspection.kind)} inspection</strong>
              <span className="mono meta">{inspection.zone_id}</span>
            </div>
            <p className="meta">Recorded: {inspection.status} · scheduled {formatTime(inspection.scheduled_at, timezone)}</p>
            {evidence.length === 0 ? <p className="meta">No evidence yet.</p> : (
              <ul className="ev-list">{evidence.map((record) => <EvidenceItem key={record.id} record={record} timezone={timezone} />)}</ul>
            )}
          </div>
        ))}
        {unresolvedEvidence.length > 0 && (
          <details className="insp">
            <summary>{unresolvedEvidence.length} inspection claim{unresolvedEvidence.length === 1 ? "" : "s"} with unresolved scope</summary>
            <p className="meta">These name no exact inspection, so they can never satisfy a precondition.</p>
            <ul className="ev-list">{unresolvedEvidence.map((record) => <EvidenceItem key={record.id} record={record} timezone={timezone} />)}</ul>
          </details>
        )}
      </Widget>
    </div>
  );
}
