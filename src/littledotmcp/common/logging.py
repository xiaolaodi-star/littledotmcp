"""统一日志（S0.5）。

- 模块级 logger，格式含时间/级别/模块/traceId/脱敏消息
- 敏感字段（token、secret、password、api_key）在记录前被脱敏
- traceId 经 contextvar 透传，便于跨工具调用追踪
"""

from __future__ import annotations

import logging
import re
import sys
from contextvars import ContextVar
from pathlib import Path

from ..config import get_settings

TRACE_ID: ContextVar[str] = ContextVar("trace_id", default="-")

_SENSITIVE_KEYS = ("token", "secret", "password", "api_key", "apikey", "auth")
_MASK = "***"


def _mask(value: str) -> str:
    """对疑似密钥/令牌做脱敏。"""
    low = value.lower()
    if any(k in low for k in _SENSITIVE_KEYS) and len(value) > 12:
        return value[:4] + _MASK + value[-2:]
    return value


def _redact(message: str) -> str:
    """去除消息中的敏感键值。"""
    return re.sub(
        r"(?i)(token|secret|password|api[_-]?key)\s*[=:]\s*['\"]?\S+",
        lambda m: f"{m.group(1)}=***",
        message,
    )


def get_logger(name: str) -> logging.Logger:
    """获取带统一格式的模块 logger。

    重要：stdio 传输模式下，stdout 被 MCP 协议独占，日志务必写 stderr，
    否则日志行会被客户端当作 JSONRPC 消息导致解析失败。
    同时追加文件 handler 便于本地排查（日志目录经配置）。
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    settings = get_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    class _RedactFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            record.traceId = TRACE_ID.get()  # type: ignore[attr-defined]
            # 仅对最终消息文本脱敏，避免递归覆盖 getMessage
            original = record.getMessage()
            record.msg = _redact(original)
            record.args = None
            return super().format(record)

    fmt = _RedactFormatter(
        fmt="%(asctime)s %(levelname)-5s [%(name)s] tid=%(traceId)s %(message)s"
    )

    # 1) stderr 流（stdio 模式安全，http 模式也可见）
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    # 2) 文件滚动（按天），与 stdout 完全隔离
    try:
        from logging.handlers import TimedRotatingFileHandler

        file_handler = TimedRotatingFileHandler(
            settings.log_dir / "littledotmcp.log",
            when="midnight",
            backupCount=15,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError:
        # 日志目录不可写时不阻断主流程
        pass

    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.propagate = False
    return logger
