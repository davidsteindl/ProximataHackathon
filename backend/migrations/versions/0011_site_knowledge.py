"""Source-linked feedback knowledge; no changes to safety rules or Evidence."""

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "site_knowledge",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("feedback_id", sa.Integer(), sa.ForeignKey("flag_audit.id"), nullable=False, unique=True),
        sa.Column("correction_event_id", sa.String(64), sa.ForeignKey("events.id")),
    )


def downgrade():
    op.drop_table("site_knowledge")
