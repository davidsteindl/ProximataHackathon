"""Static site record"""

from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('crew_leads',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('sites',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('crews',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('trade', sa.String(length=64), nullable=False),
    sa.Column('lead_id', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['lead_id'], ['crew_leads.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('zones',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('site_id', sa.String(length=64), nullable=False),
    sa.Column('parent_id', sa.String(length=64), nullable=True),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('elevation_m', sa.Float(), nullable=True),
    sa.Column('height_m', sa.Float(), nullable=True),
    sa.CheckConstraint("kind IN ('building','floor','unit','room','element')", name='zone_kind'),
    sa.CheckConstraint('height_m IS NULL OR height_m > 0', name='zone_height'),
    sa.ForeignKeyConstraint(['parent_id'], ['zones.id'], ),
    sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_zones_parent_id'), 'zones', ['parent_id'], unique=False)
    op.create_table('inspections',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('zone_id', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('pending','passed','failed')", name='inspection_status'),
    sa.ForeignKeyConstraint(['zone_id'], ['zones.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_inspections_zone_id'), 'inspections', ['zone_id'], unique=False)
    op.create_table('plans',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('floor_id', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['floor_id'], ['zones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('floor_id')
    )
    op.create_table('tasks',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('zone_id', sa.String(length=64), nullable=False),
    sa.Column('crew_id', sa.String(length=64), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('ends_at > starts_at', name='task_time_range'),
    sa.ForeignKeyConstraint(['crew_id'], ['crews.id'], ),
    sa.ForeignKeyConstraint(['zone_id'], ['zones.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tasks_starts_at'), 'tasks', ['starts_at'], unique=False)
    op.create_index(op.f('ix_tasks_zone_id'), 'tasks', ['zone_id'], unique=False)
    op.create_table('revisions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('plan_id', sa.String(length=64), nullable=False),
    sa.Column('label', sa.String(length=20), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('file_name', sa.String(length=200), nullable=False),
    sa.CheckConstraint('sequence > 0', name='revision_positive_sequence'),
    sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('plan_id', 'label', name='revision_plan_label'),
    sa.UniqueConstraint('plan_id', 'sequence', name='revision_plan_sequence')
    )
    op.create_index(op.f('ix_revisions_plan_id'), 'revisions', ['plan_id'], unique=False)
    op.create_table('task_dependencies',
    sa.Column('task_id', sa.String(length=64), nullable=False),
    sa.Column('predecessor_id', sa.String(length=64), nullable=False),
    sa.CheckConstraint('task_id != predecessor_id', name='task_not_own_predecessor'),
    sa.ForeignKeyConstraint(['predecessor_id'], ['tasks.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.PrimaryKeyConstraint('task_id', 'predecessor_id')
    )
    op.create_table('revision_acknowledgments',
    sa.Column('crew_id', sa.String(length=64), nullable=False),
    sa.Column('revision_id', sa.String(length=64), nullable=False),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['crew_id'], ['crews.id'], ),
    sa.ForeignKeyConstraint(['revision_id'], ['revisions.id'], ),
    sa.PrimaryKeyConstraint('crew_id', 'revision_id')
    )
    op.create_table('revision_zones',
    sa.Column('revision_id', sa.String(length=64), nullable=False),
    sa.Column('zone_id', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['revision_id'], ['revisions.id'], ),
    sa.ForeignKeyConstraint(['zone_id'], ['zones.id'], ),
    sa.PrimaryKeyConstraint('revision_id', 'zone_id')
    )


def downgrade():
    op.drop_table('revision_zones')
    op.drop_table('revision_acknowledgments')
    op.drop_table('task_dependencies')
    op.drop_index(op.f('ix_revisions_plan_id'), table_name='revisions')
    op.drop_table('revisions')
    op.drop_index(op.f('ix_tasks_zone_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_starts_at'), table_name='tasks')
    op.drop_table('tasks')
    op.drop_table('plans')
    op.drop_index(op.f('ix_inspections_zone_id'), table_name='inspections')
    op.drop_table('inspections')
    op.drop_index(op.f('ix_zones_parent_id'), table_name='zones')
    op.drop_table('zones')
    op.drop_table('crews')
    op.drop_table('sites')
    op.drop_table('crew_leads')
