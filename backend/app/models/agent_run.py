"""运行记录与溯源（改造方案 2.2 / 2.3）。

* ``agent_runs``：一次流程运行（模板与版本、触发方式、状态、预算与花费、LangGraph thread id、父运行）。
* ``agent_steps``：运行里的每个步骤（节点、角色、执行者、状态、尝试 / 轮次、输入输出产物、token、花费、耗时、错误）。
* ``trace_spans``：调用树中的工具调用与外部 agent 事件；模型调用在 ``llm_call_logs``（带 run_id / step_id）。
* ``artifacts`` / ``artifact_links``：产物及其来源关系（可细到段落或简报条目）。
* ``agent_decisions``：人工关卡上的决定。
* ``workbench_tokens``：工作台工具（MCP）的限定范围令牌。

LangGraph 的状态快照只用于恢复和重跑；业务数据都在这些表里。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    flow_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    flow_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # manual / project / schedule / fork / tool
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    # queued / running / waiting（人工关卡）/ paused（超预算）/ done / failed / stopped
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    inputs: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    # {cost: 元, seconds, steps, loops}
    budget: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    # 流程模板快照（节点、边、关卡开关）——节点图从这里画
    graph: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    outputs: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    fork_node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    node: Mapped[str] = mapped_column(String(64), nullable=False)
    # 并行分支键（如研究员按平台分工时的平台名）
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    # internal / deepseek_harness / claude_code / codex / human
    executor: Mapped[str] = mapped_column(String(20), nullable=False, default="internal")
    # running / done / failed / waiting / reused / stopped
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    input_artifact_ids: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    output_artifact_ids: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 节点参数快照、重跑覆盖（提示词补充 / 模型）、输出摘要
    meta: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)

    __table_args__ = (Index("ix_agent_steps_run", "run_id", "id"),)


class TraceSpan(Base):
    __tablename__ = "trace_spans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True)
    step_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("agent_steps.id", ondelete="CASCADE"), nullable=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trace_spans.id", ondelete="CASCADE"), nullable=True
    )
    # tool / agent_event
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # OpenTelemetry GenAI 约定命名：gen_ai.tool.name、gen_ai.operation.name …
    attributes: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 调用来源：flow（流程内）/ mcp（外部 agent 通过令牌）
    via: Mapped[str] = mapped_column(String(10), nullable=False, default="flow")
    token_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (Index("ix_trace_spans_step", "step_id"), Index("ix_trace_spans_run", "run_id"))


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    step_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("agent_steps.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # research_brief / direction_cards / draft / review / storyboard / prompt / image / video / platform_post / qa_report
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    # 大内容（成片、工程）的文件引用
    content_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class ArtifactLink(Base):
    __tablename__ = "artifact_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    artifact_id: Mapped[int] = mapped_column(Integer, ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False)
    # derived_from / cites / reviews / replaces
    relation: Mapped[str] = mapped_column(String(20), nullable=False)
    # artifact / content / library / url
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # 本产物内的锚点（如简报第 2 条 "f2"、段落 id）与目标内的锚点
    anchor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_anchor: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_artifact_links_artifact", "artifact_id"),
        Index("ix_artifact_links_target", "target_type", "target_id"),
    )


class AgentDecision(Base):
    __tablename__ = "agent_decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    step_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("agent_steps.id", ondelete="SET NULL"), nullable=True
    )
    gate: Mapped[str] = mapped_column(String(64), nullable=False)
    options: Mapped[list | dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    choice: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class WorkbenchToken(Base):
    __tablename__ = "workbench_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # 允许的工具名；None = 全部第一批工具
    tools: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    project_ids: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
