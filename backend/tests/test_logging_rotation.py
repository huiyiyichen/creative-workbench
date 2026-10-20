"""日志落盘按大小轮转；测试环境默认不写；LOG_DIR=off 关闭。"""

import logging
from logging.handlers import RotatingFileHandler

from app.core import logging_config as lc


def test_rotating_handler(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    h = lc.rotating_file_handler(logging.Formatter("%(message)s"))
    assert isinstance(h, RotatingFileHandler)
    assert h.maxBytes == lc.LOG_MAX_BYTES and h.backupCount == lc.LOG_BACKUPS
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "你好", None, None)
    h.emit(rec)
    h.close()
    assert (tmp_path / "backend.log").read_text(encoding="utf-8").strip() == "你好"


def test_disabled(monkeypatch):
    monkeypatch.setenv("LOG_DIR", "off")
    assert lc.rotating_file_handler(None) is None
    monkeypatch.delenv("LOG_DIR")
    monkeypatch.setenv("APP_ENV", "test")
    assert lc.rotating_file_handler(None) is None
