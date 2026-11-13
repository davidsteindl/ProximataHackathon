"""Source-backed evidence and review history"""

from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('evidence',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('origin', sa.String(length=30), nullable=False),
    sa.Column('statement_ref', sa.String(length=200), nullable=True),
    sa.Column('source_ref', sa.String(length=200), nullable=False),
    sa.Column('quote', sa.String(length=2000), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('claim', sa.String(length=30), nullable=False),
    sa.Column('zone_id', sa.String(length=64), nullable=True),
    sa.Column('inspection_id', sa.String(length=64), nullable=True),
    sa.Column('task_id', sa.String(length=64), nullable=True),
    sa.Column('crew_id', sa.String(length=64), nullable=True),
    sa.Column('revision_id', sa.String(length=64), nullable=True),
    sa.Column('import_ref', sa.String(length=64), nullable=True),
    sa.Column('imported_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("(kind = 'inspection' AND task_id IS NULL AND crew_id IS NULL AND revision_id IS NULL AND claim IN ('pending','passed','failed')) OR (kind = 'task_completion' AND inspection_id IS NULL AND crew_id IS NULL AND revision_id IS NULL AND claim IN ('completed','not_completed')) OR (kind = 'revision_acknowledgment' AND inspection_id IS NULL AND task_id IS NULL AND claim IN ('acknowledged','not_acknowledged'))", name='evidence_subject'),
    sa.CheckConstraint("kind IN ('inspection','task_completion','revision_acknowledgment')", name='evidence_kind'),
    sa.CheckConstraint("origin IN ('seed_baseline','seed_statement','llm_statement')", name='evidence_origin'),
    sa.ForeignKeyConstraint(['crew_id'], ['crews.id'], ),
    sa.ForeignKeyConstraint(['inspection_id'], ['inspections.id'], ),
    sa.ForeignKeyConstraint(['revision_id'], ['revisions.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.ForeignKeyConstraint(['zone_id'], ['zones.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_evidence_inspection_id'), 'evidence', ['inspection_id'], unique=False)
    op.create_index(op.f('ix_evidence_task_id'), 'evidence', ['task_id'], unique=False)
    op.create_index(op.f('ix_evidence_zone_id'), 'evidence', ['zone_id'], unique=False)
    op.create_table('evidence_reviews',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('evidence_id', sa.String(length=64), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('actor_type', sa.String(length=30), nullable=False),
    sa.Column('reviewer_id', sa.String(length=64), nullable=True),
    sa.Column('reviewer_role', sa.String(length=30), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("(actor_type = 'human' AND status IN ('confirmed','rejected') AND reviewer_id IS NOT NULL AND length(reviewer_id) > 0 AND reviewer_role IS NOT NULL AND reviewer_role IN ('superintendent','crew_lead') AND decided_at IS NOT NULL) OR (actor_type IN ('seed_import','statement_ingestion') AND reviewer_id IS NULL AND reviewer_role IS NULL AND decided_at IS NULL AND (status = 'unconfirmed' OR (actor_type = 'seed_import' AND status = 'confirmed')))", name='evidence_review_actor'),
    sa.CheckConstraint("status IN ('unconfirmed','confirmed','rejected')", name='evidence_review_status'),
    sa.CheckConstraint('sequence > 0', name='evidence_review_positive_sequence'),
    sa.ForeignKeyConstraint(['evidence_id'], ['evidence.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('evidence_id', 'sequence', name='evidence_review_sequence')
    )
    op.create_index(op.f('ix_evidence_reviews_evidence_id'), 'evidence_reviews', ['evidence_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_evidence_reviews_evidence_id'), table_name='evidence_reviews')
    op.drop_table('evidence_reviews')
    op.drop_index(op.f('ix_evidence_zone_id'), table_name='evidence')
    op.drop_index(op.f('ix_evidence_task_id'), table_name='evidence')
    op.drop_index(op.f('ix_evidence_inspection_id'), table_name='evidence')
    op.drop_table('evidence')
