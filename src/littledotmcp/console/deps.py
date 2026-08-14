"""M11-02 管理端鉴权依赖与工具函数。

ConsoleAuth 中间件解析 Cookie 后将当前用户注入 `request.scope["console_user"]`：
    {"user_id", "username", "role"}。
本模块提供从 Request 取当前用户、角色校验、owner 过滤的复用函数。
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..common.errors import AuthError
from ..db.models import User

_CONSOLE_USER_KEY = "console_user"


def set_console_user(request: Request, user: User) -> None:
    """由 ConsoleAuth 中间件注入当前用户。"""
    request.scope[_CONSOLE_USER_KEY] = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
    }


def get_console_user(request: Request) -> dict | None:
    """返回注入的当前用户；未登录返回 None。"""
    return request.scope.get(_CONSOLE_USER_KEY)


def require_login(request: Request) -> dict:
    """未登录抛 AuthError（由路由统一转 401）。"""
    user = get_console_user(request)
    if user is None:
        raise AuthError("未登录或会话已过期")
    return user


def require_role(request: Request, role: str) -> dict:
    """要求特定角色（如 admin）；不足抛 AuthError。"""
    user = require_login(request)
    if user["role"] != role:
        raise AuthError("权限不足")
    return user


def require_admin(request: Request) -> dict:
    """要求 admin 角色。"""
    return require_role(request, "admin")


def owner_filter_for(request: Request, target_owner_field, current_owner_id: str | None = None):
    """返回当前用户视角下的 owner 过滤值。

    - admin：可传 None 表示跨 owner（由调用方决定）；
    - user：强制本人 owner_id，杜绝越权查看他人数据。
    """
    user = require_login(request)
    if user["role"] == "admin":
        return current_owner_id  # admin 显式指定或 None（跨 owner）
    return user["user_id"]


def unauthorized_response(message: str = "未登录或会话已过期") -> JSONResponse:
    return JSONResponse(status_code=401, content={"error": message})


def forbidden_response(message: str = "权限不足") -> JSONResponse:
    return JSONResponse(status_code=403, content={"error": message})
