"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { FEED_POLL_MS, confirmationLabels, entryContext, kindLabels, mergeNewest } from "../lib/feed.mjs";
import { formatTime } from "../lib/site.mjs";

function feedUrl(filters, cursor) {
  const query = new URLSearchParams();
  if (filters.zoneId) query.set("zone", filters.zoneId);
  if (filters.fromDate) query.set("from", filters.fromDate);
  if (filters.toDate) query.set("to", filters.toDate);
  if (cursor) query.set("cursor", cursor);
  return `/api/feed?${query}`;
}

export default function ActivityFeed({ initial, filters, timezone, zones }) {
  const [entries, setEntries] = useState(initial.entries);
  const [cursor, setCursor] = useState(initial.next_cursor);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const response = await fetch(feedUrl(filters), { cache: "no-store" });
        const result = await response.json();
        if (!active) return;
        if (result.error) setError(result.error);
        else {
          setError(null);
          setEntries((current) => mergeNewest(current, result.data.entries));
        }
      } catch {
        if (active) setError("The activity feed could not be refreshed.");
      }
    };
    const timer = setInterval(poll, FEED_POLL_MS);
    return () => { active = false; clearInterval(timer); };
  }, [filters]);

  const loadOlder = async () => {
    setLoading(true);
    try {
      const result = await (await fetch(feedUrl(filters, cursor), { cache: "no-store" })).json();
      if (result.error) setError(result.error);
      else {
        setEntries((current) => [...current, ...result.data.entries.filter((entry) => !current.some((item) => item.id === entry.id))]);
        setCursor(result.data.next_cursor);
      }
    } catch {
      setError("Older entries could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section aria-labelledby="feed-title">
      <h2 id="feed-title">Latest on site</h2>
      <p>Most recently recorded first, updated automatically. Unconfirmed statements stay labelled until a responsible human confirms their evidence.</p>
      <form method="get">
        <label>
          Zone and descendants
          <select name="feed_zone" defaultValue={filters.zoneId || ""}>
            <option value="">All zones</option>
            {zones.map((zone) => (
              <option key={zone.id} value={zone.id}>{"— ".repeat(zone.depth)}{zone.id} · {zone.name}</option>
            ))}
          </select>
        </label>
        <label>From date (UTC)<input name="feed_from" type="date" defaultValue={filters.fromDate || ""} /></label>
        <label>Before date (UTC)<input name="feed_to" type="date" defaultValue={filters.toDate || ""} /></label>
        <button type="submit">Filter feed</button>
        <Link href="/">Clear</Link>
      </form>
      {error && <p role="alert">{error}</p>}
      {entries.length === 0 ? <p>Nothing recorded for this zone and time range yet.</p> : (
        <ol className="activity-feed">
          {entries.map((entry) => (
            <li key={entry.id} className={`feed-entry feed-${entry.confirmation}`}>
              <p className="feed-meta">
                <time dateTime={entry.occurred_at}>{formatTime(entry.occurred_at, timezone)}</time>
                {" · "}{kindLabels[entry.kind] || entry.kind}
                {" · "}<strong>{confirmationLabels[entry.confirmation] || entry.confirmation}</strong>
              </p>
              <h3>{entry.link ? <Link href={entry.link}>{entry.title}</Link> : entry.title}</h3>
              {entry.summary && <p>{entry.summary}</p>}
              {entry.quote && entry.kind !== "proposal" && <blockquote className="source-text">{entry.quote}</blockquote>}
              <p className="feed-context">{entryContext(entry)}</p>
            </li>
          ))}
        </ol>
      )}
      {cursor && <button type="button" onClick={loadOlder} disabled={loading}>{loading ? "Loading…" : "Show older entries"}</button>}
    </section>
  );
}
