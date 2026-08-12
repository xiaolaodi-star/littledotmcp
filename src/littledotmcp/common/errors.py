"""统一异常与错误码体系（S0.4 / I1.7）。

业务异常统一抛 ToolkitError 子类；server 层将其映射为 fail() 信封，
避免向客户端泄露堆栈或敏感细节。
"""

from __future__ import annotations


class ToolkitError(Exception):
    """所有业务异常基类。"""

    code: str = "E_INTERNAL"
    http_status: int = 500

    def __init__(self, message: str = "", *, code: str | None = None, data: object = None) -> None:
        super().__init__(message)
        self.message = message
        self.data = data
        if code:
            self.code = code


class ValidationError(ToolkitError):
    code = "E_VALIDATION"
    http_status = 400


class NotFoundError(ToolkitError):
    code = "E_NOT_FOUND"
    http_status = 404


class AuthError(ToolkitError):
    code = "E_AUTH"
    http_status = 401


class ForbiddenError(ToolkitError):
    """越权访问（跨用户数据可见性违规）。"""

    code = "E_FORBIDDEN"
    http_status = 403


class ConfigError(ToolkitError):
    code = "E_CONFIG"
    http_status = 500
