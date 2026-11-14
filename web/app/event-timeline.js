import Link from "next/link";
import { label, scenarioTime } from "../lib/site.mjs";
import { Chip, reviewTone } from "./site-view/zone-panel";

const intentLabels = {
  planned_work: "Planned work",
  task_completion: "Task completion claim",
  question: "Question",
  revision: "Plan revision statement",
  inspection_result: "Inspection result claim",
  revision_acknowledgment: "Revision acknowledgment claim",
  observation: "Observation",
};

export default function EventTimeline({ events, site, crewNames }) {
  return (
    <section className="panel" aria-labelledby="timeline-title">
      <h2 id="timeline-title">Event timeline</h2>
      <p className="pad small muted" style={{ margin: 0, paddingBottom: 0 }}>Ordered by source message time. Extraction alone does not confirm Evidence or authorize work.</p>
      {events.length === 0 ? <p className="pad small muted" style={{ margin: 0 }}>No events in this zone and time range.</p> : (
        <ol className="timeline">
          {events.map((event) => (
            <li key={event.id}>
              <time className="when" dateTime={event.source.sent_at}>{scenarioTime(event.source.sent_at, site)} · {event.source.channel}</time>
              <article style={{ minWidth: 0 }}>
                <h3 style={{ fontSize: 14 }}>{event.origin === "deterministic_plan_diff" ? "Plan revision diff" : intentLabels[event.intent] || event.intent}
                  {" · "}{event.zone_ids.join(", ") || (event.origin === "deterministic_plan_diff" ? "No affected zones" : "Zone unresolved")}</h3>
                <p className="meta">{crewNames[event.crew_id] || event.actor || "Actor unknown"}
                  {event.activity && ` · ${label(event.activity)}`}{event.trade && ` · ${event.trade}`}</p>
                <blockquote className="q">{event.quote}</blockquote>
                {event.details.learning && (
                  <p className="meta">Extraction corrected: planned work → question.{" "}
                    <Link className="link" href={`/activity#knowledge-${event.details.learning.knowledge_id}`}>Site Knowledge {event.details.learning.knowledge_id}</Link>
                    {" · "}Feedback: {event.details.learning.feedback_id} · Original source: {event.details.learning.source_message_id}</p>
                )}
                {event.unresolved_zones.length > 0 && <p className="meta">Unresolved zones: {event.unresolved_zones.join(", ")}</p>}
                <p className="meta">{event.starts_at
                  ? <>Reported time: {scenarioTime(event.starts_at, site)}{event.ends_at && ` – ${scenarioTime(event.ends_at, site)}`}
                    {event.time_precision !== "exact" && " (interpreted time window)"}{event.time_expression && ` · “${event.time_expression}”`}</>
                  : event.time_expression ? `Time unresolved: “${event.time_expression}”` : "No activity time specified."}</p>
                {event.evidence.length > 0 ? event.evidence.map((evidence) => (
                  <p className="meta" key={evidence.id}>
                    <Chip tone={reviewTone(evidence.review_status)}>{label(evidence.review_status)}</Chip> {label(evidence.claim)}
                    {" · "}<Link className="link" href={`/evidence?id=${encodeURIComponent(evidence.id)}`}>review →</Link>
                  </p>
                )) : <p className="meta">{event.origin === "deterministic_plan_diff"
                  ? "Affected zones determined by DXF plan diff. This does not confirm inspection, crew receipt or task completion."
                  : "Unconfirmed extracted statement."}</p>}
                {event.details.diff_status === "failed" && <p className="meta warn-text">Plan diff failed, using the unconfirmed revision note: {event.details.diff_error}</p>}
                <details>
                  <summary>Source message · {event.source.channel} · {label(event.source.sender_role)}</summary>
                  <blockquote className="q">{event.source.text}</blockquote>
                  <span className="mono muted">Source {event.source.id} · message {event.source.external_id}</span>
                  {event.source.attachments.length > 0 && <p className="meta">Attachments: {event.source.attachments.map((attachment) => attachment.file_name).join(", ")}</p>}
                </details>
              </article>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
