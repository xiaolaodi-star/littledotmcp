"""M0 冒烟测试：hello 工具与统一返回契约。"""

from __future__ import annotations

from littledotmcp.domains.hello import hello
from littledotmcp.common.result import ok, fail


def test_hello_returns_envelope() -> None:
    res = hello("mcp")
    assert res["success"] is True
    assert res["data"]["echo"] == "mcp"
    assert res["data"]["version"] == "0.1.0"


def test_result_envelope_shape() -> None:
    assert set(ok(data=1).keys()) == {"success", "data", "message"}
    assert ok(data=1)["success"] is True
    assert fail("boom")["success"] is False
