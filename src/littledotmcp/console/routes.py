"""M11 管理端路由（custom_route 挂载）。

- 认证：/admin/api/login、/admin/api/logout、/admin/api/me、/admin/api/setup
- 单页：/admin/（由 server.build_http_app 挂载 StaticFiles(html=True) 提供）
- 业务 API（M11-04）：知识库 / 用户 / 异常 / 运维

ConsoleAuth 中间件对 /admin/api/*（除 login/setup）做 Cookie Session 校验，
通过后注入 request.scope["console_user"]。本模块只负责路由与业务编排。
"""

from __future__ import annotations

import os
import secrets
import uuid

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from sqlalchemy import func, select

from ..common.errors import AuthError, NotFoundError, ValidationError
from ..common.logging import get_logger
from ..common.result import fail, ok
from ..config import get_settings
from ..db import engine as db_engine
from ..db.models import AuditLog, CallError, Document, KbDocument, User
from ..server import mcp
from . import auth as console_auth
from . import deps

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# 复用 M10 业务层（配置诊断/工具清单/统计/重置），不走 MCP 通道
from ..domains.admin import tools as admin_tools

logger = get_logger(__name__)

_COOKIE = console_auth.session_cookie_name()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _audit(action: str, entity: str, entity_id: str, actor_id: str, detail: str = "") -> None:
    """写入审计日志（管理端增删/重置/改角色）。失败仅记录日志，不阻断业务。"""
    try:
        with db_engine.SessionLocal() as s:
            s.add(
                AuditLog(
                    id=uuid.uuid4().hex,
                    actor_id=actor_id,
                    action=action,
                    entity=entity,
                    entity_id=entity_id,
                    detail=detail,
                )
            )
            s.commit()
    except Exception as exc:  # pragma: no cover - 审计写入失败不应阻断主流程
        logger.warning("审计写入失败 action=%s: %s", action, exc)


def _set_session_cookie(response: JSONResponse, token: str) -> None:
    # HTTP 下不设 Secure（属正常）；SameSite=Strict 防 CSRF；HttpOnly 防脚本读取
    response.set_cookie(
        _COOKIE,
        token,
        httponly=True,
        samesite="strict",
        path="/",
    )


def _clear_session_cookie(response: JSONResponse) -> None:
    response.delete_cookie(_COOKIE, path="/")


@mcp.custom_route("/admin/api/setup", methods=["POST"])
async def admin_setup(request: Request) -> JSONResponse:
    """空库时创建首个管理员（仅 users 为空可用，杜绝默认口令）。"""
    if not console_auth.is_empty_db():
        return JSONResponse(status_code=403, content={"error": "已有用户，禁止重复初始化"})
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return JSONResponse(status_code=400, content={"error": "用户名与密码必填"})
    try:
        result = console_auth.create_user(username, password, role="admin")
        return JSONResponse({"success": True, "data": result})
    except ValidationError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@mcp.custom_route("/admin/api/login", methods=["POST"])
async def admin_login(request: Request) -> JSONResponse:
    """管理端登录：用户名+密码 → argon2 校验 → 写 user_sessions → Set-Cookie。"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "请求体需为 JSON"})
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return JSONResponse(status_code=400, content={"error": "用户名与密码必填"})
    try:
        user = console_auth.authenticate_user(username, password)
    except AuthError as exc:
        return JSONResponse(status_code=401, content={"error": str(exc)})
    token = console_auth.create_session(user, ip=_client_ip(request))
    resp = JSONResponse(
        {"success": True, "data": {"user_id": user.id, "username": user.username, "role": user.role}}
    )
    _set_session_cookie(resp, token)
    return resp


@mcp.custom_route("/admin/api/logout", methods=["POST"])
async def admin_logout(request: Request) -> JSONResponse:
    """登出：销毁会话并清 Cookie。"""
    token = request.cookies.get(_COOKIE)
    console_auth.destroy_session(token)
    resp = JSONResponse({"success": True, "data": {"message": "已登出"}})
    _clear_session_cookie(resp)
    return resp


@mcp.custom_route("/admin/api/me", methods=["GET"])
async def admin_me(request: Request) -> JSONResponse:
    """返回当前登录用户信息。"""
    try:
        user = deps.require_login(request)
    except AuthError as exc:
        return deps.unauthorized_response(str(exc))
    return JSONResponse({"success": True, "data": user})


def static_dir() -> str:
    """返回静态资源目录（供 server 挂载 StaticFiles 使用）。"""
    return _STATIC_DIR


@mcp.custom_route("/admin/", methods=["GET"])
async def admin_page(request: Request) -> FileResponse:
    """管理端单页入口（M11-05 静态单页）。静态资源由 /admin/static 挂载提供。"""
    index_path = os.path.join(_STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        from starlette.responses import Response

        return Response("管理端静态资源缺失", status_code=503)
    return FileResponse(index_path)


# ===================== M11-04 管理 API =====================


def _parse_pagination(request: Request) -> tuple[int, int]:
    try:
        page = max(1, int(request.query_params.get("page", "1")))
        size = min(200, max(1, int(request.query_params.get("size", "20"))))
    except ValueError:
        page, size = 1, 20
    return page, size


def _owner_scope(request: Request, owner_param: str | None = None) -> str | None:
    """返回过滤用的 owner_id：admin 可指定 owner 参数或跨 owner（None），user 强制本人。"""
    return deps.owner_filter_for(request, None, current_owner_id=owner_param)


# ---- 知识库：documents ----

@mcp.custom_route("/admin/api/documents", methods=["GET"])
async def admin_list_documents(request: Request) -> JSONResponse:
    try:
        deps.require_login(request)
    except AuthError as exc:
        return deps.unauthorized_response(str(exc))
    owner = _owner_scope(request, request.query_params.get("owner"))
    page, size = _parse_pagination(request)
    with db_engine.SessionLocal() as s:
        if owner is None:
            total = int(s.scalar(select(func.count()).select_from(Document)) or 0)
            rows = s.scalars(
                select(Document).order_by(Document.created_at.desc()).limit(size).offset((page - 1) * size)
            ).all()
        else:
            total = int(
                s.scalar(select(func.count()).select_from(Document).where(Document.owner_id == owner)) or 0
            )
            rows = s.scalars(
                select(Document)
                .where(Document.owner_id == owner)
                .order_by(Document.created_at.desc())
                .limit(size)
                .offset((page - 1) * size)
            ).all()
        items = [
            {
                "id": r.id,
                "owner_id": r.owner_id,
                "name": r.name,
                "provider": r.provider,
                "mime": r.mime,
                "size": r.size,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
    return JSONResponse({"success": True, "data": {"items": items, "total": total, "page": page, "size": size}})


@mcp.custom_route("/admin/api/documents/{doc_id}", methods=["DELETE"])
async def admin_delete_document(request: Request) -> JSONResponse:
    try:
        deps.require_login(request)
    except AuthError as exc:
        return deps.unauthorized_response(str(exc))
    doc_id = request.path_params["doc_id"]
    owner = _owner_scope(request)  # user 仅本人；admin 跨 owner 可删任意
    with db_engine.SessionLocal() as s:
        doc = s.get(Document, doc_id)
        if doc is None:
            return JSONResponse(status_code=404, content={"error": "文档不存在"})
        if owner is not None and doc.owner_id != owner:
            return deps.forbidden_response("无权删除他人文档")
        s.delete(doc)
        s.commit()
    return JSONResponse({"success": True, "data": {"deleted": doc_id}})


# ---- 知识库：kb_documents ----

@mcp.custom_route("/admin/api/kb", methods=["GET"])
async def admin_list_kb(request: Request) -> JSONResponse:
    try:
        deps.require_login(request)
    except AuthError as exc:
        return deps.unauthorized_response(str(exc))
    owner = _owner_scope(request, request.query_params.get("owner"))
    page, size = _parse_pagination(request)
    with db_engine.SessionLocal() as s:
        if owner is None:
            total = int(s.scalar(select(func.count()).select_from(KbDocument)) or 0)
            rows = s.scalars(
                select(KbDocument).order_by(KbDocument.created_at.desc()).limit(size).offset((page - 1) * size)
            ).all()
        else:
            total = int(
                s.scalar(select(func.count()).select_from(KbDocument).where(KbDocument.owner_id == owner)) or 0
            )
            rows = s.scalars(
                select(KbDocument)
                .where(KbDocument.owner_id == owner)
                .order_by(KbDocument.created_at.desc())
                .limit(size)
                .offset((page - 1) * size)
            ).all()
        items = [
            {
                "id": r.id,
                "owner_id": r.owner_id,
                "title": r.title,
                "source_type": r.source_type,
                "chunk_count": r.chunk_count,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
    return JSONResponse({"success": True, "data": {"items": items, "total": total, "page": page, "size": size}})


@mcp.custom_route("/admin/api/kb/{kb_id}", methods=["DELETE"])
async def admin_delete_kb(request: Request) -> JSONResponse:
    try:
        deps.require_login(request)
    except AuthError as exc:
        return deps.unauthorized_response(str(exc))
    kb_id = request.path_params["kb_id"]
    owner = _owner_scope(request)
    with db_engine.SessionLocal() as s:
        kb = s.get(KbDocument, kb_id)
        if kb is None:
            return JSONResponse(status_code=404, content={"error": "知识库不存在"})
        if owner is not None and kb.owner_id != owner:
            return deps.forbidden_response("无权删除他人知识库")
        s.delete(kb)
        s.commit()
    return JSONResponse({"success": True, "data": {"deleted": kb_id}})


# ---- 用户管理（admin） ----

@mcp.custom_route("/admin/api/users", methods=["GET"])
async def admin_list_users(request: Request) -> JSONResponse:
    try:
        deps.require_admin(request)
    except AuthError as exc:
        return deps.forbidden_response(str(exc))
    page, size = _parse_pagination(request)
    with db_engine.SessionLocal() as s:
        total = int(s.scalar(select(func.count()).select_from(User)) or 0)
        rows = s.scalars(
            select(User).order_by(User.created_at.desc()).limit(size).offset((page - 1) * size)
        ).all()
        items = [
            {
                "id": r.id,
                "username": r.username,
                "display_name": r.display_name,
                "role": r.role,
                "is_active": r.is_active,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
    return JSONResponse({"success": True, "data": {"items": items, "total": total, "page": page, "size": size}})


@mcp.custom_route("/admin/api/users", methods=["POST"])
async def admin_create_user(request: Request) -> JSONResponse:
    try:
        deps.require_admin(request)
    except AuthError as exc:
        return deps.forbidden_response(str(exc))
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "请求体需为 JSON"})
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    role = body.get("role", "user")
    try:
        result = console_auth.create_user(username, password, role=role, display_name=body.get("display_name", ""))
        return JSONResponse({"success": True, "data": result})
    except ValidationError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@mcp.custom_route("/admin/api/users/{user_id}", methods=["PATCH"])
async def admin_patch_user(request: Request) -> JSONResponse:
    try:
        actor = deps.require_admin(request)
    except AuthError as exc:
        return deps.forbidden_response(str(exc))
    user_id = request.path_params["user_id"]
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "请求体需为 JSON"})
    with db_engine.SessionLocal() as s:
        user = s.get(User, user_id)
        if user is None:
            return JSONResponse(status_code=404, content={"error": "用户不存在"})
        changes = []
        if "role" in body and body["role"] in ("admin", "user"):
            user.role = body["role"]
            changes.append("role")
        if "is_active" in body and isinstance(body["is_active"], bool):
            user.is_active = body["is_active"]
            changes.append("is_active")
        if "password" in body and body["password"]:
            user.password_hash = console_auth._ph.hash(body["password"])
            changes.append("password")
        s.commit()
        _audit("patch_user", "users", user.id, actor["user_id"], f"changed={','.join(changes)}")
        return JSONResponse(
            {
                "success": True,
                "data": {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role,
                    "is_active": user.is_active,
                },
            }
        )


@mcp.custom_route("/admin/api/users/{user_id}", methods=["DELETE"])
async def admin_delete_user(request: Request) -> JSONResponse:
    try:
        actor = deps.require_admin(request)
    except AuthError as exc:
        return deps.forbidden_response(str(exc))
    user_id = request.path_params["user_id"]
    with db_engine.SessionLocal() as s:
        user = s.get(User, user_id)
        if user is None:
            return JSONResponse(status_code=404, content={"error": "用户不存在"})
        s.delete(user)
        s.commit()
        _audit("delete_user", "users", user_id, actor["user_id"], f"ip={_client_ip(request)}")
        return JSONResponse({"success": True, "data": {"deleted": user_id}})


# ---- 调用异常 ----

@mcp.custom_route("/admin/api/errors", methods=["GET"])
async def admin_list_errors(request: Request) -> JSONResponse:
    try:
        user = deps.require_login(request)
    except AuthError as exc:
        return deps.unauthorized_response(str(exc))
    status = request.query_params.get("status", "")
    tool = request.query_params.get("tool", "")
    owner_param = request.query_params.get("owner", "")
    page, size = _parse_pagination(request)
    with db_engine.SessionLocal() as s:
        stmt = select(CallError)
        # user 仅本人；admin 可指定 owner 或跨所有
        if user["role"] != "admin":
            stmt = stmt.where(CallError.owner_id == user["user_id"])
        elif owner_param:
            stmt = stmt.where(CallError.owner_id == owner_param)
        if status:
            stmt = stmt.where(CallError.status == status)
        if tool:
            stmt = stmt.where(CallError.tool_name == tool)
        total = int(s.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = s.scalars(
            stmt.order_by(CallError.created_at.desc()).limit(size).offset((page - 1) * size)
        ).all()
        items = [
            {
                "id": r.id,
                "owner_id": r.owner_id,
                "tool_name": r.tool_name,
                "error_type": r.error_type,
                "error_msg": r.error_msg,
                "status": r.status,
                "occurrences": r.occurrences,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
    return JSONResponse({"success": True, "data": {"items": items, "total": total, "page": page, "size": size}})


@mcp.custom_route("/admin/api/errors/{err_id}", methods=["DELETE"])
async def admin_delete_error(request: Request) -> JSONResponse:
    try:
        user = deps.require_login(request)
    except AuthError as exc:
        return deps.unauthorized_response(str(exc))
    err_id = request.path_params["err_id"]
    with db_engine.SessionLocal() as s:
        err = s.get(CallError, err_id)
        if err is None:
            return JSONResponse(status_code=404, content={"error": "异常不存在"})
        if user["role"] != "admin" and err.owner_id != user["user_id"]:
            return deps.forbidden_response("无权删除他人异常")
        s.delete(err)
        s.commit()
        return JSONResponse({"success": True, "data": {"deleted": err_id}})


@mcp.custom_route("/admin/api/errors/{err_id}/close", methods=["PATCH"])
async def admin_close_error(request: Request) -> JSONResponse:
    try:
        user = deps.require_login(request)
    except AuthError as exc:
        return deps.unauthorized_response(str(exc))
    err_id = request.path_params["err_id"]
    with db_engine.SessionLocal() as s:
        err = s.get(CallError, err_id)
        if err is None:
            return JSONResponse(status_code=404, content={"error": "异常不存在"})
        if user["role"] != "admin" and err.owner_id != user["user_id"]:
            return deps.forbidden_response("无权操作他人异常")
        err.status = "closed"
        s.commit()
        return JSONResponse({"success": True, "data": {"id": err.id, "status": "closed"}})


# ---- 运维（admin） ----

@mcp.custom_route("/admin/api/system/config", methods=["GET"])
async def admin_system_config(request: Request) -> JSONResponse:
    try:
        deps.require_admin(request)
    except AuthError as exc:
        return deps.forbidden_response(str(exc))
    result = admin_tools.admin_config_check()
    return JSONResponse(result)


@mcp.custom_route("/admin/api/system/tools", methods=["GET"])
async def admin_system_tools(request: Request) -> JSONResponse:
    try:
        deps.require_admin(request)
    except AuthError as exc:
        return deps.forbidden_response(str(exc))
    result = admin_tools.admin_tools()
    return JSONResponse(result)


@mcp.custom_route("/admin/api/system/reset", methods=["POST"])
async def admin_system_reset(request: Request) -> JSONResponse:
    try:
        actor = deps.require_admin(request)
    except AuthError as exc:
        return deps.forbidden_response(str(exc))
    result = admin_tools.admin_reset()
    _audit("system_reset", "system", "all", actor["user_id"], f"ip={_client_ip(request)}")
    return JSONResponse(result)


# ---- 个人 ----

@mcp.custom_route("/admin/api/me/password", methods=["PATCH"])
async def admin_me_password(request: Request) -> JSONResponse:
    try:
        user = deps.require_login(request)
    except AuthError as exc:
        return deps.unauthorized_response(str(exc))
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "请求体需为 JSON"})
    old_pwd = body.get("old_password") or ""
    new_pwd = body.get("new_password") or ""
    if not old_pwd or not new_pwd:
        return JSONResponse(status_code=400, content={"error": "旧密码与新密码必填"})
    with db_engine.SessionLocal() as s:
        db_user = s.get(User, user["user_id"])
        if db_user is None:
            return JSONResponse(status_code=404, content={"error": "用户不存在"})
        try:
            console_auth._ph.verify(db_user.password_hash, old_pwd)
        except Exception:
            return JSONResponse(status_code=400, content={"error": "旧密码错误"})
        db_user.password_hash = console_auth._ph.hash(new_pwd)
        s.commit()
    return JSONResponse({"success": True, "data": {"message": "密码已更新"}})


def register_console_routes() -> None:
    """占位：custom_route 装饰器已在导入时注册，无需额外挂载。

    保留函数以便 server.register_tools 统一调用，后续 M11-04/05 扩展此处。
    """
