"""阶段 3：流程运行记录、调用树、产物与溯源、人工决定、工作台工具令牌

Revision ID: f6b8d3e5a712
Revises: e5a7c2d4f601
Create Date: 2026-10-20 03:45:15.153775

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6b8d3e5a712"
down_revision: Union[str, None] = "e5a7c2d4f601"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("flow_key", sa.String(length=64), nullable=False),
        sa.Column("flow_version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("inputs", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("budget", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("graph", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("outputs", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("cost", sa.Float(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("parent_run_id", sa.Integer(), nullable=True),
        sa.Column("fork_node", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["parent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_agent_runs_flow_key"), ["flow_key"], unique=False)
        batch_op.create_index(batch_op.f("ix_agent_runs_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_agent_runs_status"), ["status"], unique=False)
    op.create_table(
        "agent_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("node", sa.String(length=64), nullable=False),
        sa.Column("branch", sa.String(length=64), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("executor", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("input_artifact_ids", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("output_artifact_ids", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Float(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("meta", sa.JSON(none_as_null=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("agent_steps", schema=None) as batch_op:
        batch_op.create_index("ix_agent_steps_run", ["run_id", "id"], unique=False)
    op.create_table(
        "workbench_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("tools", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("project_ids", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "agent_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("step_id", sa.Integer(), nullable=True),
        sa.Column("gate", sa.String(length=64), nullable=False),
        sa.Column("options", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("choice", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_id"], ["agent_steps.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("agent_decisions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_agent_decisions_run_id"), ["run_id"], unique=False)
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("step_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("content", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("content_ref", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["step_id"], ["agent_steps.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("artifacts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_artifacts_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_artifacts_run_id"), ["run_id"], unique=False)
    op.create_table(
        "trace_spans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("step_id", sa.Integer(), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("attributes", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("payload_ref", sa.String(length=255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("via", sa.String(length=10), nullable=False),
        sa.Column("token_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["trace_spans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_id"], ["agent_steps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("trace_spans", schema=None) as batch_op:
        batch_op.create_index("ix_trace_spans_run", ["run_id"], unique=False)
        batch_op.create_index("ix_trace_spans_step", ["step_id"], unique=False)
    op.create_table(
        "artifact_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("artifact_id", sa.Integer(), nullable=False),
        sa.Column("relation", sa.String(length=20), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("target_url", sa.String(length=1024), nullable=True),
        sa.Column("anchor", sa.String(length=64), nullable=True),
        sa.Column("target_anchor", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("artifact_links", schema=None) as batch_op:
        batch_op.create_index("ix_artifact_links_artifact", ["artifact_id"], unique=False)
        batch_op.create_index("ix_artifact_links_target", ["target_type", "target_id"], unique=False)



def downgrade() -> None:
    op.drop_table("artifact_links")
    with op.batch_alter_table("trace_spans", schema=None) as batch_op:
        batch_op.drop_index("ix_trace_spans_step")
        batch_op.drop_index("ix_trace_spans_run")
    op.drop_table("trace_spans")
    with op.batch_alter_table("artifacts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_artifacts_run_id"))
        batch_op.drop_index(batch_op.f("ix_artifacts_project_id"))
    op.drop_table("artifacts")
    with op.batch_alter_table("agent_decisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_agent_decisions_run_id"))
    op.drop_table("agent_decisions")
    op.drop_table("workbench_tokens")
    with op.batch_alter_table("agent_steps", schema=None) as batch_op:
        batch_op.drop_index("ix_agent_steps_run")
    op.drop_table("agent_steps")
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_agent_runs_status"))
        batch_op.drop_index(batch_op.f("ix_agent_runs_project_id"))
        batch_op.drop_index(batch_op.f("ix_agent_runs_flow_key"))
    op.drop_table("agent_runs")
