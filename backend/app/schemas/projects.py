"""阶段 4 创作工作台：项目、来源、文稿工作副本、版本、产出物、素材。"""

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.studio import BoundedModel, StudioDraft

Mode = Literal["article", "video_prompt", "animation_video", "music_video"]
OutputKind = Literal["xhs", "zhihu", "wechat", "video", "mv", "prompt_bundle"]
AssetRole = Literal["moodboard", "illustration", "cover", "keyframe", "bgm"]

# 文案层（定稿锁定）与制作层（产出物 settings，随时可改）
COPY_FIELDS = ("theme", "mode", "template_id", "duration_seconds", "audience", "intent", "tone")
PRODUCTION_FIELDS = ("style_id", "presentation", "production", "aspect_ratio", "bilingual")


class CopyBrief(BoundedModel):
    theme: str = Field(default="", max_length=500)
    mode: Mode = "article"
    template_id: str | None = None
    duration_seconds: float = Field(default=180, ge=5, le=600)
    audience: str = Field(default="", max_length=300)
    intent: str = Field(default="", max_length=5000)
    tone: str = Field(default="", max_length=200)


class ProjectCreate(BoundedModel):
    theme: str = Field(default="", max_length=500)
    mode: Mode = "article"
    # 来源写法：content:123 / library:45
    sources: list[str] = Field(default_factory=list, max_length=10)


class ProjectPatch(BoundedModel):
    title: str = Field(min_length=1, max_length=120)


class SourceAdd(BoundedModel):
    content_id: int | None = Field(default=None, gt=0)
    library_item_id: int | None = Field(default=None, gt=0)
    role: Literal["main", "reference"] = "reference"

    @model_validator(mode="after")
    def one_target(self):
        if bool(self.content_id) == bool(self.library_item_id):
            raise ValueError("content_id 与 library_item_id 需且只需给一个")
        return self


class SourceRole(BoundedModel):
    role: Literal["main", "reference"]


class BriefSave(BoundedModel):
    brief: CopyBrief
    draft_token: str | None = None
    idea: dict | None = None


class DraftSave(BoundedModel):
    draft: StudioDraft
    draft_token: str | None = None
    force: bool = False  # 「用我的覆盖」：先把对方内容存成版本再覆盖


class DraftGenerate(BoundedModel):
    mode: Literal["blank", "template", "ai"] = "blank"


class VersionCreate(BoundedModel):
    reason: str = Field(default="manual", max_length=50)


class FinalizeRequest(BoundedModel):
    version: int | None = Field(default=None, ge=1)


class OutputCreate(BoundedModel):
    kind: OutputKind
    title: str = Field(default="", max_length=300)


class OutputPatch(BoundedModel):
    title: str | None = Field(default=None, max_length=300)
    content: dict | None = None
    settings: dict | None = None
    published_url: str | None = Field(default=None, max_length=2048)
    status: Literal["draft", "exported", "published"] | None = None


class AssetAdd(BoundedModel):
    library_item_id: int = Field(gt=0)
    role: AssetRole = "moodboard"
    target: dict | None = None


class SuggestionCreate(BoundedModel):
    scope: dict = Field(default_factory=lambda: {"type": "all"})
    instructions: str = Field(default="", max_length=2000)
    quick: str | None = Field(default=None, max_length=40)
    n: int | None = Field(default=None, ge=50, le=20000)
    draft_token: str | None = None


class SuggestionApply(BoundedModel):
    op_ids: list[str] | None = Field(default=None, max_length=50)
