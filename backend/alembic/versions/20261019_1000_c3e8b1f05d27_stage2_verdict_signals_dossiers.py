"""阶段 2：选题结论、趋势计算 v2、专题、空档回看 / 时间段报告、报告完整度。

Revision ID: c3e8b1f05d27
Revises: a7d3e9c1b452
"""

import sqlalchemy as sa

from alembic import op

revision = "c3e8b1f05d27"
down_revision = "a7d3e9c1b452"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_items", sa.Column("verdict", sa.String(10), nullable=True))
    op.add_column("content_items", sa.Column("verdict_data", sa.JSON(none_as_null=True), nullable=True))
    op.add_column("content_items", sa.Column("verdict_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_content_items_verdict", "content_items", ["verdict"])

    for name, col in [
        ("topic_kind", sa.String(20)),
        ("event_group_id", sa.Integer()),
        ("watch_source_id", sa.Integer()),
        ("representative_content_id", sa.Integer()),
        ("signal_value", sa.Float()),
        ("signal_prev", sa.Float()),
        ("signal_peak", sa.Float()),
        ("status", sa.String(10)),
        ("platform_distribution", sa.JSON(none_as_null=True)),
        ("first_platform", sa.String(50)),
        ("source_count", sa.Integer()),
        ("series", sa.JSON(none_as_null=True)),
        ("first_seen_at", sa.DateTime(timezone=True)),
        ("last_seen_at", sa.DateTime(timezone=True)),
        ("streak_days", sa.Integer()),
    ]:
        op.add_column("topic_trends", sa.Column(name, col, nullable=True))
    op.create_index("ix_topic_trends_event_group_id", "topic_trends", ["event_group_id"])
    op.create_index("ix_topic_trends_watch_source_id", "topic_trends", ["watch_source_id"])

    op.create_table(
        "topic_dossiers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("event_group_id", sa.Integer(), sa.ForeignKey("content_event_groups.id", ondelete="SET NULL")),
        sa.Column("watch_source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="SET NULL")),
        sa.Column("query", sa.String(255)),
        sa.Column("followed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(10)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "uq_topic_dossiers_event",
        "topic_dossiers",
        ["event_group_id"],
        unique=True,
        postgresql_where=sa.text("event_group_id IS NOT NULL"),
    )
    op.create_index(
        "uq_topic_dossiers_watch",
        "topic_dossiers",
        ["watch_source_id"],
        unique=True,
        postgresql_where=sa.text("watch_source_id IS NOT NULL"),
    )

    op.create_table(
        "verdict_marks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("content_id", sa.Integer(), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("computed_verdict", sa.String(10), nullable=False),
        sa.Column("user_verdict", sa.String(10), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("content_id", name="uq_verdict_marks_content"),
    )

    op.create_table(
        "period_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("start_date", sa.String(10), nullable=False),
        sa.Column("end_date", sa.String(10), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DONE"),
        sa.Column("sections", sa.JSON(none_as_null=True)),
        sa.Column("completeness", sa.JSON(none_as_null=True)),
        sa.Column("error", sa.Text()),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_period_reports_kind_range", "period_reports", ["kind", "start_date", "end_date"])

    for table in ("daily_reports", "weekly_digests", "monthly_digests"):
        op.add_column(table, sa.Column("completeness", sa.JSON(none_as_null=True), nullable=True))


def downgrade() -> None:
    for table in ("daily_reports", "weekly_digests", "monthly_digests"):
        op.drop_column(table, "completeness")
    op.drop_index("ix_period_reports_kind_range", table_name="period_reports")
    op.drop_table("period_reports")
    op.drop_table("verdict_marks")
    op.drop_index("uq_topic_dossiers_watch", table_name="topic_dossiers")
    op.drop_index("uq_topic_dossiers_event", table_name="topic_dossiers")
    op.drop_table("topic_dossiers")
    op.drop_index("ix_topic_trends_watch_source_id", table_name="topic_trends")
    op.drop_index("ix_topic_trends_event_group_id", table_name="topic_trends")
    for name in (
        "topic_kind",
        "event_group_id",
        "watch_source_id",
        "representative_content_id",
        "signal_value",
        "signal_prev",
        "signal_peak",
        "status",
        "platform_distribution",
        "first_platform",
        "source_count",
        "series",
        "first_seen_at",
        "last_seen_at",
        "streak_days",
    ):
        op.drop_column("topic_trends", name)
    op.drop_index("ix_content_items_verdict", table_name="content_items")
    op.drop_column("content_items", "verdict_at")
    op.drop_column("content_items", "verdict_data")
    op.drop_column("content_items", "verdict")
