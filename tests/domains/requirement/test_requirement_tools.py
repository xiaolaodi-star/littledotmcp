"""M4-02 requirement 域测试：状态机 / 唯一约束 / 关联 / owner 隔离。"""

from __future__ import annotations

import pytest

from littledotmcp.db import Base
from littledotmcp.domains.requirement import tools as req_tools


@pytest.fixture
def schema(sqlite_tmp_engine) -> None:
    Base.metadata.create_all(sqlite_tmp_engine)


def _set_owner(monkeypatch: pytest.MonkeyPatch, owner: str) -> None:
    monkeypatch.setattr(req_tools, "_current_owner", lambda: owner)


def _add(owner: str, monkeypatch: pytest.MonkeyPatch, code: str = "REQ-1", title: str = "t") -> None:
    _set_owner(monkeypatch, owner)
    r = req_tools.requirement_add(code, title)
    assert r["success"] is True, r


def test_add_and_get(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _add("alice", monkeypatch)
    g = req_tools.requirement_get("REQ-1")
    assert g["success"] is True
    assert g["data"]["status"] == "DRAFT"
    assert g["data"]["title"] == "t"


def test_code_unique(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _add("alice", monkeypatch)
    dup = req_tools.requirement_add("REQ-1", "other")
    assert dup["success"] is False
    assert "已存在" in dup["message"]


def test_status_transition(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _add("alice", monkeypatch)
    ass = req_tools.requirement_assess("REQ-1")
    assert ass["success"] is True
    assert ass["data"]["status"] == "ASSESS"

    upd = req_tools.requirement_update("REQ-1", status="DEV")
    assert upd["success"] is True
    assert upd["data"]["status"] == "DEV"

    # 非法流转：DRAFT -> DEV 不允许
    _add("alice", monkeypatch, code="REQ-2")
    bad = req_tools.requirement_update("REQ-2", status="DEV")
    assert bad["success"] is False


def test_assess_requires_draft(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _add("alice", monkeypatch)
    req_tools.requirement_assess("REQ-1")
    again = req_tools.requirement_assess("REQ-1")
    assert again["success"] is False


def test_link_doc_nonexistent(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _add("alice", monkeypatch)
    bad = req_tools.requirement_link("REQ-1", related_doc="no-such-doc")
    assert bad["success"] is False


def test_owner_isolation(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _add("alice", monkeypatch)
    _set_owner(monkeypatch, "bob")
    assert req_tools.requirement_get("REQ-1")["success"] is False
    assert req_tools.requirement_list()["data"]["count"] == 0
    _set_owner(monkeypatch, "alice")
    assert req_tools.requirement_list()["data"]["count"] == 1


def test_remove(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _add("alice", monkeypatch)
    rem = req_tools.requirement_remove("REQ-1")
    assert rem["success"] is True
    assert req_tools.requirement_get("REQ-1")["success"] is False
