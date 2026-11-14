from datetime import UTC, date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator,
    field_validator,
)

Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Timestamp = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(UTC))]


class Record(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def utc_from_database(cls, value):
        # PostgreSQL preserves offsets; SQLite test storage returns naive UTC.
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Site(Record):
    id: Identifier
    name: Name
    start_date: date
    timezone: Annotated[str, Field(max_length=64)]

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("timezone must be an IANA time zone") from error
        return value


class Zone(Record):
    id: Identifier
    parent_id: Identifier | None = None
    kind: Literal["building", "floor", "unit", "room", "element"]
    name: Name
    elevation_m: float | None = Field(default=None, allow_inf_nan=False)
    height_m: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class ZoneNode(Zone):
    children: list["ZoneNode"] = Field(default_factory=list)


class CrewLead(Record):
    id: Identifier
    name: Name


class Crew(Record):
    id: Identifier
    name: Name
    trade: Annotated[str, Field(min_length=1, max_length=64)]
    lead_id: Identifier


class CrewView(Crew):
    lead: CrewLead


class Plan(Record):
    id: Identifier
    name: Name
    floor_id: Identifier


class Revision(Record):
    id: Identifier
    plan_id: Identifier
    label: Annotated[str, Field(min_length=1, max_length=20)]
    sequence: int = Field(gt=0)
    issued_at: Timestamp
    file_name: Name
    zone_ids: list[Identifier] = Field(min_length=1)


class RevisionAcknowledgment(Record):
    crew_id: Identifier
    revision_id: Identifier
    acknowledged_at: Timestamp


class RevisionView(Revision):
    # Note-only revisions have no imported drawing.
    file_name: Name | None
    # A newly registered CAD revision has no affected-zone result until #17.
    zone_ids: list[Identifier]
    acknowledgments: list[RevisionAcknowledgment]


class PlanView(Plan):
    current_revision: RevisionView | None
    revisions: list[RevisionView]


class Task(Record):
    id: Identifier
    name: Name
    zone_id: Identifier
    crew_id: Identifier
    starts_at: Timestamp
    ends_at: Timestamp
    predecessor_ids: list[Identifier] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_range(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class Inspection(Record):
    id: Identifier
    zone_id: Identifier
    kind: Annotated[str, Field(min_length=1, max_length=64)]
    status: Literal["pending", "passed", "failed"]
    scheduled_at: Timestamp


ReviewStatus = Literal["unconfirmed", "confirmed", "rejected"]


class EvidenceScope(Record):
    kind: Literal["inspection", "task_completion", "revision_acknowledgment"]
    zone_id: Identifier | None = None
    inspection_id: Identifier | None = None
    task_id: Identifier | None = None
    crew_id: Identifier | None = None
    revision_id: Identifier | None = None

    @model_validator(mode="after")
    def subject_fields(self):
        fields = {
            "inspection": {"inspection_id"},
            "task_completion": {"task_id"},
            "revision_acknowledgment": {"crew_id", "revision_id"},
        }
        allowed = fields[self.kind]
        if any(getattr(self, key) is not None for key in {"inspection_id", "task_id", "crew_id", "revision_id"} - allowed):
            raise ValueError("Evidence scope mixes different subjects")
        return self


class EvidenceReview(Record):
    sequence: int
    status: ReviewStatus
    actor_type: Literal["seed_import", "statement_ingestion", "human"]
    reviewer_id: Identifier | None
    reviewer_role: Literal["superintendent", "crew_lead"] | None
    decided_at: Timestamp | None
    recorded_at: Timestamp


class EvidenceView(Record):
    id: Identifier
    origin: Literal["seed_baseline", "seed_statement", "llm_statement"]
    statement_ref: Name | None
    source_ref: Name
    quote: str
    claim: str
    scope: EvidenceScope
    review_status: ReviewStatus
    import_ref: str | None
    imported_at: Timestamp | None
    history: list[EvidenceReview]


class SeedEvidence(Record):
    id: Identifier
    origin: Literal["seed_baseline", "seed_statement"]
    statement_ref: Name | None = None
    source_ref: Name
    quote: Annotated[str, Field(min_length=1, max_length=2000)]
    claim: str
    scope: EvidenceScope
    review_status: Literal["unconfirmed", "confirmed"] = "unconfirmed"

    @model_validator(mode="after")
    def seed_trust_boundary(self):
        claims = {
            "inspection": {"pending", "passed", "failed"},
            "task_completion": {"completed", "not_completed"},
            "revision_acknowledgment": {"acknowledged", "not_acknowledged"},
        }
        if self.claim not in claims[self.scope.kind]:
            raise ValueError("Claim does not match evidence kind")
        if not self.source_ref.startswith("seed:"):
            raise ValueError("Seed evidence must have explicit seed source provenance")
        if self.origin == "seed_statement" and (self.review_status != "unconfirmed" or self.statement_ref is None):
            raise ValueError("Seed statement examples require a statement_ref and must remain unconfirmed")
        if self.origin == "seed_baseline" and self.statement_ref is not None:
            raise ValueError("Baseline facts are explicit seed evidence, not extracted statements")
        return self


class Seed(Record):
    site: Site
    zones: list[Zone] = Field(min_length=1)
    plans: list[Plan]
    crew_leads: list[CrewLead]
    crews: list[Crew]
    tasks: list[Task]
    revisions: list[Revision]
    acknowledgments: list[RevisionAcknowledgment]
    inspections: list[Inspection]
    evidence: list[SeedEvidence]

    @model_validator(mode="after")
    def valid_references(self):
        def index(items, key=lambda item: item.id):
            result = {key(item): item for item in items}
            if len(result) != len(items):
                raise ValueError("Duplicate seed identifier or relationship")
            return result

        def require(condition, message):
            if not condition:
                raise ValueError(message)

        zones, plans = index(self.zones), index(self.plans)
        leads, crews = index(self.crew_leads), index(self.crews)
        tasks, revisions = index(self.tasks), index(self.revisions)
        inspections = index(self.inspections)
        index(self.evidence)
        index(self.acknowledgments, lambda item: (item.crew_id, item.revision_id))
        index(self.revisions, lambda item: (item.plan_id, item.sequence))
        index(self.revisions, lambda item: (item.plan_id, item.label))
        index(self.plans, lambda item: item.floor_id)
        roots = [zone for zone in self.zones if zone.parent_id is None]
        require(len(roots) == 1 and roots[0].kind == "building", "One building root is required")
        allowed_parents = {"floor": {"building"}, "unit": {"floor"}, "room": {"unit"}, "element": {"unit", "room"}}
        for zone in self.zones:
            if zone.parent_id is not None:
                require(zone.parent_id in zones, f"Unknown parent for zone {zone.id}")
                require(zones[zone.parent_id].kind in allowed_parents.get(zone.kind, set()), f"Invalid hierarchy for zone {zone.id}")
            if zone.kind == "floor":
                require(zone.height_m is not None and zone.elevation_m is not None, f"Floor {zone.id} needs elevation_m and height_m")
        for crew in self.crews:
            require(crew.lead_id in leads, f"Unknown lead for crew {crew.id}")
        for plan in self.plans:
            require(plan.floor_id in zones and zones[plan.floor_id].kind == "floor", f"Plan {plan.id} must belong to a floor")
        for task in self.tasks:
            require(task.zone_id in zones and task.crew_id in crews, f"Unknown zone or crew for task {task.id}")
            require(len(set(task.predecessor_ids)) == len(task.predecessor_ids), f"Duplicate predecessor for task {task.id}")
            require(all(pred in tasks for pred in task.predecessor_ids), f"Unknown predecessor for task {task.id}")
        visiting, visited = set(), set()

        def visit(task_id):
            require(task_id not in visiting, "Task predecessors contain a cycle")
            if task_id not in visited:
                visiting.add(task_id)
                for predecessor in tasks[task_id].predecessor_ids:
                    visit(predecessor)
                visiting.remove(task_id)
                visited.add(task_id)

        for task_id in tasks:
            visit(task_id)
        for revision in self.revisions:
            require(revision.plan_id in plans, f"Unknown plan for revision {revision.id}")
            require(len(set(revision.zone_ids)) == len(revision.zone_ids), f"Duplicate zone in revision {revision.id}")
            for zone_id in revision.zone_ids:
                require(zone_id in zones, f"Unknown zone for revision {revision.id}")
                ancestor = zones[zone_id]
                while ancestor.parent_id is not None and ancestor.id != plans[revision.plan_id].floor_id:
                    ancestor = zones[ancestor.parent_id]
                require(ancestor.id == plans[revision.plan_id].floor_id, f"Revision {revision.id} zone is outside its plan floor")
        for acknowledgment in self.acknowledgments:
            require(acknowledgment.crew_id in crews and acknowledgment.revision_id in revisions, "Unknown crew or revision in acknowledgment")
            require(acknowledgment.acknowledged_at >= revisions[acknowledgment.revision_id].issued_at, "Acknowledgment precedes revision")
        for inspection in self.inspections:
            require(inspection.zone_id in zones, f"Unknown zone for inspection {inspection.id}")
        for evidence in self.evidence:
            scope = evidence.scope
            for key, collection in (
                ("zone_id", zones), ("inspection_id", inspections), ("task_id", tasks),
                ("crew_id", crews), ("revision_id", revisions),
            ):
                reference = getattr(scope, key)
                require(reference is None or reference in collection, f"Unknown {key} for evidence {evidence.id}")
            if evidence.review_status != "confirmed":
                continue  # Missing/unclear scopes remain reviewable, never confirmed.
            require(scope.zone_id is not None, "Confirmed baseline evidence requires a zone")
            if scope.kind == "inspection":
                require(scope.inspection_id is not None and inspections[scope.inspection_id].zone_id == scope.zone_id, "Confirmed inspection scope must match the inspection zone")
                require(inspections[scope.inspection_id].status == evidence.claim, "Baseline inspection evidence must match the baseline outcome")
            elif scope.kind == "task_completion":
                require(scope.task_id is not None and tasks[scope.task_id].zone_id == scope.zone_id, "Confirmed task scope must match the task zone")
            else:
                require(scope.crew_id is not None and scope.revision_id is not None, "Confirmed acknowledgment needs a crew and exact revision")
                revision = revisions[scope.revision_id]
                require(scope.zone_id in revision.zone_ids or scope.zone_id == plans[revision.plan_id].floor_id, "Confirmed acknowledgment zone must belong to the exact revision")
                acknowledged = any(ack.crew_id == scope.crew_id and ack.revision_id == scope.revision_id for ack in self.acknowledgments)
                require((evidence.claim == "acknowledged") == acknowledged, "Confirmed baseline acknowledgment must match the baseline outcome")
        return self


class ImportResult(Record):
    site_id: str
    zones: int
    tasks: int
    crews: int
    plans: int
    revisions: int
    acknowledgments: int
    inspections: int
    evidence: int
