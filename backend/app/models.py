from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String, Table,
    UniqueConstraint,
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
    file_name: Mapped[str] = mapped_column(String(200))
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
