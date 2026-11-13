from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_session
from app.seed import import_seed

router = APIRouter()
Database = Annotated[Session, Depends(get_session)]


def zone_scope(session, zone_id, include_descendants):
    zones = session.scalars(select(models.Zone)).all()
    if zone_id not in {zone.id for zone in zones}:
        raise HTTPException(404, "Zone not found")
    ids = {zone_id}
    if include_descendants:
        while True:
            expanded = ids | {zone.id for zone in zones if zone.parent_id in ids}
            if ids == expanded:
                break
            ids = expanded
    return ids


@router.get("/site", response_model=schemas.Site | None, tags=["Site"])
def get_site(session: Database):
    """The seeded Site, or null before the first import."""
    return session.scalar(select(models.Site))


@router.get("/zones", response_model=list[schemas.ZoneNode], tags=["Zones"])
def get_zones(session: Database):
    """Building → floor → unit → room/element, including floor metadata."""
    zones = session.scalars(select(models.Zone).order_by(models.Zone.id)).all()
    nodes = {zone.id: schemas.ZoneNode.model_validate(zone) for zone in zones}
    roots = []
    for zone in zones:
        if zone.parent_id is None:
            roots.append(nodes[zone.id])
        else:
            nodes[zone.parent_id].children.append(nodes[zone.id])
    return roots


@router.get("/crews", response_model=list[schemas.CrewView], tags=["Crews"])
def get_crews(session: Database):
    return session.scalars(select(models.Crew).order_by(models.Crew.id)).all()


@router.get("/tasks", response_model=list[schemas.Task], tags=["Tasks"])
def get_tasks(
    session: Database,
    zone_id: str | None = None,
    include_descendants: bool = True,
    from_time: schemas.Timestamp | None = None,
    to_time: schemas.Timestamp | None = None,
):
    """Tasks overlapping [from_time, to_time); zone filtering includes descendants by default."""
    if from_time is not None and to_time is not None and from_time >= to_time:
        raise HTTPException(422, "from_time must be before to_time")
    statement = select(models.Task).order_by(models.Task.starts_at, models.Task.id)
    if zone_id is not None:
        statement = statement.where(models.Task.zone_id.in_(zone_scope(session, zone_id, include_descendants)))
    if from_time is not None:
        statement = statement.where(models.Task.ends_at > from_time)
    if to_time is not None:
        statement = statement.where(models.Task.starts_at < to_time)
    return session.scalars(statement).all()


@router.get("/plans", response_model=list[schemas.PlanView], tags=["Plans"])
def get_plans(session: Database):
    """Current revision is the highest sequence per plan; all acknowledgment history is retained."""
    revisions = session.scalars(
        select(models.Revision).order_by(models.Revision.sequence, models.Revision.id)
    ).all()
    result = []
    for plan in session.scalars(select(models.Plan).order_by(models.Plan.id)):
        history = [schemas.RevisionView.model_validate(revision) for revision in revisions if revision.plan_id == plan.id]
        result.append(schemas.PlanView(
            **schemas.Plan.model_validate(plan).model_dump(),
            current_revision=history[-1] if history else None,
            revisions=history,
        ))
    return result


@router.get("/inspections", response_model=list[schemas.Inspection], tags=["Inspections"])
def get_inspections(
    session: Database,
    zone_id: str | None = None,
    include_descendants: bool = True,
):
    """Inspections located in a zone/subtree; no inferred ancestor status or conflict rules."""
    statement = select(models.Inspection).order_by(models.Inspection.scheduled_at, models.Inspection.id)
    if zone_id is not None:
        statement = statement.where(models.Inspection.zone_id.in_(zone_scope(session, zone_id, include_descendants)))
    return session.scalars(statement).all()


@router.post("/seed/import", response_model=schemas.ImportResult, tags=["Seed"])
def replace_seed(seed: schemas.Seed, session: Database):
    """Replace all Issue #5 static records atomically. Repeating this request resets them to this snapshot."""
    try:
        return import_seed(session, seed)
    except IntegrityError as error:
        raise HTTPException(409, "Seed import conflicted with stored records") from error


@router.get("/evidence", response_model=list[schemas.EvidenceView], tags=["Evidence"])
def get_evidence(
    session: Database,
    zone_id: str | None = None,
    include_descendants: bool = True,
    inspection_id: str | None = None,
    task_id: str | None = None,
    crew_id: str | None = None,
    revision_id: str | None = None,
    review_status: schemas.ReviewStatus | None = None,
):
    """Source-backed evidence with exact scope and ordered review history; not a Precondition evaluation."""
    statement = select(models.Evidence).order_by(models.Evidence.id)
    if zone_id is not None:
        statement = statement.where(models.Evidence.zone_id.in_(zone_scope(session, zone_id, include_descendants)))
    for key, value in (
        ("inspection_id", inspection_id), ("task_id", task_id),
        ("crew_id", crew_id), ("revision_id", revision_id),
    ):
        if value is not None:
            statement = statement.where(getattr(models.Evidence, key) == value)
    records = session.scalars(statement).all()
    return [record for record in records if review_status is None or record.review_status == review_status]
