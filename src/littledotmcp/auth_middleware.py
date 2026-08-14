"""M6-02 HTTP 层鉴权与限流中间件。

- AuthMiddleware：解析 `Authorization: Bearer <token>`，双通道校验：
  1. 快路径：与配置 `mcp_auth_token`（服务级共享密钥）恒等比较；
  2. 用户 Token：调用 auth.authenticate 校验（M1-05 令牌体系），返回 user.id；
  通过后在 scope["owner_id"] 注入 owner，失败返回 401（不泄露区分信息）。
- RateLimitMiddleware：进程内令牌桶限流（按 client IP），避免引入 redis 等外部
  组件（符合 ADR-4 零外部中间件）；超限返回 429。
- 审计：放行/拒绝写入日志（logger），不含 token 明文。
"""

from __future__ import annotations

import asyncio
import secrets
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .auth import authenticate
from .common.errors import AuthError
from .common.logging import get_logger
from .config import get_settings

logger = get_logger(__name__)

# 默认限流：每 IP 60 次 / 60 秒（令牌桶容量 60，每秒补 1）
_DEFAULT_RATE: int = 60
_DEFAULT_PER_SECONDS: int = 60

# 快路径共享密钥通过时的默认 owner（与业务层 _DEFAULT_OWNER 一致）
_LOCAL_OWNER: str = "local"

# 免鉴权路径前缀（无敏感信息的健康检查 + 管理端整段交由 ConsoleAuth 处理）
_PUBLIC_PATH_PREFIXES: tuple[str, ...] = ("/health", "/admin", "/admin/api/login", "/admin/api/setup")


def _client_ip(request: Request) -> str:
    """取客户端 IP；无直连信息时回退为 unknown。"""
    return request.client.host if request.client else "unknown"


def _is_public_path(path: str) -> bool:
    """是否免鉴权路径（健康检查 / 管理端整段放行给 ConsoleAuth）。"""
    return any(path == p or path.startswith(p + "/") or path == p for p in _PUBLIC_PATH_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    """Bearer Token 鉴权（共享密钥快路径 + 用户 Token 校验）。"""

    def __init__(self, app):
        super().__init__(app)
        self._settings = get_settings()

    async def dispatch(self, request: Request, call_next):
        # 健康检查免鉴权（无敏感信息）
        if _is_public_path(request.url.path):
            return await call_next(request)
        authz = request.headers.get("authorization", "")
        if not authz.lower().startswith("bearer "):
            logger.warning("鉴权拒绝：缺少 Authorization Bearer 头 ip=%s", _client_ip(request))
            return JSONResponse(status_code=401, content={"error": "未提供鉴权 Token"})
        token = authz[len("bearer "):].strip()
        if not token:
            return JSONResponse(status_code=401, content={"error": "未提供鉴权 Token"})

        owner_id = await self._resolve_owner(token)
        if owner_id is None:
            logger.warning("鉴权拒绝：Token 无效 ip=%s", _client_ip(request))
            return JSONResponse(status_code=401, content={"error": "鉴权失败"})
        request.scope["owner_id"] = owner_id
        logger.info("鉴权通过 owner_id=%s ip=%s", owner_id, _client_ip(request))
        return await call_next(request)

    async def _resolve_owner(self, token: str) -> str | None:
        """解析 token 对应的 owner_id；无效返回 None。"""
        shared = self._settings.mcp_auth_token
        if shared and secrets.compare_digest(token, shared):
            return _LOCAL_OWNER
        try:
            return await asyncio.to_thread(authenticate, token)
        except AuthError:
            return None
        except Exception:
            logger.exception("鉴权异常：authenticate 未预期错误")
            return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """进程内令牌桶限流（按 client IP）。"""

    def __init__(
        self,
        app,
        rate: int = _DEFAULT_RATE,
        per_seconds: int = _DEFAULT_PER_SECONDS,
    ):
        super().__init__(app)
        self._rate = rate
        self._per_seconds = per_seconds
        # ip -> [tokens, last_refill_ts]
        self._buckets: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        ip = _client_ip(request)
        allowed = await self._consume(ip)
        if not allowed:
            logger.warning("限流拒绝 ip=%s", ip)
            return JSONResponse(status_code=429, content={"error": "请求过于频繁，请稍后再试"})
        return await call_next(request)

    async def _consume(self, ip: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            bucket = self._buckets.get(ip)
            if bucket is None:
                bucket = [float(self._rate), now]
                self._buckets[ip] = bucket
            tokens, last = bucket
            elapsed = now - last
            tokens = min(
                float(self._rate),
                tokens + elapsed * (self._rate / self._per_seconds),
            )
            if tokens >= 1.0:
                bucket[0], bucket[1] = tokens - 1.0, now
                return True
            bucket[0], bucket[1] = tokens, now
            return False
