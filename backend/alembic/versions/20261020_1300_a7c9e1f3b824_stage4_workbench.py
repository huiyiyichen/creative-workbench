"""阶段 4：创作工作台——项目来源、产出物、AI 建议、项目素材；工作副本 token 与步骤

Revision ID: a7c9e1f3b824
Revises: f6b8d3e5a712
Create Date: 2026-10-20 13:00:00

数据迁移（设计文档 10.4）：
1. 每个项目 spec.brief 里的制作层字段复制到新建的「讲解视频」产出物 settings（文章形态且无作品的不建）；
2. 现有作品 output_id 指向该产出物，settings 取当时版本修订快照里的制作层字段；
3. source_snapshot 转成一条 project_sources（role=main）；
4. draft_token 初始化为 updated_at 的哈希；stage 按定稿 / 有稿 / 其他推断。
旧字段只读不删，降级后照常可用。
"""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "a7c9e1f3b824"
down_revision: Union[str, None] = "f6b8d3e5a712"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PRODUCTION_FIELDS = ("style_id", "presentation", "production", "aspect_ratio", "bilingual")


def _json(value):
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return value


def upgrade() -> None:
    op.add_column("studio_projects", sa.Column("draft_token", sa.String(length=32), nullable=True))
    op.add_column("studio_projects", sa.Column("stage", sa.String(length=16), nullable=False, server_default="idea"))
    op.add_column("studio_projects", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "project_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("studio_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=True),
        sa.Column("library_item_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_sources_project_id", "project_sources", ["project_id"])
    op.create_table(
        "studio_outputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("studio_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("based_on_version", sa.Integer(), nullable=True),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("published_url", sa.String(length=2048), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_studio_outputs_project_id", "studio_outputs", ["project_id"])
    op.create_table(
        "project_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("studio_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("base_token", sa.String(length=32), nullable=True),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("patch", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("applied_ops", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_suggestions_project_id", "project_suggestions", ["project_id"])
    op.create_table(
        "project_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("studio_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("library_item_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("target", sa.JSON(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_assets_project_id", "project_assets", ["project_id"])
    op.create_index("ix_project_assets_library_item_id", "project_assets", ["library_item_id"])
    op.add_column(
        "studio_artifacts",
        sa.Column("output_id", sa.Integer(), sa.ForeignKey("studio_outputs.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("studio_artifacts", sa.Column("settings", sa.JSON(), nullable=True))
    op.create_index("ix_studio_artifacts_output_id", "studio_artifacts", ["output_id"])

    _migrate_data()


def _migrate_data() -> None:
    bind = op.get_bind()
    meta = sa.MetaData()
    projects = sa.Table("studio_projects", meta, autoload_with=bind)
    revisions = sa.Table("studio_revisions", meta, autoload_with=bind)
    artifacts = sa.Table("studio_artifacts", meta, autoload_with=bind)
    outputs = sa.Table("studio_outputs", meta, autoload_with=bind)
    sources = sa.Table("project_sources", meta, autoload_with=bind)
    now = datetime.now(UTC)

    for p in bind.execute(sa.select(projects)).mappings().all():
        spec = _json(p["spec"])
        brief = spec.get("brief") or {}
        draft = spec.get("draft") or {}
        arts = bind.execute(sa.select(artifacts).where(artifacts.c.project_id == p["id"])).mappings().all()
        mode = brief.get("mode") or "article"
        output_id = None
        if mode != "article" or arts:
            settings = {k: brief.get(k) for k in PRODUCTION_FIELDS if brief.get(k) is not None}
            settings.setdefault("executor", "deepseek_harness")
            kind = (
                "mv" if mode == "music_video" else "prompt_bundle" if mode == "video_prompt" and not arts else "video"
            )
            done = any(a["status"] == "done" for a in arts)
            output_id = bind.execute(
                outputs.insert()
                .values(
                    project_id=p["id"],
                    kind=kind,
                    title={"mv": "音乐 MV", "prompt_bundle": "视频提示词包"}.get(kind, "讲解视频"),
                    status="done" if done else "draft",
                    based_on_version=p["finalized_version"],
                    content={},
                    settings=settings,
                    created_at=p["created_at"] or now,
                    updated_at=p["updated_at"] or now,
                )
                .returning(outputs.c.id)
            ).scalar_one()
        for a in arts:
            rev = bind.execute(
                sa.select(revisions.c.spec).where(
                    revisions.c.project_id == p["id"], revisions.c.version == a["version"]
                )
            ).scalar_one_or_none()
            rbrief = (_json(rev).get("brief") or {}) if rev is not None else brief
            bind.execute(
                artifacts.update()
                .where(artifacts.c.id == a["id"])
                .values(
                    output_id=output_id,
                    settings={k: rbrief.get(k) for k in PRODUCTION_FIELDS if rbrief.get(k) is not None},
                )
            )
        snap = _json(p["source_snapshot"])
        if snap and snap.get("kind") in {"content", "favorite"}:
            bind.execute(
                sources.insert().values(
                    project_id=p["id"],
                    content_id=snap.get("content_id") if snap.get("kind") == "content" else None,
                    library_item_id=None,
                    role="main",
                    snapshot={
                        "kind": snap.get("kind"),
                        "title": snap.get("title"),
                        "url": snap.get("url"),
                        "platform": snap.get("source_name"),
                        "published_at": snap.get("published_at"),
                        "crawled_at": snap.get("crawled_at"),
                        "summary": snap.get("summary"),
                        "cover_url": snap.get("cover_url"),
                        "metrics": {},
                    },
                    added_at=p["created_at"] or now,
                )
            )
        stamp = (p["updated_at"] or now).isoformat()
        stage = (
            "outputs" if p["finalized_version"] else "draft" if (draft.get("body") or draft.get("shots")) else "idea"
        )
        bind.execute(
            projects.update()
            .where(projects.c.id == p["id"])
            .values(draft_token=hashlib.md5(stamp.encode()).hexdigest(), stage=stage)
        )


def downgrade() -> None:
    op.drop_index("ix_studio_artifacts_output_id", table_name="studio_artifacts")
    op.drop_column("studio_artifacts", "settings")
    op.drop_column("studio_artifacts", "output_id")
    op.drop_table("project_assets")
    op.drop_table("project_suggestions")
    op.drop_table("studio_outputs")
    op.drop_table("project_sources")
    op.drop_column("studio_projects", "archived_at")
    op.drop_column("studio_projects", "stage")
    op.drop_column("studio_projects", "draft_token")
