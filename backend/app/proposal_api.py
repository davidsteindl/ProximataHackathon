"""Store advice only. Human approval and subsequent execution belong to Issue #13."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import StringConstraints
from sqlalchemy import select

from app import models, schemas
from app.flag_api import flag_view
from app.site_api import Database

router = APIRouter(tags=["Proposals"])
ProposalText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class ProposalInput(schemas.Record):
    flag_id: schemas.Identifier
    action: ProposalText
    rationale: ProposalText


class ProposalView(ProposalInput):
    id: schemas.Identifier
    status: Literal["proposed"]
    channel: Literal["mcp", "chat", "agent"]
    source_refs: list[str]
    created_at: schemas.Timestamp


@router.post("/agent/proposals", response_model=ProposalView, status_code=201)
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


@router.get("/proposals", response_model=list[ProposalView])
def list_proposals(session: Database, flag_id: str | None = None):
    statement = select(models.Proposal).order_by(models.Proposal.created_at, models.Proposal.id)
    if flag_id is not None:
        if session.get(models.Flag, flag_id) is None:
            raise HTTPException(404, "Flag not found")
        statement = statement.where(models.Proposal.flag_id == flag_id)
    return session.scalars(statement).all()


@router.get("/proposals/{proposal_id}", response_model=ProposalView)
def get_proposal(proposal_id: str, session: Database):
    proposal = session.get(models.Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    return proposal
