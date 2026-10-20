"""阶段 4：生成服务与生成任务（改造方案第 8 节）

Revision ID: b8d2f4a6c913
Revises: a7c9e1f3b824
Create Date: 2026-10-20 15:00:00
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "b8d2f4a6c913"
down_revision: Union[str, None] = "a7c9e1f3b824"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generation_services",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="image"),
        sa.Column("api_format", sa.String(32), nullable=False, server_default="openai_images"),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("api_key_enc", sa.Text(), nullable=True),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("unit_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("daily_limit", sa.Float(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False, server_default="image"),
        sa.Column(
            "service_id",
            sa.Integer(),
            sa.ForeignKey("generation_services.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("ref_item_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("params", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("target", sa.JSON(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("output_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("step_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("results", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_generation_jobs_service_id", "generation_jobs", ["service_id"])
    op.create_index("ix_generation_jobs_project_id", "generation_jobs", ["project_id"])
    op.create_index("ix_generation_jobs_created_at", "generation_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_generation_jobs_created_at", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_project_id", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_service_id", table_name="generation_jobs")
    op.drop_table("generation_jobs")
    op.drop_table("generation_services")
