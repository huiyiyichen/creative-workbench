"""阶段 3：条目评论（content_comments）与评论摘要

Revision ID: e5a7c2d4f601
Revises: d4f1a2b3c5e6
Create Date: 2026-10-20 11:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5a7c2d4f601"
down_revision: str | None = "d4f1a2b3c5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_comments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("platform_comment_id", sa.String(length=64), nullable=False),
        sa.Column("author_name", sa.String(length=120), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("like_count", sa.Integer(), nullable=True),
        sa.Column("reply_count", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("crawled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["content_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "platform_comment_id", name="uq_content_comment"),
    )
    op.create_index("ix_content_comments_content", "content_comments", ["content_id"])
    op.add_column("content_items", sa.Column("comment_digest", sa.JSON(none_as_null=True), nullable=True))


def downgrade() -> None:
    op.drop_column("content_items", "comment_digest")
    op.drop_index("ix_content_comments_content", table_name="content_comments")
    op.drop_table("content_comments")
