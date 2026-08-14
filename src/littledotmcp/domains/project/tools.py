"""项目域 MCP 工具（M4-03）：project/milestone/task 全套 CRUD 与进度统计。

- 元数据落 projects / milestones / tasks（均继承 OwnerScopedRepository 强制 owner 隔离）
- milestones/tasks 通过 project_id 外键级联删除（models 已 ondelete=CASCADE）
- task.status 合法值 {todo, doing, done}；weight 默认 1，用于进度加权统计
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select

from ...common.errors import NotFoundError, ValidationError
from ...common.logging import get_logger
from ...common.result import fail, ok
from ...db import engine as db_engine
from ...db.models import Milestone, Project, Task
from ...db.repository import OwnerScopedRepository
from ...server import mcp

logger = get_logger(__name__)

_DEFAULT_OWNER = "local"

TASK_STATUSES = {"todo", "doing", "done"}


class ProjectRepository(OwnerScopedRepository[Project]):
    model = Project


class MilestoneRepository(OwnerScopedRepository[Milestone]):
    model = Milestone

    def list_by_project(self, owner_id: str, project_id: str) -> list[Milestone]:
        stmt = (
            select(Milestone)
            .where(Milestone.owner_id == owner_id, Milestone.project_id == project_id)
            .order_by(Milestone.due.asc().nullslast())
        )
        return list(self.session.scalars(stmt).all())


class TaskRepository(OwnerScopedRepository[Task]):
    model = Task

    def list_by_project(
        self, owner_id: str, project_id: str, milestone_id: str | None = None
    ) -> list[Task]:
        stmt = select(Task).where(
            Task.owner_id == owner_id, Task.project_id == project_id
        )
        if milestone_id:
            stmt = stmt.where(Task.milestone_id == milestone_id)
        return list(self.session.scalars(stmt).all())


def _current_owner() -> str:
    return _DEFAULT_OWNER


def _parse_due(due: str) -> datetime | None:
    if not due:
        return None
    try:
        return datetime.fromisoformat(due)
    except ValueError as exc:
        raise ValidationError(f"due 需为 ISO 格式日期：{exc}") from exc


def _project_to_dict(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "status": p.status,
        "created_at": p.created_at.isoformat() if p.created_at else "",
    }


def _milestone_to_dict(m: Milestone) -> dict:
    return {
        "id": m.id,
        "project_id": m.project_id,
        "name": m.name,
        "due": m.due.isoformat() if m.due else "",
        "done": m.done,
    }


def _task_to_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "project_id": t.project_id,
        "milestone_id": t.milestone_id,
        "title": t.title,
        "status": t.status,
        "weight": t.weight,
    }


def _progress(tasks: list[Task]) -> dict:
    total = sum(t.weight for t in tasks) or 0
    done = sum(t.weight for t in tasks if t.status == "done")
    pct = round(done / total * 100, 1) if total else 0.0
    return {"total_weight": total, "done_weight": done, "progress_pct": pct}


@mcp.tool(name="project_add", description="新增项目：name 必填，description 可选。")
def project_add(name: str, description: str = "") -> dict:
    owner = _current_owner()
    try:
        name = (name or "").strip()
        if not name:
            return fail(message="name 必填")
        if len(name) > 255:
            return fail(message="name 超长")
        with db_engine.SessionLocal() as session:
            repo = ProjectRepository(session)
            proj = Project(
                id=uuid.uuid4().hex,
                owner_id=owner,
                name=name,
                description=(description or "").strip(),
                status="active",
            )
            repo.add(proj)
            session.commit()
            logger.info("project_add 完成 id=%s name=%s", proj.id, proj.name)
        return ok(data=_project_to_dict(proj), message="项目创建成功")
    except Exception as exc:
        logger.exception("project_add 未预期错误")
        return fail(message=f"创建失败：{exc}")


@mcp.tool(name="project_list", description="列出当前用户全部项目。")
def project_list() -> dict:
    owner = _current_owner()
    try:
        with db_engine.SessionLocal() as session:
            projects = ProjectRepository(session).list_by_owner(owner)
        items = [_project_to_dict(p) for p in projects]
        return ok(data={"items": items, "count": len(items)}, message=f"共 {len(items)} 个项目")
    except Exception as exc:
        logger.exception("project_list 未预期错误")
        return fail(message=f"列出失败：{exc}")


@mcp.tool(name="project_get", description="获取项目详情与进度统计。")
def project_get(project_id: str) -> dict:
    owner = _current_owner()
    try:
        with db_engine.SessionLocal() as session:
            repo = ProjectRepository(session)
            proj = repo.get_by_owner(owner, project_id)
            if proj is None:
                return fail(message="项目不存在")
            tasks = TaskRepository(session).list_by_project(owner, project_id)
            data = _project_to_dict(proj)
            data["progress"] = _progress(tasks)
        return ok(data=data, message="获取成功")
    except Exception as exc:
        logger.exception("project_get 未预期错误")
        return fail(message=f"获取失败：{exc}")


@mcp.tool(name="project_remove", description="删除项目（级联删除其里程碑与任务）。")
def project_remove(project_id: str) -> dict:
    owner = _current_owner()
    try:
        with db_engine.SessionLocal() as session:
            repo = ProjectRepository(session)
            proj = repo.get_by_owner(owner, project_id)
            if proj is None:
                return fail(message="项目不存在")
            # 手动级联删除（SQLite 默认不启用外键约束，依赖 DB 级联不可靠）
            task_repo = TaskRepository(session)
            for t in task_repo.list_by_project(owner, project_id):
                task_repo.delete(t)
            ms_repo = MilestoneRepository(session)
            for m in ms_repo.list_by_project(owner, project_id):
                ms_repo.delete(m)
            repo.delete_by_owner(owner, project_id)
            session.commit()
            logger.info("project_remove 完成 id=%s", project_id)
        return ok(data={"id": project_id}, message="删除成功")
    except NotFoundError as exc:
        return fail(message=exc.message)
    except Exception as exc:
        logger.exception("project_remove 未预期错误")
        return fail(message=f"删除失败：{exc}")


@mcp.tool(name="milestone_add", description="新增里程碑：project_id 必填，due 可选 ISO 日期。")
def milestone_add(project_id: str, name: str, due: str = "") -> dict:
    owner = _current_owner()
    try:
        name = (name or "").strip()
        if not project_id or not name:
            return fail(message="project_id 与 name 必填")
        due_dt = _parse_due(due)
        with db_engine.SessionLocal() as session:
            repo = ProjectRepository(session)
            if repo.get_by_owner(owner, project_id) is None:
                return fail(message="项目不存在")
            ms = Milestone(
                id=uuid.uuid4().hex,
                owner_id=owner,
                project_id=project_id,
                name=name,
                due=due_dt,
                done=False,
            )
            MilestoneRepository(session).add(ms)
            session.commit()
            logger.info("milestone_add 完成 id=%s", ms.id)
        return ok(data=_milestone_to_dict(ms), message="里程碑创建成功")
    except ValidationError as exc:
        return fail(message=exc.message)
    except Exception as exc:
        logger.exception("milestone_add 未预期错误")
        return fail(message=f"创建失败：{exc}")


@mcp.tool(name="milestone_list", description="列出项目的里程碑。")
def milestone_list(project_id: str) -> dict:
    owner = _current_owner()
    try:
        if not project_id:
            return fail(message="project_id 必填")
        with db_engine.SessionLocal() as session:
            items = MilestoneRepository(session).list_by_project(owner, project_id)
        data = [_milestone_to_dict(m) for m in items]
        return ok(data={"items": data, "count": len(data)}, message=f"共 {len(data)} 个里程碑")
    except Exception as exc:
        logger.exception("milestone_list 未预期错误")
        return fail(message=f"列出失败：{exc}")


@mcp.tool(
    name="task_add",
    description="新增任务：project_id/title 必填，milestone_id 可选，weight 默认 1。",
)
def task_add(
    project_id: str,
    title: str,
    milestone_id: str = "",
    weight: int = 1,
) -> dict:
    owner = _current_owner()
    try:
        title = (title or "").strip()
        if not project_id or not title:
            return fail(message="project_id 与 title 必填")
        if weight < 1:
            return fail(message="weight 必须 >= 1")
        with db_engine.SessionLocal() as session:
            repo = ProjectRepository(session)
            if repo.get_by_owner(owner, project_id) is None:
                return fail(message="项目不存在")
            task = Task(
                id=uuid.uuid4().hex,
                owner_id=owner,
                project_id=project_id,
                milestone_id=(milestone_id or "").strip() or None,
                title=title,
                status="todo",
                weight=weight,
            )
            TaskRepository(session).add(task)
            session.commit()
            logger.info("task_add 完成 id=%s", task.id)
        return ok(data=_task_to_dict(task), message="任务创建成功")
    except Exception as exc:
        logger.exception("task_add 未预期错误")
        return fail(message=f"创建失败：{exc}")


@mcp.tool(
    name="task_list",
    description="列出任务：project_id 必填，milestone_id 可选过滤。",
)
def task_list(project_id: str, milestone_id: str = "") -> dict:
    owner = _current_owner()
    try:
        if not project_id:
            return fail(message="project_id 必填")
        milestone_id = (milestone_id or "").strip()
        with db_engine.SessionLocal() as session:
            tasks = TaskRepository(session).list_by_project(
                owner, project_id, milestone_id or None
            )
        data = [_task_to_dict(t) for t in tasks]
        return ok(
            data={"items": data, "count": len(data), "progress": _progress(tasks)},
            message=f"共 {len(data)} 个任务",
        )
    except Exception as exc:
        logger.exception("task_list 未预期错误")
        return fail(message=f"列出失败：{exc}")


@mcp.tool(
    name="task_update",
    description="更新任务：status 需为 todo/doing/done，weight 可改。",
)
def task_update(task_id: str, status: str = "", weight: int = 0) -> dict:
    owner = _current_owner()
    try:
        if not task_id:
            return fail(message="task_id 必填")
        status = (status or "").strip().lower()
        if status and status not in TASK_STATUSES:
            return fail(message=f"非法 status：{status}")
        if weight and weight < 1:
            return fail(message="weight 必须 >= 1")
        with db_engine.SessionLocal() as session:
            repo = TaskRepository(session)
            task = repo.get_by_owner(owner, task_id)
            if task is None:
                return fail(message="任务不存在")
            if status:
                task.status = status
            if weight:
                task.weight = weight
            session.commit()
            logger.info("task_update 完成 id=%s", task_id)
            data = _task_to_dict(task)
        return ok(data=data, message="更新成功")
    except Exception as exc:
        logger.exception("task_update 未预期错误")
        return fail(message=f"更新失败：{exc}")


@mcp.tool(name="task_remove", description="删除任务。")
def task_remove(task_id: str) -> dict:
    owner = _current_owner()
    try:
        if not task_id:
            return fail(message="task_id 必填")
        with db_engine.SessionLocal() as session:
            repo = TaskRepository(session)
            task = repo.get_by_owner(owner, task_id)
            if task is None:
                return fail(message="任务不存在")
            repo.delete_by_owner(owner, task_id)
            session.commit()
            logger.info("task_remove 完成 id=%s", task_id)
        return ok(data={"id": task_id}, message="删除成功")
    except NotFoundError as exc:
        return fail(message=exc.message)
    except Exception as exc:
        logger.exception("task_remove 未预期错误")
        return fail(message=f"删除失败：{exc}")
