from pathlib import Path

import pytest
from PIL import ImageChops

from app.schemas.studio import StudioBrief, StudioDraft
from app.services.studio_animation import plan_scenes, scene_frame
from app.services.studio_media import NEUTRAL_STYLE


@pytest.mark.asyncio
async def test_scene_planning_uses_the_selected_storyboard(monkeypatch):
    messages = []

    async def fake_llm(request, **kwargs):
        messages.extend(request)
        return {"scenes": [{
            "kind": "counter", "title": "日均用量", "figure": "601",
            "unit": "美元 / 天", "labels": ["API 牌价折算"], "values": [601],
        }]}, {}

    monkeypatch.setattr("app.services.llm.provider.call_llm_json_with_metadata", fake_llm)
    draft = StudioDraft(body="完整旁白", shots=[{
        "seconds": 5, "beat": "关键数字", "visual": "数字增长到601",
        "audio": "日均用量601美元", "prompt": "数字计数器",
    }])
    plan = await plan_scenes(StudioBrief(theme="日均用量", mode="animation_video"), draft, NEUTRAL_STYLE)
    assert plan["scenes"][0]["values"] == [601]
    assert "数字增长到601" in messages[1]["content"]


def test_animation_frames_are_nonblank_and_change_with_time():
    font = Path("C:/Windows/Fonts/NotoSansSC-VF.ttf")
    if not font.is_file():
        pytest.skip("Local Chinese font is required for the rendered frame check")
    plan = {
        "palette": NEUTRAL_STYLE,
        "scenes": [{
            "kind": "counter", "title": "日均用量", "figure": "601", "unit": "美元 / 天",
            "subtitle": "按 API 牌价折算", "labels": [], "values": [601],
            "duration": 5, "narration": "日均用量已经达到601美元。",
        }],
    }
    early = scene_frame(plan, 0, 0.5, 960, 540, str(font))
    later = scene_frame(plan, 0, 2.5, 960, 540, str(font))
    assert ImageChops.difference(early, later).getbbox()
    assert early.getextrema() != ((17, 17), (17, 17), (17, 17))
