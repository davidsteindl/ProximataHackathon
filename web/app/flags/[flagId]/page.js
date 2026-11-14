import Link from "next/link";
import { formatTime } from "../../../lib/site.mjs";
import SiteNav from "../../site-view/site-nav";
import { Chip, EVALUATION, EvidenceItem, Widget } from "../../site-view/zone-panel";
import "../../site-view/site-view.css";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }) {
  const { flagId } = await params;
  return { title: `Flag ${flagId} · SiteMind` };
}

async function getFlag(flagId) {
  try {
    const response = await fetch(new URL(`/flags/${encodeURIComponent(flagId)}`, process.env.API_BASE_URL), {
      cache: "no-store", signal: AbortSignal.timeout(5000),
    });
    if (response.status === 404) return { flag: null, error: "This Flag does not exist." };
    if (!response.ok) throw new Error();
    const [flag, site] = await Promise.all([response.json(), fetch(new URL("/site", process.env.API_BASE_URL), { cache: "no-store" }).then((r) => r.json())]);
    return { flag, timezone: site?.timezone || "UTC", error: null };
  } catch {
    return { flag: null, error: "The Flag could not be loaded from the API." };
  }
}

const label = (value) => (value || "").replaceAll("_", " ");

// Read-only Flag detail; lifecycle actions (acknowledge, close) belong to #9.
export default async function FlagPage({ params }) {
  const { flagId } = await params;
  const { flag, timezone, error } = await getFlag(flagId);
  return (
    <div className="sv sv-page">
      <SiteNav />
      <main className="fd">
        {error ? (
          <div className="sv-state" role="alert">
            <h1>{error}</h1>
            <p>Nothing was changed.</p>
            <Link className="primary-btn" href="/site">Back to the site model</Link>
          </div>
        ) : <FlagDetail flag={flag} timezone={timezone} />}
      </main>
    </div>
  );
}

function FlagDetail({ flag, timezone }) {
  const evaluation = EVALUATION[flag.evaluation] || { text: label(flag.evaluation), tone: "unk", note: "" };
  const zoneHref = `/zones/${encodeURIComponent(flag.zone_id)}`;
  return (
    <>
      <p className="crumbs mono">
        <Link href="/site">Site model</Link> / <Link href={zoneHref}>{flag.zone_id}</Link> / Flag {flag.type}
      </p>
      <section className="fd-hero">
        <div className="fd-tags">
          <span className="flag-id">Flag {flag.type}</span>
          <Chip tone={flag.severity === "high" ? "crit" : "warn"}>{flag.severity} severity</Chip>
          <Chip tone="info">{label(flag.state)}</Chip>
          <span className="meta mono">detected {formatTime(flag.created_at, timezone)}</span>
        </div>
        <h1>{label(flag.activity)} in {flag.zone_id} before {label(flag.precondition)}</h1>
        <p className="fd-lead">{flag.explanation}</p>
        <div className="fd-actions">
          <Link className="primary-btn" href={zoneHref}>Show {flag.zone_id} in 3D <span aria-hidden="true">→</span></Link>
          <span className="meta">Read-only. Acknowledgment, evidence review and closure are separate human decisions.</span>
        </div>
      </section>

      <div className="fd-grid">
        <div className="widgets">
          <Widget wide title="Precondition" aside={<Chip tone={evaluation.tone}>{evaluation.text}</Chip>}>
            <p className="meta">{evaluation.note}</p>
            <dl className="fd-facts">
              <dt>Required inspection</dt><dd className="mono">{flag.inspection_id || "missing or ambiguous"}</dd>
              <dt>Work</dt><dd><span className="mono">{flag.task_id || "no matching task"}</span> · {label(flag.activity)}</dd>
              <dt>Responsible</dt><dd><strong>{flag.responsible?.name || "Unassigned — needs clarification"}</strong></dd>
              <dt>Last updated</dt><dd className="mono">{formatTime(flag.updated_at, timezone)}</dd>
            </dl>
          </Widget>

          <Widget title="Work announcement" aside={<span className="meta">{flag.sources.length} source{flag.sources.length === 1 ? "" : "s"}</span>}>
            {flag.sources.map((event) => (
              <figure className="source" key={event.id}>
                <blockquote>{event.quote}</blockquote>
                <figcaption className="meta">{event.source.channel} · {label(event.source.sender_role)} · {formatTime(event.source.sent_at, timezone)}</figcaption>
                <details>
                  <summary>Original source message</summary>
                  <blockquote>{event.source.text}</blockquote>
                  <p className="meta mono fd-ref">Source {event.source.id} · message {event.source.external_id}</p>
                </details>
              </figure>
            ))}
          </Widget>
        </div>

        <div className="widgets">
          <Widget title="Inspection evidence" aside={<span className="meta">{flag.evidence.length} record{flag.evidence.length === 1 ? "" : "s"}</span>}>
            {flag.evidence.length === 0 ? <p className="empty">No matching inspection evidence.</p> : (
              <ul className="ev-list">{flag.evidence.map((record) => <EvidenceItem key={record.id} record={record} timezone={timezone} />)}</ul>
            )}
          </Widget>

          <Widget title="Audit trail">
            <ol className="fd-audit">
              {flag.audit.map((entry, i) => (
                <li key={i}>
                  <span className="mono meta">{formatTime(entry.recorded_at, timezone)}</span>
                  <strong>{label(entry.action)}</strong>
                  <span className="meta">{entry.actor} · {entry.channel}</span>
                  <span className="meta mono fd-ref">{entry.source_ref}</span>
                </li>
              ))}
            </ol>
          </Widget>
        </div>
      </div>
    </>
  );
}
