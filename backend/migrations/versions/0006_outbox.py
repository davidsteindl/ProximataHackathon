"""Crew Lead email and durable Flag notification outbox."""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('outbox_messages',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('flag_id', sa.String(length=64), nullable=False),
    sa.Column('recipient', sa.String(length=254), nullable=True),
    sa.Column('channel', sa.String(length=32), nullable=False),
    sa.Column('subject', sa.String(length=200), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('available_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('lease_token', sa.String(length=64), nullable=True),
    sa.Column('error_code', sa.String(length=40), nullable=True),
    sa.Column('provider_message_id', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("channel = 'gmail'", name='outbox_channel'),
    sa.CheckConstraint("status IN ('pending','sending','sent','failed')", name='outbox_status'),
    sa.CheckConstraint('attempts >= 0', name='outbox_attempts'),
    sa.ForeignKeyConstraint(['flag_id'], ['flags.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('flag_id', name='outbox_flag_notification')
    )
    op.create_index(op.f('ix_outbox_messages_available_at'), 'outbox_messages', ['available_at'], unique=False)
    op.add_column('crew_leads', sa.Column('email', sa.String(length=254), nullable=True))

def downgrade():
    op.drop_column('crew_leads', 'email')
    op.drop_index(op.f('ix_outbox_messages_available_at'), table_name='outbox_messages')
    op.drop_table('outbox_messages')
