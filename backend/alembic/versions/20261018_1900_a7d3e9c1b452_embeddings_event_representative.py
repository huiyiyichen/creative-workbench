"""阶段 1：本地向量表、事件分析代表。"""

import sqlalchemy as sa
from alembic import op

revision = "a7d3e9c1b452"
down_revision = "f2a6c1d8e470"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_embeddings",
        sa.Column("content_id", sa.Integer(), sa.ForeignKey("content_items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_content_embeddings_created", "content_embeddings", ["created_at"])
    with op.batch_alter_table("content_event_groups") as batch:
        batch.add_column(
            sa.Column(
                "representative_content_id",
                sa.Integer(),
                sa.ForeignKey("content_items.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
    op.execute("UPDATE content_event_groups SET representative_content_id = canonical_content_id")


def downgrade() -> None:
    with op.batch_alter_table("content_event_groups") as batch:
        batch.drop_column("representative_content_id")
    op.drop_index("ix_content_embeddings_created", table_name="content_embeddings")
    op.drop_table("content_embeddings")
