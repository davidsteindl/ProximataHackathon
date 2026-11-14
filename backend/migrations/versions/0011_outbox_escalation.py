"""Outbox message kinds: one factual warning and at most one escalation per Flag."""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("outbox_messages") as batch:
        batch.add_column(sa.Column("kind", sa.String(length=20), server_default="warning", nullable=False))
        batch.drop_constraint("outbox_flag_notification", type_="unique")
        batch.create_unique_constraint("outbox_flag_notification", ["flag_id", "kind"])
        batch.create_check_constraint("outbox_kind", "kind IN ('warning','escalation')")


def downgrade():
    op.execute("DELETE FROM outbox_messages WHERE kind = 'escalation'")
    with op.batch_alter_table("outbox_messages") as batch:
        batch.drop_constraint("outbox_kind", type_="check")
        batch.drop_constraint("outbox_flag_notification", type_="unique")
        batch.create_unique_constraint("outbox_flag_notification", ["flag_id"])
        batch.drop_column("kind")
