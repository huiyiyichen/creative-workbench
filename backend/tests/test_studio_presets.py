import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.favorite import FavoriteTargetType
from app.models.user import User
from app.repositories.favorite_repo import FavoriteRepo
from app.schemas.favorite import FavoriteCreate, FavoriteUpdate
from app.schemas.studio import CreateProject, GenerateDraft, StudioBrief
from app.services.studio_catalog import catalog_for_user
from app.services.studio_media import native_filter
from app.services.studio_service import build_prompt, create_project, generate_project_draft


@pytest.mark.asyncio
async def test_custom_presets_share_catalog_and_drive_project_output():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(User(id=1, email="local@test.example", display_name="Local", role="admin", plan="local"))
        await db.commit()
        repo = FavoriteRepo(db, 1)
        template = await repo.upsert(FavoriteCreate(
            target_type=FavoriteTargetType.TEMPLATE,
            target_key="custom:story",
            title="三段故事",
            snapshot={"modes": ["video_prompt"], "beats": ["起点", "转折", "落点"]},
        ))
        style = await repo.upsert(FavoriteCreate(
            target_type=FavoriteTargetType.STYLE,
            target_key="custom:ink",
            title="我的墨绿",
            note="留白与墨绿",
            snapshot={"colors": ["#FFFFFF", "#16715D", "#111111"], "rules": ["墨绿线条", "大面积留白"]},
        ))
        await repo.update(style.id, FavoriteUpdate(
            title="编辑后的墨绿",
            snapshot={**style.snapshot, "local_path": "1/preview.png"},
        ))
        await db.commit()
        catalog = await catalog_for_user(db, 1)
        custom_style = next(item for item in catalog["styles"] if item.get("favorite_id") == style.id)
        assert custom_style["name"] == "编辑后的墨绿"
        assert custom_style["image"] == f"/api/v1/favorites/{style.id}/file"
        brief = StudioBrief(
            theme="自定义故事",
            template_id=f"favorite:template:{template.id}",
            style_id=custom_style["id"],
            duration_seconds=30,
        )
        project = await create_project(db, 1, CreateProject(brief=brief))
        generated = await generate_project_draft(
            db, 1, project["id"], GenerateDraft(expected_version=1, engine="rules"),
        )
        assert [shot["beat"] for shot in generated["draft"]["shots"]] == ["起点", "转折", "落点"]
        prompt = (await build_prompt(db, 1, project["id"]))["prompt"]
        assert "三段故事" in prompt
        assert "编辑后的墨绿" in prompt
        assert "墨绿线条" in prompt
        assert "colors=#16715D" in native_filter(brief, 960, 540, custom_style)
        assert len((await catalog_for_user(db, 2))["styles"]) == len(catalog["styles"]) - 1
    await engine.dispose()
