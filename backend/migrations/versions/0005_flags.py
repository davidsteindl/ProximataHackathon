"""Deterministic Flags, source links and creation/evaluation audit."""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "flags",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("zone_id", sa.String(64), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id")),
        sa.Column("activity", sa.String(200), nullable=False),
        sa.Column("precondition", sa.String(64), nullable=False),
        sa.Column("inspection_id", sa.String(64), sa.ForeignKey("inspections.id")),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("responsible_id", sa.String(64), sa.ForeignKey("crew_leads.id")),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("evaluation", sa.String(20), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("open_key", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state IN ('detected','notified','acknowledged','in_progress','resolved','false_alarm')", name="flag_state"),
        sa.CheckConstraint("severity IN ('high','medium','low')", name="flag_severity"),
        sa.CheckConstraint("evaluation IN ('satisfied','not_satisfied','unknown','contradictory')", name="flag_evaluation"),
        sa.UniqueConstraint("open_key", name="flag_open_conflict"),
    )
    op.create_index("ix_flags_zone_id", "flags", ["zone_id"])
    op.create_table(
        "flag_sources",
        sa.Column("flag_id", sa.String(64), sa.ForeignKey("flags.id"), primary_key=True),
        sa.Column("event_id", sa.String(64), sa.ForeignKey("events.id"), primary_key=True),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "flag_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("flag_id", sa.String(64), sa.ForeignKey("flags.id"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(200), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_flag_audit_flag_id", "flag_audit", ["flag_id"])


def downgrade():
    op.drop_table("flag_audit")
    op.drop_table("flag_sources")
    op.drop_table("flags")
