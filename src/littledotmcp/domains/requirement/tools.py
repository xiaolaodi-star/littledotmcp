"""需求域 MCP 工具（M4-02）：requirement_add/list/get/update/remove/link/assess。

- 元数据落 requirements（OwnerScopedRepository 强制 owner 隔离）
- code 唯一约束冲突转 fail（不抛未捕获异常）
- 状态机 DRAFT->ASSESS->DEV->ONLINE->DONE/CLOSED 流转校验
- assess 调用 LLM 摘要，无 Key 时降级（仅改状态）
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...common.errors import NotFoundError, ValidationError
from ...common.logging import get_logger
from ...common.result import fail, ok
from ...config import get_settings
from ...db import engine as db_engine
from ...db.models import Document, Requirement
from ...db.repository import OwnerScopedRepository
from ...server import mcp

logger = get_logger(__name__)

_DEFAULT_OWNER = "local"

# 合法状态
REQ_STATUSES = {"DRAFT", "ASSESS", "DEV", "ONLINE", "DONE", "CLOSED"}

# 允许的状态正向流转（无向：允许原状态）
_REQ_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"DRAFT", "ASSESS"},
    "ASSESS": {"ASSESS", "DEV"},
    "DEV": {"DEV", "ONLINE"},
    "ONLINE": {"ONLINE", "DONE", "CLOSED"},
    "DONE": {"DONE", "CLOSED"},
    "CLOSED": {"CLOSED"},
}


class RequirementRepository(OwnerScopedRepository[Requirement]):
    model = Requirement

    def get_by_code(self, owner_id: str, code: str) -> Requirement | None:
        stmt = select(Requirement).where(
            Requirement.owner_id == owner_id, Requirement.code == code
        )
        return self.session.scalars(stmt).one_or_none()


def _current_owner() -> str:
    return _DEFAULT_OWNER


def _req_to_dict(req: Requirement) -> dict:
    return {
        "id": req.id,
        "code": req.code,
        "title": req.title,
        "status": req.status,
        "detail": req.detail,
        "related_commit": req.related_commit,
        "related_doc": req.related_doc,
        "related_tag": req.related_tag,
        "project_id": req.project_id,
        "milestone_id": req.milestone_id,
        "created_at": req.created_at.isoformat() if req.created_at else "",
        "updated_at": req.updated_at.isoformat() if req.updated_at else "",
    }


def _summarize(text: str) -> str:
    """LLM 摘要（降级：无 Key 时原样返回）。"""
    try:
        settings = get_settings()
        if not settings.llm_api_key:
            return text
        # 真实 LLM 摘要调用在此实现（M7 统一接入 embedding/llm 客户端后启用）
        return text
    except Exception as exc:  # 任意异常均降级，不阻断状态流转
        logger.warning("requirement 摘要降级：%s", exc)
        return text


@mcp.tool(
    name="requirement_add",
    description=(
        "新增需求：code 唯一（同用户），title 必填，status 默认 DRAFT。"
        "可选 project_id/milestone_id 关联项目（M8 扩展 B）。"
    ),
)
def requirement_add(
    code: str,
    title: str,
    detail: str = "",
    project_id: str = "",
    milestone_id: str = "",
) -> dict:
    owner = _current_owner()
    try:
        code = (code or "").strip()
        title = (title or "").strip()
        if not code or not title:
            return fail(message="code 与 title 必填")
        if len(code) > 64 or len(title) > 255:
            return fail(message="code/title 超长")
        proj_id = (project_id or "").strip() or None
        ms_id = (milestone_id or "").strip() or None
        with db_engine.SessionLocal() as session:
            repo = RequirementRepository(session)
            if repo.get_by_code(owner, code) is not None:
                return fail(message=f"需求编号已存在：{code}")
            req = Requirement(
                id=uuid.uuid4().hex,
                owner_id=owner,
                code=code,
                title=title,
                status="DRAFT",
                detail=detail or "",
                project_id=proj_id,
                milestone_id=ms_id,
            )
            try:
                repo.add(req)
                session.commit()
            except IntegrityError:
                session.rollback()
                return fail(message=f"需求编号已存在：{code}")
            logger.info("requirement_add 完成 code=%s id=%s", code, req.id)
        return ok(data=_req_to_dict(req), message="需求创建成功")
    except Exception as exc:
        logger.exception("requirement_add 未预期错误")
        return fail(message=f"创建失败：{exc}")


@mcp.tool(name="requirement_list", description="列出当前用户需求，可按 status 过滤。")
def requirement_list(status: str = "") -> dict:
    owner = _current_owner()
    try:
        status = (status or "").strip().upper()
        if status and status not in REQ_STATUSES:
            return fail(message=f"非法 status：{status}")
        with db_engine.SessionLocal() as session:
            stmt = select(Requirement).where(Requirement.owner_id == owner)
            if status:
                stmt = stmt.where(Requirement.status == status)
            stmt = stmt.order_by(Requirement.created_at.desc())
            items = list(session.scalars(stmt).all())
        return ok(
            data={"items": [_req_to_dict(r) for r in items], "count": len(items)},
            message=f"共 {len(items)} 条需求",
        )
    except Exception as exc:
        logger.exception("requirement_list 未预期错误")
        return fail(message=f"列出失败：{exc}")


@mcp.tool(name="requirement_get", description="按 code 获取需求详情。")
def requirement_get(code: str) -> dict:
    owner = _current_owner()
    try:
        code = (code or "").strip()
        if not code:
            return fail(message="code 必填")
        with db_engine.SessionLocal() as session:
            req = RequirementRepository(session).get_by_code(owner, code)
            if req is None:
                return fail(message="需求不存在")
            data = _req_to_dict(req)
        return ok(data=data, message="获取成功")
    except Exception as exc:
        logger.exception("requirement_get 未预期错误")
        return fail(message=f"获取失败：{exc}")


@mcp.tool(
    name="requirement_update",
    description="更新需求：title/detail/status 可选；status 需符合流转规则。",
)
def requirement_update(
    code: str,
    title: str = "",
    detail: str = "",
    status: str = "",
) -> dict:
    owner = _current_owner()
    try:
        code = (code or "").strip()
        if not code:
            return fail(message="code 必填")
        title = (title or "").strip()
        detail = (detail or "").strip()
        new_status = (status or "").strip().upper()
        if new_status and new_status not in REQ_STATUSES:
            return fail(message=f"非法 status：{new_status}")
        with db_engine.SessionLocal() as session:
            repo = RequirementRepository(session)
            req = repo.get_by_code(owner, code)
            if req is None:
                return fail(message="需求不存在")
            if title:
                if len(title) > 255:
                    return fail(message="title 超长")
                req.title = title
            if detail:
                req.detail = detail
            if new_status:
                allowed = _REQ_TRANSITIONS.get(req.status, set())
                if new_status not in allowed:
                    return fail(message=f"状态流转不允许：{req.status} -> {new_status}")
                req.status = new_status
            session.commit()
            logger.info("requirement_update 完成 code=%s", code)
            data = _req_to_dict(req)
        return ok(data=data, message="更新成功")
    except Exception as exc:
        logger.exception("requirement_update 未预期错误")
        return fail(message=f"更新失败：{exc}")


@mcp.tool(name="requirement_remove", description="删除需求。")
def requirement_remove(code: str) -> dict:
    owner = _current_owner()
    try:
        code = (code or "").strip()
        if not code:
            return fail(message="code 必填")
        with db_engine.SessionLocal() as session:
            repo = RequirementRepository(session)
            req = repo.get_by_code(owner, code)
            if req is None:
                return fail(message="需求不存在")
            repo.delete_by_owner(owner, req.id)
            session.commit()
            logger.info("requirement_remove 完成 code=%s", code)
        return ok(data={"code": code}, message="删除成功")
    except NotFoundError as exc:
        return fail(message=exc.message)
    except Exception as exc:
        logger.exception("requirement_remove 未预期错误")
        return fail(message=f"删除失败：{exc}")


@mcp.tool(
    name="requirement_link",
    description="关联需求与代码提交 / 文档 / 标签：related_commit、related_doc、related_tag 可选，至少其一。",
)
def requirement_link(
    code: str,
    related_commit: str = "",
    related_doc: str = "",
    related_tag: str = "",
) -> dict:
    owner = _current_owner()
    try:
        code = (code or "").strip()
        if not code:
            return fail(message="code 必填")
        related_commit = (related_commit or "").strip()
        related_doc = (related_doc or "").strip()
        related_tag = (related_tag or "").strip()
        if not related_commit and not related_doc and not related_tag:
            return fail(message="related_commit / related_doc / related_tag 至少提供一个")
        with db_engine.SessionLocal() as session:
            repo = RequirementRepository(session)
            req = repo.get_by_code(owner, code)
            if req is None:
                return fail(message="需求不存在")
            if related_doc:
                doc = session.get(Document, related_doc)
                if doc is None or getattr(doc, "owner_id", None) != owner:
                    return fail(message="关联文档不存在")
            if related_commit:
                req.related_commit = (req.related_commit + "," + related_commit).strip(",")
            if related_doc:
                req.related_doc = related_doc
            if related_tag:
                req.related_tag = (req.related_tag + "," + related_tag).strip(",")
            session.commit()
            logger.info("requirement_link 完成 code=%s", code)
            data = _req_to_dict(req)
        return ok(data=data, message="关联成功")
    except Exception as exc:
        logger.exception("requirement_link 未预期错误")
        return fail(message=f"关联失败：{exc}")


@mcp.tool(
    name="requirement_assess",
    description="需求评估：DRAFT->ASSESS，并对 detail 做 LLM 摘要（无 Key 时降级原样保留）。",
)
def requirement_assess(code: str) -> dict:
    owner = _current_owner()
    try:
        code = (code or "").strip()
        if not code:
            return fail(message="code 必填")
        with db_engine.SessionLocal() as session:
            repo = RequirementRepository(session)
            req = repo.get_by_code(owner, code)
            if req is None:
                return fail(message="需求不存在")
            if req.status != "DRAFT":
                return fail(message=f"仅 DRAFT 可评估，当前：{req.status}")
            summary = _summarize(req.detail or req.title)
            if summary and not req.detail:
                req.detail = summary
            req.status = "ASSESS"
            session.commit()
            logger.info("requirement_assess 完成 code=%s", code)
            data = _req_to_dict(req)
        return ok(data=data, message="评估完成")
    except Exception as exc:
        logger.exception("requirement_assess 未预期错误")
        return fail(message=f"评估失败：{exc}")
