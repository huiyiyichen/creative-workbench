"""Add versioned single-user creation projects; preserve all historical tables."""

import sqlalchemy as sa
from alembic import op

revision = "a71c9e604b22"
down_revision = "d8f3b6a21c70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "studio_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("finalized_version", sa.Integer(), nullable=True),
        sa.Column("publications", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_studio_projects_owner_id", "studio_projects", ["owner_id"])
    op.create_table(
        "studio_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("studio_projects.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "version", name="uq_studio_revision_version"),
    )
    op.create_index("ix_studio_revisions_project_id", "studio_revisions", ["project_id"])
    op.create_table(
        "studio_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("studio_projects.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(250), nullable=False),
        sa.Column("relative_path", sa.String(300), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("rights_confirmed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_studio_assets_project_id", "studio_assets", ["project_id"])
    op.create_table(
        "studio_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("studio_projects.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("relative_path", sa.String(300), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_studio_artifacts_project_id", "studio_artifacts", ["project_id"])


def downgrade() -> None:
    for table in ("studio_artifacts", "studio_assets", "studio_revisions", "studio_projects"):
        op.drop_table(table)
