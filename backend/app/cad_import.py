"""Import DXF files and revision metadata inside the API service."""

import argparse
import hashlib
import json
from datetime import UTC
from pathlib import Path, PurePosixPath

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import cad_schemas, models
from app.cad_extract import InvalidPlan, extract_dxf
from app.database import get_engine


class ImportConflict(ValueError):
    pass


def import_plan(session: Session, source: bytes, filename: str, metadata: cad_schemas.ImportMetadata):
    filename = PurePosixPath(filename.replace("\\", "/")).name
    if not filename.lower().endswith(".dxf") or len(filename) > 200:
        raise InvalidPlan("A DXF filename of at most 200 characters is required")
    digest = hashlib.sha256(source).hexdigest()
    with session.begin():
        plan = session.get(models.Plan, metadata.plan_id)
        floor = session.get(models.Zone, metadata.floor_id)
        if plan is None or floor is None or floor.kind != "floor" or plan.floor_id != floor.id:
            raise InvalidPlan("Sheet and floor must match the seeded building metadata")
        if floor.height_m is None or floor.elevation_m is None:
            raise InvalidPlan("Floor height and elevation are required")
        revision = session.get(models.Revision, metadata.revision_id)
        if revision is not None:
            issued_at = revision.issued_at
            if issued_at.tzinfo is None:
                issued_at = issued_at.replace(tzinfo=UTC)
            if (revision.plan_id, revision.label, revision.sequence, issued_at) != (
                metadata.plan_id, metadata.label, metadata.sequence, metadata.issued_at,
            ):
                raise ImportConflict("Revision metadata conflicts with the stored revision")
        else:
            collision = session.scalar(select(models.Revision).where(
                models.Revision.plan_id == plan.id,
                (models.Revision.label == metadata.label) | (models.Revision.sequence == metadata.sequence),
            ))
            if collision is not None:
                raise ImportConflict("Revision label/sequence is already registered with a different ID")
        stored = session.get(models.PlanGeometry, metadata.revision_id)
        if stored is not None:
            if stored.source_sha256 != digest:
                raise ImportConflict("Different source content requires a new plan revision")
            count = session.scalar(select(func.count()).select_from(models.GeometryElement).where(
                models.GeometryElement.revision_id == metadata.revision_id,
            ))
            return cad_schemas.ImportResult(
                revision_id=metadata.revision_id, element_count=count,
                source_sha256=digest, ignored_layers=stored.ignored_layers,
            )
        zones = session.scalars(select(models.Zone)).all()
        elements, ignored = extract_dxf(source, zones, metadata.floor_id)
        if revision is None:
            # Coverage comes from geometry associations. Changed/affected zones
            # belong to #17's diff; do not invent them or acknowledge a revision.
            revision = models.Revision(
                id=metadata.revision_id, plan_id=plan.id, label=metadata.label,
                sequence=metadata.sequence, issued_at=metadata.issued_at, file_name=filename,
            )
            session.add(revision)
            session.flush()
        session.add(models.PlanGeometry(
            revision_id=revision.id, original_filename=filename, source=source,
            source_sha256=digest, floor_height_m=floor.height_m,
            floor_elevation_m=floor.elevation_m,
            ignored_layers=[layer.model_dump() for layer in ignored],
        ))
        session.flush()
        by_id = {zone.id: zone for zone in zones}
        for element in elements:
            session.add(models.GeometryElement(
                revision_id=revision.id, element_id=element.element_id, kind=element.kind,
                layer=element.layer, shape=element.shape.model_dump(mode="json"),
                zones=[by_id[key] for key in element.zone_ids],
            ))
    return cad_schemas.ImportResult(
        revision_id=metadata.revision_id, element_count=len(elements),
        source_sha256=digest, ignored_layers=ignored,
    )


def main():
    parser = argparse.ArgumentParser(description="Import all DXFs listed in the metadata file")
    parser.add_argument("--metadata", type=Path, default=Path(__file__).resolve().parents[2] / "cad" / "import-metadata.json")
    args = parser.parse_args()
    entries = json.loads(args.metadata.read_text(encoding="utf-8-sig"))
    for entry in entries:
        metadata = cad_schemas.ImportMetadata.model_validate(entry["metadata"])
        path = args.metadata.parent / entry["file"]
        with Session(get_engine()) as session:
            result = import_plan(session, path.read_bytes(), path.name, metadata)
        print(result.model_dump_json())


if __name__ == "__main__":
    main()
