"""admin 域 MCP 工具：服务运维管理（M10）。

仅承载服务级运维能力，不涉业务管理（业务管理归入 M8 追溯 / M9 企微）：

- admin_config_check：诊断 LLM / Embedding / 鉴权 / 存储配置就绪状态，明确降级原因；
- admin_tools：返回已注册 MCP 工具清单；
- admin_stats：返回当前 owner 各域数据量统计（强制 owner 隔离）；
- admin_reset：一键重置（复用 M3-05 scripts.reset_data），限定管理员。

管理权限复用 M6 共享 Token 的 local owner 语义：MCP 工具无法读取 HTTP 头，且
域 _current_owner() 在 stdio 单人模式恒返回 "local"；M6 共享 Token 命中时 owner
即 "local"，普通用户 Token owner 为 user.id（≠ local，M9 OAuth 后自然生效）。
故 admin_reset / admin_config_check 内判定 owner=="local" 即管理员，零新增鉴权模型。
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, select

from ...common.logging import get_logger
from ...common.result import fail, ok
from ...config import get_settings
from ...db import engine as db_engine
from ...db.models import (
    Document,
    EntityTag,
    KbChunk,
    KbDocument,
    Milestone,
    Mindmap,
    Project,
    Requirement,
    Standard,
    SvnOpLog,
    SvnRepo,
    Tag,
    Task,
    User,
)
from ...server import mcp

logger = get_logger(__name__)

# stdio 单人模式固定归属；http 模式按鉴权上下文（M6）解析
_DEFAULT_OWNER = "local"


def _current_owner() -> str:
    """返回当前调用方 owner_id（stdio 单人固定 local）。"""
    return _DEFAULT_OWNER


def _require_admin() -> str | None:
    """管理员权限判定：返回 None 表示通过，否则返回错误提示。

    复用 M6 共享 Token 的 local owner 语义（ADR-15）。
    """
    if _current_owner() != "local":
        return "需要管理员权限（共享 Token 或本地模式）"
    return None


# 参与统计的域表（owner_id 隔离）
_STAT_TABLES = {
    "users": User,
    "kb_documents": KbDocument,
    "kb_chunks": KbChunk,
    "documents": Document,
    "svn_repos": SvnRepo,
    "svn_ops_log": SvnOpLog,
    "projects": Project,
    "milestones": Milestone,
    "tasks": Task,
    "requirements": Requirement,
    "tags": Tag,
    "entity_tags": EntityTag,
    "mindmaps": Mindmap,
    "standards": Standard,
}


@mcp.tool()
def admin_config_check() -> dict:
    """诊断 LLM / Embedding / 鉴权 / 存储等配置就绪状态，明确降级原因。

    Returns:
        success: 恒为 True（诊断不失败）；data 含 checks 列表与各就绪标记。
    """
    deny = _require_admin()
    if deny:
        return fail(deny)
    s = get_settings()
    checks: list[dict] = []

    # LLM
    llm_ready = bool(s.llm_api_key)
    llm_detail = (
        "kb_ask 可用"
        if llm_ready
        else "未配置 LLM_API_KEY，kb_ask 将降级为检索片段直出"
    )
    checks.append(
        {
            "name": "llm",
            "ready": llm_ready,
            "detail": llm_detail,
            "provider": s.llm_model,
        }
    )

    # Embedding
    emb_ready = s.embedding_provider in ("openai", "ollama")
    emb_detail = (
        f"使用 {s.embedding_provider} 真实向量（dim={s.embedding_dim}）"
        if emb_ready
        else "使用 fake 确定性向量（离线，非语义）"
    )
    if s.embedding_provider == "openai":
        emb_detail += "，未配置 EMBEDDING_API_KEY 时启动将报错" if not s.embedding_api_key else ""
    checks.append(
        {
            "name": "embedding",
            "ready": emb_ready,
            "detail": emb_detail,
            "provider": s.embedding_provider,
            "dim": s.embedding_dim,
        }
    )

    # 鉴权（http 模式需 Token）
    auth_needed = s.mcp_transport == "http"
    auth_ready = (not auth_needed) or bool(s.mcp_auth_token)
    if not auth_needed:
        auth_detail = "stdio 模式无需鉴权"
    elif auth_ready:
        auth_detail = "已配置 MCP_AUTH_TOKEN"
    else:
        auth_detail = "http 模式未配置 MCP_AUTH_TOKEN，启动将报错"
    checks.append(
        {
            "name": "auth",
            "ready": auth_ready,
            "detail": auth_detail,
            "transport": s.mcp_transport,
        }
    )

    # 存储
    storage_ready = bool(s.db_url)
    checks.append(
        {
            "name": "storage",
            "ready": storage_ready,
            "detail": f"DB_URL={s.db_url}；文件根={s.storage_root}；向量目录={s.vector_dir}",
        }
    )

    all_ready = all(c["ready"] for c in checks)
    return ok(
        {
            "all_ready": all_ready,
            "checks": checks,
            "transport": s.mcp_transport,
            "embedding_provider": s.embedding_provider,
            "llm_model": s.llm_model,
        },
        message="全部就绪" if all_ready else "存在降级项，详见 checks",
    )


@mcp.tool()
def admin_tools() -> dict:
    """返回当前已注册 MCP 工具清单（名称 + 说明）。

    Returns:
        success: 恒为 True；data 含 tools 列表（name/description）。
    """
    deny = _require_admin()
    if deny:
        return fail(deny)
    # FastMCP.list_tools 为异步，改用同步的 ToolManager 访问已注册工具
    tool_manager = getattr(mcp, "_tool_manager", None)
    raw = tool_manager.list_tools() if tool_manager is not None else []
    items: list[dict] = []
    for t in raw:
        items.append(
            {
                "name": getattr(t, "name", str(t)),
                "description": getattr(t, "description", "") or "",
            }
        )
    return ok(
        {"count": len(items), "tools": items},
        message=f"已注册 {len(items)} 个工具",
    )


@mcp.tool()
def admin_stats() -> dict:
    """返回当前 owner 各域数据量统计（强制 owner 隔离，普通用户仅见自己数据）。

    Returns:
        success: 恒为 True；data 含 owner 与各域 counts。
    """
    owner = _current_owner()
    counts: dict[str, int] = {}
    with db_engine.SessionLocal() as session:
        for name, model in _STAT_TABLES.items():
            n = session.scalar(
                select(func.count()).select_from(model).where(model.owner_id == owner)
            )
            counts[name] = int(n or 0)
    total = sum(counts.values())
    return ok(
        {"owner": owner, "total": total, "counts": counts},
        message=f"owner={owner} 共 {total} 条数据",
    )


@mcp.tool()
def admin_reset() -> dict:
    """一键重置全部数据（复用 M3-05 scripts.reset_data），限定管理员。

    清空 DB / 向量目录 / Embedding 缓存并重建空库，不删 .env/配置。

    Returns:
        success: 重置成功为 True；权限不足为 False。
    """
    deny = _require_admin()
    if deny:
        return fail(deny)
    try:
        # tools.py 路径: <root>/src/littledotmcp/domains/admin/tools.py
        # scripts 目录: <root>/scripts
        scripts_dir = Path(__file__).resolve().parents[4] / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import reset_data  # 复用 M3-05 幂等重置

        rc = reset_data.reset_data()
        if rc != 0:
            return fail(f"重置脚本返回非零退出码：{rc}")
        return ok(message="数据已重置（DB/向量/Embedding 缓存已清空并重建空库）")
    except Exception as exc:  # 规约-07：不抛未捕获异常
        logger.exception("admin_reset 失败")
        return fail(f"重置失败：{exc}")
