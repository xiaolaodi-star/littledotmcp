"""FastMCP 服务组装与启动（S0.2 / S0.6）。

- 单一 FastMCP 实例，stdio 与 streamable-http 双传输由 MCP_TRANSPORT 决定
- http 模式强制 Bearer Token 鉴权（见 auth 中间件，M6 完善）
- 工具按域前缀命名：sql_er_* / sql_validate_* / doc_* / kb_* / svn_* /
  mindmap_* / standard_* / project_* / tag_* / requirement_*
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .common.logging import get_logger
from .config import get_settings

logger = get_logger(__name__)

settings = get_settings()

# 统一服务名；http 相关参数预置，run 时按 transport 选择
mcp = FastMCP(
    "littledotmcp",
    host=settings.http_host,
    port=settings.http_port,
    streamable_http_path="/mcp",
)


def register_tools() -> None:
    """导入各域工具模块，触发 @mcp.tool 注册。

    按里程碑推进逐步解除注释：
        M0: hello（占位）
        M2: sql_er, sql_validate
        M3: doc, kb（kb_ask 与真实 Embedding 待 M7）
        M4: svn, requirement, project, tag
        M5: mindmap, standard
    """
    from .domains import hello  # noqa: F401  (占位连通测试)
    from .domains.doc import (
        tools as doc_tools,  # noqa: F401  (注册 doc_save/read/search/list/delete)
    )
    from .domains.kb import tools as kb_tools  # noqa: F401  (注册 kb_ingest/search/list/delete)
    from .domains.mindmap import tools as mindmap_tools  # noqa: F401  (注册 mindmap_* 工具)
    from .domains.project import tools as proj_tools  # noqa: F401  (注册 project_* 工具)
    from .domains.requirement import tools as req_tools  # noqa: F401  (注册 requirement_* 工具)
    from .domains.sql_er import tools as sql_er_tools  # noqa: F401  (注册 sql_er_from_ddl)
    from .domains.sql_validate import (
        tools as sql_validate_tools,  # noqa: F401  (注册 sql_validate_script)
    )
    from .domains.standard import tools as standard_tools  # noqa: F401  (注册 standard_* 工具)
    from .domains.svn import tools as svn_tools  # noqa: F401  (注册 svn_* 工具)
    from .domains.tag import tools as tag_tools  # noqa: F401  (注册 tag_* 工具)
    from .resources import (
        standards as standards_resources,  # noqa: F401  (注册 standard:// Resource + Prompt)
    )


def run() -> None:
    """依据配置启动传输。"""
    transport = settings.mcp_transport
    if transport == "http":
        settings.require_http_auth()
        logger.info(
            "启动 streamable-http 传输 host=%s port=%s",
            settings.http_host,
            settings.http_port,
        )
        mcp.run(transport="streamable-http")
    elif transport == "stdio":
        logger.info("启动 stdio 传输")
        mcp.run(transport="stdio")
    else:
        raise SystemExit(f"不支持的 MCP_TRANSPORT={transport!r}（可选 stdio/http）")
