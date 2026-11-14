"use client";

import { createContext, useActionState, useContext, useState } from "react";
import { submitReview } from "./actions/review";

const Reviewer = createContext(null);

export function HumanReview({ crews, children }) {
  const [identity, setIdentity] = useState("superintendent:synthetic-superintendent");
  const [role, actor] = identity.split(":");
  const leads = [...new Map(crews.map((crew) => [crew.lead.id, crew.lead])).values()];
  return (
    <Reviewer.Provider value={{ role, actor }}>
      <section aria-labelledby="reviewer-title">
        <h2 id="reviewer-title">Dashboard reviewer</h2>
        <p>Demo role switcher using synthetic identities. This is not production authentication.</p>
        <label>Act as
          <select value={identity} onChange={(event) => setIdentity(event.target.value)}>
            <option value="superintendent:synthetic-superintendent">Superintendent</option>
            {leads.map((lead) => <option key={lead.id} value={`crew_lead:${lead.id}`}>Crew Lead · {lead.name}</option>)}
          </select>
        </label>
      </section>
      {children}
    </Reviewer.Provider>
  );
}

function ReviewForm({ kind, record, children, label }) {
  const reviewer = useContext(Reviewer);
  const [result, formAction, pending] = useActionState(submitReview.bind(null, kind, record.id), null);
  return (
    <form action={formAction}>
      <input type="hidden" name="actor" value={reviewer.actor} />
      <input type="hidden" name="role" value={reviewer.role} />
      <fieldset disabled={pending}>
        <legend>{label}</legend>
        {children}
        <label>Reason<textarea name="reason" required maxLength={2000} /></label>
        <button type="submit">{pending ? "Recording…" : "Record decision"}</button>
      </fieldset>
      {result?.error && <p role="alert">{result.error}</p>}
      {result?.message && <p role="status">{result.message}</p>}
    </form>
  );
}

export function FlagActions({ flag }) {
  const reviewer = useContext(Reviewer);
  if (["resolved", "false_alarm"].includes(flag.state)) return null;
  if (reviewer.role === "crew_lead" && reviewer.actor !== flag.responsible?.id) {
    return <p>Only the responsible Crew Lead or Superintendent may act on this Flag.</p>;
  }
  if (flag.state === "detected") return <p>Awaiting notification delivery before acknowledgment.</p>;
  return (
    <ReviewForm kind="flag" record={flag} label="Flag feedback">
      <input type="hidden" name="expected_state" value={flag.state} />
      <p>Flag feedback does not confirm Evidence or approve a Proposal.</p>
      <label>Decision
        <select name="action" key={flag.state} defaultValue={flag.state === "notified" ? "acknowledge" : flag.state === "in_progress" ? "resolved" : "false_alarm"}>
          {flag.state === "notified" && <option value="acknowledge">Acknowledge · problem confirmed</option>}
          {flag.state === "in_progress" && <option value="resolved">Close · resolved</option>}
          <option value="false_alarm">Close · false alarm</option>
        </select>
      </label>
      {flag.state === "acknowledged" && <p>Resolving this Flag requires an approved measure first.</p>}
      {flag.sources.some((event) => event.intent === "planned_work") && (
        <label>Optional extraction correction · only applied when closing as false alarm
          <select name="correction_event_id" defaultValue="">
            <option value="">No extraction correction</option>
            {flag.sources.filter((event) => event.intent === "planned_work").map((event) => (
              <option key={event.id} value={event.id}>Question, not planned work: {event.quote}</option>
            ))}
          </select>
          <small>Applies only to an exact replay of this message, sender role and Crew. Never confirms Evidence or changes safety rules.</small>
        </label>
      )}
    </ReviewForm>
  );
}

export function ProposalActions({ flag, proposal }) {
  const reviewer = useContext(Reviewer);
  if (proposal.status !== "proposed" || ["resolved", "false_alarm"].includes(flag.state)) return null;
  if (reviewer.role !== "superintendent") return <p>Only the Superintendent decides on Proposals.</p>;
  const canApprove = ["acknowledged", "in_progress"].includes(flag.state);
  return (
    <ReviewForm kind="proposal" record={proposal} label="Superintendent decision">
      <p>Approval sends the follow-up to the affected Crew Leads. It neither confirms Evidence nor closes the Flag.</p>
      {!canApprove && <p>Acknowledge the Flag before approving a measure.</p>}
      <label>Decision
        <select name="decision" key={flag.state} defaultValue={canApprove ? "approved" : "rejected"}>
          {canApprove && <option value="approved">Approve and send follow-up</option>}
          <option value="rejected">Reject · nothing is sent</option>
        </select>
      </label>
    </ReviewForm>
  );
}

export function EvidenceActions({ evidence, crews, tasks }) {
  const reviewer = useContext(Reviewer);
  const task = tasks.find((item) => item.id === evidence.scope.task_id);
  const crew = crews.find((item) => item.id === (evidence.scope.crew_id || task?.crew_id));
  if (reviewer.role === "crew_lead" && (evidence.scope.kind === "inspection" || (crew && reviewer.actor !== crew.lead.id))) {
    return <p>Review requires the Superintendent or the responsible Crew Lead. Inspection review requires the Superintendent.</p>;
  }
  return (
    <ReviewForm kind="evidence" record={evidence} label="Review source and exact scope">
      <input type="hidden" name="expected_sequence" value={evidence.history.at(-1)?.sequence || 0} />
      <p>Check the quote, source and scope before deciding. This neither closes a Flag nor approves a Proposal.</p>
      <label>Evidence decision
        <select name="decision" key={evidence.review_status} defaultValue={evidence.review_status === "confirmed" ? "rejected" : "confirmed"}>
          {evidence.review_status !== "confirmed" && <option value="confirmed">Confirm this exact Evidence</option>}
          {evidence.review_status !== "rejected" && <option value="rejected">Reject this Evidence</option>}
        </select>
      </label>
    </ReviewForm>
  );
}
