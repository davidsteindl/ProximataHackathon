"""Telegram warnings and non-Flag compliance replies in the outbox."""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("outbox_messages") as batch:
        batch.alter_column("flag_id", existing_type=sa.String(64), nullable=True)
        batch.drop_constraint("outbox_channel", type_="check")
        batch.create_check_constraint("outbox_channel", "channel IN ('gmail','telegram')")
        batch.drop_constraint("outbox_status", type_="check")
        batch.create_check_constraint("outbox_status", "status IN ('pending','sending','sent','failed','cancelled')")


def downgrade():
    op.execute("DELETE FROM outbox_messages WHERE channel = 'telegram'")
    with op.batch_alter_table("outbox_messages") as batch:
        batch.alter_column("flag_id", existing_type=sa.String(64), nullable=False)
        batch.drop_constraint("outbox_channel", type_="check")
        batch.create_check_constraint("outbox_channel", "channel = 'gmail'")
        batch.drop_constraint("outbox_status", type_="check")
        batch.create_check_constraint("outbox_status", "status IN ('pending','sending','sent','failed')")
