from fastapi import APIRouter

from app.api.v1.admin_prompts import router as admin_prompts_router
from app.api.v1.analyses import router as analyses_router
from app.api.v1.auth import router as auth_router
from app.api.v1.backups import router as backups_router
from app.api.v1.categories import router as categories_router
from app.api.v1.collection import router as collection_router
from app.api.v1.content_events import router as content_events_router
from app.api.v1.contents import router as contents_router
from app.api.v1.costs import router as costs_router
from app.api.v1.daily_reports import router as daily_reports_router
from app.api.v1.discover import router as discover_router
from app.api.v1.events import router as events_router
from app.api.v1.favorites import router as favorites_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.feishu import router as feishu_router
from app.api.v1.generations import router as generations_router
from app.api.v1.library import router as library_router
from app.api.v1.llm_calls import router as llm_calls_router
from app.api.v1.llm_evaluations import router as llm_evaluations_router
from app.api.v1.llm_models import router as llm_models_router
from app.api.v1.media import router as media_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.model_catalog import router as model_catalog_router
from app.api.v1.monthly_digests import router as monthly_digests_router
from app.api.v1.mother_topics import router as mother_topics_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.projects import router as projects_router
from app.api.v1.publishing import router as publishing_router
from app.api.v1.read_records import router as read_records_router
from app.api.v1.renders import router as renders_router
from app.api.v1.reports import router as reports_router
from app.api.v1.runs import mcp_router, router as runs_router
from app.api.v1.scheduler import router as scheduler_router
from app.api.v1.scoring import router as scoring_router
from app.api.v1.search import router as search_router
from app.api.v1.settings import router as settings_router
from app.api.v1.skill import router as skill_router
from app.api.v1.sources import router as sources_router
from app.api.v1.sources_health import router as sources_health_router
from app.api.v1.stats import router as stats_router
from app.api.v1.stats_jobs import router as stats_jobs_router
from app.api.v1.topics import router as topics_router
from app.api.v1.trending import router as trending_router
from app.api.v1.trends import router as trends_router
from app.api.v1.wechat import router as wechat_router
from app.api.v1.weekly_digests import router as weekly_digests_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(scoring_router)
router.include_router(skill_router)
router.include_router(sources_router)
router.include_router(collection_router)
router.include_router(search_router)
router.include_router(costs_router)
router.include_router(events_router)
router.include_router(publishing_router)
router.include_router(wechat_router)
router.include_router(backups_router)
router.include_router(discover_router)
router.include_router(library_router)
router.include_router(runs_router)
router.include_router(projects_router)
router.include_router(generations_router)
router.include_router(mcp_router)
router.include_router(reports_router)
router.include_router(llm_calls_router)
router.include_router(media_router)
router.include_router(content_events_router)
router.include_router(contents_router)
router.include_router(topics_router)
router.include_router(analyses_router)
router.include_router(daily_reports_router)
router.include_router(trends_router)
router.include_router(settings_router)
router.include_router(categories_router)
router.include_router(stats_router)
router.include_router(stats_jobs_router)
router.include_router(renders_router)
router.include_router(feishu_router)
router.include_router(sources_health_router)
router.include_router(metrics_router)
router.include_router(feedback_router)
router.include_router(weekly_digests_router)
router.include_router(monthly_digests_router)
router.include_router(trending_router)
router.include_router(mother_topics_router)
router.include_router(notifications_router)
router.include_router(scheduler_router)
router.include_router(llm_models_router)
router.include_router(model_catalog_router)
router.include_router(llm_evaluations_router)
router.include_router(favorites_router)
router.include_router(read_records_router)
router.include_router(admin_prompts_router)
