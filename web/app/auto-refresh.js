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
