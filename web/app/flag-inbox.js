import { FlagActions, ProposalActions } from "./human-review";
import { formatTime } from "../lib/site.mjs";

const notificationLabels = {
  warning: "Warning",
  escalation: "Escalation",
  approval_request: "Approval request",
  proposal_followup: "Approved follow-up",
};

function citationNote(citation) {
  if (citation.review_status) return ` · Evidence ${citation.review_status}`;
  return citation.ref.startsWith("source:") ? " · unconfirmed statement" : " · site record";
}

function Advice({ flag, timezone }) {
  const { advice } = flag;
  return (
    <section aria-label="Advisor proposals">
      <h4>Advisor explanation <small>(advisory only · {advice.backend})</small></h4>
      <p>{advice.explanation}</p>
      <ul>{advice.citations.map((citation) => (
        <li key={citation.handle}><code>[{citation.handle}]</code> <small className="record-id">{citation.ref}</small>{citationNote(citation)}</li>
      ))}</ul>
      {advice.proposals.length === 0 ? <p>No proposals.</p> : (
        <ol>{advice.proposals.map((proposal) => (
          <li key={proposal.id}>
            <p><strong>{proposal.action}</strong> · {proposal.status}</p>
            <p>{proposal.rationale}</p>
            <p>Affected: crews {proposal.affected_crews.join(", ")}
              {" · "}tasks {proposal.affected_tasks.join(", ") || "—"}
              {" · "}zones {proposal.affected_zones.join(", ") || "—"}</p>
            <details>
              <summary>Follow-up sent only after approval</summary>
              <blockquote className="source-text">{proposal.message}</blockquote>
            </details>
            {proposal.status !== "proposed" && (
              <p>{proposal.status} by {proposal.decided_by} · {formatTime(proposal.decided_at, timezone)} · {proposal.decision_reason}</p>
            )}
            <ProposalActions flag={flag} proposal={proposal} />
          </li>
        ))}</ol>
      )}
    </section>
  );
}

const evaluationLabels = {
  satisfied: "Precondition satisfied — awaiting human Flag closure",
  not_satisfied: "Precondition not satisfied",
  unknown: "Required evidence missing or unconfirmed",
  contradictory: "Conflicting statements — review required",
};

export default function FlagInbox({ flags, timezone, closed = false }) {
  return (
    <section aria-labelledby={closed ? "closed-flags-title" : "flags-title"}>
      <h2 id={closed ? "closed-flags-title" : "flags-title"}>{closed ? "Closed Flags" : "Flag inbox"}</h2>
      {!closed && <p>Open flags, highest severity first. Flags stay open until a responsible human closes them.</p>}
      {flags.length === 0 ? <p>{closed ? "No closed Flags." : "No open flags."}</p> : (
        <ol className="flag-inbox">
          {flags.map((flag) => (
            <li key={flag.id} id={`flag-${flag.id}`}>
              <article>
                <h3>Flag {flag.type} · {flag.zone_id} · {flag.severity} severity</h3>
                <p>{closed && flag.evaluation === "satisfied" ? "Precondition satisfied" : evaluationLabels[flag.evaluation] || flag.evaluation}</p>
                <p>{flag.explanation}</p>
                <p>Responsible: <strong>{flag.responsible?.name || "Unassigned — responsibility needs clarification"}</strong></p>
                <p>Work: {flag.task_id || flag.activity.replaceAll("_", " ")}
                  {flag.type === "A" && <> · Required inspection: {flag.inspection_id || "Missing or ambiguous"}</>}</p>
                {flag.type === "B" && (
                  <div>
                    <p>Crew: {flag.context.crew_id || "Unresolved"} · Plan: {flag.context.plan_id}
                      {" · "}Confirmed receipt: Rev {flag.context.acknowledged_revision || "unknown"}
                      {" · "}Required: Rev {flag.context.current_revision}</p>
                    <p>{flag.context.affected_zones_origin === "deterministic_plan_diff"
                      ? "Affected zones determined by DXF plan diff."
                      : flag.context.diff_status === "failed"
                        ? `Plan diff failed — using unconfirmed revision note: ${flag.context.diff_error}`
                        : "Affected zones come from an unconfirmed revision note."}</p>
                    <p>Receipt confirms that the revision was received; implementation requires separate evidence.</p>
                  </div>
                )}
                <p>State: {flag.state.replaceAll("_", " ")} · Detected {formatTime(flag.created_at, timezone)}</p>
                <FlagActions flag={flag} />
                {flag.advice && <Advice flag={flag} timezone={timezone} />}
                {(flag.notifications || []).map((message) => (
                  <p key={message.id} role={message.status === "failed" ? "alert" : undefined}>
                    {notificationLabels[message.kind] || "Message"} ({message.channel}): {message.status} · Attempts: {message.attempts}
                    {message.status === "failed" && message.error_code ? ` · ${message.error_code.replaceAll("_", " ")} · Retry scheduled` : ""}
                  </p>
                ))}
                <details>
                  <summary>Flag details · {flag.sources.length} source(s)</summary>
                  <p>Last updated: {formatTime(flag.updated_at, timezone)}</p>
                  <h4>Triggering sources</h4>
                  {flag.sources.map((event) => (
                    <div key={event.id}>
                      <blockquote className="source-text">{event.quote}</blockquote>
                      <p>{event.source.channel} · {event.source.sender_role.replaceAll("_", " ")}
                        {" · "}{formatTime(event.source.sent_at, timezone)}</p>
                      <details>
                        <summary>Original source message</summary>
                        <blockquote className="source-text">{event.source.text}</blockquote>
                        <small className="record-id">Source: {event.source.id} · Message: {event.source.external_id}</small>
                      </details>
                    </div>
                  ))}
                  <h4>{flag.type === "B" ? "Revision receipt evidence" : "Inspection evidence"}</h4>
                  {flag.evidence.length === 0 ? <p>No matching evidence.</p> : (
                    <ul>{flag.evidence.map((evidence) => (
                      <li key={evidence.id}>
                        <strong>{evidence.review_status}</strong> · {evidence.claim}
                        <blockquote className="source-text">{evidence.quote}</blockquote>
                        <p>Zone: {evidence.scope.zone_id || "Unresolved"}
                          {flag.type === "B" ? <> · Crew: {evidence.scope.crew_id || "Unresolved"}
                            {" · "}Revision: {evidence.scope.revision_id || "Unresolved"}</> :
                            <> · Inspection: {evidence.scope.inspection_id || "Unresolved"}</>}</p>
                        <small className="record-id">Source: {evidence.source_ref} · {evidence.origin.replaceAll("_", " ")}</small>
                      </li>
                    ))}</ul>
                  )}
                  <h4>Audit trail</h4>
                  <ul>{flag.audit.map((entry, index) => (
                    <li key={index}>{formatTime(entry.recorded_at, timezone)} · {entry.action.replaceAll("_", " ")}
                      {" · "}{entry.actor}{entry.actor_role && ` (${entry.actor_role})`} · {entry.channel}
                      {entry.from_state && <p>{entry.from_state} → {entry.to_state}</p>}
                      {entry.feedback && <p>Feedback: {entry.feedback} · {entry.reason}</p>}
                      <small className="record-id">{entry.source_ref}</small>
                    </li>
                  ))}</ul>
                </details>
              </article>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
