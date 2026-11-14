import Link from "next/link";
import { fetchAll, getSiteModel } from "../lib/site-data.mjs";
import { floorOf, indexZones, upcoming } from "../lib/site-model.mjs";
import { SEVERITY, flagTitle, label, scenarioTime } from "../lib/site.mjs";
import AutoRefresh from "./auto-refresh";
import { StatePanel, WorkShell } from "./shell";
import ModelPreview from "./site-view/model-preview";
import { Chip, EVALUATION } from "./site-view/zone-panel";

export const dynamic = "force-dynamic";

const CHANNEL = { telegram: "TG", gmail: "MAIL" };

export default async function Home() {
  const base = process.env.API_BASE_URL;
  const [records, model] = await Promise.all([
    fetchAll(base, { site: "/site", flags: "/flags", evidence: "/evidence", inspections: "/inspections", plans: "/plans", tasks: "/tasks", crews: "/crews", events: "/events" }),
    getSiteModel(base),
  ]);
  const data = records.data;
  if (records.error || !data.site) {
    return (
      <WorkShell current="overview">
        <AutoRefresh ms={10000} />
        <section className="panel">
          <StatePanel kind={records.error ? "error" : "empty"} heading="h1" title={records.error ? "Site data unavailable" : "No site data loaded yet"}
            action={<Link className="btn btn-acc" href="/">Retry</Link>}>
            {records.error ? `${records.error} The view retries automatically; nothing was changed.` : "Run the seed import, then reload."}
          </StatePanel>
        </section>
      </WorkShell>
    );
  }
  return <Dashboard data={data} model={model} />;
}

function Dashboard({ data, model }) {
  const { site, flags, evidence, events } = data;
  const index = indexZones(model.data?.zones);
  const building = model.data?.zones?.[0];
  // eslint-disable-next-line react-hooks/purity -- server render of the current moment; AutoRefresh re-renders it
  const now = Date.now();
  const critical = flags.filter((flag) => flag.severity === "high");
  const today = scenarioTime(now, site)?.split(" · ")[0];
  const newToday = critical.filter((flag) => scenarioTime(flag.created_at, site)?.startsWith(`${today} `)).length;
  const unconfirmed = evidence.filter((record) => record.review_status === "unconfirmed");
  const closable = flags.filter((flag) => flag.awaiting_human_closure).length;
  const next = upcoming(data, index, now);
  const clear = next.filter((item) => item.chip.tone !== "crit").length;
  const lead = flags[0];
  const focusFloor = (lead && floorOf(index, lead.zone_id)) || model.data?.geometry?.[0]?.floor_id || null;
  const recent = [...events].sort((a, b) => b.source.sent_at.localeCompare(a.source.sent_at)).slice(0, 6);

  return (
    <WorkShell current="overview">
      <AutoRefresh />
      <div className="page-head">
        <h1>{site.name}{building ? ` — ${building.id}` : ""}</h1>
        <Chip tone="info">Live · {today}</Chip>
        <span className="push mono muted">{recent[0] ? `last event ${scenarioTime(recent[0].source.sent_at, site)}` : "no events yet"}</span>
      </div>

      <div className="grid-4">
        <div className="panel pad kpi"><p className="label">Critical flags</p>
          <div className="value"><span className="num" style={{ color: critical.length ? "var(--crit-fg)" : undefined }}>{critical.length}</span>{newToday > 0 && <Chip tone="crit">+{newToday} today</Chip>}</div></div>
        <div className="panel pad kpi"><p className="label">Open flags</p>
          <div className="value"><span className="num">{flags.length}</span><Link className="link small" href="/flags">inbox →</Link></div></div>
        <div className="panel pad kpi"><p className="label">Awaiting your decision</p>
          <div className="value"><span className="num">{unconfirmed.length + closable}</span>
            {(unconfirmed.length + closable) > 0 && <Chip tone="warn">{unconfirmed.length} evidence{closable ? ` · ${closable} closure` : ""}</Chip>}</div></div>
        <div className="panel pad kpi" style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <Ring value={next.length ? clear / next.length : 0} />
          <div><p className="label" style={{ marginBottom: 2 }}>Next 48 h without open Flag</p><span className="num" style={{ fontSize: 24 }}>{clear} / {next.length}</span></div>
        </div>
      </div>

      <div className="grid-main">
        {model.error ? (
          <section className="panel"><StatePanel kind="error" title="Site model unavailable" action={<Link className="btn btn-acc" href="/">Retry</Link>}>{model.error}</StatePanel></section>
        ) : <ModelPreview model={model.data} state={data} floorId={focusFloor} title={`Digital site model — ${[building?.id, focusFloor].filter(Boolean).join(" · ")}`} />}

        <section className="panel" aria-labelledby="att-h">
          <h2 id="att-h">Needs your attention</h2>
          <div className="pad stack">
            {lead ? <LeadFlag flag={lead} site={site} /> : (
              <StatePanel title="No open flags">Nothing is blocked by a rule right now. New events are checked as they arrive.</StatePanel>
            )}
            <div className="stack small" style={{ gap: 9 }}>
              {unconfirmed.length > 0 && <Link href="/evidence"><Chip tone="unk">Review</Chip>&ensp;{unconfirmed.length} Evidence item{unconfirmed.length === 1 ? "" : "s"} await review →</Link>}
              {flags.slice(1).map((flag) => (
                <Link key={flag.id} href={`/flags/${flag.id}`}><Chip tone={SEVERITY[flag.severity].tone}>{SEVERITY[flag.severity].text}</Chip>&ensp;{flagTitle(flag)} →</Link>
              ))}
            </div>
          </div>
        </section>
      </div>

      <div className="grid-main">
        <section className="panel" aria-labelledby="act-h">
          <div className="panel-head"><h2 id="act-h">Activity</h2><Link className="link small" href="/activity">All activity →</Link></div>
          {recent.length === 0 ? <p className="pad small muted" style={{ margin: 0 }}>No messages ingested yet.</p> : recent.map((event) => {
            const flag = flags.find((item) => item.sources.some((source) => source.id === event.id));
            const pending = event.evidence.find((record) => record.review_status === "unconfirmed");
            return (
              <div key={event.id} className="row">
                <span className="when" style={{ flexBasis: 120 }}>{scenarioTime(event.source.sent_at, site)} · {CHANNEL[event.source.channel] || event.source.channel.toUpperCase()}</span>
                <span className="small" style={{ flex: 1, minWidth: 0 }}>
                  {label(event.source.sender_role)}: “{event.quote}”
                  {flag ? <> → <Link className="link" href={`/flags/${flag.id}`}>{SEVERITY[flag.severity].text.toLowerCase()} flag</Link></>
                    : pending ? <> · unconfirmed, <Link className="link" href={`/evidence?id=${encodeURIComponent(pending.id)}`}>awaiting review</Link></>
                      : event.origin === "deterministic_plan_diff" ? " · plan diff" : ""}
                </span>
              </div>
            );
          })}
        </section>

        <section className="panel" aria-labelledby="next-h">
          <h2 id="next-h">Next 48 h</h2>
          {next.length === 0 ? <p className="pad small muted" style={{ margin: 0 }}>Nothing scheduled in the next 48 hours. <Link className="link" href="/activity">Full schedule →</Link></p> : next.slice(0, 6).map((item) => (
            <div key={item.key} className="row">
              <span className="small"><Link href={item.href}><strong>{item.name}</strong></Link> <span className="mono muted">{item.zone}</span><br /><span className="mono muted">{scenarioTime(item.at, site)}</span></span>
              <Chip tone={item.chip.tone}>{item.chip.text}</Chip>
            </div>
          ))}
        </section>
      </div>
    </WorkShell>
  );
}

function LeadFlag({ flag, site }) {
  const severity = SEVERITY[flag.severity];
  const evaluation = EVALUATION[flag.evaluation];
  const source = flag.sources[0];
  return (
    <div className="lead-flag">
      <p style={{ margin: "0 0 8px" }}><Chip tone={severity.tone}>{severity.text}</Chip></p>
      <Link href={`/flags/${flag.id}`}><strong style={{ fontSize: 15 }}>{flagTitle(flag)}</strong></Link>
      <div className="small stack" style={{ marginTop: 10, gap: 6, color: "var(--text-2)" }}>
        <span><Chip tone={evaluation.tone} glyph>{evaluation.text}</Chip> {flag.explanation}</span>
        {flag.type === "A" && <span><span className="mono muted">insp</span> {flag.inspection_id || "required inspection missing or ambiguous"}</span>}
        {flag.type === "B" && <span><span className="mono muted">rev</span> confirmed Rev {flag.context.acknowledged_revision || "none"}, required Rev {flag.context.current_revision}</span>}
        {source && <span><span className="mono" style={{ color: "var(--crit-fg)" }}>{scenarioTime(source.source.sent_at, site)}</span> “{source.quote}” — {source.source.channel}</span>}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
        <Link href={`/flags/${flag.id}`} className="btn btn-acc">Open flag</Link>
        <Link href="/proposals" className="btn">Decide proposal</Link>
      </div>
    </div>
  );
}

function Ring({ value }) {
  const c = 2 * Math.PI * 20;
  return (
    <svg width="52" height="52" viewBox="0 0 52 52" aria-hidden="true">
      <circle cx="26" cy="26" r="20" fill="none" stroke="var(--line)" strokeWidth="6" />
      <circle cx="26" cy="26" r="20" fill="none" stroke="var(--blue)" strokeWidth="6" strokeDasharray={`${c * value} ${c}`} transform="rotate(-90 26 26)" strokeLinecap="round" />
    </svg>
  );
}
