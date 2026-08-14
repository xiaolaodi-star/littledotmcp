"""FastMCP 服务组装与启动（S0.2 / S0.6）。

- 单一 FastMCP 实例，stdio 与 streamable-http 双传输由 MCP_TRANSPORT 决定
- http 模式强制 Bearer Token 鉴权（见 auth 中间件，M6 完善）
- 工具按域前缀命名：sql_er_* / sql_validate_* / doc_* / kb_* / svn_* /
  mindmap_* / standard_* / project_* / tag_* / requirement_*
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .auth_middleware import AuthMiddleware, RateLimitMiddleware
from .common.logging import get_logger
from .config import get_settings
from .db import models  # noqa: F401 确保模型注册
from .db.engine import engine
from .db.models import Base

logger = get_logger(__name__)

settings = get_settings()

# 统一服务名；http 相关参数预置，run 时按 transport 选择
mcp = FastMCP(
    "littledotmcp",
    host=settings.http_host,
    port=settings.http_port,
    streamable_http_path="/mcp",
)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """健康检查（反代可用）。"""
    return JSONResponse({"status": "ok", "service": "littledotmcp"})


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


def init_data() -> None:
    """首次启动自动建库（幂等），空知识库无用户数据（M6-05）。"""
    Base.metadata.create_all(engine)
    logger.info("数据库已初始化/更新（幂等）：%s", engine.url)


def build_http_app():
    """构建 streamable-http Starlette 应用并包装鉴权/限流/CORS 中间件。

    注意：add_middleware 后加的在外层，故先加 RateLimit（内）再加 Auth（外），
    保证请求先过鉴权再过限流。
    """
    app = mcp.streamable_http_app()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)
    return app


def run() -> None:
    """依据配置启动传输。"""
    init_data()
    transport = settings.mcp_transport
    if transport == "http":
        settings.require_http_auth()
        import uvicorn

        logger.info(
            "启动 streamable-http 传输 host=%s port=%s",
            settings.http_host,
            settings.http_port,
        )
        app = build_http_app()
        uvicorn.run(
            app,
            host=settings.http_host,
            port=settings.http_port,
            log_level=settings.log_level.lower(),
        )
    elif transport == "stdio":
        logger.info("启动 stdio 传输")
        mcp.run(transport="stdio")
    else:
        raise SystemExit(f"不支持的 MCP_TRANSPORT={transport!r}（可选 stdio/http）")
