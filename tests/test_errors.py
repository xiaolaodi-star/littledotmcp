"""M1 统一异常与错误码映射测试（M1-07）。"""

from __future__ import annotations

import pytest

from littledotmcp.common.errors import (
    AuthError,
    ForbiddenError,
    NotFoundError,
    ToolkitError,
    ValidationError,
)
from littledotmcp.common.result import fail, ok


def test_error_code_hierarchy() -> None:
    assert issubclass(ValidationError, ToolkitError)
    assert issubclass(NotFoundError, ToolkitError)
    assert issubclass(AuthError, ToolkitError)
    assert issubclass(ForbiddenError, ToolkitError)


def test_error_codes_distinct() -> None:
    assert ValidationError().code == "E_VALIDATION"
    assert NotFoundError().code == "E_NOT_FOUND"
    assert AuthError().code == "E_AUTH"
    assert ForbiddenError().code == "E_FORBIDDEN"


def test_result_envelope_keys() -> None:
    assert set(ok(1).keys()) == {"success", "data", "message"}
    assert set(fail("x").keys()) == {"success", "data", "message"}
    assert ok(1)["success"] is True
    assert fail("x")["success"] is False
