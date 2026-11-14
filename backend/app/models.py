from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, JSON, LargeBinary, String, Table, Text,
    UniqueConstraint, event, inspect,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date]
    timezone: Mapped[str] = mapped_column(String(64))


class Zone(Base):
    __tablename__ = "zones"
    __table_args__ = (
        CheckConstraint("kind IN ('building','floor','unit','room','element')", name="zone_kind"),
        CheckConstraint("height_m IS NULL OR height_m > 0", name="zone_height"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("zones.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    elevation_m: Mapped[float | None] = mapped_column(Float)
    height_m: Mapped[float | None] = mapped_column(Float)


class CrewLead(Base):
    __tablename__ = "crew_leads"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254))


class Crew(Base):
    __tablename__ = "crews"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    trade: Mapped[str] = mapped_column(String(64))
    lead_id: Mapped[str] = mapped_column(ForeignKey("crew_leads.id"))
    lead: Mapped[CrewLead] = relationship(lazy="selectin")


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    floor_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), unique=True)


revision_zones = Table(
    "revision_zones", Base.metadata,
    Column("revision_id", ForeignKey("revisions.id"), primary_key=True),
    Column("zone_id", ForeignKey("zones.id"), primary_key=True),
)


class Revision(Base):
    __tablename__ = "revisions"
    __table_args__ = (
        UniqueConstraint("plan_id", "sequence", name="revision_plan_sequence"),
        UniqueConstraint("plan_id", "label", name="revision_plan_label"),
        CheckConstraint("sequence > 0", name="revision_positive_sequence"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), index=True)
    label: Mapped[str] = mapped_column(String(20))
    sequence: Mapped[int] = mapped_column(Integer)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    file_name: Mapped[str | None] = mapped_column(String(200))
    zones: Mapped[list[Zone]] = relationship(secondary=revision_zones, lazy="selectin")
    acknowledgments: Mapped[list["RevisionAcknowledgment"]] = relationship(lazy="selectin")

    @property
    def zone_ids(self):
        return sorted(zone.id for zone in self.zones)


class RevisionAcknowledgment(Base):
    __tablename__ = "revision_acknowledgments"
    crew_id: Mapped[str] = mapped_column(ForeignKey("crews.id"), primary_key=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("revisions.id"), primary_key=True)
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


task_dependencies = Table(
    "task_dependencies", Base.metadata,
    Column("task_id", ForeignKey("tasks.id"), primary_key=True),
    Column("predecessor_id", ForeignKey("tasks.id"), primary_key=True),
    CheckConstraint("task_id != predecessor_id", name="task_not_own_predecessor"),
)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (CheckConstraint("ends_at > starts_at", name="task_time_range"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), index=True)
    crew_id: Mapped[str] = mapped_column(ForeignKey("crews.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    predecessors: Mapped[list["Task"]] = relationship(
        secondary=task_dependencies,
        primaryjoin=id == task_dependencies.c.task_id,
        secondaryjoin=id == task_dependencies.c.predecessor_id,
        lazy="selectin",
    )

    @property
    def predecessor_ids(self):
        return sorted(task.id for task in self.predecessors)


class Inspection(Base):
    __tablename__ = "inspections"
    __table_args__ = (
        CheckConstraint("status IN ('pending','passed','failed')", name="inspection_status"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceMessage(Base):
    __tablename__ = "source_messages"
    __table_args__ = (
        UniqueConstraint("channel", "source_key", "external_id", name="source_message_identity"),
        CheckConstraint("status IN ('pending','processing','processed','failed')", name="source_message_status"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"))
    channel: Mapped[str] = mapped_column(String(32))
    source_key: Mapped[str] = mapped_column(String(200))
    external_id: Mapped[str] = mapped_column(String(200))
    payload_hash: Mapped[str] = mapped_column(String(64))
    sender_id: Mapped[str | None] = mapped_column(String(200))
    sender_role: Mapped[str] = mapped_column(String(32))
    sender_crew_id: Mapped[str | None] = mapped_column(ForeignKey("crews.id"))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(40))
    processing_token: Mapped[str | None] = mapped_column(String(64))
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extraction_backend: Mapped[str | None] = mapped_column(String(200))
    attachments: Mapped[list["SourceAttachment"]] = relationship(lazy="selectin", order_by="SourceAttachment.id")


class SourceAttachment(Base):
    __tablename__ = "source_attachments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_message_id: Mapped[str] = mapped_column(ForeignKey("source_messages.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(200))
    media_type: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary)


event_zones = Table(
    "event_zones", Base.metadata,
    Column("event_id", ForeignKey("events.id"), primary_key=True),
    Column("zone_id", ForeignKey("zones.id"), primary_key=True),
)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("source_message_id", "ordinal", name="event_source_ordinal"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="event_confidence"),
        CheckConstraint("ordinal >= 0", name="event_ordinal"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_message_id: Mapped[str] = mapped_column(ForeignKey("source_messages.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    intent: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str | None] = mapped_column(String(200))
    crew_id: Mapped[str | None] = mapped_column(ForeignKey("crews.id"))
    activity: Mapped[str | None] = mapped_column(String(200))
    trade: Mapped[str | None] = mapped_column(String(64))
    quote: Mapped[str] = mapped_column(String(2000))
    confidence: Mapped[float] = mapped_column(Float)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_precision: Mapped[str] = mapped_column(String(20))
    time_expression: Mapped[str | None] = mapped_column(String(200))
    unresolved_zones: Mapped[list] = mapped_column(JSON)
    details: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    zones: Mapped[list[Zone]] = relationship(secondary=event_zones, lazy="selectin")
    source: Mapped[SourceMessage] = relationship(lazy="selectin")

    @property
    def zone_ids(self):
        return sorted(zone.id for zone in self.zones)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint("kind IN ('inspection','task_completion','revision_acknowledgment')", name="evidence_kind"),
        CheckConstraint("origin IN ('seed_baseline','seed_statement','llm_statement')", name="evidence_origin"),
        CheckConstraint(
            "(kind = 'inspection' AND task_id IS NULL AND crew_id IS NULL AND revision_id IS NULL AND claim IN ('pending','passed','failed')) OR "
            "(kind = 'task_completion' AND inspection_id IS NULL AND crew_id IS NULL AND revision_id IS NULL AND claim IN ('completed','not_completed')) OR "
            "(kind = 'revision_acknowledgment' AND inspection_id IS NULL AND task_id IS NULL AND claim IN ('acknowledged','not_acknowledged'))",
            name="evidence_subject",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    origin: Mapped[str] = mapped_column(String(30))
    statement_ref: Mapped[str | None] = mapped_column(String(200))
    source_ref: Mapped[str] = mapped_column(String(200))
    quote: Mapped[str] = mapped_column(String(2000))
    kind: Mapped[str] = mapped_column(String(30), server_default="warning")
    claim: Mapped[str] = mapped_column(String(30))
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("zones.id"), index=True)
    inspection_id: Mapped[str | None] = mapped_column(ForeignKey("inspections.id"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), index=True)
    crew_id: Mapped[str | None] = mapped_column(ForeignKey("crews.id"))
    revision_id: Mapped[str | None] = mapped_column(ForeignKey("revisions.id"))
    import_ref: Mapped[str | None] = mapped_column(String(64))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    history: Mapped[list["EvidenceReview"]] = relationship(
        lazy="selectin", order_by="EvidenceReview.sequence", back_populates="evidence",
    )

    @property
    def review_status(self):
        return self.history[-1].status if self.history else "unconfirmed"

    @property
    def scope(self):
        return {key: getattr(self, key) for key in (
            "kind", "zone_id", "inspection_id", "task_id", "crew_id", "revision_id",
        )}


class EvidenceReview(Base):
    __tablename__ = "evidence_reviews"
    __table_args__ = (
        UniqueConstraint("evidence_id", "sequence", name="evidence_review_sequence"),
        CheckConstraint("sequence > 0", name="evidence_review_positive_sequence"),
        CheckConstraint("status IN ('unconfirmed','confirmed','rejected')", name="evidence_review_status"),
        CheckConstraint(
            "(actor_type = 'human' AND status IN ('confirmed','rejected') AND "
            "reviewer_id IS NOT NULL AND length(reviewer_id) > 0 AND "
            "reviewer_role IS NOT NULL AND reviewer_role IN ('superintendent','crew_lead') AND decided_at IS NOT NULL) OR "
            "(actor_type IN ('seed_import','statement_ingestion') AND reviewer_id IS NULL AND "
            "reviewer_role IS NULL AND decided_at IS NULL AND "
            "(status = 'unconfirmed' OR (actor_type = 'seed_import' AND status = 'confirmed')))",
            name="evidence_review_actor",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"), index=True)
    evidence: Mapped[Evidence] = relationship(back_populates="history")
    sequence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    actor_type: Mapped[str] = mapped_column(String(30))
    reviewer_id: Mapped[str | None] = mapped_column(String(64))
    reviewer_role: Mapped[str | None] = mapped_column(String(30))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)


@event.listens_for(EvidenceReview, "before_update")
@event.listens_for(EvidenceReview, "before_delete")
def preserve_evidence_review_history(_mapper, _connection, _record):
    raise ValueError("Evidence review history is append-only; use explicit seed reset to clear demo data")


@event.listens_for(Evidence, "before_update")
def preserve_evidence_source_and_scope(_mapper, _connection, record):
    if any(inspect(record).attrs[column.key].history.has_changes() for column in Evidence.__table__.columns):
        raise ValueError("Evidence content is immutable; store a new statement or clarification separately")


class Flag(Base):
    __tablename__ = "flags"
    __table_args__ = (
        CheckConstraint("state IN ('detected','notified','acknowledged','in_progress','resolved','false_alarm')", name="flag_state"),
        CheckConstraint("severity IN ('high','medium','low')", name="flag_severity"),
        CheckConstraint("evaluation IN ('satisfied','not_satisfied','unknown','contradictory')", name="flag_evaluation"),
        UniqueConstraint("open_key", name="flag_open_conflict"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(32))
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    activity: Mapped[str] = mapped_column(String(200))
    precondition: Mapped[str] = mapped_column(String(64))
    inspection_id: Mapped[str | None] = mapped_column(ForeignKey("inspections.id"))
    severity: Mapped[str] = mapped_column(String(20))
    responsible_id: Mapped[str | None] = mapped_column(ForeignKey("crew_leads.id"))
    responsible: Mapped[CrewLead | None] = relationship(lazy="selectin")
    state: Mapped[str] = mapped_column(String(20))
    evaluation: Mapped[str] = mapped_column(String(20))
    explanation: Mapped[str] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    open_key: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sources: Mapped[list["FlagSource"]] = relationship(lazy="selectin", order_by="FlagSource.attached_at, FlagSource.event_id")
    audit: Mapped[list["FlagAudit"]] = relationship(lazy="selectin", order_by="FlagAudit.id")


class FlagAdvice(Base):
    """Advisory LLM output for one Flag. It never changes the Flag or Evidence."""
    __tablename__ = "flag_advice"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    flag_id: Mapped[str] = mapped_column(ForeignKey("flags.id"), unique=True)
    backend: Mapped[str] = mapped_column(String(200))
    explanation: Mapped[str] = mapped_column(Text)
    # Citation handle -> record reference, e.g. {"S1": "source:<id>", "inspection:rough-in-F3": ...}.
    citations: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    proposals: Mapped[list["Proposal"]] = relationship(lazy="selectin", order_by="Proposal.ordinal", back_populates="advice")


class Proposal(Base):
    __tablename__ = "proposals"
    __table_args__ = (
        UniqueConstraint("advice_id", "ordinal", name="proposal_advice_ordinal"),
        CheckConstraint("status IN ('proposed','approved','rejected')", name="proposal_status"),
        CheckConstraint(
            "(status = 'proposed' AND decided_by IS NULL AND decided_role IS NULL AND decided_at IS NULL) OR "
            "(status IN ('approved','rejected') AND decided_by IS NOT NULL AND decided_role = 'superintendent' "
            "AND decided_at IS NOT NULL AND decision_reason IS NOT NULL)",
            name="proposal_decision",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    flag_id: Mapped[str] = mapped_column(ForeignKey("flags.id"), index=True)
    channel: Mapped[str] = mapped_column(String(32))
    source_refs: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    advice_id: Mapped[str | None] = mapped_column(ForeignKey("flag_advice.id", name="fk_proposals_advice_id"), index=True)
    advice: Mapped[FlagAdvice | None] = relationship(back_populates="proposals")
    ordinal: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    affected_crews: Mapped[list] = mapped_column(JSON, default=list)
    affected_tasks: Mapped[list] = mapped_column(JSON, default=list)
    affected_zones: Mapped[list] = mapped_column(JSON, default=list)
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    decided_by: Mapped[str | None] = mapped_column(String(64))
    decided_role: Mapped[str | None] = mapped_column(String(30))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"
    __table_args__ = (
        UniqueConstraint("dedup_key", name="outbox_dedup_key"),
        CheckConstraint("status IN ('pending','sending','sent','failed','cancelled')", name="outbox_status"),
        CheckConstraint("channel IN ('gmail','telegram')", name="outbox_channel"),
        CheckConstraint("attempts >= 0", name="outbox_attempts"),
        CheckConstraint("kind IN ('warning','escalation','approval_request','proposal_followup','compliance_reply','qa_reply','decision_request')", name="outbox_kind"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    flag_id: Mapped[str | None] = mapped_column(ForeignKey("flags.id"))
    flag: Mapped[Flag | None] = relationship()
    kind: Mapped[str] = mapped_column(String(30), server_default="warning")
    # warning:<flag> | approval:<advice> | followup:<proposal>:<lead> | telegram-<kind>:<source>.
    dedup_key: Mapped[str | None] = mapped_column(String(200))
    recipient: Mapped[str | None] = mapped_column(String(254))
    channel: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    attempts: Mapped[int] = mapped_column(Integer)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lease_token: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(40))
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FlagSource(Base):
    __tablename__ = "flag_sources"
    flag_id: Mapped[str] = mapped_column(ForeignKey("flags.id"), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), primary_key=True)
    event: Mapped[Event] = relationship(lazy="selectin")
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FlagAudit(Base):
    __tablename__ = "flag_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flag_id: Mapped[str] = mapped_column(ForeignKey("flags.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(32))
    source_ref: Mapped[str] = mapped_column(String(200))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_role: Mapped[str | None] = mapped_column(String(30))
    from_state: Mapped[str | None] = mapped_column(String(20))
    to_state: Mapped[str | None] = mapped_column(String(20))
    feedback: Mapped[str | None] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)


@event.listens_for(FlagAudit, "before_update")
@event.listens_for(FlagAudit, "before_delete")
def preserve_flag_audit(_mapper, _connection, _record):
    raise ValueError("Flag audit is append-only; use explicit seed reset to clear demo data")


class SiteKnowledge(Base):
    __tablename__ = "site_knowledge"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    feedback_id: Mapped[int] = mapped_column(ForeignKey("flag_audit.id"), unique=True)
    correction_event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"))
    source_text_sha256: Mapped[str | None] = mapped_column(String(64))
    feedback: Mapped[FlagAudit] = relationship(lazy="selectin")
    correction_event: Mapped[Event | None] = relationship(lazy="selectin")


class PlanGeometry(Base):
    __tablename__ = "plan_geometry"
    revision_id: Mapped[str] = mapped_column(ForeignKey("revisions.id", ondelete="CASCADE"), primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(200))
    source: Mapped[bytes] = mapped_column(LargeBinary)
    source_sha256: Mapped[str] = mapped_column(String(64))
    floor_height_m: Mapped[float] = mapped_column(Float)
    floor_elevation_m: Mapped[float] = mapped_column(Float)
    ignored_layers: Mapped[list] = mapped_column(JSON)


geometry_element_zones = Table(
    "geometry_element_zones", Base.metadata,
    Column("element_id", ForeignKey("geometry_elements.id", ondelete="CASCADE"), primary_key=True),
    Column("zone_id", ForeignKey("zones.id", ondelete="CASCADE"), primary_key=True),
)


class GeometryElement(Base):
    __tablename__ = "geometry_elements"
    __table_args__ = (UniqueConstraint("revision_id", "element_id", name="geometry_revision_element"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("plan_geometry.revision_id", ondelete="CASCADE"), index=True)
    element_id: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30), server_default="warning")
    layer: Mapped[str] = mapped_column(String(200))
    shape: Mapped[dict] = mapped_column(JSON)
    zones: Mapped[list[Zone]] = relationship(secondary=geometry_element_zones, lazy="selectin")

    @property
    def zone_ids(self):
        return sorted(zone.id for zone in self.zones)
