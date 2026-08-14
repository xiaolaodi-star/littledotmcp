"""思维导图域 MCP 工具（M5）：create/update/get/list/remove/export/from_doc。

- mermaid ↔ 树双向转换由 model.py 负责，非法输入转 fail
- 落库 mindmaps（OwnerScopedRepository 强制 owner 隔离），mermaid 与 opml 同写
- from_doc 优先 LLM 提炼，无 Key 降级 Markdown 标题解析
"""

from __future__ import annotations

import uuid

from ...common.logging import get_logger
from ...common.result import fail, ok
from ...db import engine as db_engine
from ...db.models import Mindmap
from ...server import mcp
from .export import tree_to_opml
from .from_doc import summarize_outline
from .model import MindNode, mermaid_to_tree, tree_to_mermaid, validate_mermaid
from .storage import MindmapRepository

logger = get_logger(__name__)

_DEFAULT_OWNER = "local"


def _current_owner() -> str:
    return _DEFAULT_OWNER


def _mindmap_to_dict(m: Mindmap) -> dict:
    return {
        "id": m.id,
        "title": m.title,
        "mermaid": m.mermaid,
        "opml": m.opml,
        "created_at": m.created_at.isoformat() if m.created_at else "",
    }


def _render(root: MindNode, title: str) -> tuple[str, str]:
    """渲染 mermaid 与 opml 文本。"""
    mermaid = tree_to_mermaid(root)
    opml = tree_to_opml(root, title)
    return mermaid, opml


@mcp.tool(
    name="mindmap_create",
    description="创建思维导图：title 必填，mermaid 可选（Mermaid mindmap 语法，非法将返回失败）。",
)
def mindmap_create(title: str, mermaid: str = "") -> dict:
    owner = _current_owner()
    try:
        title = (title or "").strip()
        if not title:
            return fail(message="title 必填")
        if len(title) > 255:
            return fail(message="title 超长")
        mermaid = (mermaid or "").strip()
        if mermaid and not validate_mermaid(mermaid):
            return fail(message="mermaid 语法非法：需以 mindmap 开头且只有一个根节点")
        with db_engine.SessionLocal() as session:
            repo = MindmapRepository(session)
            if repo.get_by_title(owner, title) is not None:
                return fail(message=f"思维导图已存在：{title}")
            if mermaid:
                root = mermaid_to_tree(mermaid)
                mm_mermaid, mm_opml = _render(root, title)
            else:
                root = MindNode(title)
                mm_mermaid, mm_opml = _render(root, title)
            m = Mindmap(
                id=uuid.uuid4().hex,
                owner_id=owner,
                title=title,
                mermaid=mm_mermaid,
                opml=mm_opml,
            )
            repo.add(m)
            session.commit()
            logger.info("mindmap_create 完成 id=%s title=%s", m.id, m.title)
            return ok(data=_mindmap_to_dict(m), message="思维导图创建成功")
    except ValueError as exc:
        return fail(message=str(exc))
    except Exception as exc:
        logger.exception("mindmap_create 未预期错误")
        return fail(message=f"创建失败：{exc}")


@mcp.tool(name="mindmap_list", description="列出当前用户全部思维导图。")
def mindmap_list() -> dict:
    owner = _current_owner()
    try:
        with db_engine.SessionLocal() as session:
            maps = MindmapRepository(session).list_by_owner(owner)
        items = [_mindmap_to_dict(m) for m in maps]
        return ok(data={"items": items, "count": len(items)}, message=f"共 {len(items)} 个思维导图")
    except Exception as exc:
        logger.exception("mindmap_list 未预期错误")
        return fail(message=f"列出失败：{exc}")


@mcp.tool(name="mindmap_get", description="按 title 获取思维导图详情。")
def mindmap_get(title: str) -> dict:
    owner = _current_owner()
    try:
        title = (title or "").strip()
        if not title:
            return fail(message="title 必填")
        with db_engine.SessionLocal() as session:
            m = MindmapRepository(session).get_by_title(owner, title)
            if m is None:
                return fail(message="思维导图不存在")
            data = _mindmap_to_dict(m)
        return ok(data=data, message="获取成功")
    except Exception as exc:
        logger.exception("mindmap_get 未预期错误")
        return fail(message=f"获取失败：{exc}")


@mcp.tool(
    name="mindmap_update",
    description="更新思维导图：mermaid 必填（整树替换，opml 同步重写）。",
)
def mindmap_update(title: str, mermaid: str) -> dict:
    owner = _current_owner()
    try:
        title = (title or "").strip()
        mermaid = (mermaid or "").strip()
        if not title:
            return fail(message="title 必填")
        if not validate_mermaid(mermaid):
            return fail(message="mermaid 语法非法：需以 mindmap 开头且只有一个根节点")
        with db_engine.SessionLocal() as session:
            repo = MindmapRepository(session)
            m = repo.get_by_title(owner, title)
            if m is None:
                return fail(message="思维导图不存在")
            root = mermaid_to_tree(mermaid)
            m.mermaid, m.opml = _render(root, m.title)
            session.commit()
            logger.info("mindmap_update 完成 id=%s", m.id)
            data = _mindmap_to_dict(m)
        return ok(data=data, message="更新成功")
    except ValueError as exc:
        return fail(message=str(exc))
    except Exception as exc:
        logger.exception("mindmap_update 未预期错误")
        return fail(message=f"更新失败：{exc}")


@mcp.tool(name="mindmap_remove", description="删除思维导图。")
def mindmap_remove(title: str) -> dict:
    owner = _current_owner()
    try:
        title = (title or "").strip()
        if not title:
            return fail(message="title 必填")
        with db_engine.SessionLocal() as session:
            repo = MindmapRepository(session)
            m = repo.get_by_title(owner, title)
            if m is None:
                return fail(message="思维导图不存在")
            repo.delete_by_owner(owner, m.id)
            session.commit()
            logger.info("mindmap_remove 完成 id=%s", m.id)
        return ok(data={"title": title}, message="删除成功")
    except Exception as exc:
        logger.exception("mindmap_remove 未预期错误")
        return fail(message=f"删除失败：{exc}")


@mcp.tool(
    name="mindmap_export",
    description="导出思维导图：format=opml（默认，可导入 XMind/FreeMind）。",
)
def mindmap_export(title: str, format: str = "opml") -> dict:
    owner = _current_owner()
    try:
        title = (title or "").strip()
        fmt = (format or "opml").strip().lower()
        if not title:
            return fail(message="title 必填")
        if fmt not in {"opml"}:
            return fail(message=f"不支持的格式：{fmt}（当前仅 opml）")
        with db_engine.SessionLocal() as session:
            m = MindmapRepository(session).get_by_title(owner, title)
            if m is None:
                return fail(message="思维导图不存在")
            opml = m.opml or tree_to_opml(mermaid_to_tree(m.mermaid), m.title)
        return ok(data={"title": title, "format": fmt, "content": opml}, message="导出成功")
    except ValueError as exc:
        return fail(message=str(exc))
    except Exception as exc:
        logger.exception("mindmap_export 未预期错误")
        return fail(message=f"导出失败：{exc}")


@mcp.tool(
    name="mindmap_from_doc",
    description="从文档/文本生成思维导图：优先 LLM 提炼大纲，无 Key 时按 Markdown 标题层级降级。",
)
def mindmap_from_doc(title: str, text: str) -> dict:
    owner = _current_owner()
    try:
        title = (title or "").strip()
        text = (text or "").strip()
        if not title:
            return fail(message="title 必填")
        if not text:
            return fail(message="text 必填")
        if len(title) > 255:
            return fail(message="title 超长")
        root = summarize_outline(text, title)
        mm_mermaid, mm_opml = _render(root, title)
        with db_engine.SessionLocal() as session:
            repo = MindmapRepository(session)
            m = repo.get_by_title(owner, title)
            if m is not None:
                m.mermaid, m.opml = mm_mermaid, mm_opml
                session.commit()
                logger.info("mindmap_from_doc 更新 id=%s", m.id)
                return ok(data=_mindmap_to_dict(m), message="思维导图已更新")
            m = Mindmap(
                id=uuid.uuid4().hex,
                owner_id=owner,
                title=title,
                mermaid=mm_mermaid,
                opml=mm_opml,
            )
            repo.add(m)
            session.commit()
            logger.info("mindmap_from_doc 创建 id=%s", m.id)
            return ok(data=_mindmap_to_dict(m), message="思维导图生成成功")
    except Exception as exc:
        logger.exception("mindmap_from_doc 未预期错误")
        return fail(message=f"生成失败：{exc}")
