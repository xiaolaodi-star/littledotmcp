"""M11-03 调用异常采集测试。

覆盖：工具抛异常后写入 call_errors、参数脱敏、同错误 5 分钟合并 occurrences、
客户端仍收到原始异常、owner 经 contextvars 归属。
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from littledotmcp.console import errors as err_mod
from littledotmcp.db import engine as db_engine
from littledotmcp.db.models import Base, CallError
from littledotmcp.server import mcp


def _count() -> int:
    with db_engine.SessionLocal() as s:
        return int(s.scalar(select(__import__("sqlalchemy").func.count()).select_from(CallError)) or 0)


def _latest() -> CallError | None:
    with db_engine.SessionLocal() as s:
        return s.scalars(select(CallError).order_by(CallError.created_at.desc())).first()


def test_error_collected_and_reraised(sqlite_tmp_engine, isolated_settings) -> None:
    """工具抛异常：写入 call_errors，且原异常照常抛出。"""
    Base.metadata.create_all(sqlite_tmp_engine)
    err_mod.install_error_collector(mcp)

    @mcp.tool(name="boom_tool")
    async def boom() -> str:
        raise ValueError("boom detail")

    err_mod.owner_cv.set("owner-xyz")
    raised = None
    try:
        import asyncio

        asyncio.run(mcp.call_tool("boom_tool", {}))
    except Exception as e:  # wrapped 重抛的可能被包为 ToolError，验证 call_errors 还原原始类型
        raised = e
    assert raised is not None and "boom detail" in str(raised)
    assert _count() == 1
    rec = _latest()
    assert rec is not None
    assert rec.tool_name == "boom_tool"
    assert rec.owner_id == "owner-xyz"
    assert rec.error_type == "ValueError"
    assert rec.status == "open"


def test_args_redacted(sqlite_tmp_engine, isolated_settings) -> None:
    """参数含敏感字段时摘要脱敏。"""
    Base.metadata.create_all(sqlite_tmp_engine)
    err_mod.install_error_collector(mcp)

    @mcp.tool(name="boom_secret")
    async def boom_secret() -> str:
        raise RuntimeError("x")

    err_mod.owner_cv.set("owner-a")
    import asyncio

    try:
        asyncio.run(mcp.call_tool("boom_secret", {"password": "hunter2", "query": "ok"}))
    except Exception:
        pass
    rec = _latest()
    assert rec is not None
    assert "hunter2" not in rec.args_summary
    assert "***" in rec.args_summary
    assert "ok" in rec.args_summary


def test_merge_within_window(sqlite_tmp_engine, isolated_settings, monkeypatch) -> None:
    """同工具同错误类型 5 分钟内合并 occurrences，不新增行。"""
    Base.metadata.create_all(sqlite_tmp_engine)
    err_mod.install_error_collector(mcp)

    @mcp.tool(name="boom_merge")
    async def boom_merge() -> str:
        raise KeyError("missing")

    err_mod.owner_cv.set("owner-b")
    import asyncio

    for _ in range(3):
        try:
            asyncio.run(mcp.call_tool("boom_merge", {}))
        except Exception:
            pass
    # 合并后应只有 1 行，occurrences=3
    assert _count() == 1
    rec = _latest()
    assert rec.occurrences == 3


def test_no_collection_on_success(sqlite_tmp_engine, isolated_settings) -> None:
    """成功调用不写 call_errors。"""
    Base.metadata.create_all(sqlite_tmp_engine)
    err_mod.install_error_collector(mcp)

    @mcp.tool(name="ok_tool")
    async def ok_tool() -> str:
        return "fine"

    err_mod.owner_cv.set("owner-c")
    import asyncio

    asyncio.run(mcp.call_tool("ok_tool", {}))
    assert _count() == 0
