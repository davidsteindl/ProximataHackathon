import Link from "next/link";
import { formatTime } from "../lib/site.mjs";

/** Site Knowledge from Flag feedback (#21) and the cumulative confirmed-Flag share. No per-person metrics. */
export default function SiteKnowledge({ knowledge, metric, timezone }) {
  const latest = metric.at(-1);
  const x = (index) => 40 + (metric.length > 1 ? index / (metric.length - 1) : 0) * 540;
  const y = (share) => 140 - share * 120;
  const points = metric.map((point, index) => `${x(index)},${y(point.confirmed_share)}`).join(" ");
  return (
    <section className="panel" aria-labelledby="knowledge-title">
      <h2 id="knowledge-title">Site Knowledge &amp; learning</h2>
      <div className="pad stack">
        <p className="small muted" style={{ margin: 0 }}>Source-linked feedback and explicit extraction corrections. Safety rules and Evidence review requirements remain unchanged.</p>
        <div>
          <h3 style={{ fontSize: 14 }}>Confirmed Flags over time</h3>
          <p style={{ margin: "4px 0 0", fontWeight: 600 }}>{latest ? `${Math.round(latest.confirmed_share * 100)}% · ${latest.confirmed_flags} of ${latest.reviewed_flags} reviewed Flags confirmed` : "No Flag feedback yet — no rate available."}</p>
          <p className="meta">Cumulative daily share (UTC), latest feedback per Flag. Confirmed/resolved count positively, false alarms negatively; unreviewed Flags are excluded. No per-person metrics.</p>
        </div>
        {metric.length > 0 && (
          <>
            <svg viewBox="0 0 640 180" role="img" aria-label="Confirmed Flag share over time; daily values in the following table" style={{ width: "100%", maxWidth: 640, height: "auto" }}>
              <g fill="var(--muted)" fontSize="12" fontFamily="var(--font-mono)">
                <text x="0" y="24">100%</text>
                <text x="8" y="144">0%</text>
                <text x="40" y="172">{metric[0].date}</text>
                {metric.length > 1 && <text x="580" y="172" textAnchor="end">{latest.date}</text>}
              </g>
              <path d="M40 20 V140 H600" fill="none" stroke="var(--line)" />
              <polyline points={points} fill="none" stroke="var(--blue)" strokeWidth="3" strokeLinejoin="round" />
              {metric.map((point, index) => (
                <circle key={point.date} cx={x(index)} cy={y(point.confirmed_share)} r="4" fill="var(--blue)">
                  <title>{`${point.date}: ${Math.round(point.confirmed_share * 100)}%`}</title>
                </circle>
              ))}
            </svg>
            <details>
              <summary>Daily metric values</summary>
              <table className="t">
                <thead><tr><th>Date (UTC)</th><th>Confirmed</th><th>Reviewed</th><th>Share</th></tr></thead>
                <tbody>{metric.map((point) => <tr key={point.date}><td className="mono">{point.date}</td><td>{point.confirmed_flags}</td><td>{point.reviewed_flags}</td><td>{Math.round(point.confirmed_share * 100)}%</td></tr>)}</tbody>
              </table>
            </details>
          </>
        )}
        <h3 style={{ fontSize: 14 }}>Feedback knowledge ({knowledge.length})</h3>
        {knowledge.length === 0 ? <p className="small muted" style={{ margin: 0 }}>No Site Knowledge yet.</p> : (
          <ul className="ev-list">{knowledge.map((entry) => (
            <li key={entry.id} id={`knowledge-${entry.id}`} className="ev-item">
              <div className="ev-head"><strong>{entry.feedback.replaceAll("_", " ")}</strong><span className="mono muted">{formatTime(entry.recorded_at, timezone)}</span></div>
              <p className="meta" style={{ color: "var(--text-2)" }}>{entry.reason}</p>
              <p className="meta">{entry.correction || "Feedback context only — no automatic extraction or rule change."}</p>
              <p className="meta"><Link className="link" href={`/flags/${encodeURIComponent(entry.flag_id)}`}>Source Flag &amp; feedback audit</Link></p>
              <p className="meta mono">Knowledge: {entry.id} · Feedback: {entry.feedback_id} · Sources: {entry.source_ids.join(", ")}{entry.correction_event_id && ` · Corrected Event: ${entry.correction_event_id}`}</p>
            </li>
          ))}</ul>
        )}
      </div>
    </section>
  );
}
