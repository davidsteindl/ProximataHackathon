"""REST contracts for source-agnostic ingestion; caller-supplied reviews are forbidden."""

import base64
import binascii
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.schemas import EvidenceView, Identifier, Name, Record, Timestamp


SenderRole = Literal["architect", "inspector", "crew_lead", "crew", "superintendent", "unknown"]


class AttachmentInput(Record):
    file_name: Name
    media_type: Annotated[str, Field(min_length=1, max_length=100)]
    content_base64: Annotated[str, Field(max_length=2_800_000)]

    @model_validator(mode="after")
    def valid_content(self):
        try:
            content = base64.b64decode(self.content_base64, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("Attachment content must be valid base64") from error
        if not content or len(content) > 2_000_000:
            raise ValueError("Attachment must contain 1 to 2,000,000 bytes")
        if "/" in self.file_name or "\\" in self.file_name or self.file_name in {".", ".."}:
            raise ValueError("Attachment file_name must be a name, not a path")
        return self


class SourceMessageInput(Record):
    channel: Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_-]*$")]
    source_key: Name
    external_id: Name
    sender_id: Name | None = None
    sender_role: SenderRole = "unknown"
    sender_crew_id: Identifier | None = None
    sent_at: Timestamp
    text: Annotated[str, Field(max_length=50_000)]
    attachments: list[AttachmentInput] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def nonempty_message(self):
        if not self.text.strip() and not self.attachments:
            raise ValueError("A source message needs text or an attachment")
        return self


class AttachmentView(Record):
    id: Identifier
    file_name: str
    media_type: str
    sha256: str


class SourceMessageView(Record):
    id: Identifier
    channel: str
    source_key: str
    external_id: str
    sender_id: str | None
    sender_role: SenderRole
    sender_crew_id: str | None
    sent_at: Timestamp
    received_at: Timestamp
    text: str
    status: Literal["pending", "processing", "processed", "failed"]
    error_code: str | None
    extraction_backend: str | None
    attachments: list[AttachmentView]


class EventView(Record):
    id: Identifier
    source_message_id: Identifier
    intent: str
    actor: str | None
    crew_id: str | None
    activity: str | None
    trade: str | None
    zone_ids: list[str]
    unresolved_zones: list[str]
    quote: str
    confidence: float
    starts_at: Timestamp | None
    ends_at: Timestamp | None
    time_precision: str
    time_expression: str | None
    details: dict
    created_at: Timestamp
    origin: Literal["llm_statement", "llm_vision", "deterministic_plan_diff"] = "llm_statement"
    source: SourceMessageView
    evidence: list[EvidenceView] = Field(default_factory=list)

    @model_validator(mode="after")
    def event_origin(self):
        self.origin = self.details.get("origin", "llm_statement")
        return self


class IngestionResult(Record):
    source: SourceMessageView
    events: list[EventView]
    duplicate: bool
