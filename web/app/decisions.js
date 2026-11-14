"use client";

import { useActionState } from "react";
import { submitReview } from "./actions/review";
import { useApp } from "./app-context";

// Each human decision has its own form and endpoint: Flag acknowledgment, Flag closure and Evidence review
// never imply one another. The API re-validates role, person, state and scope; these checks only explain.

function ReviewForm({ kind, record, children }) {
  const { actor, role } = useApp();
  const [result, formAction, pending] = useActionState(submitReview.bind(null, kind, record.id), null);
  return (
    <form action={formAction}>
      <input type="hidden" name="actor" value={actor} />
      <input type="hidden" name="role" value={role} />
      <fieldset disabled={pending}>
        {children}
        {pending && <p className="form-note" role="status">Recording…</p>}
      </fieldset>
      {result?.error && <p className="form-msg" role="alert">{result.error}</p>}
      {result?.message && <p className="form-msg" role="status">{result.message}</p>}
    </form>
  );
}

const Reason = ({ id }) => (
  <label className="field" htmlFor={id}>Reason (required)
    <textarea id={id} name="reason" required maxLength={2000} rows={2} />
  </label>
);

const CLOSABLE = ["notified", "acknowledged", "in_progress"];

/** Acknowledge and Close as two separate cards; Crew Leads only for Flags they are responsible for. */
export function FlagDecisions({ flag }) {
  const { role, actor } = useApp();
  const closed = ["resolved", "false_alarm"].includes(flag.state);
  const foreignLead = role === "crew_lead" && actor !== flag.responsible?.id;
  const title = role === "crew_lead" ? "Crew Lead: acknowledge your warning" : "Acknowledge";
  return (
    <>
      <section className="panel" aria-labelledby="ack-h">
        <h2 id="ack-h">{title}</h2>
        <div className="pad stack">
          {closed ? <p className="form-note">This Flag is closed. Its feedback is in the timeline.</p>
            : foreignLead ? <p className="form-note">Only the responsible Crew Lead or the Superintendent may act on this Flag.</p>
              : flag.state === "detected" ? <p className="form-note">Awaiting notification delivery before acknowledgment.</p>
                : flag.state !== "notified" ? <p className="form-note">Acknowledged. The Flag stays open until a person closes it.</p>
                  : (
                    <ReviewForm kind="flag" record={flag}>
                      <input type="hidden" name="expected_state" value={flag.state} />
                      <input type="hidden" name="action" value="acknowledge" />
                      <Reason id={`ack-reason-${flag.id}`} />
                      <button type="submit" className="btn">Acknowledge flag</button>
                    </ReviewForm>
                  )}
          <p className="form-note">Confirms the problem was seen. It confirms no Evidence, approves no work and does not close the Flag.</p>
        </div>
      </section>

      {role === "crew_lead" && foreignLead ? null : (
        <section className="panel" aria-labelledby="close-h">
          <h2 id="close-h">Close flag</h2>
          <div className="pad stack">
            {closed ? <p className="form-note">Already closed.</p>
              : !CLOSABLE.includes(flag.state) ? <p className="form-note">Closing becomes possible once the Flag has been notified.</p>
                : (
                  <ReviewForm kind="flag" record={flag}>
                    <input type="hidden" name="expected_state" value={flag.state} />
                    <div role="radiogroup" aria-label="Feedback" className="stack" style={{ gap: 6 }}>
                      <label className="field-row">
                        <input type="radio" name="action" value="resolved" required disabled={flag.state !== "in_progress"} /> Resolved
                      </label>
                      {flag.state !== "in_progress" && <p className="form-note">Resolved needs an approved measure first (Flag in progress).</p>}
                      <label className="field-row"><input type="radio" name="action" value="false_alarm" required /> False alarm</label>
                    </div>
                    <Reason id={`close-reason-${flag.id}`} />
                    <button type="submit" className="btn btn-crit">Close flag</button>
                  </ReviewForm>
                )}
            <p className="form-note">Closing confirms no Evidence. The system never closes Flags itself.</p>
          </div>
        </section>
      )}

      {role === "crew_lead" && (
        <section className="panel" aria-labelledby="sup-h">
          <h2 id="sup-h">Superintendent decisions</h2>
          <p className="pad small" style={{ margin: 0 }}>Inspection Evidence review and Proposal decisions belong to the Superintendent. Switch the demo role in the sidebar to see them.</p>
        </section>
      )}
    </>
  );
}

/** Confirm or reject one exact Evidence record. Works without any Flag; never closes one. */
export function EvidenceDecision({ evidence, crews, tasks }) {
  const { role, actor } = useApp();
  const task = tasks.find((item) => item.id === evidence.scope.task_id);
  const crew = crews.find((item) => item.id === (evidence.scope.crew_id || task?.crew_id));
  if (role === "crew_lead" && (evidence.scope.kind === "inspection" || (crew && actor !== crew.lead.id))) {
    return <p className="form-note">Review requires the Superintendent or the responsible Crew Lead. Inspection review requires the Superintendent.</p>;
  }
  return (
    <ReviewForm kind="evidence" record={evidence}>
      <input type="hidden" name="expected_sequence" value={evidence.history.at(-1)?.sequence || 0} />
      <Reason id={`ev-reason-${evidence.id}`} />
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {evidence.review_status !== "confirmed" && <button type="submit" name="decision" value="confirmed" className="btn btn-ok">Confirm</button>}
        {evidence.review_status !== "rejected" && <button type="submit" name="decision" value="rejected" className="btn btn-crit">Reject</button>}
      </div>
    </ReviewForm>
  );
}

