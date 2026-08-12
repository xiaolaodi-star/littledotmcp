"""hello 示例工具（S0.6）：首个 @mcp.tool，用于客户端联调验证。

后续每个功能域都沿用同样的「工具函数 -> ok()/fail() 信封 -> 异常映射」范式。
"""

from __future__ import annotations

from ..common.logging import get_logger
from ..common.result import ok
from ..server import mcp

logger = get_logger(__name__)


@mcp.tool(name="hello", description="连通性自测：返回服务版本与入参回声。")
def hello(name: str = "world") -> dict:
    """连通性自测工具。"""
    logger.info("hello 被调用 name=%s", name)
    return ok(data={"echo": name, "version": "0.1.0"}, message="连通正常")
