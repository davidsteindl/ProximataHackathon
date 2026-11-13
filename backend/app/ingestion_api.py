from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from app import models, schemas
from app.ingestion import event_views, ingestion_result, process_source, store_source
from app.ingestion_schemas import EventView, IngestionResult, SourceMessageInput, SourceMessageView
from app.site_api import Database, zone_scope

router = APIRouter(tags=["Ingestion"])


@router.post("/ingestion/messages", response_model=IngestionResult, responses={
    201: {"model": IngestionResult}, 202: {"model": IngestionResult}, 502: {"model": IngestionResult},
})
def ingest_message(payload: SourceMessageInput, session: Database, response: Response):
    """Persist a source, then extract advisory Events. Re-delivery safely retries failures."""
    source_id, duplicate = store_source(session, payload)
    process_source(session, source_id)
    result = ingestion_result(session, source_id, duplicate)
    if result.source.status == "failed":
        response.status_code = 502
    elif result.source.status in {"pending", "processing"}:
        response.status_code = 202
    else:
        response.status_code = 200 if duplicate else 201
    return result


@router.get("/source-messages/{source_id}", response_model=SourceMessageView)
def get_source_message(source_id: str, session: Database):
    """Original source and processing status; no caller-supplied review action."""
    source = session.get(models.SourceMessage, source_id)
    if source is None:
        raise HTTPException(404, "Source Message not found")
    return source


@router.get("/source-messages/{source_id}/attachments/{attachment_id}")
def get_source_attachment(source_id: str, attachment_id: str, session: Database):
    attachment = session.scalar(select(models.SourceAttachment).where(
        models.SourceAttachment.id == attachment_id, models.SourceAttachment.source_message_id == source_id,
    ))
    if attachment is None:
        raise HTTPException(404, "Source attachment not found")
    return Response(content=attachment.content, media_type="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(attachment.file_name, safe='')}",
        "X-Content-Type-Options": "nosniff",
    })


@router.get("/events", response_model=list[EventView], tags=["Events"])
def list_events(
    session: Database, zone_id: str | None = None, include_descendants: bool = True,
    from_time: schemas.Timestamp | None = None, to_time: schemas.Timestamp | None = None,
):
    """Timeline ordered by source message time, source ID and statement ordinal."""
    if from_time is not None and to_time is not None and from_time >= to_time:
        raise HTTPException(422, "from_time must be before to_time")
    statement = select(models.Event).join(models.SourceMessage).order_by(
        models.SourceMessage.sent_at, models.SourceMessage.id, models.Event.ordinal,
    )
    if zone_id is not None:
        ids = zone_scope(session, zone_id, include_descendants)
        statement = statement.where(models.Event.zones.any(models.Zone.id.in_(ids)))
    if from_time is not None:
        statement = statement.where(models.SourceMessage.sent_at >= from_time)
    if to_time is not None:
        statement = statement.where(models.SourceMessage.sent_at < to_time)
    return event_views(session, session.scalars(statement).all())
