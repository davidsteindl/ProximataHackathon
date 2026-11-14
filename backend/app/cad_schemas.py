from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import Identifier, Record, Timestamp

Point = tuple[float, float]


class ImportMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: Identifier
    floor_id: Identifier
    revision_id: Identifier
    label: Annotated[str, Field(min_length=1, max_length=20)]
    sequence: int = Field(gt=0)
    issued_at: Timestamp


class Shape(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outline: list[Point] = Field(default_factory=list)
    segments: list[tuple[Point, Point]] = Field(default_factory=list)
    position: Point | None = None
    thickness_m: float | None = None
    rotation_deg: float | None = None
    width_m: float | None = None
    block_name: str | None = None
    scale: Point | None = None


class Element(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    element_id: str
    kind: Literal["unit", "room", "wall", "door", "plumbing_fixture", "drain"]
    layer: str
    shape: Shape
    zone_ids: list[str]


class IgnoredLayer(BaseModel):
    layer: str
    entity_count: int


class GeometryView(Record):
    revision_id: str
    plan_id: str
    floor_id: str
    label: str
    sequence: int
    issued_at: Timestamp
    units: Literal["m"] = "m"
    floor_height_m: float
    floor_elevation_m: float
    original_filename: str
    source_sha256: str
    ignored_layers: list[IgnoredLayer]
    elements: list[Element]


class ImportResult(BaseModel):
    revision_id: str
    element_count: int
    source_sha256: str
    ignored_layers: list[IgnoredLayer]


class ElementChange(BaseModel):
    change: Literal["added", "removed", "moved"]
    element_id: str
    before: Element | None
    after: Element | None


class ZoneChanges(BaseModel):
    zone_id: str
    changes: list[ElementChange]


class PlanDiff(BaseModel):
    revision_id: str
    previous_revision_id: str
    origin: Literal["deterministic_plan_diff"] = "deterministic_plan_diff"
    affected_zone_ids: list[str]
    zones: list[ZoneChanges]
