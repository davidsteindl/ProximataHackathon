"""Keep exact learning matches independent of raw-message retention."""

import hashlib

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("site_knowledge", sa.Column("source_text_sha256", sa.String(64), nullable=True))
    knowledge = sa.table("site_knowledge", sa.column("id"), sa.column("correction_event_id"),
                         sa.column("source_text_sha256"))
    events = sa.table("events", sa.column("id"), sa.column("source_message_id"))
    sources = sa.table("source_messages", sa.column("id"), sa.column("text"))
    connection = op.get_bind()
    rows = connection.execute(sa.select(knowledge.c.id, sources.c.text).select_from(
        knowledge.join(events, knowledge.c.correction_event_id == events.c.id)
                 .join(sources, events.c.source_message_id == sources.c.id)
    ).where(sources.c.text != "")).mappings().all()
    for row in rows:
        connection.execute(knowledge.update().where(knowledge.c.id == row["id"]).values(
            source_text_sha256=hashlib.sha256(row["text"].encode("utf-8")).hexdigest(),
        ))


def downgrade():
    with op.batch_alter_table("site_knowledge") as batch:
        batch.drop_column("source_text_sha256")
