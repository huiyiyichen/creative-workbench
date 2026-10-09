"""Persist production stages and progress across page navigation."""

import sqlalchemy as sa
from alembic import op

revision = "b91e438ca552"
down_revision = "a71c9e604b22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("studio_artifacts", sa.Column("progress", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("studio_artifacts", "progress")
