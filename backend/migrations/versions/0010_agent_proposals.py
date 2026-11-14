"""Persist agent advice without approval or execution capabilities."""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "proposals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("flag_id", sa.String(64), sa.ForeignKey("flags.id"), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status = 'proposed'", name="proposal_status"),
    )
    op.create_index("ix_proposals_flag_id", "proposals", ["flag_id"])


def downgrade():
    op.drop_index("ix_proposals_flag_id", table_name="proposals")
    op.drop_table("proposals")
