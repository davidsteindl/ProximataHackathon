export async function postHumanAction(baseUrl, kind, id, formData) {
  if (!["flag", "evidence"].includes(kind)) return { error: "Unknown review action." };
  const payload = {
    actor: formData.get("actor"),
    role: formData.get("role"),
    channel: "dashboard",
    reason: formData.get("reason"),
  };
  let path;
  if (kind === "flag") {
    const action = formData.get("action");
    if (!["acknowledge", "resolved", "false_alarm"].includes(action)) {
      return { error: "Unknown Flag action." };
    }
    Object.assign(payload, {
      action,
      feedback: action === "acknowledge" ? "confirmed" : action,
      expected_state: formData.get("expected_state"),
    });
    path = `/flags/${encodeURIComponent(id)}/actions`;
  } else {
    Object.assign(payload, {
      decision: formData.get("decision"),
      expected_sequence: Number(formData.get("expected_sequence")),
    });
    path = `/evidence/${encodeURIComponent(id)}/reviews`;
  }
  try {
    const response = await fetch(new URL(path, baseUrl), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) {
      const body = await response.json();
      return { error: typeof body.detail === "string" ? body.detail : "Decision rejected. Check role, scope and required fields, then reload before retrying." };
    }
    return { error: null, message: "Decision recorded." };
  } catch {
    return { error: "Decision could not be recorded. Reload to check the current state before retrying." };
  }
}
