from __future__ import annotations

from app.services.json_cache import invalidate_json_cache

STATS_CACHE_PREFIX = "stats:"
STATS_DASHBOARD_CACHE_PREFIX = "stats:dashboard:"


def invalidate_stats_cache() -> None:
    invalidate_json_cache(STATS_CACHE_PREFIX)
