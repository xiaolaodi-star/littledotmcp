"""标签域 MCP 工具（M4-04）：tag_add/list/remove + attach/detach/list_by_entity/list_entities。

- 元数据落 tags / entity_tags（均继承 OwnerScopedRepository 强制 owner 隔离）
- tag.name 唯一约束冲突转 fail（不抛未捕获异常）
- entity_type 白名单：requirement/project/task/doc/kb_chunk/milestone
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...common.errors import NotFoundError, ValidationError
from ...common.logging import get_logger
from ...common.result import fail, ok
from ...db import engine as db_engine
from ...db.models import EntityTag, Tag
from ...db.repository import OwnerScopedRepository
from ...server import mcp

logger = get_logger(__name__)

_DEFAULT_OWNER = "local"

# 允许的关联实体类型
ENTITY_TYPES = {"requirement", "project", "task", "doc", "kb_chunk", "milestone"}

_COLOR_RE = __import__("re").compile(r"^#[0-9A-Fa-f]{6}$")


class TagRepository(OwnerScopedRepository[Tag]):
    model = Tag

    def get_by_name(self, owner_id: str, name: str) -> Tag | None:
        stmt = select(Tag).where(Tag.owner_id == owner_id, Tag.name == name)
        return self.session.scalars(stmt).one_or_none()


class EntityTagRepository(OwnerScopedRepository[EntityTag]):
    model = EntityTag

    def list_by_entity(self, owner_id: str, entity_type: str, entity_id: str) -> list[EntityTag]:
        stmt = select(EntityTag).where(
            EntityTag.owner_id == owner_id,
            EntityTag.entity_type == entity_type,
            EntityTag.entity_id == entity_id,
        )
        return list(self.session.scalars(stmt).all())

    def list_by_tag(self, owner_id: str, tag_id: str) -> list[EntityTag]:
        stmt = select(EntityTag).where(
            EntityTag.owner_id == owner_id, EntityTag.tag_id == tag_id
        )
        return list(self.session.scalars(stmt).all())


def _current_owner() -> str:
    return _DEFAULT_OWNER


def _tag_to_dict(tag: Tag) -> dict:
    return {
        "id": tag.id,
        "name": tag.name,
        "color": tag.color,
    }


@mcp.tool(
    name="tag_add",
    description="新增标签：name 唯一，color 默认 #888888（十六进制颜色）。",
)
def tag_add(name: str, color: str = "#888888") -> dict:
    owner = _current_owner()
    try:
        name = (name or "").strip()
        color = (color or "#888888").strip()
        if not name:
            return fail(message="name 必填")
        if len(name) > 128:
            return fail(message="name 超长")
        if not _COLOR_RE.match(color):
            return fail(message="color 需为 #RRGGBB 格式")
        with db_engine.SessionLocal() as session:
            repo = TagRepository(session)
            if repo.get_by_name(owner, name) is not None:
                return fail(message=f"标签已存在：{name}")
            tag = Tag(id=uuid.uuid4().hex, owner_id=owner, name=name, color=color)
            try:
                repo.add(tag)
                session.commit()
            except IntegrityError:
                session.rollback()
                return fail(message=f"标签已存在：{name}")
            logger.info("tag_add 完成 id=%s name=%s", tag.id, tag.name)
        return ok(data=_tag_to_dict(tag), message="标签创建成功")
    except Exception as exc:
        logger.exception("tag_add 未预期错误")
        return fail(message=f"创建失败：{exc}")


@mcp.tool(name="tag_list", description="列出当前用户全部标签。")
def tag_list() -> dict:
    owner = _current_owner()
    try:
        with db_engine.SessionLocal() as session:
            tags = TagRepository(session).list_by_owner(owner)
        items = [_tag_to_dict(t) for t in tags]
        return ok(data={"items": items, "count": len(items)}, message=f"共 {len(items)} 个标签")
    except Exception as exc:
        logger.exception("tag_list 未预期错误")
        return fail(message=f"列出失败：{exc}")


@mcp.tool(name="tag_remove", description="删除标签（级联解除所有实体的关联）。")
def tag_remove(tag_id: str) -> dict:
    owner = _current_owner()
    try:
        with db_engine.SessionLocal() as session:
            repo = TagRepository(session)
            tag = repo.get_by_owner(owner, tag_id)
            if tag is None:
                return fail(message="标签不存在")
            et_repo = EntityTagRepository(session)
            for et in et_repo.list_by_tag(owner, tag_id):
                et_repo.delete(et)
            repo.delete_by_owner(owner, tag_id)
            session.commit()
            logger.info("tag_remove 完成 id=%s", tag_id)
        return ok(data={"id": tag_id}, message="删除成功")
    except NotFoundError as exc:
        return fail(message=exc.message)
    except Exception as exc:
        logger.exception("tag_remove 未预期错误")
        return fail(message=f"删除失败：{exc}")


@mcp.tool(
    name="tag_attach",
    description="给实体打标签：entity_type 限 requirement/project/task/doc/kb_chunk/milestone。",
)
def tag_attach(tag_id: str, entity_type: str, entity_id: str) -> dict:
    owner = _current_owner()
    try:
        entity_type = (entity_type or "").strip().lower()
        entity_id = (entity_id or "").strip()
        if not tag_id or not entity_id:
            return fail(message="tag_id 与 entity_id 必填")
        if entity_type not in ENTITY_TYPES:
            return fail(message=f"不支持的 entity_type：{entity_type}")
        with db_engine.SessionLocal() as session:
            repo = TagRepository(session)
            tag = repo.get_by_owner(owner, tag_id)
            if tag is None:
                return fail(message="标签不存在")
            et_repo = EntityTagRepository(session)
            for et in et_repo.list_by_entity(owner, entity_type, entity_id):
                if et.tag_id == tag_id:
                    return ok(
                        data={"tag_id": tag_id, "entity_type": entity_type, "entity_id": entity_id},
                        message="已关联，无需重复",
                    )
            et = EntityTag(
                id=uuid.uuid4().hex,
                owner_id=owner,
                tag_id=tag_id,
                entity_type=entity_type,
                entity_id=entity_id,
            )
            et_repo.add(et)
            session.commit()
            logger.info("tag_attach 完成 tag=%s entity=%s/%s", tag_id, entity_type, entity_id)
        return ok(
            data={"tag_id": tag_id, "entity_type": entity_type, "entity_id": entity_id},
            message="关联成功",
        )
    except Exception as exc:
        logger.exception("tag_attach 未预期错误")
        return fail(message=f"关联失败：{exc}")


@mcp.tool(name="tag_detach", description="解除实体与标签的关联。")
def tag_detach(tag_id: str, entity_type: str, entity_id: str) -> dict:
    owner = _current_owner()
    try:
        entity_type = (entity_type or "").strip().lower()
        entity_id = (entity_id or "").strip()
        if not tag_id or not entity_id:
            return fail(message="tag_id 与 entity_id 必填")
        if entity_type not in ENTITY_TYPES:
            return fail(message=f"不支持的 entity_type：{entity_type}")
        with db_engine.SessionLocal() as session:
            et_repo = EntityTagRepository(session)
            removed = 0
            for et in et_repo.list_by_entity(owner, entity_type, entity_id):
                if et.tag_id == tag_id:
                    et_repo.delete(et)
                    removed += 1
            session.commit()
            logger.info("tag_detach 完成 removed=%d", removed)
        return ok(
            data={"tag_id": tag_id, "entity_type": entity_type, "entity_id": entity_id, "removed": removed},
            message="解除成功" if removed else "无关联记录",
        )
    except Exception as exc:
        logger.exception("tag_detach 未预期错误")
        return fail(message=f"解除失败：{exc}")


@mcp.tool(name="tag_list_by_entity", description="列出某实体已关联的全部标签。")
def tag_list_by_entity(entity_type: str, entity_id: str) -> dict:
    owner = _current_owner()
    try:
        entity_type = (entity_type or "").strip().lower()
        entity_id = (entity_id or "").strip()
        if not entity_id:
            return fail(message="entity_id 必填")
        if entity_type not in ENTITY_TYPES:
            return fail(message=f"不支持的 entity_type：{entity_type}")
        with db_engine.SessionLocal() as session:
            et_repo = EntityTagRepository(session)
            tag_repo = TagRepository(session)
            tags = [
                tag_repo.get_by_owner(owner, et.tag_id)
                for et in et_repo.list_by_entity(owner, entity_type, entity_id)
            ]
            tags = [t for t in tags if t is not None]
        items = [_tag_to_dict(t) for t in tags]
        return ok(data={"items": items, "count": len(items)}, message=f"共 {len(items)} 个标签")
    except Exception as exc:
        logger.exception("tag_list_by_entity 未预期错误")
        return fail(message=f"列出失败：{exc}")


@mcp.tool(name="tag_list_entities", description="列出某标签关联的全部实体。")
def tag_list_entities(tag_id: str) -> dict:
    owner = _current_owner()
    try:
        if not tag_id:
            return fail(message="tag_id 必填")
        with db_engine.SessionLocal() as session:
            if TagRepository(session).get_by_owner(owner, tag_id) is None:
                return fail(message="标签不存在")
            et_repo = EntityTagRepository(session)
            entities = [
                {"entity_type": e.entity_type, "entity_id": e.entity_id}
                for e in et_repo.list_by_tag(owner, tag_id)
            ]
        return ok(data={"items": entities, "count": len(entities)}, message=f"共 {len(entities)} 个关联")
    except Exception as exc:
        logger.exception("tag_list_entities 未预期错误")
        return fail(message=f"列出失败：{exc}")
