"""规范域 MCP Resource 与 Prompt 注册（M5-05）。

- Resource `standard://{name}`：读取当前 owner 的规范正文（Markdown）
- Prompt `review_by_standard`：让 LLM 按指定规范对给定文本做评审

复用统一 owner 与 storage 层，隔离语义与工具一致。
"""

from __future__ import annotations

from ..common.logging import get_logger
from ..db import engine as db_engine
from ..domains.standard.storage import StandardRepository
from ..server import mcp

logger = get_logger(__name__)

_DEFAULT_OWNER = "local"


def _current_owner() -> str:
    return _DEFAULT_OWNER


@mcp.resource("standard://{name}")
def standard_resource(name: str) -> str:
    """返回规范正文（Markdown）。"""
    owner = _current_owner()
    with db_engine.SessionLocal() as session:
        std = StandardRepository(session).get_by_name(owner, name)
    if std is None:
        return f"# {name}\n\n（规范不存在）"
    return f"# {std.name}\n\n> 类别：{std.category}\n\n{std.content}"


@mcp.prompt()
def review_by_standard(standard_name: str, text: str) -> str:
    """按规范评审文本。"""
    owner = _current_owner()
    with db_engine.SessionLocal() as session:
        std = StandardRepository(session).get_by_name(owner, standard_name)
    if std is None:
        return f"规范 {standard_name!r} 不存在，请先 standard_add 注册。\n\n待评审内容：\n{text}"
    return (
        f"请严格按以下规范评审给定内容，逐条指出违规项并给出修改建议：\n\n"
        f"--- 规范：{std.name}（{std.category}）---\n{std.content}\n\n"
        f"--- 待评审内容 ---\n{text}"
    )
