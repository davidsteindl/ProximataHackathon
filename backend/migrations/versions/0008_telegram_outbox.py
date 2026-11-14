"""Telegram warnings and non-Flag compliance replies in the outbox."""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("outbox_messages") as batch:
        batch.alter_column("flag_id", existing_type=sa.String(64), nullable=True)
        batch.drop_constraint("outbox_channel", type_="check")
        batch.create_check_constraint("outbox_channel", "channel IN ('gmail','telegram')")


def downgrade():
    op.execute("DELETE FROM outbox_messages WHERE channel = 'telegram'")
    with op.batch_alter_table("outbox_messages") as batch:
        batch.alter_column("flag_id", existing_type=sa.String(64), nullable=False)
        batch.drop_constraint("outbox_channel", type_="check")
        batch.create_check_constraint("outbox_channel", "channel = 'gmail'")
