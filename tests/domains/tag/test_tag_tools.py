"""M4-04 tag 域测试：唯一约束 / 关联 / 非法 entity_type / owner 隔离。"""

from __future__ import annotations

import pytest

from littledotmcp.db import Base
from littledotmcp.domains.tag import tools as tag_tools


@pytest.fixture
def schema(sqlite_tmp_engine) -> None:
    Base.metadata.create_all(sqlite_tmp_engine)


def _set_owner(monkeypatch: pytest.MonkeyPatch, owner: str) -> None:
    monkeypatch.setattr(tag_tools, "_current_owner", lambda: owner)


def _tag(owner: str, monkeypatch: pytest.MonkeyPatch, name: str = "red", color: str = "#ff0000") -> str:
    _set_owner(monkeypatch, owner)
    r = tag_tools.tag_add(name, color)
    assert r["success"] is True, r
    return r["data"]["id"]


def test_add_and_list(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _tag("alice", monkeypatch)
    lst = tag_tools.tag_list()
    assert lst["data"]["count"] == 1
    assert lst["data"]["items"][0]["color"] == "#ff0000"


def test_name_unique(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _tag("alice", monkeypatch)
    dup = tag_tools.tag_add("red")
    assert dup["success"] is False
    assert "已存在" in dup["message"]


def test_invalid_color(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = tag_tools.tag_add("blue", color="red")
    assert bad["success"] is False


def test_invalid_entity_type(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    tid = _tag("alice", monkeypatch)
    bad = tag_tools.tag_attach(tid, "unknown_type", "e1")
    assert bad["success"] is False


def test_attach_detach_and_query(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    tid = _tag("alice", monkeypatch)
    att = tag_tools.tag_attach(tid, "requirement", "REQ-1")
    assert att["success"] is True
    # 重复 attach 幂等
    assert tag_tools.tag_attach(tid, "requirement", "REQ-1")["success"] is True

    by_entity = tag_tools.tag_list_by_entity("requirement", "REQ-1")
    assert by_entity["data"]["count"] == 1

    by_tag = tag_tools.tag_list_entities(tid)
    assert by_tag["data"]["count"] == 1

    det = tag_tools.tag_detach(tid, "requirement", "REQ-1")
    assert det["data"]["removed"] == 1
    assert tag_tools.tag_list_by_entity("requirement", "REQ-1")["data"]["count"] == 0


def test_remove_cascades(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    tid = _tag("alice", monkeypatch)
    tag_tools.tag_attach(tid, "requirement", "REQ-1")
    rem = tag_tools.tag_remove(tid)
    assert rem["success"] is True
    assert tag_tools.tag_list_entities(tid)["success"] is False


def test_owner_isolation(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    tid = _tag("alice", monkeypatch)
    _set_owner(monkeypatch, "bob")
    assert tag_tools.tag_list()["data"]["count"] == 0
    assert tag_tools.tag_attach(tid, "requirement", "REQ-1")["success"] is False
    _set_owner(monkeypatch, "alice")
    assert tag_tools.tag_list()["data"]["count"] == 1
