import Link from "next/link";
import { fetchAll } from "../../lib/site-data.mjs";
import { flagTitle, label, scenarioTime } from "../../lib/site.mjs";
import { PROPOSAL_STATUS, ProposalItem } from "../advice";
import { StatePanel, WorkShell } from "../shell";
import { Chip } from "../site-view/zone-panel";

export const dynamic = "force-dynamic";
export const metadata = { title: "Proposals" };

export default async function ProposalsPage() {
  const { data, error } = await fetchAll(process.env.API_BASE_URL, { flags: "/flags?status=all", proposals: "/proposals", site: "/site" },
    "Proposals could not be loaded from the API.");
  const advised = (data?.flags || []).filter((flag) => flag.advice?.proposals.length)
    .sort((a, b) => b.advice.proposals.filter((p) => p.status === "proposed").length - a.advice.proposals.filter((p) => p.status === "proposed").length);
  // MCP/chat/agent suggestions are stored only; they have no reviewed follow-up and cannot be decided (#13).
  const suggestions = (data?.proposals || []).filter((proposal) => proposal.channel !== "advisor");
  const flagsById = new Map((data?.flags || []).map((flag) => [flag.id, flag]));
  return (
    <WorkShell current="flags">
      <div className="page-head">
        <h1>Proposals</h1>
        <Chip tone="info">LLM proposal · advisory</Chip>
        <span className="muted small">Only the Superintendent decides. Approval sends the follow-up; it confirms no Evidence and closes no Flag.</span>
      </div>
      {error ? (
        <section className="panel"><StatePanel kind="error" title="Could not load proposals" action={<Link className="btn btn-acc" href="/proposals">Retry</Link>}>{error} No decision was lost.</StatePanel></section>
      ) : (
        <div className="stack" style={{ gap: 16 }}>
          {advised.length === 0 && (
            <section className="panel"><StatePanel title="No advisor proposals yet">The worker requests advice for each open Flag. Proposals appear here and on the Flag for a Superintendent decision.</StatePanel></section>
          )}
          {advised.map((flag) => (
            <section key={flag.id} className="panel" aria-labelledby={`pf-${flag.id}`}>
              <div className="panel-head">
                <h2 id={`pf-${flag.id}`}><Link href={`/flags/${flag.id}`}>{flagTitle(flag)}</Link></h2>
                <span className="mono muted">{label(flag.state)}</span>
              </div>
              <div className="pad stack">
                <p className="small" style={{ margin: 0, color: "var(--text-2)" }}>{flag.advice.explanation}</p>
                <ol className="ev-list">{flag.advice.proposals.map((proposal) => <ProposalItem key={proposal.id} flag={flag} proposal={proposal} site={data.site} />)}</ol>
              </div>
            </section>
          ))}
          {suggestions.length > 0 && (
            <section className="panel" aria-labelledby="sugg-h">
              <h2 id="sugg-h">Agent suggestions · stored only</h2>
              {suggestions.map((proposal) => {
                const flag = flagsById.get(proposal.flag_id);
                const status = PROPOSAL_STATUS[proposal.status];
                return (
                  <div key={proposal.id} className="row">
                    <span className="small"><strong>{proposal.action}</strong><br /><span className="muted">{proposal.rationale}</span><br />
                      <span className="mono muted">{proposal.channel} · {scenarioTime(proposal.created_at, data.site)}{flag && <> · <Link className="link" href={`/flags/${flag.id}`}>{flagTitle(flag)}</Link></>}</span></span>
                    <Chip tone={status.tone}>{status.text}</Chip>
                  </div>
                );
              })}
              <p className="pad form-note">Suggestions from MCP or chat have no reviewed crew follow-up, so they cannot be approved here.</p>
            </section>
          )}
        </div>
      )}
    </WorkShell>
  );
}
