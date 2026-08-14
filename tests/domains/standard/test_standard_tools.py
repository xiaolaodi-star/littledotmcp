"""M5-04 standard 工具测试：增查/搜索/删除/重复拒绝/owner 隔离。"""

from __future__ import annotations

import pytest

from littledotmcp.db import Base
from littledotmcp.domains.standard import tools as std_tools

CONTENT = "# 命名规范\n\n- 表名小写蛇形。\n- 主键统一 id。"


@pytest.fixture
def schema(sqlite_tmp_engine) -> None:
    Base.metadata.create_all(sqlite_tmp_engine)


def _set_owner(monkeypatch: pytest.MonkeyPatch, owner: str) -> None:
    monkeypatch.setattr(std_tools, "_current_owner", lambda: owner)


def test_add_get_remove(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_owner(monkeypatch, "alice")
    r = std_tools.standard_add("命名规范", CONTENT, category="naming")
    assert r["success"] is True, r
    assert r["data"]["category"] == "naming"

    got = std_tools.standard_get("命名规范")
    assert got["success"] is True
    assert "小写蛇形" in got["data"]["content"]

    rem = std_tools.standard_remove("命名规范")
    assert rem["success"] is True
    assert std_tools.standard_get("命名规范")["success"] is False


def test_duplicate_rejected(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_owner(monkeypatch, "alice")
    std_tools.standard_add("命名规范", CONTENT)
    dup = std_tools.standard_add("命名规范", "另一份")
    assert dup["success"] is False
    assert "已存在" in dup["message"]


def test_required_fields(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_owner(monkeypatch, "alice")
    assert std_tools.standard_add("", CONTENT)["success"] is False
    assert std_tools.standard_add("名", "")["success"] is False
    assert std_tools.standard_get("")["success"] is False


def test_search_keyword_and_category(
    isolated_settings, schema, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_owner(monkeypatch, "alice")
    std_tools.standard_add("命名规范", CONTENT, category="naming")
    std_tools.standard_add("SQL 规范", "# SQL\n\n- 禁止 SELECT *。", category="sql")

    by_kw = std_tools.standard_search(keyword="SELECT")
    assert by_kw["data"]["count"] == 1
    assert by_kw["data"]["items"][0]["name"] == "SQL 规范"

    by_cat = std_tools.standard_search(category="naming")
    assert by_cat["data"]["count"] == 1

    none = std_tools.standard_search(keyword="不存在词")
    assert none["data"]["count"] == 0


def test_owner_isolation(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_owner(monkeypatch, "alice")
    std_tools.standard_add("命名规范", CONTENT)
    _set_owner(monkeypatch, "bob")
    assert std_tools.standard_search()["data"]["count"] == 0
    assert std_tools.standard_get("命名规范")["success"] is False
    _set_owner(monkeypatch, "alice")
    assert std_tools.standard_search()["data"]["count"] == 1
