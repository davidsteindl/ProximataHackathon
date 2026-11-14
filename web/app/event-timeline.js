import { formatTime } from "../lib/site.mjs";

const intentLabels = {
  planned_work: "Planned work",
  task_completion: "Task completion claim",
  question: "Question",
  revision: "Plan revision statement",
  inspection_result: "Inspection result claim",
  revision_acknowledgment: "Revision acknowledgment claim",
  observation: "Observation",
};

export default function EventTimeline({ events, timezone, crewNames }) {
  return (
    <section aria-labelledby="timeline-title">
      <h2 id="timeline-title">Event timeline</h2>
      <p>Ordered by source message time. Extraction alone does not confirm evidence or authorize work.</p>
      {events.length === 0 ? <p>No events in this zone and time range.</p> : (
        <ol className="event-timeline">
          {events.map((event) => (
            <li key={event.id}>
              <article>
                <p><time dateTime={event.source.sent_at}>{formatTime(event.source.sent_at, timezone)}</time></p>
                <h3>{event.origin === "deterministic_plan_diff" ? "Plan revision diff" : intentLabels[event.intent] || event.intent}
                  {" · "}{event.zone_ids.join(", ") || (event.origin === "deterministic_plan_diff" ? "No affected zones" : "Zone unresolved")}</h3>
                <p>{crewNames[event.crew_id] || event.actor || "Actor unknown"}
                  {event.activity && ` · ${event.activity.replaceAll("_", " ")}`}
                  {event.trade && ` · ${event.trade}`}</p>
                <blockquote>{event.quote}</blockquote>
                {event.details.learning && <p>Extraction corrected: planned work → question. <a href={`/#knowledge-${event.details.learning.knowledge_id}`}>Site Knowledge {event.details.learning.knowledge_id}</a>
                  {" · "}Feedback: {event.details.learning.feedback_id} · Original source: {event.details.learning.source_message_id}
                </p>}
                {event.unresolved_zones.length > 0 && <p>Unresolved zones: {event.unresolved_zones.join(", ")}</p>}
                {event.starts_at ? (
                  <p>Reported time: {formatTime(event.starts_at, timezone)}
                    {event.ends_at && ` – ${formatTime(event.ends_at, timezone)}`}
                    {event.time_precision !== "exact" && " (interpreted time window)"}
                    {event.time_expression && ` · “${event.time_expression}”`}</p>
                ) : <p>{event.time_expression ? `Time unresolved: “${event.time_expression}”` : "No activity time specified."}</p>}
                {event.evidence.length > 0 ? (
                  <ul aria-label="Evidence review status">
                    {event.evidence.map((evidence) => (
                      <li key={evidence.id}>
                        Evidence: <strong>{evidence.review_status}</strong> · {evidence.claim.replaceAll("_", " ")}
                        <p>Scope: {evidence.scope.zone_id || "Zone unresolved"}
                          {evidence.scope.kind === "inspection" && ` · Inspection: ${evidence.scope.inspection_id || "Unresolved"}`}
                          {evidence.scope.kind === "task_completion" && ` · Task: ${evidence.scope.task_id || "Unresolved"}`}
                          {evidence.scope.kind === "revision_acknowledgment" && ` · Crew: ${evidence.scope.crew_id || "Unresolved"} · Revision: ${evidence.scope.revision_id || "Unresolved"}`}</p>
                      </li>
                    ))}
                  </ul>
                ) : <p>{event.origin === "deterministic_plan_diff"
                  ? "Affected zones determined by DXF plan diff. This does not confirm inspection, crew receipt or task completion."
                  : "Unconfirmed extracted statement."}</p>}
                {event.details.diff_status === "failed" && <p>Plan diff failed — using unconfirmed revision note: {event.details.diff_error}</p>}
                <details>
                  <summary>Source message · {event.source.channel} · {event.source.sender_role.replaceAll("_", " ")}</summary>
                  <blockquote className="source-text">{event.source.text}</blockquote>
                  <small className="record-id">Source: {event.source.id} · Message: {event.source.external_id}</small>
                  {event.source.attachments.length > 0 && <p>Attachments: {event.source.attachments.map((attachment) => attachment.file_name).join(", ")}</p>}
                </details>
              </article>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
