"""音乐 MV：上传音频（ffprobe 读时长）、LRC 歌词、分镜边界跟随歌词、定稿后不可改。"""

from __future__ import annotations

import io
import shutil
import wave

import pytest

from app.core.exceptions import AppException, ValidationError
from app.schemas.projects import DraftSave, ProjectCreate
from app.schemas.studio import LyricCue, StudioDraft, StudioShot
from app.services import mv_service, project_service as ps

pytestmark = pytest.mark.skipif(shutil.which("ffprobe") is None, reason="需要 ffprobe")


def _wav(seconds: float = 12.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buf.getvalue()


def test_retime_uses_lyric_times():
    draft = StudioDraft(
        shots=[StudioShot(seconds=3, visual=str(i)) for i in range(3)],
        cues=[LyricCue(time=t, text=f"句{t}") for t in (2.5, 5.0, 8.0)],
    )
    out = mv_service.retime(draft, 12)
    assert round(sum(s.seconds for s in out.shots), 3) == 12
    assert [round(s.seconds, 3) for s in out.shots] == [2.5, 2.5, 7.0]
    plain = mv_service.retime(StudioDraft(shots=[StudioShot(seconds=1)] * 4), 10)
    assert [s.seconds for s in plain.shots] == [2.5, 2.5, 2.5, 2.5]


@pytest.mark.asyncio
async def test_audio_and_lrc(test_session_factory, monkeypatch, tmp_path):
    monkeypatch.setattr(mv_service, "media_root", lambda: tmp_path)
    async with test_session_factory() as db:
        p = await ps.create_project(db, 1, ProjectCreate(theme="夏夜", mode="music_video"))
        shots = [StudioShot(seconds=4, visual=f"画面{i}") for i in range(3)]
        await ps.save_draft(db, p["id"], DraftSave(draft=StudioDraft(title="夏夜", shots=shots)))

        with pytest.raises(ValidationError):
            await mv_service.add_audio(db, p["id"], "a.txt", b"x")
        with pytest.raises(ValidationError):
            await mv_service.add_audio(db, p["id"], "a.mp3", b"")

        res = await mv_service.add_audio(db, p["id"], "夏夜 demo.wav", _wav(12))
        assert res["audio"]["duration"] == pytest.approx(12, abs=0.05)
        assert res["draft"]["brief"]["mode"] == "music_video" and res["draft"]["brief"]["duration_seconds"] == 12
        assert sum(s["seconds"] for s in res["draft"]["draft"]["shots"]) == pytest.approx(12, abs=0.05)
        path, name = await mv_service.audio_path(db, p["id"])
        assert path.read_bytes()[:4] == b"RIFF" and name.endswith(".wav")

        view = await mv_service.set_lrc(
            db, p["id"], "[ti:夏夜]\n[00:02.50]第一句\n[00:05.00]第二句\n[00:08.00]第三句\n"
        )
        assert [c["time"] for c in view["draft"]["cues"]] == [2.5, 5.0, 8.0]
        assert [round(s["seconds"], 2) for s in view["draft"]["shots"]] == [2.5, 2.5, 7.0]
        with pytest.raises(ValidationError):
            await mv_service.set_lrc(db, p["id"], "[00:20.00]超出音频")

        # 换一条更短的音频：只保留一条，超出的歌词丢掉
        await mv_service.add_audio(db, p["id"], "short.wav", _wav(6))
        info = await mv_service.audio_info(db, p["id"])
        assert info["audio"]["name"] == "short.wav"
        assert [c["time"] for c in (await ps.draft_view(db, p["id"]))["draft"]["cues"]] == [2.5, 5.0]

        await ps.finalize(db, p["id"])
        with pytest.raises(AppException):
            await mv_service.set_lrc(db, p["id"], "[00:01.00]改")
