"""阶段 6：全局搜索补 pg_trgm 索引（采集内容标题 / 摘要、项目标题、产出物标题）

灵感库与随笔在阶段 3 已建；这里补上全局搜索里另外几处 ILIKE '%词%'。

Revision ID: e5a7c9d1f326
Revises: d4f6b8c0e215
Create Date: 2026-10-21 05:00:00
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "e5a7c9d1f326"
down_revision: Union[str, None] = "d4f6b8c0e215"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEXES = (
    ("ix_content_items_title_trgm", "content_items", "title"),
    ("ix_content_items_summary_trgm", "content_items", "summary"),
    ("ix_studio_projects_title_trgm", "studio_projects", "title"),
    ("ix_studio_outputs_title_trgm", "studio_outputs", "title"),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, table, col in INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} USING gin ({col} gin_trgm_ops)")


def downgrade() -> None:
    for name, _, _ in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
