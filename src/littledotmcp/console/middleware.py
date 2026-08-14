"""M11-02 ConsoleAuth 会话中间件。

职责：
- 对 /admin/ 路径（除 /admin/api/login、/admin/api/setup、登录/初始化页）校验 Cookie Session；
- 通过则注入 scope["console_user"]，失败对 API 返回 401、对页面 302 登录页；
- 与现有 AuthMiddleware（Bearer 双通道）双轨并存，互不干扰。

无证书 HTTP 安全：Cookie HttpOnly + SameSite=Strict（HTTP 不设 Secure 属正常），
Session 默认 12h 过期，校验 Origin 头防 CSRF（POST/PUT/PATCH/DELETE）。
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from ..common.logging import get_logger
from . import auth as console_auth
from . import deps
from .errors import owner_cv

logger = get_logger(__name__)

# 免会话校验的管理端路径
_PUBLIC_ADMIN_PATHS = frozenset(
    {"/admin/api/login", "/admin/api/setup"}
)
# 免 Origin 校验的安全方法
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_COOKIE = console_auth.session_cookie_name()


def _is_public_admin(path: str) -> bool:
    if path in _PUBLIC_ADMIN_PATHS:
        return True
    # 登录页/初始化页（非 API）允许匿名访问，由页面自行跳登录
    if path == "/admin/":
        return True
    # 静态资源（css/js）免会话校验，由 StaticFiles 直接服务
    if path.startswith("/admin/static/"):
        return True
    return False


class ConsoleAuthMiddleware(BaseHTTPMiddleware):
    """管理端 Cookie Session 鉴权中间件。"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/admin"):
            return await call_next(request)

        # 公共路径直接放行（login/setup/登录页）
        if _is_public_admin(path):
            return await call_next(request)

        # CSRF 防护：变更类请求校验 Origin（HTTP 下同源即可，无 Origin 时放行简单场景）
        if request.method not in _SAFE_METHODS:
            origin = request.headers.get("origin")
            host = request.headers.get("host")
            if origin and host and origin.split("://", 1)[-1] != host:
                logger.warning("管理端 CSRF 拦截：Origin 不匹配 host=%s origin=%s", host, origin)
                return JSONResponse(status_code=403, content={"error": "跨站请求被拒绝"})

        token = request.cookies.get(_COOKIE)
        user = console_auth.get_user_from_session(token)
        if user is None:
            if path.startswith("/admin/api/"):
                return deps.unauthorized_response()
            return RedirectResponse("/admin/", status_code=302)

        deps.set_console_user(request, user)
        return await call_next(request)


class OwnerContextMiddleware(BaseHTTPMiddleware):
    """将 scope 中的 owner_id（AuthMiddleware 注入 /mcp 请求）透传至 call_tool 调用链。

    通过 contextvars 在异步调用链内共享，使 M11-03 异常采集能归属到发起调用的 owner。
    仅对存在 owner_id 的请求生效；/admin 管理端请求由 ConsoleAuth 注入 console_user，
    其 owner 不入此变量（管理端异常属 API 级别，不在 MCP call_tool 采集范围）。
    """

    async def dispatch(self, request: Request, call_next):
        owner = request.scope.get("owner_id")
        if owner:
            owner_cv.set(owner)
        return await call_next(request)
