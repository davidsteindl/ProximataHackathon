"""Structured Flag transition feedback and Evidence decision reasons."""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    for name, type_ in (
        ("actor_role", sa.String(30)), ("from_state", sa.String(20)),
        ("to_state", sa.String(20)), ("feedback", sa.String(20)), ("reason", sa.Text()),
    ):
        op.add_column("flag_audit", sa.Column(name, type_, nullable=True))
    op.add_column("evidence_reviews", sa.Column("reason", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("evidence_reviews", "reason")
    for name in ("reason", "feedback", "to_state", "from_state", "actor_role"):
        op.drop_column("flag_audit", name)
