"""花费总览：LLM 按用途 / 模型 / 项目分组，生成任务单列，按北京时间分天。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.generation import GenerationJob, GenerationService
from app.models.llm_model import LlmCallLog
from app.schemas.projects import ProjectCreate
from app.services import cost_service, project_service as ps


def _call(scene: str, cost: float, at: datetime, *, model="gpt-x", project_id=None, status="DONE") -> LlmCallLog:
    return LlmCallLog(
        request_id=uuid.uuid4().hex,
        scene=scene,
        model_name=model,
        total_cost=cost,
        input_tokens=100,
        output_tokens=50,
        status=status,
        project_id=project_id,
        created_at=at,
    )


def test_scene_groups():
    assert cost_service.scene_group("quick_judge")[0] == "analysis"
    assert cost_service.scene_group("daily_report")[0] == "report"
    assert cost_service.scene_group("flow_writer")[0] == "create"
    assert cost_service.scene_group("studio_draft")[1] == "创作"
    assert cost_service.scene_group(None)[0] == "other"
    assert cost_service.scene_label("flow_writer").startswith("全流程")


@pytest.mark.asyncio
async def test_cost_summary(test_session_factory):
    now = datetime(2026, 10, 21, 4, 0, tzinfo=UTC)  # 北京 12:00
    async with test_session_factory() as db:
        project = await ps.create_project(db, 1, ProjectCreate(theme="花费测试项目"))
        pid = project["id"] if isinstance(project, dict) else project.id
        svc = GenerationService(name="即梦", kind="image", base_url="https://ex.com", model="m", api_key_enc="x")
        db.add(svc)
        await db.flush()
        db.add_all(
            [
                _call("quick_judge", 0.10, now - timedelta(hours=1)),
                _call("content_analysis", 0.30, now - timedelta(hours=2), model="claude"),
                _call("daily_report", 0.05, now - timedelta(days=1)),
                _call("studio_draft", 0.20, now - timedelta(hours=3), project_id=pid),
                _call("studio_draft", 0.00, now - timedelta(hours=3), project_id=pid, status="FAILED"),
                _call("quick_judge", 9.99, now - timedelta(days=40)),  # 窗口外
                # 北京时间 10-21 00:30 = UTC 10-20 16:30：算 21 日
                _call("quick_judge", 0.01, datetime(2026, 10, 20, 16, 30, tzinfo=UTC)),
                GenerationJob(
                    kind="image",
                    service_id=svc.id,
                    prompt="p",
                    project_id=pid,
                    cost=0.50,
                    status="done",
                    created_at=now - timedelta(hours=1),
                ),
                GenerationJob(kind="video", prompt="p", cost=0.0, status="failed", created_at=now - timedelta(hours=1)),
            ]
        )
        await db.commit()
        out = await cost_service.cost_summary(db, days=7, now=now)

    assert out["days"] == 7 and len(out["series"]) == 7
    assert out["series"][-1]["date"] == "2026-10-21"
    assert out["llm"] == pytest.approx(0.66)
    assert out["generation"] == pytest.approx(0.50)
    assert out["total"] == pytest.approx(1.16)
    assert out["today"] == pytest.approx(0.10 + 0.30 + 0.20 + 0.01 + 0.50)
    assert out["series"][-2]["total"] == pytest.approx(0.05)
    groups = {g["key"]: g for g in out["groups"]}
    assert groups["analysis"]["cost"] == pytest.approx(0.41)
    assert groups["create"]["cost"] == pytest.approx(0.20)
    assert groups["gen_image"]["label"] == "生图"
    assert out["failed"] == 2 and out["unpriced_jobs"] == 1
    assert out["projects"][0]["title"] == "花费测试项目"
    assert out["projects"][0]["generation"] == pytest.approx(0.5)
    assert out["models"][0]["cost"] >= out["models"][-1]["cost"]
    assert "budget" in out["analysis_budget"]
