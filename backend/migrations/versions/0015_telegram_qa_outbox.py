"""Durable Telegram Q&A replies and Superintendent decision forwards."""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("outbox_messages") as batch:
        batch.drop_constraint("outbox_kind", type_="check")
        batch.create_check_constraint(
            "outbox_kind",
            "kind IN ('warning','escalation','approval_request','proposal_followup','compliance_reply','qa_reply','decision_request')",
        )


def downgrade():
    op.execute("DELETE FROM outbox_messages WHERE kind IN ('qa_reply','decision_request')")
    with op.batch_alter_table("outbox_messages") as batch:
        batch.drop_constraint("outbox_kind", type_="check")
        batch.create_check_constraint(
            "outbox_kind", "kind IN ('warning','escalation','approval_request','proposal_followup','compliance_reply')",
        )
