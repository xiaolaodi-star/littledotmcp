"""统一返回结构（S0.4）。

所有 MCP 工具返回均经 ok() / fail() 包装为统一信封：
    { "success": bool, "data": Any | None, "message": str }
客户端可据 success 判定成败，data 携带载荷，message 携带可读说明。
"""

from __future__ import annotations

from typing import Any


def ok(data: Any = None, message: str = "") -> dict:
    """成功返回。"""
    return {"success": True, "data": data, "message": message}


def fail(message: str, data: Any = None) -> dict:
    """失败返回（保留 code 字段占位，错误码体系见 errors.py）。"""
    return {"success": False, "data": data, "message": message}
