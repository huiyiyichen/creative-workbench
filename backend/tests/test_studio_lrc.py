import pytest

from app.core.exceptions import ValidationError
from app.models.studio import StudioProject
from app.schemas.studio import StudioBrief, StudioDraft
from app.services.studio_catalog import clean_draft, compile_draft, production_prompt
from app.services.studio_lrc import parse_lrc
from app.services.studio_service import _coerce_ai_draft, _project_dict, _retime_draft


def test_parse_lrc_supports_multiple_timestamps_and_offset():
    cues = parse_lrc("[offset:-500]\n[00:01.00][00:02.00]same line\n[00:03.50]next")
    assert [(cue.time, cue.text) for cue in cues] == [
        (0.5, "same line"),
        (1.5, "same line"),
        (3.0, "next"),
    ]


def test_parse_lrc_rejects_out_of_range():
    with pytest.raises(ValidationError):
        parse_lrc("[10:01.00]too late")


def test_style_compiler_keeps_content_structure_separate():
    brief = StudioBrief(theme="光", template_id="cinematic_arc", style_id="bauhaus", duration_seconds=60)
    draft = compile_draft(brief, StudioDraft())
    prompt = production_prompt(brief, draft, {"title": "光", "url": "https://example.com"})
    assert len(draft.shots) == 6
    assert "视觉规则：包豪斯" in prompt
    assert "执行重点：基础圆、方与直线" in prompt


def test_freeform_template_is_optional_and_does_not_fall_back_to_named_template():
    brief = StudioBrief(theme="深海少女 MV", mode="music_video", duration_seconds=60)
    draft = compile_draft(brief, StudioDraft())
    assert len(draft.shots) == 6
    assert draft.shots[0].beat == "建立母题"
    prompt = production_prompt(brief, draft, {"title": "资料", "url": "https://example.com"})
    assert "内容结构：自由结构" in prompt
    assert "来源证据" not in prompt
    assert "版权" not in prompt
    assert "授权" not in prompt
    assert "待核查" not in prompt
    assert "避免" not in prompt


def test_content_form_changes_compiled_output():
    article = compile_draft(StudioBrief(theme="研究报告", mode="article"), StudioDraft())
    animation = compile_draft(
        StudioBrief(theme="研究报告", mode="video_prompt", presentation="kinetic", production="code_animation"),
        StudioDraft(),
    )
    mv = compile_draft(
        StudioBrief(theme="研究报告", mode="music_video", presentation="cinematic", production="native_mv"),
        StudioDraft(),
    )
    assert article.shots == []
    assert "旁白" not in article.body
    assert len(animation.shots) == 6
    assert "旁白" in animation.body
    assert "动画讲解" in animation.shots[0].prompt
    assert len(mv.shots) == 6
    assert "视觉段落" in mv.body


def test_animation_video_is_a_distinct_content_form():
    brief = StudioBrief(theme="研究报告", mode="animation_video")
    draft = compile_draft(brief, StudioDraft())
    assert len(draft.shots) == 6
    assert "动画讲解" in draft.shots[0].prompt
    assert "动画动作" in draft.body


def test_music_video_shots_follow_lrc_boundaries_and_cover_audio_duration():
    brief = StudioBrief(theme="深海少女 MV", mode="music_video", duration_seconds=60)
    draft = compile_draft(
        brief,
        StudioDraft(
            cues=[
                {"time": 2, "text": "a"},
                {"time": 10, "text": "b"},
                {"time": 18, "text": "c"},
                {"time": 26, "text": "d"},
                {"time": 34, "text": "e"},
                {"time": 42, "text": "f"},
            ],
        ),
    )
    retimed = _retime_draft(draft, 60)
    assert retimed.shots[0].seconds == 2
    assert round(sum(shot.seconds for shot in retimed.shots), 3) == 60


def test_generated_prompts_keep_story_and_remove_production_disclaimers():
    brief = StudioBrief(theme="反乌托邦 MV", mode="music_video")
    draft = StudioDraft(
        title="反乌托邦 MV（暂定）",
        logline="他必须用不完美的声音让彼此重新成为人。演唱者、发行信息均待核查。",
        body=(
            "项目定位：音乐 MV，暂定总长 180 秒。\n"
            "当前未提供官方 LRC，因此不写歌词行、不伪造歌词时间。\n"
            "来源与风险：版权、授权和使用权待确认。\n"
            "声音原则：音乐为主体，环境音与音效辅助。\n"
            "字幕仅在必要时出现；不添加装饰性字幕。\n"
            "交付可运行的代码工程，不是口播稿。"
        ),
        shots=[{
            "seconds": 180,
            "beat": "Intro / 待核查",
            "visual": "一座禁止音乐的城市，雨夜的混凝土街道。屏幕不出现可读品牌文字。",
            "camera": "轻微手持不稳定，缓慢推近。",
            "audio": "低频轰鸣；音乐段落待音频与 LRC 校准。",
            "caption": "无歌词字幕；待官方 LRC 校准。",
            "prompt": (
                "cinematic, rainy night, giant screens without readable text, "
                "slow push-in, no text, no watermark, no brand logo, cold cyan palette."
            ),
        }],
        cues=[{"time": 0, "text": "不完美的声音"}],
        provenance="ai",
    )
    cleaned = clean_draft(draft)
    normalized = _coerce_ai_draft(draft.model_dump(), brief, StudioDraft())
    project = StudioProject(
        id=1, owner_id=1, title=brief.theme, version=1,
        spec={"brief": brief.model_dump(), "draft": draft.model_dump()}, source_snapshot={},
    )
    assert _project_dict(project, [], [], [])["draft"] == cleaned.model_dump()
    assert project.spec["draft"]["body"] == draft.body
    assert normalized.model_dump() == cleaned.model_dump()
    prompt = production_prompt(brief, cleaned, {})
    assert cleaned.title == "反乌托邦 MV"
    assert cleaned.shots[0].beat == "Intro"
    assert cleaned.cues == draft.cues
    assert "不完美的声音" in prompt
    assert "手持不稳定" in prompt
    assert "一座禁止音乐的城市" in prompt
    assert "rainy night" in prompt
    assert "giant screens" in prompt
    for text in ("版权", "授权", "使用权", "待核查", "待确认", "未提供", "不写", "不伪造", "不添加", "不是口播", "待音频", "no text", "no watermark", "no brand logo", "without readable"):
        assert text not in prompt
