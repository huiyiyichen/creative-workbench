import base64
import io
import json
import wave

import httpx
import pytest

from app.services import studio_tts


@pytest.mark.asyncio
async def test_omni_pcm_is_wrapped_as_playable_wav_and_keeps_script(tmp_path, monkeypatch):
    pcm = b"\x00\x00\xff\x7f" * 12000
    encoded = base64.b64encode(pcm).decode()
    requests = []
    config = {**studio_tts.DEFAULTS, "api_key": "test-key"}

    def respond(request):
        requests.append(json.loads(request.content))
        events = [
            {"choices": [{"delta": {"content": "这是稿件。", "audio": {"data": encoded[:7]}}}]},
            {"choices": [{"delta": {"audio": {"data": encoded[7:]}}}]},
        ]
        return httpx.Response(
            200,
            text="\n".join(f"data: {json.dumps(event)}\n" for event in events) + "data: [DONE]\n",
        )

    client = httpx.Client
    monkeypatch.setattr(
        studio_tts.httpx,
        "Client",
        lambda **kwargs: client(
            transport=httpx.MockTransport(respond),
            **kwargs,
        ),
    )
    output = await studio_tts.synthesize_speech("这是稿件。", config, tmp_path / "voice.wav")
    with wave.open(io.BytesIO(output.read_bytes())) as wav:
        assert wav.getparams()[:4] == (1, 2, 24000, 24000)
        assert wav.readframes(wav.getnframes()) == pcm
    assert output.with_suffix(".txt").read_text(encoding="utf-8") == "这是稿件。"
    assert requests[0]["messages"][0]["role"] == "system"
    assert requests[0]["messages"][1]["content"] == "这是稿件。"


def test_remotion_preview_and_source_use_separate_files(tmp_path, monkeypatch):
    from app.models.studio import StudioArtifact
    from app.services import studio_service

    monkeypatch.setattr(studio_service, "MEDIA_ROOT", tmp_path)
    preview = tmp_path / "36/harness-13/dist/preview.mp4"
    preview.parent.mkdir(parents=True)
    preview.touch()
    archive = preview.parent.parent.with_suffix(".zip")
    archive.touch()
    artifact = StudioArtifact(
        id=13,
        project_id=36,
        version=8,
        kind="remotion_video",
        status="done",
        relative_path=str(preview.relative_to(tmp_path)),
    )
    assert studio_service.artifact_preview_file(artifact) == preview
    assert studio_service.artifact_source_file(artifact) == archive
    assert studio_service.artifact_dict(artifact)["storage_path"] == str(preview)


def test_subtitles_follow_voice_duration_and_scene_offsets(tmp_path):
    from app.services.studio_subtitles import write_subtitles

    voice = tmp_path / "public/voice.wav"
    voice.parent.mkdir()
    with wave.open(str(voice), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x00" * 24000 * 4)
    timeline = {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "scenes": [
            {"frames": 150, "voiceFile": "voice.wav", "audio": "配音完成。动画交接。"},
            {"frames": 150, "voiceFile": "voice.wav", "audio": "视频生成。"},
        ],
    }
    write_subtitles(tmp_path, timeline)
    assert [(cue["start"], cue["end"]) for cue in timeline["captions"]] == [(0, 2), (2, 4), (5, 9)]
    assert "".join(cue["text"] for cue in timeline["captions"]) == "配音完成。动画交接。视频生成。"
    assert "00:00:05,000 --> 00:00:09,000" in (tmp_path / "narration.srt").read_text(encoding="utf-8")


def test_animation_subtitles_are_required_even_with_empty_emphasis_caption(tmp_path):
    from app.core.exceptions import ValidationError
    from app.schemas.studio import StudioBrief, StudioDraft
    from app.services.studio_catalog import production_prompt
    from app.services.studio_subtitles import install_subtitle_layer

    voice = tmp_path / "public/voice.wav"
    voice.parent.mkdir()
    with wave.open(str(voice), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x00" * 24000 * 2)
    source = tmp_path / "src"
    source.mkdir()
    (source / "index.tsx").write_text("placeholder", encoding="utf-8")
    timeline = {
        "width": 1920, "height": 1080, "fps": 30,
        "scenes": [{"frames": 90, "voiceFile": "voice.wav", "audio": "完整旁白。", "caption": ""}],
        "captions": [],
    }
    install_subtitle_layer(tmp_path, timeline, required=True)
    assert timeline["captions"][0]["text"] == "完整旁白。"
    assert "<Captions />" in (source / "index.tsx").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "timeline.json").read_text(encoding="utf-8"))["captions"] == timeline["captions"]
    brief = StudioBrief(theme="讲解", mode="animation_video", bilingual=False)
    draft = StudioDraft(shots=[{"seconds": 3, "audio": "完整旁白。", "caption": ""}])
    prompt = production_prompt(brief, draft, {})
    assert "完整中文旁白配套中文字幕" in prompt
    assert "字幕：完整旁白。" in prompt
    timeline["scenes"].append({"frames": 90, "audio": "另一段旁白。"})
    with pytest.raises(ValidationError, match="覆盖完整旁白"):
        install_subtitle_layer(tmp_path, timeline, required=True)
