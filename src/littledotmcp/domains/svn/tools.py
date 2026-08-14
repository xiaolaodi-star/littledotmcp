"""SVN 域 MCP 工具（M4-01）：svn_repo_add/list/remove/checkout/update/commit/log。

- 元数据落 svn_repos / svn_ops_log（OwnerScopedRepository 强制 owner 隔离）
- 凭据明文经 encrypt 转 cred_enc 入库，绝不落明文
- 外部 svn 操作走 storage.get_svn_client（默认本地 fake，无 CLI 可测）
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from sqlalchemy import select

from ...common.errors import NotFoundError, ValidationError
from ...common.logging import get_logger
from ...common.result import fail, ok
from ...config import get_settings
from ...db import engine as db_engine
from ...db.models import SvnOpLog, SvnRepo
from ...db.repository import OwnerScopedRepository
from ...server import mcp
from .storage import decrypt, encrypt, get_svn_client

logger = get_logger(__name__)

_DEFAULT_OWNER = "local"

_NAME_RE = re.compile(r"^[A-Za-z0-9._@-]{1,255}$")


class SvnRepoRepository(OwnerScopedRepository[SvnRepo]):
    model = SvnRepo

    def get_by_name(self, owner_id: str, name: str) -> SvnRepo | None:
        stmt = select(SvnRepo).where(
            SvnRepo.owner_id == owner_id, SvnRepo.name == name
        )
        return self.session.scalars(stmt).one_or_none()


class SvnOpLogRepository(OwnerScopedRepository[SvnOpLog]):
    model = SvnOpLog

    def list_by_repo(self, owner_id: str, repo_id: str) -> list[SvnOpLog]:
        stmt = (
            select(SvnOpLog)
            .where(SvnOpLog.owner_id == owner_id, SvnOpLog.repo_id == repo_id)
            .order_by(SvnOpLog.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())


def _current_owner() -> str:
    return _DEFAULT_OWNER


def _repo_to_dict(repo: SvnRepo) -> dict:
    return {
        "id": repo.id,
        "name": repo.name,
        "url": repo.url,
        "username": repo.username,
        "created_at": repo.created_at.isoformat(),
    }


@mcp.tool(
    name="svn_repo_add",
    description="登记 SVN 仓库：name 唯一、url 必填、cred 为明文口令（仅内存使用，入库加密）。",
)
def svn_repo_add(name: str, url: str, username: str = "", cred: str = "") -> dict:
    owner = _current_owner()
    try:
        name = (name or "").strip()
        url = (url or "").strip()
        if not name or not url:
            return fail(message="name 与 url 必填")
        if not _NAME_RE.match(name):
            return fail(message="name 仅允许字母数字与 . _ @ - ，长度 1~255")
        if len(url) > 512:
            return fail(message="url 过长")
        with db_engine.SessionLocal() as session:
            repo_repo = SvnRepoRepository(session)
            if repo_repo.get_by_name(owner, name) is not None:
                return fail(message=f"仓库名已存在：{name}")
            repo = SvnRepo(
                id=uuid.uuid4().hex,
                owner_id=owner,
                name=name,
                url=url,
                username=(username or "").strip()[:128],
                cred_enc=encrypt(cred or ""),
            )
            repo_repo.add(repo)
            session.commit()
            logger.info("svn_repo_add 完成 id=%s name=%s", repo.id, repo.name)
        return ok(data=_repo_to_dict(repo), message="仓库登记成功")
    except Exception as exc:
        logger.exception("svn_repo_add 未预期错误")
        return fail(message=f"登记失败：{exc}")


@mcp.tool(name="svn_repo_list", description="列出当前用户登记的 SVN 仓库。")
def svn_repo_list() -> dict:
    owner = _current_owner()
    try:
        with db_engine.SessionLocal() as session:
            repos = SvnRepoRepository(session).list_by_owner(owner)
        items = [_repo_to_dict(r) for r in repos]
        return ok(data={"items": items, "count": len(items)}, message=f"共 {len(items)} 个仓库")
    except Exception as exc:
        logger.exception("svn_repo_list 未预期错误")
        return fail(message=f"列出失败：{exc}")


@mcp.tool(name="svn_repo_remove", description="删除登记的 SVN 仓库（含其操作日志）。")
def svn_repo_remove(repo_id: str) -> dict:
    owner = _current_owner()
    try:
        with db_engine.SessionLocal() as session:
            repo_repo = SvnRepoRepository(session)
            repo = repo_repo.get_by_owner(owner, repo_id)
            if repo is None:
                return fail(message="仓库不存在")
            op_repo = SvnOpLogRepository(session)
            for op in op_repo.list_by_repo(owner, repo_id):
                op_repo.delete(op)
            repo_repo.delete_by_owner(owner, repo_id)
            session.commit()
            logger.info("svn_repo_remove 完成 id=%s", repo_id)
        return ok(data={"id": repo_id}, message="删除成功")
    except NotFoundError as exc:
        return fail(message=exc.message)
    except Exception as exc:
        logger.exception("svn_repo_remove 未预期错误")
        return fail(message=f"删除失败：{exc}")


@mcp.tool(name="svn_checkout", description="检出仓库到本地路径（默认 storage_root/owner/svn/<name>）。")
def svn_checkout(repo_id: str, local_path: str = "") -> dict:
    owner = _current_owner()
    try:
        path = _resolve_local_path(owner, repo_id, local_path)
        with db_engine.SessionLocal() as session:
            repo = SvnRepoRepository(session).get_by_owner(owner, repo_id)
            if repo is None:
                return fail(message="仓库不存在")
            client = get_svn_client(repo_id, on_op=_make_on_op(owner, repo_id))
            rev = client.checkout(Path(path))
        return ok(data={"repo_id": repo_id, "local_path": str(path), "rev": rev}, message="检出成功")
    except ValidationError as exc:
        return fail(message=exc.message)
    except Exception as exc:
        logger.exception("svn_checkout 未预期错误")
        return fail(message=f"检出失败：{exc}")


@mcp.tool(name="svn_update", description="更新本地工作副本。")
def svn_update(repo_id: str, local_path: str = "") -> dict:
    owner = _current_owner()
    try:
        path = _resolve_local_path(owner, repo_id, local_path)
        with db_engine.SessionLocal() as session:
            if SvnRepoRepository(session).get_by_owner(owner, repo_id) is None:
                return fail(message="仓库不存在")
            client = get_svn_client(repo_id, on_op=_make_on_op(owner, repo_id))
            rev = client.update(Path(path))
        return ok(data={"repo_id": repo_id, "local_path": str(path), "rev": rev}, message="更新成功")
    except Exception as exc:
        logger.exception("svn_update 未预期错误")
        return fail(message=f"更新失败：{exc}")


@mcp.tool(name="svn_commit", description="提交本地改动，message 必填，并写入操作日志。")
def svn_commit(repo_id: str, message: str, local_path: str = "") -> dict:
    owner = _current_owner()
    try:
        message = (message or "").strip()
        if not message:
            return fail(message="commit message 必填")
        path = _resolve_local_path(owner, repo_id, local_path)
        with db_engine.SessionLocal() as session:
            if SvnRepoRepository(session).get_by_owner(owner, repo_id) is None:
                return fail(message="仓库不存在")
            client = get_svn_client(repo_id, on_op=_make_on_op(owner, repo_id))
            rev = client.commit(Path(path), message)
        return ok(data={"repo_id": repo_id, "rev": rev}, message="提交成功")
    except ValueError as exc:
        return fail(message=str(exc))
    except Exception as exc:
        logger.exception("svn_commit 未预期错误")
        return fail(message=f"提交失败：{exc}")


@mcp.tool(name="svn_log", description="查看仓库操作日志（倒序）。")
def svn_log(repo_id: str) -> dict:
    owner = _current_owner()
    try:
        with db_engine.SessionLocal() as session:
            if SvnRepoRepository(session).get_by_owner(owner, repo_id) is None:
                return fail(message="仓库不存在")
            ops = SvnOpLogRepository(session).list_by_repo(owner, repo_id)
        items = [
            {
                "id": o.id,
                "op": o.op,
                "rev": o.rev,
                "message": o.message,
                "created_at": o.created_at.isoformat(),
            }
            for o in ops
        ]
        return ok(data={"items": items, "count": len(items)}, message=f"共 {len(items)} 条记录")
    except Exception as exc:
        logger.exception("svn_log 未预期错误")
        return fail(message=f"查询失败：{exc}")


def _resolve_local_path(owner: str, repo_id: str, local_path: str) -> Path:
    if local_path:
        p = Path(local_path)
        if p.is_absolute() and not str(p).startswith(str(get_settings().storage_root)):
            raise ValidationError("local_path 必须位于 storage_root 内")
        return p
    base = Path(get_settings().storage_root) / owner / "svn" / repo_id
    return base


def _make_on_op(owner: str, repo_id: str) -> callable:
    """返回写入 SvnOpLog 的回调（在 db 会话外收集，tools 内已开会话提交）。"""

    def _on_op(op: str, rev: str, message: str) -> None:
        with db_engine.SessionLocal() as session:
            repo = SvnOpLogRepository(session)
            repo.add(
                SvnOpLog(
                    id=uuid.uuid4().hex,
                    owner_id=owner,
                    repo_id=repo_id,
                    op=op,
                    rev=rev,
                    message=message,
                )
            )
            session.commit()

    return _on_op
