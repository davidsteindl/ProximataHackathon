"""Advisor explanations and Proposals. The LLM advises; only the Superintendent decides."""

import os
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import StringConstraints
from sqlalchemy import select

from app import models
from app.advisor import advice_facts, get_advisor, validate_advice
from app.extraction import ExtractionError
from app.lifecycle import transition_flag
from app.outbox import enqueue, flag_link, lead_route
from app.review_api import HumanAction, Reason, validate_person
from app.schemas import Identifier, Record, Timestamp
from app.site_api import Database

router = APIRouter(tags=["Proposals"])
CLOSED = {"resolved", "false_alarm"}


class CitationView(Record):
    handle: str
    ref: str
    review_status: Literal["unconfirmed", "confirmed", "rejected"] | None


class ProposalView(Record):
    id: Identifier
    ordinal: int
    action: str
    rationale: str
    affected_crews: list[str]
    affected_tasks: list[str]
    affected_zones: list[str]
    message: str
    status: Literal["proposed", "approved", "rejected"]
    decided_by: str | None
    decided_role: str | None
    decided_at: Timestamp | None
    decision_reason: str | None


class AdviceView(Record):
    id: Identifier
    flag_id: Identifier
    backend: str
    explanation: str
    citations: list[CitationView]
    created_at: Timestamp
    proposals: list[ProposalView]


def advice_view(session, flag):
    advice = session.scalar(select(models.FlagAdvice).where(models.FlagAdvice.flag_id == flag.id))
    if advice is None:
        return None
    citations = []
    for handle, ref in advice.citations.items():
        # Evidence status is shown live, so a later human review is never hidden.
        evidence = session.get(models.Evidence, ref.split(":", 1)[1]) if ref.startswith("evidence:") else None
        citations.append({"handle": handle, "ref": ref, "review_status": evidence.review_status if evidence else None})
    return AdviceView.model_validate({
        **{key: getattr(advice, key) for key in ("id", "flag_id", "backend", "explanation", "created_at", "proposals")},
        "citations": citations,
    })


def parties(proposal):
    return (f"crews {', '.join(proposal.affected_crews)}; tasks {', '.join(proposal.affected_tasks) or '-'}; "
            f"zones {', '.join(proposal.affected_zones) or '-'}")


@router.post("/flags/{flag_id}/advice", response_model=AdviceView)
def create_advice(flag_id: str, session: Database):
    """Idempotent: generate advice once per open Flag; the worker triggers it."""
    flag = session.get(models.Flag, flag_id)
    if flag is None:
        raise HTTPException(404, "Flag not found")
    if existing := advice_view(session, flag):
        return existing
    if flag.state in CLOSED:
        raise HTTPException(409, "Closed Flags get no new advice")
    facts, refs, allowed = advice_facts(session, flag)
    session.rollback()  # Hold no transaction while the advisor runs.
    try:
        advisor = get_advisor()
        advice = advisor.advise(facts)
        cited = validate_advice(advice, refs, allowed)
    except ExtractionError as error:
        raise HTTPException(502, error.code) from error
    session.scalar(select(models.Site).with_for_update())
    flag = session.get(models.Flag, flag_id)
    if existing := advice_view(session, flag):
        return existing
    if flag.state in CLOSED:
        raise HTTPException(409, "Closed Flags get no new advice")
    now = datetime.now(UTC)
    record = models.FlagAdvice(
        id=uuid4().hex, flag_id=flag.id, backend=advisor.name, explanation=advice.explanation,
        citations={handle: refs[handle] for handle in cited}, created_at=now,
        proposals=[models.Proposal(id=uuid4().hex, flag_id=flag.id, ordinal=number, status="proposed",
                                   channel="advisor", created_at=now,
                                   source_refs=list(dict.fromkeys([f"flag:{flag.id}", *[refs[handle] for handle in cited]])),
                                   **item.model_dump()) for number, item in enumerate(advice.proposals)],
    )
    session.add(record)
    flag.audit.append(models.FlagAudit(action="advice_generated", actor="advisor", channel="system",
                                       source_ref=f"advice:{record.id}", recorded_at=now))
    if record.proposals:
        lines = [f"{item.ordinal + 1}. {item.action}\n   Affected: {parties(item)}" for item in record.proposals]
        enqueue(session, flag, "approval_request", f"approval:{record.id}",
                os.environ.get("SUPERINTENDENT_EMAIL", "").strip() or None,
                f"SiteMind approval request — Flag {flag.type}, Zone {flag.zone_id}",
                f"Flag {flag.type}: {flag.activity} in Zone {flag.zone_id}; Precondition {flag.precondition}, "
                f"evaluation {flag.evaluation}.\n"
                "Advisor proposals (advisory only, nothing is executed without your approval):\n"
                + "\n".join(lines) + "\n"
                f"Review, approve or reject: {flag_link(flag.id)}\n"
                "Approving a Proposal neither confirms Evidence nor closes the Flag.", now)
    session.commit()
    return advice_view(session, flag)


class ProposalDecision(HumanAction):
    decision: Literal["approved", "rejected"]
    reason: Reason


@router.post("/proposals/{proposal_id}/decisions", response_model=AdviceView)
def decide_proposal(proposal_id: str, decision: ProposalDecision, session: Database):
    session.scalar(select(models.Site).with_for_update())
    proposal = session.get(models.Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    validate_person(session, decision)
    if decision.role != "superintendent":
        raise HTTPException(403, "Only the Superintendent may decide on a Proposal")
    if proposal.status != "proposed":
        raise HTTPException(409, "Proposal already decided")
    if proposal.advice_id is None:
        raise HTTPException(409, "Agent suggestions have no reviewed delivery targets")
    flag = session.get(models.Flag, proposal.flag_id)
    if flag.state in CLOSED:
        raise HTTPException(409, "Flag is closed")
    approved = decision.decision == "approved"
    if approved and flag.state not in {"acknowledged", "in_progress"}:
        raise HTTPException(409, "Acknowledge the Flag before approving a measure")
    now, source_ref = datetime.now(UTC), f"proposal:{proposal.id}"
    proposal.status, proposal.decided_by, proposal.decided_role = decision.decision, decision.actor, decision.role
    proposal.decided_at, proposal.decision_reason = now, decision.reason
    flag.audit.append(models.FlagAudit(action=f"proposal_{decision.decision}", actor=decision.actor,
        actor_role=decision.role, channel=decision.channel, source_ref=source_ref, recorded_at=now,
        reason=decision.reason))
    if approved:
        if flag.state == "acknowledged":
            transition_flag(session, flag, action="action_approved", actor=decision.actor, actor_type="human",
                            role=decision.role, channel=decision.channel, source_ref=source_ref)
        crews = [session.get(models.Crew, crew_id) for crew_id in proposal.affected_crews]
        for lead in {crew.lead_id: crew.lead for crew in crews if crew}.values():
            channel, recipient = lead_route(lead)
            enqueue(session, flag, "proposal_followup", f"followup:{proposal.id}:{lead.id}", recipient,
                    f"SiteMind: approved measure — Zone {flag.zone_id}",
                    f"The Superintendent approved this measure for Flag {flag.type} in Zone {flag.zone_id}:\n"
                    f"{proposal.action}\n\n{proposal.message}\n\n"
                    f"Affected: {parties(proposal)}.\nApproved {now.isoformat()} · {source_ref}.\n"
                    "This does not confirm any inspection or other Evidence and does not close the Flag.\n"
                    f"Details: {flag_link(flag.id)}", now, channel)
    session.commit()
    return advice_view(session, flag)


ProposalText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class ProposalInput(Record):
    flag_id: Identifier
    action: ProposalText
    rationale: ProposalText


class ProposalRecordView(ProposalInput):
    id: Identifier
    status: Literal["proposed", "approved", "rejected"]
    channel: Literal["mcp", "chat", "agent", "advisor"]
    source_refs: list[str]
    created_at: Timestamp


@router.post("/agent/proposals", response_model=ProposalRecordView, status_code=201)
def create_proposal(
    payload: ProposalInput, session: Database,
    channel: Annotated[Literal["mcp", "chat", "agent"], Header(alias="X-SiteMind-Client")] = "mcp",
):
    """Persist an unapproved suggestion; never change a Flag, Evidence, Task or the outbox."""
    session.scalar(select(models.Site).with_for_update())
    flag = session.get(models.Flag, payload.flag_id)
    if flag is None:
        raise HTTPException(404, "Flag not found")
    if flag.state in {"resolved", "false_alarm"}:
        raise HTTPException(409, "Cannot propose an action for a closed Flag")
    from app.flag_api import flag_view
    value = flag_view(session, flag)
    proposal = models.Proposal(
        **payload.model_dump(), id=str(uuid4()), status="proposed", channel=channel,
        source_refs=list(dict.fromkeys([
            f"flag:{flag.id}", *[f"source:{event.source_message_id}" for event in value.sources],
            *[evidence.source_ref for evidence in value.evidence],
        ])), created_at=datetime.now(UTC),
    )
    session.add(proposal)
    session.commit()
    return proposal


@router.get("/proposals", response_model=list[ProposalRecordView])
def list_proposals(session: Database, flag_id: str | None = None):
    statement = select(models.Proposal).order_by(models.Proposal.created_at, models.Proposal.id)
    if flag_id is not None:
        if session.get(models.Flag, flag_id) is None:
            raise HTTPException(404, "Flag not found")
        statement = statement.where(models.Proposal.flag_id == flag_id)
    return session.scalars(statement).all()


@router.get("/proposals/{proposal_id}", response_model=ProposalRecordView)
def get_proposal(proposal_id: str, session: Database):
    proposal = session.get(models.Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    return proposal
