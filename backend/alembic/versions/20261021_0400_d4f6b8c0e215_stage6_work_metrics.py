"""阶段 6：作品发布后的数据回收（work_metric_observations）

Revision ID: d4f6b8c0e215
Revises: c3e5a7b9d104
Create Date: 2026-10-21 04:00:00
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "d4f6b8c0e215"
down_revision: Union[str, None] = "c3e5a7b9d104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_metric_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("output_id", sa.Integer(), sa.ForeignKey("studio_outputs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric", sa.String(20), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_work_metric_observations_output_id", "work_metric_observations", ["output_id"])
    op.create_index("ix_work_metric_observations_observed_at", "work_metric_observations", ["observed_at"])


def downgrade() -> None:
    op.drop_index("ix_work_metric_observations_observed_at", table_name="work_metric_observations")
    op.drop_index("ix_work_metric_observations_output_id", table_name="work_metric_observations")
    op.drop_table("work_metric_observations")
