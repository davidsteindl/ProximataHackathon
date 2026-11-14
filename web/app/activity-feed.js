"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { FEED_POLL_MS, confirmationLabels, entryContext, kindLabels, readFeedPages } from "../lib/feed.mjs";
import { formatTime, scenarioTime } from "../lib/site.mjs";

// Trust level as chip tone; unconfirmed statements never read as facts (PLAN §3.2).
const TONE = { unconfirmed: "warn", confirmed: "ok", rejected: "unk", deterministic: "info", seed: "unk", human: "info", system: "unk", advice: "info" };

// Stable default: the polling effect depends on `filters`, so a fresh {} per render would re-poll forever.
const NO_FILTERS = {};

function feedUrl(filters, cursor) {
  const query = new URLSearchParams();
  if (filters.zoneId) query.set("zone", filters.zoneId);
  if (filters.fromDate) query.set("from", filters.fromDate);
  if (filters.toDate) query.set("to", filters.toDate);
  if (cursor) query.set("cursor", cursor);
  return `/api/feed?${query}`;
}

/**
 * Superintendent activity feed (#37), polled through /api/feed. `compact` is the dashboard panel (latest entries,
 * link to the full feed); the full variant on /activity has zone/date filters and older pages.
 */
export default function ActivityFeed({ initial, filters = NO_FILTERS, site, zones = [], compact = false, limit = 6 }) {
  const [feed, setFeed] = useState(initial);
  const [pageCount, setPageCount] = useState(1);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const { entries, next_cursor: cursor } = feed;

  useEffect(() => {
    let active = true;
    let running = false;
    const controller = new AbortController();
    const poll = async () => {
      if (running) return;
      running = true;
      setLoading(true);
      try {
        const updated = await readFeedPages(async (after) => {
          const response = await fetch(feedUrl(filters, after), { cache: "no-store", signal: controller.signal });
          if (!response.ok) throw new Error("The activity feed could not be refreshed.");
          return response.json();
        }, pageCount);
        if (active) { setFeed(updated); setError(null); }
      } catch (failure) {
        if (active) setError(failure.message || "The activity feed could not be refreshed.");
      } finally {
        running = false;
        if (active) setLoading(false);
      }
    };
    poll(); // also loads the next page right away after "Show older entries"
    const timer = setInterval(poll, FEED_POLL_MS);
    return () => { active = false; controller.abort(); clearInterval(timer); };
  }, [filters, pageCount]);

  const shown = compact ? entries.slice(0, limit) : entries;
  return (
    <section className="panel" aria-labelledby="feed-title">
      <div className="panel-head">
        <h2 id="feed-title">{compact ? "Activity" : "Latest on site"}</h2>
        {compact ? <Link className="link small" href="/activity">All activity →</Link> : <span className="small muted">updated automatically</span>}
      </div>
      {!compact && (
        <form method="get" action="/activity" className="pad" aria-label="Filter the activity feed" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end", paddingBottom: 0 }}>
          <label className="field">Zone and descendants
            <select name="feed_zone" defaultValue={filters.zoneId || ""}>
              <option value="">All zones</option>
              {zones.map((zone) => <option key={zone.id} value={zone.id}>{"— ".repeat(zone.depth)}{zone.id} · {zone.name}</option>)}
            </select>
          </label>
          <label className="field">From date (UTC)<input name="feed_from" type="date" defaultValue={filters.fromDate || ""} /></label>
          <label className="field">Before date (UTC)<input name="feed_to" type="date" defaultValue={filters.toDate || ""} /></label>
          <button type="submit" className="btn">Filter feed</button>
          <Link className="link small" href="/activity" style={{ alignSelf: "center" }}>Clear</Link>
          <p className="form-note" style={{ flexBasis: "100%" }}>Most recently recorded first. Unconfirmed statements stay labelled until a responsible human confirms their Evidence.</p>
        </form>
      )}
      {error && <p className="pad form-msg" role="alert" style={{ margin: 0 }}>{error}</p>}
      {shown.length === 0 ? <p className="pad small muted" style={{ margin: 0 }}>Nothing recorded for this zone and time range yet.</p> : (
        <ol className="feed">
          {shown.map((entry) => (
            <li key={entry.id} className="row">
              <time className="when" dateTime={entry.occurred_at} title={formatTime(entry.occurred_at, site?.timezone || "UTC")} style={{ flexBasis: 104 }}>
                {scenarioTime(entry.occurred_at, site) || formatTime(entry.occurred_at, "UTC")}
              </time>
              <div className="small" style={{ flex: 1, minWidth: 0 }}>
                <p className="meta" style={{ margin: 0 }}>{kindLabels[entry.kind] || entry.kind}{" "}
                  <span className={`chip t-${TONE[entry.confirmation] || "unk"}`}>{confirmationLabels[entry.confirmation] || entry.confirmation}</span></p>
                <strong style={{ display: "block", marginTop: 3 }}>{entry.link ? <Link href={entry.link}>{entry.title}</Link> : entry.title}</strong>
                {entry.summary && <p className="meta" style={{ color: "var(--text-2)" }}>{entry.summary}</p>}
                {!compact && entry.quote && entry.kind !== "proposal" && <blockquote className="q">{entry.quote}</blockquote>}
                <p className="meta">{entryContext(entry)}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
      {!compact && cursor && (
        <div className="pad"><button type="button" className="btn" onClick={() => setPageCount((count) => count + 1)} disabled={loading}>{loading ? "Loading…" : "Show older entries"}</button></div>
      )}
    </section>
  );
}
