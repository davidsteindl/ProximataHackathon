"""Deterministic comparison of extracted DXF elements, without evidence approval."""

from sqlalchemy import select

from app import cad_schemas, models
from app.cad_extract import InvalidPlan


def compare_elements(before, after, zones):
    """Stable IDs identify changes; retain both old and new unit membership."""
    old = {item.element_id: item for item in before}
    new = {item.element_id: item for item in after}
    grouped = {}
    for key in sorted(old.keys() | new.keys()):
        left, right = old.get(key), new.get(key)
        if left is not None and right is not None and (
            left.kind, left.layer, left.shape, sorted(left.zone_ids)
        ) == (right.kind, right.layer, right.shape, sorted(right.zone_ids)):
            continue
        change = cad_schemas.ElementChange(
            change="added" if left is None else "removed" if right is None else "moved",
            element_id=key, before=left, after=right,
        )
        # Floor/building associations describe coverage, not affected work.
        memberships = set(left.zone_ids if left else []) | set(right.zone_ids if right else [])
        units = sorted(key for key in memberships if zones[key].kind == "unit")
        if not units:
            raise InvalidPlan("Changed geometry cannot be assigned to a unit zone")
        for zone_id in units:
            grouped.setdefault(zone_id, []).append(change)
    return [cad_schemas.ZoneChanges(zone_id=key, changes=value) for key, value in sorted(grouped.items())]


def revision_diff(session, revision_id):
    revision = session.get(models.Revision, revision_id)
    if revision is None:
        raise InvalidPlan("Revision not found")
    previous = session.scalar(select(models.Revision).where(
        models.Revision.plan_id == revision.plan_id,
        models.Revision.sequence < revision.sequence,
    ).order_by(models.Revision.sequence.desc()).limit(1))
    if previous is None or any(session.get(models.PlanGeometry, key) is None for key in (previous.id, revision.id)):
        raise InvalidPlan("Previous and current revision geometry are required")

    def elements(key):
        return [cad_schemas.Element.model_validate(item) for item in session.scalars(
            select(models.GeometryElement).where(models.GeometryElement.revision_id == key))]

    grouped = compare_elements(elements(previous.id), elements(revision.id), {
        zone.id: zone for zone in session.scalars(select(models.Zone))
    })
    return cad_schemas.PlanDiff(
        revision_id=revision.id, previous_revision_id=previous.id,
        affected_zone_ids=[item.zone_id for item in grouped], zones=grouped,
    )
