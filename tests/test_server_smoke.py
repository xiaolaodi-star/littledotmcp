"""M0 服务端冒烟：FastMCP 可初始化并列出 hello 工具（S0.2 / S0.6）。

通过内存态 ClientServer 直接驱动，不依赖真实 stdio 进程。
"""

from __future__ import annotations

import anyio

from littledotmcp.server import mcp


def test_server_lists_hello_tool() -> None:
    async def _run() -> None:
        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert "hello" in names

    anyio.run(_run)
