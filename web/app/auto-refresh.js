"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Re-renders the server page while it is visible, so dashboard counts follow Flag and Evidence changes. */
export default function AutoRefresh({ ms = 5000 }) {
  const router = useRouter();
  useEffect(() => {
    const timer = setInterval(() => { if (document.visibilityState === "visible") router.refresh(); }, ms);
    return () => clearInterval(timer);
  }, [router, ms]);
  return null;
}

/**
 * Outbox messages link to `/#flag-<id>` (and learning notes to `/#knowledge-<id>`), anchors of the former
 * single-page dashboard. Forward them to the dedicated pages so existing mails and Telegram links keep working.
 */
export function HashRedirect() {
  useEffect(() => {
    const [, kind, id] = window.location.hash.match(/^#(flag|knowledge)-(.+)$/) || [];
    // Full navigation: these are one-off entry links, and the target page should load with its anchor in place.
    if (kind === "flag") window.location.replace(`/flags/${id}`);
    if (kind === "knowledge") window.location.replace(`/activity#knowledge-${id}`);
  }, []);
  return null;
}
