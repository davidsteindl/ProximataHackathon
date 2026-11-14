"""Extend existing agent Proposals with advisor advice and human decisions."""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "flag_advice",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("flag_id", sa.String(64), sa.ForeignKey("flags.id"), nullable=False, unique=True),
        sa.Column("backend", sa.String(200), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    with op.batch_alter_table("proposals") as batch:
        batch.add_column(sa.Column("advice_id", sa.String(64),
                                   sa.ForeignKey("flag_advice.id", name="fk_proposals_advice_id")))
        batch.add_column(sa.Column("ordinal", sa.Integer()))
        for field in ("affected_crews", "affected_tasks", "affected_zones"):
            batch.add_column(sa.Column(field, sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("message", sa.Text()))
        batch.add_column(sa.Column("decided_by", sa.String(64)))
        batch.add_column(sa.Column("decided_role", sa.String(30)))
        batch.add_column(sa.Column("decided_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("decision_reason", sa.Text()))
        batch.drop_constraint("proposal_status", type_="check")
        batch.create_check_constraint("proposal_status", "status IN ('proposed','approved','rejected')")
        batch.create_check_constraint(
            "proposal_decision",
            "(status = 'proposed' AND decided_by IS NULL AND decided_role IS NULL AND decided_at IS NULL) OR "
            "(status IN ('approved','rejected') AND decided_by IS NOT NULL AND decided_role = 'superintendent' "
            "AND decided_at IS NOT NULL AND decision_reason IS NOT NULL)",
        )
        batch.create_unique_constraint("proposal_advice_ordinal", ["advice_id", "ordinal"])
        batch.create_index("ix_proposals_advice_id", ["advice_id"])
    with op.batch_alter_table("proposals") as batch:
        for field in ("affected_crews", "affected_tasks", "affected_zones"):
            batch.alter_column(field, existing_type=sa.JSON(), server_default=None)
    with op.batch_alter_table("outbox_messages") as batch:
        batch.alter_column("kind", existing_type=sa.String(20), type_=sa.String(30))
        batch.add_column(sa.Column("dedup_key", sa.String(200)))
        batch.drop_constraint("outbox_kind", type_="check")
        batch.drop_constraint("outbox_flag_notification", type_="unique")
        batch.create_unique_constraint("outbox_dedup_key", ["dedup_key"])
        batch.create_check_constraint(
            "outbox_kind", "kind IN ('warning','escalation','approval_request','proposal_followup','compliance_reply')",
        )
    op.execute("UPDATE outbox_messages SET kind = 'compliance_reply' WHERE flag_id IS NULL")
    op.execute("UPDATE outbox_messages SET dedup_key = kind || ':' || flag_id WHERE flag_id IS NOT NULL")


def downgrade():
    op.execute("DELETE FROM outbox_messages WHERE kind IN ('approval_request','proposal_followup')")
    op.execute("UPDATE outbox_messages SET kind = 'warning' WHERE kind = 'compliance_reply'")
    with op.batch_alter_table("outbox_messages") as batch:
        batch.drop_constraint("outbox_kind", type_="check")
        batch.drop_constraint("outbox_dedup_key", type_="unique")
        batch.create_unique_constraint("outbox_flag_notification", ["flag_id", "kind"])
        batch.create_check_constraint("outbox_kind", "kind IN ('warning','escalation')")
        batch.alter_column("kind", existing_type=sa.String(30), type_=sa.String(20))
        batch.drop_column("dedup_key")
    op.execute("DELETE FROM proposals WHERE advice_id IS NOT NULL")
    with op.batch_alter_table("proposals") as batch:
        batch.drop_index("ix_proposals_advice_id")
        batch.drop_constraint("proposal_advice_ordinal", type_="unique")
        batch.drop_constraint("proposal_decision", type_="check")
        batch.drop_constraint("proposal_status", type_="check")
        batch.create_check_constraint("proposal_status", "status = 'proposed'")
        batch.drop_constraint("fk_proposals_advice_id", type_="foreignkey")
        for field in ("advice_id", "ordinal", "affected_crews", "affected_tasks", "affected_zones", "message",
                      "decided_by", "decided_role", "decided_at", "decision_reason"):
            batch.drop_column(field)
    op.drop_table("flag_advice")
