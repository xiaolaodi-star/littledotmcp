"""M5-01/02 mindmap 工具测试：CRUD、非法输入、导出、from_doc、owner 隔离。"""

from __future__ import annotations

import pytest

from littledotmcp.db import Base
from littledotmcp.domains.mindmap import from_doc
from littledotmcp.domains.mindmap import tools as mm_tools

VALID = "mindmap\n  root((主题))\n    子1\n    子2"


@pytest.fixture
def schema(sqlite_tmp_engine) -> None:
    Base.metadata.create_all(sqlite_tmp_engine)


def _set_owner(monkeypatch: pytest.MonkeyPatch, owner: str) -> None:
    monkeypatch.setattr(mm_tools, "_current_owner", lambda: owner)


def test_create_get_update_remove(
    isolated_settings, schema, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_owner(monkeypatch, "alice")
    r = mm_tools.mindmap_create("主题", VALID)
    assert r["success"] is True, r
    assert r["data"]["opml"].startswith("<?xml")
    assert "<outline" in r["data"]["opml"]

    got = mm_tools.mindmap_get("主题")
    assert got["success"] is True
    assert "子1" in got["data"]["mermaid"]

    updated = mm_tools.mindmap_update("主题", "mindmap\n  root((新主题))\n    新子")
    assert updated["success"] is True
    assert "新主题" in updated["data"]["mermaid"]
    # opml 同步重写
    assert "新子" in updated["data"]["opml"]

    rem = mm_tools.mindmap_remove("主题")
    assert rem["success"] is True
    assert mm_tools.mindmap_get("主题")["success"] is False


def test_create_duplicate_rejected(
    isolated_settings, schema, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_owner(monkeypatch, "alice")
    assert mm_tools.mindmap_create("主题", VALID)["success"] is True
    dup = mm_tools.mindmap_create("主题", VALID)
    assert dup["success"] is False
    assert "已存在" in dup["message"]


def test_invalid_mermaid_rejected(
    isolated_settings, schema, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_owner(monkeypatch, "alice")
    bad = mm_tools.mindmap_create("坏图", "graph TD\n  a --> b")
    assert bad["success"] is False


def test_export_returns_opml(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_owner(monkeypatch, "alice")
    mm_tools.mindmap_create("主题", VALID)
    ex = mm_tools.mindmap_export("主题")
    assert ex["success"] is True
    assert ex["data"]["format"] == "opml"
    assert ex["data"]["content"].startswith("<?xml")

    bad_fmt = mm_tools.mindmap_export("主题", format="pdf")
    assert bad_fmt["success"] is False


def test_from_doc_degrade_and_persist(
    isolated_settings, schema, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_owner(monkeypatch, "alice")
    isolated_settings.llm_api_key = ""
    monkeypatch.setattr(from_doc, "get_settings", lambda: isolated_settings)
    r = mm_tools.mindmap_from_doc("文档导图", "# 一章\n## 1.1\n# 二章")
    assert r["success"] is True, r
    assert "一章" in r["data"]["mermaid"]
    assert "<outline" in r["data"]["opml"]
    # 再次调用更新
    r2 = mm_tools.mindmap_from_doc("文档导图", "# 新章")
    assert r2["success"] is True
    assert "新章" in r2["data"]["mermaid"]


def test_owner_isolation(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_owner(monkeypatch, "alice")
    mm_tools.mindmap_create("主题", VALID)
    _set_owner(monkeypatch, "bob")
    assert mm_tools.mindmap_list()["data"]["count"] == 0
    assert mm_tools.mindmap_get("主题")["success"] is False
    _set_owner(monkeypatch, "alice")
    assert mm_tools.mindmap_list()["data"]["count"] == 1
