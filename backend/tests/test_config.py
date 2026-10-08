import pytest
from pydantic import ValidationError

from app.core.config import Settings

_TEST_DB_URL = "postgresql+asyncpg://test:test@localhost:5432/test"


def test_database_url_required():
    """DATABASE_URL 留空时应在 Settings 初始化阶段报错。"""
    with pytest.raises(ValidationError, match="DATABASE_URL 未设置"):
        Settings(_env_file=None, DATABASE_URL="")


def test_cors_origins_defaults_empty(monkeypatch):
    """CORS_ORIGINS 默认为空字符串，cors_origins 属性返回空列表。"""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = Settings(_env_file=None, DATABASE_URL=_TEST_DB_URL)
    assert settings.CORS_ORIGINS == ""
    assert settings.cors_origins == []
