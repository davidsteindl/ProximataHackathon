"""Revision DXF sources and zone-linked geometry"""

from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('plan_geometry',
    sa.Column('revision_id', sa.String(length=64), nullable=False),
    sa.Column('original_filename', sa.String(length=200), nullable=False),
    sa.Column('source', sa.LargeBinary(), nullable=False),
    sa.Column('source_sha256', sa.String(length=64), nullable=False),
    sa.Column('floor_height_m', sa.Float(), nullable=False),
    sa.Column('floor_elevation_m', sa.Float(), nullable=False),
    sa.Column('ignored_layers', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['revision_id'], ['revisions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('revision_id')
    )
    op.create_table('geometry_elements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('revision_id', sa.String(length=64), nullable=False),
    sa.Column('element_id', sa.String(length=200), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('layer', sa.String(length=200), nullable=False),
    sa.Column('shape', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['revision_id'], ['plan_geometry.revision_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('revision_id', 'element_id', name='geometry_revision_element')
    )
    op.create_index(op.f('ix_geometry_elements_revision_id'), 'geometry_elements', ['revision_id'], unique=False)
    op.create_table('geometry_element_zones',
    sa.Column('element_id', sa.Integer(), nullable=False),
    sa.Column('zone_id', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['element_id'], ['geometry_elements.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['zone_id'], ['zones.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('element_id', 'zone_id')
    )


def downgrade():
    op.drop_table('geometry_element_zones')
    op.drop_index(op.f('ix_geometry_elements_revision_id'), table_name='geometry_elements')
    op.drop_table('geometry_elements')
    op.drop_table('plan_geometry')
