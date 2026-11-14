"""DXF attachments use the same importer and keep source-backed diff provenance."""

import re
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import cad_schemas, models
from app.cad_extract import InvalidPlan
from app.cad_import import ImportConflict, import_plan_in_transaction
from app.plan_diff import revision_diff


def process_plan_attachments(session, source, events):
    from app.rules import utc

    for attachment in source.attachments:
        if not attachment.file_name.lower().endswith('.dxf'):
            continue
        match = re.fullmatch(r'([A-Za-z0-9_-]+)_Rev([A-Za-z0-9_-]+)\.dxf', attachment.file_name, re.IGNORECASE)
        plan_id, label = match.groups() if match else (None, None)
        notes = [event for event in events if event.intent == 'revision'
                 and (not match or (event.details.get('plan_reference'), event.details.get('revision_label')) == (plan_id, label))]
        diff, error = None, None
        try:
            # A malformed drawing must not roll back the explanatory note.
            with session.begin_nested():
                plan = session.get(models.Plan, plan_id) if plan_id else None
                if plan is None:
                    raise InvalidPlan('DXF filename must identify a known Plan as <plan>_Rev<label>.dxf')
                history = session.scalars(select(models.Revision).where(models.Revision.plan_id == plan.id)).all()
                revision = next((item for item in history if item.label == label), None)
                latest = max(history, key=lambda item: item.sequence, default=None)
                if revision is None and latest:
                    if utc(source.sent_at) <= utc(latest.issued_at):
                        raise InvalidPlan('Cannot establish revision sequence from historical attachment')
                metadata = cad_schemas.ImportMetadata(
                    plan_id=plan.id, floor_id=plan.floor_id,
                    revision_id=revision.id if revision else f'{plan.id}-{label}', label=label,
                    sequence=revision.sequence if revision else latest.sequence + 1 if latest else 1,
                    issued_at=utc(revision.issued_at if revision else source.sent_at),
                )
                import_plan_in_transaction(session, attachment.content, attachment.file_name, metadata)
                diff = revision_diff(session, metadata.revision_id)
                session.get(models.Revision, metadata.revision_id).zones = [
                    session.get(models.Zone, key) for key in diff.affected_zone_ids
                ]
        except (InvalidPlan, ImportConflict, IntegrityError, ValidationError) as exc:
            diff = None
            error = str(exc) if not isinstance(exc, IntegrityError) else 'Conflicting revision import'
        if diff is not None:
            if not notes:
                note = models.Event(
                    id=uuid4().hex, source_message_id=source.id, ordinal=len(events),
                    intent='revision', actor=source.sender_role, quote=attachment.file_name,
                    confidence=1, time_precision='unspecified', unresolved_zones=[],
                    created_at=datetime.now(UTC), details={}, zones=[],
                )
                session.add(note)
                events.append(note)
                notes = [note]
            for note in notes:
                note.zones = [session.get(models.Zone, key) for key in diff.affected_zone_ids]
                note.unresolved_zones = []
                details = {key: value for key, value in note.details.items() if key != 'diff_error'}
                note.details = {**details, 'plan_reference': plan_id, 'revision_label': label,
                                'revision_id': diff.revision_id, 'origin': diff.origin,
                                'affected_zones_origin': diff.origin, 'plan_diff': diff.model_dump(mode='json'),
                                'attachment_id': attachment.id, 'source_sha256': attachment.sha256,
                                'diff_status': 'succeeded'}
        else:
            for note in notes:
                # A failed/unmatched attachment cannot replace a valid result
                # or point its geometry/hash at a different source attachment.
                if note.details.get('diff_status') == 'succeeded':
                    continue
                note.details = {**note.details, 'diff_status': 'failed', 'diff_error': error,
                                'affected_zones_origin': 'unconfirmed_revision_note',
                                'attachment_id': attachment.id}
