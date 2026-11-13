export async function getHealth(baseUrl) {
  try {
    const response = await fetch(`${baseUrl}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    const health = await response.json();
    return {
      api: health.api === "ok" ? "ok" : "error",
      db: health.db === "ok" ? "ok" : "error",
    };
  } catch {
    return { api: "unreachable", db: "unknown" };
  }
}
