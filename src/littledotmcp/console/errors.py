"""M11-03 调用异常采集。

通过覆写 `mcp.call_tool` 包裹所有 MCP 工具调用：捕获异常后写入 `call_errors`
（含脱敏参数摘要、错误类型/信息/堆栈头），异常照常抛出不改变工具契约。
- owner 取自 AuthMiddleware 注入 scope 的 owner_id，经 contextvars 在调用链内透传；
- 同工具同错误类型 5 分钟内合并计数（occurrences），防刷库；
- 参数摘要截断 2000 字符，并对密码/密钥类字段脱敏。

注：FastMCP 当前版本无 @mcp.middleware API，故采用覆写 call_tool 的统一入口方案。
"""

from __future__ import annotations

import asyncio
import datetime as dt
import traceback
import uuid
from contextvars import ContextVar

from sqlalchemy import select

from ..common.logging import get_logger
from ..db import engine as db_engine
from ..db.models import CallError

logger = get_logger(__name__)

# 由 AuthMiddleware 注入 scope 的 owner_id 经此透传至 call_tool 调用链
owner_cv: ContextVar[str] = ContextVar("call_error_owner", default="system")

# 脱敏字段（参数键匹配其一即遮蔽）
_SENSITIVE_KEYS = ("password", "token", "secret", "api_key", "key", "authorization", "pwd")
_ARGS_TRUNCATE = 2000
_MERGE_WINDOW_SEC = 300  # 5 分钟内同工具同错误类型合并


def _redact(value: object, key: str = "") -> object:
    if isinstance(key, str) and any(s in key.lower() for s in _SENSITIVE_KEYS):
        return "***"
    if isinstance(value, dict):
        return {k: _redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _summarize_args(arguments: dict) -> str:
    try:
        redacted = _redact(arguments)
        text = repr(redacted)
    except Exception:
        text = "<unserializable>"
    if len(text) > _ARGS_TRUNCATE:
        text = text[:_ARGS_TRUNCATE] + "...(truncated)"
    return text


def _merge_or_insert(error: dict) -> None:
    """落库：5 分钟窗口内同工具同错误类型合并 occurrences，否则新建。"""
    with db_engine.SessionLocal() as session:
        cutoff = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(
            seconds=_MERGE_WINDOW_SEC
        )
        existing = session.scalars(
            select(CallError)
            .where(
                CallError.tool_name == error["tool_name"],
                CallError.error_type == error["error_type"],
                CallError.created_at >= cutoff,
            )
            .order_by(CallError.created_at.desc())
            .limit(1)
        ).first()
        if existing is not None:
            existing.occurrences += 1
            existing.error_msg = error["error_msg"][:2000]
            existing.trace_head = error["trace_head"][:2000]
            session.commit()
            return
        rec = CallError(
            id=uuid.uuid4().hex,
            owner_id=error["owner_id"],
            tool_name=error["tool_name"],
            args_summary=error["args_summary"],
            error_type=error["error_type"],
            error_msg=error["error_msg"][:2000],
            trace_head=error["trace_head"][:2000],
            status="open",
            occurrences=1,
        )
        session.add(rec)
        session.commit()


def _original_error(exc: Exception) -> Exception:
    """ToolError 由 FastMCP 在 tool.run 内用 `from e` 包装，取 __cause__ 还原原始异常。"""
    cause = getattr(exc, "__cause__", None)
    return cause if isinstance(cause, Exception) else exc


def install_error_collector(mcp) -> None:
    """覆写 mcp._tool_manager.call_tool，包裹异常采集。幂等：仅替换一次。

    必须覆写 _tool_manager.call_tool（而非 FastMCP.call_tool）：后者在 FastMCP.__init__
    内已被绑定为 MCP 协议的 call_tool handler，事后替换无效；而 _tool_manager.call_tool
    是每次真实调用时动态属性查找，替换后真实协议调用也会命中 wrapped。
    """
    tool_manager = getattr(mcp, "_tool_manager", None)
    if tool_manager is None:
        logger.warning("M11-03 调用异常采集跳过：无 _tool_manager")
        return
    original = getattr(tool_manager, "_wrapped_original", None)
    if original is None:
        original = tool_manager.call_tool
        tool_manager._wrapped_original = original

    async def wrapped_call_tool(name: str, arguments: dict, *args, **kwargs):
        try:
            return await original(name, arguments, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001  - 采集所有异常但不改变工具契约
            src = _original_error(exc)
            owner = owner_cv.get()
            tb = "".join(traceback.format_exception_only(type(src), src))[:2000]
            summary = {
                "owner_id": owner,
                "tool_name": name,
                "args_summary": _summarize_args(arguments or {}),
                "error_type": type(src).__name__,
                "error_msg": str(src)[:2000],
                "trace_head": tb,
            }
            try:
                await asyncio.to_thread(_merge_or_insert, summary)
            except Exception:  # 采集失败绝不阻断主流程
                logger.exception("调用异常采集失败 tool=%s", name)
            raise  # 照常抛出给客户端（FastMCP 会包成 ToolError 返回）

    tool_manager.call_tool = wrapped_call_tool
    logger.info("M11-03 调用异常采集已安装")
