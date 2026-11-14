"""Load a complete static site snapshot; also used by the REST import endpoint."""

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_engine


def load_seed(directory: Path) -> schemas.Seed:
    def read(name):
        return json.loads((directory / name).read_text(encoding="utf-8-sig"))

    with (directory / "schedule.csv").open(encoding="utf-8-sig", newline="") as file:
        tasks = list(csv.DictReader(file))
    for task in tasks:
        task["predecessor_ids"] = task["predecessor_ids"].split("|") if task["predecessor_ids"] else []
    return schemas.Seed.model_validate({
        **read("building.json"),
        **read("crews.json"),
        **read("revisions.json"),
        "inspections": read("inspections.json"),
        "tasks": tasks,
        "evidence": read("evidence.json"),
    })


def import_seed(session: Session, seed: schemas.Seed) -> schemas.ImportResult:
    # Validation is complete before the transaction starts. Readers see either
    # the old or the new snapshot, never a partly imported hierarchy.
    with session.begin():
        for table in (
            models.Proposal.__table__,
            models.OutboxMessage.__table__, models.FlagAudit.__table__, models.FlagSource.__table__, models.Flag.__table__,
            models.EvidenceReview.__table__, models.Evidence.__table__,
            models.event_zones, models.Event.__table__,
            models.SourceAttachment.__table__, models.SourceMessage.__table__,
            models.task_dependencies, models.RevisionAcknowledgment.__table__,
            models.revision_zones, models.Inspection.__table__, models.Task.__table__,
            models.Revision.__table__, models.Plan.__table__, models.Crew.__table__,
            models.CrewLead.__table__, models.Zone.__table__, models.Site.__table__,
        ):
            session.execute(delete(table))
        session.add(models.Site(**seed.site.model_dump()))
        session.flush()

        for kind in ("building", "floor", "unit", "room", "element"):
            session.add_all([
                models.Zone(site_id=seed.site.id, **zone.model_dump())
                for zone in seed.zones if zone.kind == kind
            ])
            session.flush()

        session.add_all([models.CrewLead(**lead.model_dump()) for lead in seed.crew_leads])
        session.flush()
        session.add_all([models.Crew(**crew.model_dump()) for crew in seed.crews])
        session.add_all([models.Plan(**plan.model_dump()) for plan in seed.plans])
        session.flush()

        tasks = {
            task.id: models.Task(**task.model_dump(exclude={"predecessor_ids"}))
            for task in seed.tasks
        }
        session.add_all(tasks.values())
        session.flush()
        for task in seed.tasks:
            tasks[task.id].predecessors = [tasks[key] for key in task.predecessor_ids]

        for revision in seed.revisions:
            record = models.Revision(**revision.model_dump(exclude={"zone_ids"}))
            record.zones = [session.get(models.Zone, key) for key in revision.zone_ids]
            session.add(record)
        session.flush()
        session.add_all([
            models.RevisionAcknowledgment(**ack.model_dump())
            for ack in seed.acknowledgments
        ])
        session.add_all([
            models.Inspection(**inspection.model_dump())
            for inspection in seed.inspections
        ])
        session.flush()
        import_ref, imported_at = uuid4().hex, datetime.now(UTC)
        for evidence in seed.evidence:
            record = models.Evidence(
                **evidence.model_dump(exclude={"scope", "review_status"}),
                **evidence.scope.model_dump(),
                import_ref=import_ref, imported_at=imported_at,
            )
            record.history = [models.EvidenceReview(
                sequence=1, status=evidence.review_status, actor_type="seed_import",
                reviewer_id=None, reviewer_role=None, decided_at=None,
                recorded_at=imported_at,
            )]
            session.add(record)

    return schemas.ImportResult(
        site_id=seed.site.id,
        **{key: len(getattr(seed, key)) for key in (
            "zones", "tasks", "crews", "plans", "revisions", "acknowledgments", "inspections", "evidence",
        )},
    )


def main():
    parser = argparse.ArgumentParser(description="Replace the static site record with a seed snapshot")
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parents[1] / "seed")
    args = parser.parse_args()
    seed = load_seed(args.directory)
    with Session(get_engine()) as session:
        print(import_seed(session, seed).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
