"""阶段 1：内容模型、指标观测、封面缓存、内容经历、分析漏斗字段、模型调用溯源、信源类型。"""

import sqlalchemy as sa
from alembic import op

revision = "f2a6c1d8e470"
down_revision = "e1c4a7b2d903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("url_hash", sa.String(64), nullable=False),
        sa.Column("local_path", sa.String(512), nullable=True),
        sa.Column("thumb_path", sa.String(512), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("dominant_color", sa.String(7), nullable=True),
        sa.Column("bytes", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("url_hash", name="uq_media_assets_url_hash"),
    )
    op.create_index("ix_media_assets_status", "media_assets", ["status"])
    op.create_index("ix_media_assets_last_accessed", "media_assets", ["last_accessed_at"])

    with op.batch_alter_table("content_items") as batch:
        batch.add_column(sa.Column("media_type", sa.String(20), nullable=True))
        batch.add_column(sa.Column("platform_item_id", sa.String(128), nullable=True))
        batch.add_column(sa.Column("author_id", sa.String(128), nullable=True))
        batch.add_column(sa.Column("author_url", sa.String(1024), nullable=True))
        batch.add_column(sa.Column("media", sa.JSON(), nullable=True))
        batch.add_column(
            sa.Column(
                "cover_asset_id", sa.Integer(), sa.ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
            )
        )
        batch.add_column(sa.Column("comment_state", sa.String(20), nullable=False, server_default="none"))
        batch.add_column(sa.Column("comment_crawled_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("triage_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("triage_signals", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("analysis_level", sa.String(10), nullable=False, server_default="none"))
        batch.add_column(sa.Column("quick_result", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("full_eligible", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("attributed_date", sa.Date(), nullable=True))
    op.create_index("ix_content_items_attributed_date", "content_items", ["attributed_date"])
    op.create_index("ix_content_items_platform_item", "content_items", ["platform", "platform_item_id"])
    op.create_index("ix_content_items_triage", "content_items", ["status", "triage_score"])

    # 回填：归属日期、形态、分析层级
    op.execute(
        "UPDATE content_items SET attributed_date = "
        "(COALESCE(published_at, crawled_at) AT TIME ZONE 'Asia/Shanghai')::date"
    )
    op.execute(
        "UPDATE content_items SET media_type = CASE "
        "WHEN platform IN ('bilibili', 'douyin', 'youtube') OR source_type IN ('YouTube', 'DouyinHot') THEN 'video' "
        "WHEN platform = 'xiaohongshu' THEN 'image' "
        "WHEN platform = 'github' THEN 'repo' "
        "WHEN source_type IN ('Reddit', 'X', 'TwitterRSS') THEN 'post' "
        "ELSE 'article' END"
    )
    op.execute("UPDATE content_items SET analysis_level = 'full', full_eligible = TRUE WHERE status = 'analyzed'")

    op.create_table(
        "content_metric_observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("content_id", sa.Integer(), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric", sa.String(20), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "sync_run_id", sa.Integer(), sa.ForeignKey("source_sync_runs.id", ondelete="SET NULL"), nullable=True
        ),
    )
    op.create_index(
        "ix_metric_obs_content_metric_time", "content_metric_observations", ["content_id", "metric", "observed_at"]
    )
    op.create_index("ix_metric_obs_observed", "content_metric_observations", ["observed_at"])
    # 旧快照里非零的指标转成观测（旧数据的 0 无法区分「真为 0」和「缺失」，不迁移）
    for col, metric in (("views", "views"), ("likes", "likes"), ("comments", "comments"), ("shares", "shares"),
                        ("favorites", "favorites")):
        op.execute(
            f"INSERT INTO content_metric_observations (content_id, metric, value, observed_at) "
            f"SELECT content_id, '{metric}', {col}, snapshot_at FROM content_metrics WHERE {col} IS NOT NULL AND {col} > 0"
        )

    op.create_table(
        "content_journey",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("content_id", sa.Integer(), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(24), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("sync_run_id", sa.Integer(), nullable=True),
        sa.Column("llm_request_id", sa.String(64), nullable=True),
        sa.Column("agent_run_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_content_journey_content_time", "content_journey", ["content_id", "created_at"])

    for col in ("views", "likes", "comments", "shares", "favorites", "followers_count"):
        op.alter_column("content_metrics", col, server_default=None)

    with op.batch_alter_table("llm_call_logs") as batch:
        batch.add_column(sa.Column("run_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("step_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("content_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("payload_ref", sa.String(255), nullable=True))
        batch.add_column(sa.Column("prompt_summary", sa.String(300), nullable=True))
        batch.add_column(sa.Column("response_summary", sa.String(300), nullable=True))
    op.create_index("ix_llm_call_logs_content", "llm_call_logs", ["content_id"])
    op.create_index("ix_llm_call_logs_run", "llm_call_logs", ["run_id"])

    with op.batch_alter_table("sources") as batch:
        batch.add_column(sa.Column("kind", sa.String(20), nullable=False, server_default="subscription"))
        batch.add_column(sa.Column("query", sa.String(255), nullable=True))
        batch.add_column(sa.Column("platforms", sa.JSON(), nullable=True))
    op.execute("UPDATE sources SET kind = 'list' WHERE source_type IN ('DouyinHot', 'Zhihu')")
    op.execute("UPDATE sources SET kind = 'list' WHERE source_type = 'RSSHub' AND url LIKE 'bilibili/ranking%'")
    op.execute("UPDATE sources SET kind = 'keyword' WHERE source_type = 'RSSHub' AND url LIKE 'bilibili/vsearch/%'")


def downgrade() -> None:
    with op.batch_alter_table("sources") as batch:
        for col in ("platforms", "query", "kind"):
            batch.drop_column(col)
    op.drop_index("ix_llm_call_logs_run", table_name="llm_call_logs")
    op.drop_index("ix_llm_call_logs_content", table_name="llm_call_logs")
    with op.batch_alter_table("llm_call_logs") as batch:
        for col in ("response_summary", "prompt_summary", "payload_ref", "project_id", "content_id", "step_id", "run_id"):
            batch.drop_column(col)
    op.drop_index("ix_content_journey_content_time", table_name="content_journey")
    op.drop_table("content_journey")
    op.drop_index("ix_metric_obs_observed", table_name="content_metric_observations")
    op.drop_index("ix_metric_obs_content_metric_time", table_name="content_metric_observations")
    op.drop_table("content_metric_observations")
    op.drop_index("ix_content_items_triage", table_name="content_items")
    op.drop_index("ix_content_items_platform_item", table_name="content_items")
    op.drop_index("ix_content_items_attributed_date", table_name="content_items")
    with op.batch_alter_table("content_items") as batch:
        for col in (
            "attributed_date", "full_eligible", "quick_result", "analysis_level", "triage_signals", "triage_score",
            "comment_crawled_at", "comment_state", "cover_asset_id", "media", "author_url", "author_id",
            "platform_item_id", "media_type",
        ):
            batch.drop_column(col)
    op.drop_index("ix_media_assets_last_accessed", table_name="media_assets")
    op.drop_index("ix_media_assets_status", table_name="media_assets")
    op.drop_table("media_assets")
