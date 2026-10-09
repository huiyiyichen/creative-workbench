from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BoundedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StudioBrief(BoundedModel):
    theme: str = Field(min_length=1, max_length=500)
    mode: Literal["article", "video_prompt", "animation_video", "music_video"] = "video_prompt"
    # Templates, visual styles and production paths are suggestions, not
    # gates. A freeform project can be created before the user decides how it
    # should look or where it should be rendered.
    template_id: str | None = None
    style_id: str | None = None
    presentation: Literal["cinematic", "kinetic", "ascii", "tui"] | None = None
    production: Literal["video_model", "code_animation", "native_mv"] | None = None
    duration_seconds: float = Field(default=180, ge=5, le=600)
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    audience: str = Field(default="", max_length=300)
    intent: str = Field(default="", max_length=5000)
    bilingual: bool = False

    @model_validator(mode="after")
    def align_output_settings(self):
        if self.mode == "article":
            self.presentation = None
            self.production = None
            self.bilingual = False
        elif self.mode == "animation_video":
            self.presentation = self.presentation or "kinetic"
            self.production = self.production if self.production != "native_mv" else "code_animation"
            self.production = self.production or "code_animation"
        elif self.mode == "video_prompt" and self.production == "native_mv":
            self.production = "code_animation"
        return self

    @field_validator("theme")
    @classmethod
    def nonblank_theme(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("选题不能为空")
        return value


class StudioShot(BoundedModel):
    seconds: float = Field(ge=0.1, le=600)
    beat: str = Field(default="", max_length=500)
    visual: str = Field(default="", max_length=2000)
    camera: str = Field(default="", max_length=1000)
    audio: str = Field(default="", max_length=1000)
    transition: str = Field(default="直切", max_length=300)
    caption: str = Field(default="", max_length=300)
    prompt: str = Field(default="", max_length=4000)


class LyricCue(BoundedModel):
    time: float = Field(ge=0, le=600)
    text: str = Field(min_length=1, max_length=500)


class StudioDraft(BoundedModel):
    title: str = Field(default="", max_length=500)
    logline: str = Field(default="", max_length=2000)
    body: str = Field(default="", max_length=50000)
    shots: list[StudioShot] = Field(default_factory=list, max_length=80)
    cues: list[LyricCue] = Field(default_factory=list, max_length=1500)
    provenance: Literal["manual", "compiled", "ai"] = "manual"


class CreateProject(BoundedModel):
    brief: StudioBrief
    content_id: int | None = Field(default=None, gt=0)
    favorite_id: int | None = Field(default=None, gt=0)


class SaveProject(BoundedModel):
    expected_version: int = Field(ge=1)
    brief: StudioBrief
    draft: StudioDraft


class VersionAction(BoundedModel):
    expected_version: int = Field(ge=1)


class GenerateDraft(VersionAction):
    engine: Literal["rules", "ai"] = "rules"
    action: Literal["generate", "refine"] = "generate"
    instructions: str = Field(default="", max_length=5000)
