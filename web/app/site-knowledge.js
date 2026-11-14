import Link from "next/link";
import { formatTime } from "../lib/site.mjs";

export default function SiteKnowledge({ knowledge, metric, timezone }) {
  const latest = metric.at(-1);
  const points = metric.map((point, index) => `${40 + (metric.length > 1 ? index / (metric.length - 1) : 0) * 540},${140 - point.confirmed_share * 120}`).join(" ");
  return (
    <section aria-labelledby="knowledge-title">
      <h2 id="knowledge-title">Site Knowledge &amp; learning</h2>
      <p>Source-linked feedback and explicit extraction corrections. Safety rules and Evidence review requirements remain unchanged.</p>
      <h3>Confirmed Flags over time</h3>
      <p>{latest ? `${Math.round(latest.confirmed_share * 100)}% · ${latest.confirmed_flags} of ${latest.reviewed_flags} reviewed Flags confirmed` : "No Flag feedback yet — no rate available."}</p>
      <p>Cumulative daily share (UTC), latest feedback per Flag. Confirmed/resolved count positively, false alarms negatively; unreviewed Flags are excluded. No per-person metrics.</p>
      {metric.length > 0 && (
        <>
          <svg viewBox="0 0 640 180" role="img" aria-label="Confirmed Flag share over time; daily values in the following table" style={{ width: "100%", maxWidth: 640, height: 180 }}>
            <text x="0" y="24" fill="currentColor">100%</text>
            <text x="8" y="144" fill="currentColor">0%</text>
            <path d="M40 20 V140 H600" fill="none" stroke="currentColor" />
            <polyline points={points} fill="none" stroke="currentColor" strokeWidth="3" />
            {metric.map((point, index) => (
              <circle key={point.date} cx={40 + (metric.length > 1 ? index / (metric.length - 1) : 0) * 540} cy={140 - point.confirmed_share * 120} r="4" fill="currentColor">
                <title>{`${point.date}: ${Math.round(point.confirmed_share * 100)}%`}</title>
              </circle>
            ))}
            <text x="40" y="172" fill="currentColor">{metric[0].date}</text>
            {metric.length > 1 && <text x="580" y="172" textAnchor="end" fill="currentColor">{latest.date}</text>}
          </svg>
          <details>
            <summary>Daily metric values</summary>
            <table>
              <thead><tr><th>Date (UTC)</th><th>Confirmed</th><th>Reviewed</th><th>Share</th></tr></thead>
              <tbody>{metric.map((point) => <tr key={point.date}><td>{point.date}</td><td>{point.confirmed_flags}</td><td>{point.reviewed_flags}</td><td>{Math.round(point.confirmed_share * 100)}%</td></tr>)}</tbody>
            </table>
          </details>
        </>
      )}
      <h3>Feedback knowledge ({knowledge.length})</h3>
      {knowledge.length === 0 ? <p>No Site Knowledge yet.</p> : (
        <ul>{knowledge.map((entry) => (
          <li key={entry.id} id={`knowledge-${entry.id}`}>
            <p><strong>{entry.feedback.replaceAll("_", " ")}</strong> · {formatTime(entry.recorded_at, timezone)}</p>
            <p>{entry.reason}</p>
            <p>{entry.correction || "Feedback context only — no automatic extraction or rule change."}</p>
            <p><Link href={`/flags/${encodeURIComponent(entry.flag_id)}`}>Source Flag &amp; feedback audit</Link></p>
            <small className="record-id">Knowledge: {entry.id} · Feedback: {entry.feedback_id} · Sources: {entry.source_ids.join(", ")}{entry.correction_event_id && ` · Corrected Event: ${entry.correction_event_id}`}</small>
          </li>
        ))}</ul>
      )}
    </section>
  );
}
