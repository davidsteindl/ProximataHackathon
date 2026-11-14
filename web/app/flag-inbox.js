import { formatTime } from "../lib/site.mjs";

const evaluationLabels = {
  satisfied: "Precondition satisfied — awaiting human Flag closure",
  not_satisfied: "Precondition not satisfied",
  unknown: "Inspection proof missing or unconfirmed",
  contradictory: "Conflicting inspection statements — review required",
};

export default function FlagInbox({ flags, timezone }) {
  return (
    <section aria-labelledby="flags-title">
      <h2 id="flags-title">Flag inbox</h2>
      <p>Open flags, highest severity first. Flags stay open until a responsible human closes them.</p>
      {flags.length === 0 ? <p>No open flags.</p> : (
        <ol className="flag-inbox">
          {flags.map((flag) => (
            <li key={flag.id} id={`flag-${flag.id}`}>
              <article>
                <h3>Flag {flag.type} · {flag.zone_id} · {flag.severity} severity</h3>
                <p>{evaluationLabels[flag.evaluation] || flag.evaluation}</p>
                <p>{flag.explanation}</p>
                <p>Responsible: <strong>{flag.responsible?.name || "Unassigned — responsibility needs clarification"}</strong></p>
                <p>Work: {flag.task_id || flag.activity.replaceAll("_", " ")}
                  {" · "}Required inspection: {flag.inspection_id || "Missing or ambiguous"}</p>
                <p>State: {flag.state.replaceAll("_", " ")} · Detected {formatTime(flag.created_at, timezone)}</p>
                {(flag.notifications || []).map((message) => (
                  <p key={message.id} role={message.status === "failed" ? "alert" : undefined}>
                    Gmail warning: {message.status} · Attempts: {message.attempts}
                    {message.status === "failed" && message.error_code ? ` · ${message.error_code.replaceAll("_", " ")} · Retry scheduled` : ""}
                  </p>
                ))}
                <details>
                  <summary>Flag details · {flag.sources.length} work source(s)</summary>
                  <p>Last updated: {formatTime(flag.updated_at, timezone)}</p>
                  <h4>Work announcements</h4>
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
                  <h4>Inspection evidence</h4>
                  {flag.evidence.length === 0 ? <p>No matching inspection evidence.</p> : (
                    <ul>{flag.evidence.map((evidence) => (
                      <li key={evidence.id}>
                        <strong>{evidence.review_status}</strong> · {evidence.claim}
                        <blockquote className="source-text">{evidence.quote}</blockquote>
                        <p>Zone: {evidence.scope.zone_id || "Unresolved"} · Inspection: {evidence.scope.inspection_id || "Unresolved"}</p>
                        <small className="record-id">Source: {evidence.source_ref} · {evidence.origin.replaceAll("_", " ")}</small>
                      </li>
                    ))}</ul>
                  )}
                  <h4>Audit trail</h4>
                  <ul>{flag.audit.map((entry, index) => (
                    <li key={index}>{formatTime(entry.recorded_at, timezone)} · {entry.action.replaceAll("_", " ")}
                      {" · "}{entry.actor} · {entry.channel}
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
