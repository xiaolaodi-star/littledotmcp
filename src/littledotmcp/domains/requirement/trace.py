"""M8 需求追溯链路：按需求编号聚合端到端可追溯信息。

聚合维度：
- SVN 提交（SvnOpLog.requirement_id）
- 关联文档（Requirement.related_doc 解析为 Document）
- 关联标签（Requirement.related_tag 字段 + EntityTag(entity_type="requirement")）
- 项目 / 里程碑（Requirement.project_id / milestone_id）
- 需求状态流转时间线（created_at / updated_at）

所有查询强制 owner 隔离（规约）。
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from ...common.result import fail, ok
from ...db import engine as db_engine
from ...db.models import Document, EntityTag, Milestone, Project, Requirement, SvnOpLog, Tag
from ...server import mcp
from .tools import _current_owner, _req_to_dict

logger = logging.getLogger(__name__)


def _split(value: str) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def build_trace(owner: str, code: str) -> dict:
    """聚合需求端到端追溯信息，返回结构化 dict。"""
    with db_engine.SessionLocal() as session:
        req = (
            session.execute(select(Requirement).where(Requirement.owner_id == owner, Requirement.code == code))
            .scalars()
            .first()
        )
        if req is None:
            return {"found": False, "code": code}

        # SVN 提交：经 requirement_id 反查
        svn_rows = (
            session.execute(
                select(SvnOpLog)
                .where(SvnOpLog.owner_id == owner, SvnOpLog.requirement_id == req.id)
                .order_by(SvnOpLog.created_at)
            )
            .scalars()
            .all()
        )
        svn_commits = [
            {
                "repo_id": s.repo_id,
                "op": s.op,
                "rev": s.rev,
                "message": s.message,
                "created_at": s.created_at.isoformat() if s.created_at else "",
            }
            for s in svn_rows
        ]

        # 关联文档：related_doc 解析为 Document
        doc_ids = _split(req.related_doc)
        documents = []
        if doc_ids:
            doc_rows = (
                session.execute(
                    select(Document).where(Document.owner_id == owner, Document.id.in_(doc_ids))
                )
                .scalars()
                .all()
            )
            documents = [
                {"id": d.id, "title": d.title, "path": d.path, "provider": d.provider}
                for d in doc_rows
            ]

        # 关联标签：related_tag 字段（tag_id 列表）
        tag_ids = _split(req.related_tag)
        # 另经 EntityTag 多态聚合
        entity_tag_rows = (
            session.execute(
                select(EntityTag)
                .where(EntityTag.owner_id == owner, EntityTag.entity_type == "requirement", EntityTag.entity_id == req.id)
            )
            .scalars()
            .all()
        )
        for et in entity_tag_rows:
            if et.tag_id not in tag_ids:
                tag_ids.append(et.tag_id)
        tags = []
        if tag_ids:
            tag_rows = (
                session.execute(select(Tag).where(Tag.owner_id == owner, Tag.id.in_(tag_ids)))
                .scalars()
                .all()
            )
            tags = [{"id": t.id, "name": t.name, "color": t.color} for t in tag_rows]

        # 项目 / 里程碑（M8 扩展 B）
        project = None
        milestone = None
        if req.project_id:
            proj = (
                session.execute(
                    select(Project).where(Project.owner_id == owner, Project.id == req.project_id)
                )
                .scalars()
                .first()
            )
            if proj is not None:
                project = {"id": proj.id, "name": proj.name, "status": proj.status}
        if req.milestone_id:
            ms = (
                session.execute(
                    select(Milestone).where(Milestone.owner_id == owner, Milestone.id == req.milestone_id)
                )
                .scalars()
                .first()
            )
            if ms is not None:
                milestone = {"id": ms.id, "name": ms.name, "done": ms.done}

        # 状态流转时间线
        timeline = [
            {"event": "created", "status": req.status, "at": req.created_at.isoformat() if req.created_at else ""},
        ]
        if req.updated_at and req.updated_at != req.created_at:
            timeline.append(
                {"event": "updated", "status": req.status, "at": req.updated_at.isoformat() if req.updated_at else ""}
            )

        return {
            "found": True,
            "requirement": _req_to_dict(req),
            "svn_commits": svn_commits,
            "documents": documents,
            "tags": tags,
            "project": project,
            "milestone": milestone,
            "timeline": timeline,
        }


@mcp.tool(
    name="requirement_trace",
    description="按需求编号一键查询完整追溯树：SVN 提交/文档/标签/项目里程碑/状态流转（M8）。",
)
def requirement_trace(code: str) -> dict:
    owner = _current_owner()
    try:
        code = (code or "").strip()
        if not code:
            return fail(message="code 必填")
        trace = build_trace(owner, code)
        if not trace.get("found"):
            return fail(message=f"需求不存在：{code}")
        return ok(data=trace, message="追溯成功")
    except Exception as exc:
        logger.exception("requirement_trace 未预期错误")
        return fail(message=f"追溯失败：{exc}")
