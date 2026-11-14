"""Note-only revision metadata and Precondition context on Flags."""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("revisions") as batch:
        batch.alter_column("file_name", existing_type=sa.String(200), nullable=True)
    op.add_column("flags", sa.Column("context", sa.JSON(), nullable=False, server_default="{}"))
    with op.batch_alter_table("flags") as batch:
        batch.alter_column("context", existing_type=sa.JSON(), server_default=None)


def downgrade():
    op.drop_column("flags", "context")
    # A note-only record has no drawing to restore in the old schema.
    op.execute("UPDATE revisions SET file_name = 'No drawing imported (revision note)' WHERE file_name IS NULL")
    with op.batch_alter_table("revisions") as batch:
        batch.alter_column("file_name", existing_type=sa.String(200), nullable=False)
