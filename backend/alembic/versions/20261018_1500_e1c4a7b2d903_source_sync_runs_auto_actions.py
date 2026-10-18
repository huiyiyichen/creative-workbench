"""阶段 0：source_sync_runs、auto_actions、信源自动处理字段；进程指标可空。"""

import sqlalchemy as sa
from alembic import op

revision = "e1c4a7b2d903"
down_revision = "b91e438ca552"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False, server_default="schedule"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("error_kind", sa.String(20), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("fetched", sa.Integer(), nullable=True),
        sa.Column("new", sa.Integer(), nullable=True),
        sa.Column("duplicates", sa.Integer(), nullable=True),
        sa.Column("skipped", sa.JSON(), nullable=True, comment="预筛跳过，按原因计数"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("is_backfill", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_source_sync_runs_source_started", "source_sync_runs", ["source_id", "started_at"])
    op.create_index("ix_source_sync_runs_started", "source_sync_runs", ["started_at"])

    op.create_table(
        "auto_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False, server_default="source"),
        sa.Column("target_id", sa.String(100), nullable=False),
        sa.Column("target_label", sa.String(255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("previous_state", sa.JSON(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_auto_actions_executed", "auto_actions", ["executed_at"])
    op.create_index("ix_auto_actions_target", "auto_actions", ["target_type", "target_id"])

    op.add_column("sources", sa.Column("auto_paused_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("auto_pause_reason", sa.String(255), nullable=True))
    op.add_column(
        "sources", sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("sources", sa.Column("base_interval_minutes", sa.Integer(), nullable=True))
    op.add_column("sources", sa.Column("stale_flagged_at", sa.DateTime(timezone=True), nullable=True))

    for col in ("process_rss_mb", "process_cpu_user_s", "process_cpu_sys_s"):
        op.alter_column("metrics_snapshots", col, existing_type=sa.Float(), nullable=True)

    # 抖音账号被误识别成榜单类型（问题清单 C3）：URL 是账号路由的改回 RSSHub
    op.execute(
        "UPDATE content_items SET source_type = 'RSSHub' WHERE source_id IN "
        "(SELECT id FROM sources WHERE source_type = 'DouyinHot' AND url LIKE 'douyin/user/%')"
    )
    op.execute(
        "UPDATE sources SET source_type = 'RSSHub', platform = 'douyin' "
        "WHERE source_type = 'DouyinHot' AND url LIKE 'douyin/user/%'"
    )


def downgrade() -> None:
    for col in ("process_rss_mb", "process_cpu_user_s", "process_cpu_sys_s"):
        op.execute(f"UPDATE metrics_snapshots SET {col} = 0 WHERE {col} IS NULL")
        op.alter_column("metrics_snapshots", col, existing_type=sa.Float(), nullable=False)
    for col in ("stale_flagged_at", "base_interval_minutes", "consecutive_failures", "auto_pause_reason", "auto_paused_at"):
        op.drop_column("sources", col)
    op.drop_index("ix_auto_actions_target", table_name="auto_actions")
    op.drop_index("ix_auto_actions_executed", table_name="auto_actions")
    op.drop_table("auto_actions")
    op.drop_index("ix_source_sync_runs_started", table_name="source_sync_runs")
    op.drop_index("ix_source_sync_runs_source_started", table_name="source_sync_runs")
    op.drop_table("source_sync_runs")
