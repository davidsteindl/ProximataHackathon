from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import cad_schemas, models, schemas
from app.cad_extract import InvalidPlan
from app.cad_import import ImportConflict, import_plan
from app.database import get_session
from app.site_api import zone_scope

router = APIRouter(tags=["Geometry"])
Database = Annotated[Session, Depends(get_session)]


@router.post("/geometry/import", response_model=cad_schemas.ImportResult)
def upload_geometry(
    session: Database,
    file: Annotated[UploadFile, File(description="Original DXF R2000 in millimetres")],
    plan_id: Annotated[schemas.Identifier, Form()],
    floor_id: Annotated[schemas.Identifier, Form()],
    revision_id: Annotated[schemas.Identifier, Form()],
    label: Annotated[str, Form(min_length=1, max_length=20)],
    sequence: Annotated[int, Form(gt=0)],
    issued_at: Annotated[schemas.Timestamp, Form()],
):
    metadata = cad_schemas.ImportMetadata(
        plan_id=plan_id, floor_id=floor_id, revision_id=revision_id,
        label=label, sequence=sequence, issued_at=issued_at,
    )
    try:
        return import_plan(session, file.file.read(), file.filename or "plan.dxf", metadata)
    except InvalidPlan as error:
        raise HTTPException(422, str(error)) from error
    except (ImportConflict, IntegrityError) as error:
        detail = str(error) if isinstance(error, ImportConflict) else "Concurrent/conflicting revision import"
        raise HTTPException(409, detail) from error


@router.get("/geometry", response_model=list[cad_schemas.GeometryView])
def get_geometry(
    session: Database,
    floor_id: str | None = None,
    zone_id: str | None = None,
    revision_id: str | None = None,
    include_descendants: bool = True,
):
    """Latest imported geometry per plan, or an exact revision. All coordinates and heights are metres."""
    statement = select(models.PlanGeometry, models.Revision, models.Plan).join(
        models.Revision, models.Revision.id == models.PlanGeometry.revision_id,
    ).join(models.Plan, models.Plan.id == models.Revision.plan_id).order_by(
        models.Plan.id, models.Revision.sequence.desc(),
    )
    if floor_id is not None:
        floor = session.get(models.Zone, floor_id)
        if floor is None or floor.kind != "floor":
            raise HTTPException(404, "Floor not found")
        statement = statement.where(models.Plan.floor_id == floor_id)
    if revision_id is not None:
        if session.get(models.Revision, revision_id) is None:
            raise HTTPException(404, "Revision not found")
        statement = statement.where(models.Revision.id == revision_id)
    scope = zone_scope(session, zone_id, include_descendants) if zone_id is not None else None
    result, seen = [], set()
    for stored, revision, plan in session.execute(statement).all():
        if plan.id in seen:
            continue
        seen.add(plan.id)
        elements_query = select(models.GeometryElement).where(
            models.GeometryElement.revision_id == revision.id,
        ).order_by(models.GeometryElement.element_id)
        if scope is not None:
            elements_query = elements_query.where(models.GeometryElement.zones.any(models.Zone.id.in_(scope)))
        elements = session.scalars(elements_query).all()
        if scope is not None and not elements:
            continue
        result.append(cad_schemas.GeometryView(
            revision_id=revision.id, plan_id=plan.id, floor_id=plan.floor_id,
            label=revision.label, sequence=revision.sequence, issued_at=revision.issued_at,
            floor_height_m=stored.floor_height_m, floor_elevation_m=stored.floor_elevation_m,
            original_filename=stored.original_filename, source_sha256=stored.source_sha256,
            ignored_layers=stored.ignored_layers,
            elements=[cad_schemas.Element.model_validate(element) for element in elements],
        ))
    return result


@router.get("/geometry/revisions/{revision_id}/source", response_class=Response)
def get_source(revision_id: str, session: Database):
    stored = session.get(models.PlanGeometry, revision_id)
    if stored is None:
        raise HTTPException(404, "No DXF source for this revision")
    return Response(
        stored.source, media_type="image/vnd.dxf",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(stored.original_filename, safe="")},
    )
