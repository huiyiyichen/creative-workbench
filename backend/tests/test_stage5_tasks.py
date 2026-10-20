"""阶段 5：任务中心——流程运行、生成、采集、分析合成一张表。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.agent_run import AgentRun, AgentStep
from app.models.analysis_job import AnalysisJobRecord
from app.models.generation import GenerationJob
from app.models.source import Source
from app.models.source_sync_run import SourceSyncRun
from app.schemas.projects import ProjectCreate
from app.services import project_service as ps, task_service


@pytest.mark.asyncio
async def test_tasks_merge_filter_and_hint(test_session_factory):
    async with test_session_factory() as db:
        p = await ps.create_project(db, 1, ProjectCreate(theme="任务中心"))
        now = datetime.now(UTC)
        running = AgentRun(
            flow_key="draft_writing", title="成稿 · 任务中心", status="running", thread_id="a", project_id=p["id"], started_at=now
        )
        failed = AgentRun(
            flow_key="video_production",
            title="成片",
            status="failed",
            thread_id="b",
            status_reason="DeepSeek 设计超时 10 分钟，已停止",
            started_at=now - timedelta(minutes=12),
            finished_at=now,
            cost=0.42,
        )
        old = AgentRun(flow_key="topic_research", title="很早", status="done", thread_id="c")
        db.add_all([running, failed, old])
        await db.flush()
        old.created_at = now - timedelta(days=30)
        db.add(AgentStep(run_id=running.id, node="write", role="writer", label="写手", executor="internal", status="running"))
        db.add(GenerationJob(prompt="一只猫", status="done", results=[{"url": "/a.png"}], cost=0.1, project_id=p["id"]))
        src = Source(name="少数派", url="https://sspai.com/feed", source_type="RSS", status="active")
        db.add(src)
        await db.flush()
        db.add(SourceSyncRun(source_id=src.id, status="success", fetched=12, new=3, finished_at=now))
        db.add(AnalysisJobRecord(job_id="j1", status="running", content_ids=[1, 2, 3], analyzed_ids=[1]))
        await db.commit()

        data = await task_service.list_tasks(db)
        keys = [r["key"] for r in data["items"]]
        assert f"flow:{old.id}" not in keys  # 超出时间范围
        assert data["counts"]["running"] == 2 and data["counts"]["failed"] == 1 and data["counts"]["done"] == 2
        assert data["active"] == 2
        # 进行中排在前面
        assert {r["status"] for r in data["items"][:2]} == {"running"}
        row = next(r for r in data["items"] if r["key"] == f"flow:{running.id}")
        assert row["stage"] == "写手" and row["project_title"] == "任务中心" and row["kind_label"] == "成稿"
        assert row["can_stop"] and row["href"] == f"/runs/{running.id}"
        bad = next(r for r in data["items"] if r["key"] == f"flow:{failed.id}")
        assert bad["hint"].startswith("可以重试") and bad["can_retry"] and bad["duration_ms"] >= 12 * 60 * 1000
        sync = next(r for r in data["items"] if r["type"] == "sync")
        assert sync["title"] == "少数派" and sync["stage"] == "抓到 12 条，新增 3"
        ana = next(r for r in data["items"] if r["type"] == "analysis")
        assert ana["stage"] == "1 / 3"

        only = await task_service.list_tasks(db, types=["flow"], status="failed")
        assert [r["key"] for r in only["items"]] == [f"flow:{failed.id}"]
        mine = await task_service.list_tasks(db, project_id=p["id"])
        assert {r["type"] for r in mine["items"]} == {"flow", "generation"}
        summ = await task_service.summary(db)
        assert summ["active"] == 2 and all(r["status"] == "running" for r in summ["items"])

        with pytest.raises(Exception):
            await task_service.stop(db, "sync:1")
