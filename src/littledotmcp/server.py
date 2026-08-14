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
from starlette.responses import JSONResponse, Response

from .auth_middleware import AuthMiddleware, RateLimitMiddleware
from .common.logging import get_logger
from .config import get_settings
from .console.middleware import ConsoleAuthMiddleware
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


@mcp.custom_route("/metrics", methods=["GET"])
async def metrics(request: Request) -> Response:
    """Prometheus 文本格式指标（M10-01，仅非敏感聚合）。"""
    from .rag.embedding import METRICS, uptime_seconds

    hits = METRICS.get("embedding_cache_hits", 0)
    misses = METRICS.get("embedding_cache_misses", 0)
    total = hits + misses
    rate = (hits / total) if total else 0.0
    try:
        from importlib.metadata import version

        ver = version("littledotmcp")
    except Exception:
        ver = "unknown"
    lines = [
        "# HELP process_uptime_seconds 进程已运行秒数",
        "# TYPE process_uptime_seconds gauge",
        f"process_uptime_seconds {uptime_seconds():.3f}",
        "# HELP embedding_cache_hits 向量缓存命中次数（M10-01）",
        "# TYPE embedding_cache_hits counter",
        f"embedding_cache_hits {hits}",
        "# HELP embedding_cache_misses 向量缓存未命中次数（M10-01）",
        "# TYPE embedding_cache_misses counter",
        f"embedding_cache_misses {misses}",
        "# HELP embedding_cache_hit_rate 向量缓存命中率（0~1）",
        "# TYPE embedding_cache_hit_rate gauge",
        f"embedding_cache_hit_rate {rate:.4f}",
        "# HELP embed_calls 向量化调用次数",
        "# TYPE embed_calls counter",
        f"embed_calls {METRICS.get('embed_calls', 0)}",
        "# HELP service_info 服务版本信息",
        "# TYPE service_info gauge",
        f'service_info{{version="{ver}"}} 1',
    ]
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


def register_tools() -> None:
    """导入各域工具模块，触发 @mcp.tool 注册。

    按里程碑推进逐步解除注释：
        M0: hello（占位）
        M2: sql_er, sql_validate
        M3: doc, kb（kb_ask 与真实 Embedding 待 M7）
        M4: svn, requirement, project, tag
        M5: mindmap, standard
        M10: admin（服务运维管理：config_check/tools/stats/reset）
    """
    from .domains import hello  # noqa: F401  (占位连通测试)
    from .domains.admin import tools as admin_tools  # noqa: F401  (注册 admin_* 运维工具，M10)
    from .console import routes as console_routes  # noqa: F401  (注册 /admin/ 与 /admin/api/* 路由，M11)
    from .domains.doc import (
        tools as doc_tools,  # noqa: F401  (注册 doc_save/read/search/list/delete)
    )
    from .domains.kb import tools as kb_tools  # noqa: F401  (注册 kb_ingest/search/list/delete)
    from .domains.mindmap import tools as mindmap_tools  # noqa: F401  (注册 mindmap_* 工具)
    from .domains.project import tools as proj_tools  # noqa: F401  (注册 project_* 工具)
    from .domains.requirement import tools as req_tools  # noqa: F401  (注册 requirement_* 工具)
    from .domains.requirement import trace as req_trace  # noqa: F401  (注册 requirement_trace 工具)
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


def _ensure_mcp_routes_registered() -> None:
    """确保所有 @mcp.custom_route / 工具 / 异常采集已注册。

    必须在 mcp.streamable_http_app() 之前调用，否则自定义路由不会进入应用。
    """
    from .console import routes as _console_routes  # noqa: F401
    from .console.errors import install_error_collector
    from .domains import hello  # noqa: F401  (占位连通测试)
    from .domains.admin import tools as admin_tools  # noqa: F401  (注册 admin_* 运维工具，M10)
    # M11-03 调用异常采集：覆写 mcp.call_tool 包裹所有工具调用
    install_error_collector(mcp)


def _mount_console(app, *, with_mcp_auth: bool) -> None:
    """给应用挂载管理端静态资源与中间件栈。

    - 管理端 /admin/* 始终由 ConsoleAuthMiddleware + OwnerContextMiddleware 负责
      （独立 Cookie Session，与 MCP Bearer Token 双轨并存）。
    - with_mcp_auth=True（http 模式）时额外挂 CORS / RateLimit / AuthMiddleware，
      保护 /mcp 端点需要 Bearer Token；
      with_mcp_auth=False（stdio 模式附带管理端）时不挂 MCP Bearer 鉴权，
      避免 stdio 模式无 MCP_AUTH_TOKEN 而拒绝所有 /admin 请求。
    """
    from .console import routes as _console_routes
    from .console.middleware import ConsoleAuthMiddleware, OwnerContextMiddleware
    from starlette.staticfiles import StaticFiles

    # M11-05 管理端静态资源：/admin/static/* 由普通 StaticFiles 提供（正确 content-type），
    # /admin/ 单页由 console.routes.admin_page (custom_route) 返回 index.html。
    # mount 在 streamable_http_app 之后，确保 /admin/static/* 不被 /admin/ 路由吞掉。
    app.mount("/admin/static", StaticFiles(directory=_console_routes.static_dir()), name="admin-static")
    if with_mcp_auth:
        app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
        app.add_middleware(RateLimitMiddleware)
        app.add_middleware(AuthMiddleware)
    app.add_middleware(OwnerContextMiddleware)
    app.add_middleware(ConsoleAuthMiddleware)


def build_http_app():
    """构建 streamable-http Starlette 应用并包装鉴权/限流/CORS 中间件。

    注意：add_middleware 后加的在外层，故先加 RateLimit（内）再加 Auth（外），
    保证请求先过鉴权再过限流。ConsoleAuth 置于最内层，仅处理 /admin/* 段，
    与 /mcp 的 Bearer 双轨鉴权互不干扰。
    """
    _ensure_mcp_routes_registered()
    app = mcp.streamable_http_app()
    _mount_console(app, with_mcp_auth=True)
    return app


def build_console_app():
    """构建仅承载管理端的 Starlette 应用（用于 stdio 模式后台附带 HTTP 服务）。

    复用 mcp.streamable_http_app() 天然包含的 /admin/* custom routes，但不挂
    MCP Bearer 鉴权（stdio 模式无 MCP_AUTH_TOKEN），管理端以独立 Cookie Session 鉴权。
    """
    _ensure_mcp_routes_registered()
    app = mcp.streamable_http_app()
    _mount_console(app, with_mcp_auth=False)
    return app


def _serve_console_in_thread(host: str, port: int, log_level: str) -> None:
    """在后台 daemon 线程内启动管理端 HTTP 服务，不阻塞调用方。"""
    import asyncio
    import threading
    import uvicorn

    def _run() -> None:
        app = build_console_app()
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level=log_level,
        )
        server = uvicorn.Server(config)
        # 子线程内不可安装信号处理器（否则报错），显式关闭。
        server.install_signal_handlers = False
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.serve())
        finally:
            loop.close()

    t = threading.Thread(target=_run, name="console-http", daemon=True)
    t.start()


def run() -> None:
    """依据配置启动传输。"""
    init_data()
    # 管理端引导：空库时用一次性环境变量创建首个管理员（M11-02）
    from .console import auth as console_auth

    if console_auth.is_empty_db():
        try:
            console_auth.bootstrap_admin()
        except Exception:
            logger.exception("ADMIN_BOOTSTRAP 初始化异常（已忽略，可经 /admin/api/setup 创建）")
    transport = settings.mcp_transport
    if transport == "http":
        settings.require_http_auth()
        import uvicorn

        logger.info(
            "启动 streamable-http 传输 host=%s port=%s",
            settings.http_host,
            settings.http_port,
        )
        if settings.http_host in ("0.0.0.0", ""):
            logger.warning(
                "⚠ 安全告警：HTTP 绑定在 %s（全网卡/任意地址）。管理端与 MCP 均为明文无证书，"
                "仅限本地或可信内网使用；公网暴露须前置反向代理启用 TLS，否则存在窃听与会话劫持风险。",
                settings.http_host,
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
        # M11-07：stdio 模式额外在后台起一个 HTTP 服务承载管理端 Web Console，
        # 主线程继续以 stdio 对外提供 MCP 能力；管理端以独立 Cookie Session 鉴权，
        # 不依赖 MCP_AUTH_TOKEN，故 stdio 模式无需配置该 Token。
        _serve_console_in_thread(
            settings.http_host,
            settings.http_port,
            settings.log_level.lower(),
        )
        logger.info(
            "stdio 模式已附带管理端 HTTP：http://%s:%s/admin/（本地浏览器可访问）",
            settings.http_host,
            settings.http_port,
        )
        if settings.http_host in ("0.0.0.0", ""):
            logger.warning(
                "⚠ 安全告警：管理端 HTTP 绑定在 %s（全网卡/任意地址）。管理端为明文无证书，"
                "仅限本地或可信内网使用；公网暴露须前置反向代理启用 TLS，否则存在窃听与会话劫持风险。",
                settings.http_host,
            )
        mcp.run(transport="stdio")
    else:
        raise SystemExit(f"不支持的 MCP_TRANSPORT={transport!r}（可选 stdio/http）")
