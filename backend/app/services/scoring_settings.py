"""设置 · 评分说明（4.1 / 4.3 / 5.3）：初筛权重、结论规则、话题状态阈值可调；附近 30 天一致率。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.services.topic_signals import DEFAULT_STATUS_RULES
from app.services.triage import DEFAULT_WEIGHTS, TRIAGE_WEIGHTS_KEY
from app.services.verdict import DEFAULT_RULES

VERDICT_RULES_KEY = "verdict_rules"
STATUS_RULES_KEY = "trend_status_rules"

GROUPS: dict[str, tuple[str, dict[str, float]]] = {
    "triage_weights": (TRIAGE_WEIGHTS_KEY, DEFAULT_WEIGHTS),
    "verdict_rules": (VERDICT_RULES_KEY, DEFAULT_RULES),
    "status_rules": (STATUS_RULES_KEY, DEFAULT_STATUS_RULES),
}


async def _load(db: AsyncSession, key: str, defaults: dict[str, float]) -> dict[str, float]:
    row = await db.get(AppSetting, key)
    values = dict(defaults)
    if row is not None and row.value:
        try:
            parsed = json.loads(row.value)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            for k, v in parsed.items():
                if k in defaults:
                    try:
                        values[k] = float(v)
                    except (TypeError, ValueError):
                        continue
    return values


async def load_rules(db: AsyncSession, group: str) -> dict[str, float]:
    key, defaults = GROUPS[group]
    return await _load(db, key, defaults)


async def get_scoring_settings(db: AsyncSession) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for group, (key, defaults) in GROUPS.items():
        out[group] = {"values": await _load(db, key, defaults), "defaults": dict(defaults)}
    return out


async def save_scoring_settings(db: AsyncSession, values: dict[str, dict[str, float]]) -> dict[str, Any]:
    for group, new in values.items():
        if group not in GROUPS:
            raise ValueError(f"未知设置组 {group}")
        key, defaults = GROUPS[group]
        current = await _load(db, key, defaults)
        for k, v in new.items():
            if k not in defaults:
                raise ValueError(f"{group} 没有 {k}")
            if v is None or float(v) < 0:
                raise ValueError(f"{k} 必须是非负数")
            current[k] = float(v)
        row = await db.get(AppSetting, key)
        payload = json.dumps(current)
        if row is None:
            db.add(AppSetting(key=key, value=payload))
        else:
            row.value = payload
    await db.commit()
    return await get_scoring_settings(db)
