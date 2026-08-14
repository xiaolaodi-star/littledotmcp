"""规范域 MCP 工具（M5-04）：standard_add/search/get/remove。

- 元数据落 standards（OwnerScopedRepository 强制 owner 隔离）
- name 同一用户下唯一，冲突转 fail
- search 支持按名称/类别模糊检索
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from ...common.logging import get_logger
from ...common.result import fail, ok
from ...db import engine as db_engine
from ...db.models import Standard
from ...server import mcp
from .storage import StandardRepository

logger = get_logger(__name__)

_DEFAULT_OWNER = "local"


def _current_owner() -> str:
    return _DEFAULT_OWNER


def _std_to_dict(s: Standard) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "category": s.category,
        "content": s.content,
        "created_at": s.created_at.isoformat() if s.created_at else "",
    }


@mcp.tool(
    name="standard_add",
    description="新增规范：name 唯一（同用户），content 为 Markdown 正文，category 默认 general。",
)
def standard_add(name: str, content: str, category: str = "general") -> dict:
    owner = _current_owner()
    try:
        name = (name or "").strip()
        content = (content or "").strip()
        category = (category or "general").strip()
        if not name:
            return fail(message="name 必填")
        if not content:
            return fail(message="content 必填")
        if len(name) > 128:
            return fail(message="name 超长")
        if len(category) > 64:
            return fail(message="category 超长")
        with db_engine.SessionLocal() as session:
            repo = StandardRepository(session)
            if repo.get_by_name(owner, name) is not None:
                return fail(message=f"规范已存在：{name}")
            std = Standard(
                id=uuid.uuid4().hex,
                owner_id=owner,
                name=name,
                category=category,
                content=content,
            )
            try:
                repo.add(std)
                session.commit()
            except IntegrityError:
                session.rollback()
                return fail(message=f"规范已存在：{name}")
            logger.info("standard_add 完成 id=%s name=%s", std.id, std.name)
        return ok(data=_std_to_dict(std), message="规范创建成功")
    except Exception as exc:
        logger.exception("standard_add 未预期错误")
        return fail(message=f"创建失败：{exc}")


@mcp.tool(
    name="standard_search",
    description="检索规范：keyword 匹配名称/正文，category 过滤类别，可仅按类别。",
)
def standard_search(keyword: str = "", category: str = "") -> dict:
    owner = _current_owner()
    try:
        keyword = (keyword or "").strip()
        category = (category or "").strip()
        with db_engine.SessionLocal() as session:
            stmt = select(Standard).where(Standard.owner_id == owner)
            if keyword:
                like = f"%{keyword}%"
                stmt = stmt.where(
                    or_(Standard.name.like(like), Standard.content.like(like))
                )
            if category:
                stmt = stmt.where(Standard.category == category)
            stmt = stmt.order_by(Standard.created_at.desc())
            items = list(session.scalars(stmt).all())
        return ok(
            data={"items": [_std_to_dict(s) for s in items], "count": len(items)},
            message=f"共 {len(items)} 条规范",
        )
    except Exception as exc:
        logger.exception("standard_search 未预期错误")
        return fail(message=f"检索失败：{exc}")


@mcp.tool(name="standard_get", description="按 name 获取规范正文。")
def standard_get(name: str) -> dict:
    owner = _current_owner()
    try:
        name = (name or "").strip()
        if not name:
            return fail(message="name 必填")
        with db_engine.SessionLocal() as session:
            std = StandardRepository(session).get_by_name(owner, name)
            if std is None:
                return fail(message="规范不存在")
            data = _std_to_dict(std)
        return ok(data=data, message="获取成功")
    except Exception as exc:
        logger.exception("standard_get 未预期错误")
        return fail(message=f"获取失败：{exc}")


@mcp.tool(name="standard_remove", description="删除规范。")
def standard_remove(name: str) -> dict:
    owner = _current_owner()
    try:
        name = (name or "").strip()
        if not name:
            return fail(message="name 必填")
        with db_engine.SessionLocal() as session:
            repo = StandardRepository(session)
            std = repo.get_by_name(owner, name)
            if std is None:
                return fail(message="规范不存在")
            repo.delete_by_owner(owner, std.id)
            session.commit()
            logger.info("standard_remove 完成 id=%s", std.id)
        return ok(data={"name": name}, message="删除成功")
    except Exception as exc:
        logger.exception("standard_remove 未预期错误")
        return fail(message=f"删除失败：{exc}")
