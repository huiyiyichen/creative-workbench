"""阶段 6：飞书多维表格同步记录（改造方案 10.2）

Revision ID: c3e5a7b9d104
Revises: b8d2f4a6c913
Create Date: 2026-10-20 20:00:00
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "c3e5a7b9d104"
down_revision: Union[str, None] = "b8d2f4a6c913"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feishu_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("object_type", sa.String(16), nullable=False),
        sa.Column("object_id", sa.Integer(), nullable=False),
        sa.Column("app_token", sa.String(64), nullable=False),
        sa.Column("table_id", sa.String(64), nullable=False),
        sa.Column("record_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("trigger", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("object_type", "object_id", "table_id", name="uq_feishu_records_object_table"),
    )
    op.create_index("ix_feishu_records_object_id", "feishu_records", ["object_id"])


def downgrade() -> None:
    op.drop_index("ix_feishu_records_object_id", table_name="feishu_records")
    op.drop_table("feishu_records")
