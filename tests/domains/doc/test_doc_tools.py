"""M3-04 golden 测试：doc 工具 CRUD 与 owner 隔离（A/B 互不可见）。"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from littledotmcp.db import Base
from littledotmcp.domains.doc.tools import (
    _current_owner,
    doc_delete,
    doc_list,
    doc_read,
    doc_save,
    doc_search,
)

OWNER_A = "owner-a"
OWNER_B = "owner-b"


@pytest.fixture
def schema(sqlite_tmp_engine) -> Iterator[None]:
    Base.metadata.create_all(sqlite_tmp_engine)
    yield
    Base.metadata.drop_all(sqlite_tmp_engine)


@pytest.fixture
def as_owner_a(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("littledotmcp.domains.doc.tools._current_owner", lambda: OWNER_A)


def _save_a(name: str = "笔记.md", content: str = "第一行\n第二行") -> str:
    result = doc_save(name=name, content=content)
    assert result["success"] is True, result["message"]
    return str(result["data"]["id"])


def test_save_read_roundtrip(schema: None, as_owner_a: None) -> None:
    doc_id = _save_a()
    read = doc_read(doc_id)
    assert read["success"] is True
    assert read["data"]["content"] == "第一行\n第二行"
    assert read["data"]["name"] == "笔记.md"
    assert read["data"]["mime"] == "text/markdown"


def test_save_requires_content_or_path(schema: None, as_owner_a: None) -> None:
    assert doc_save(name="x.txt")["success"] is False
    assert doc_save(name="x.txt", content="a", path="b")["success"] is False


def test_save_requires_name(schema: None, as_owner_a: None) -> None:
    assert doc_save(name="  ", content="a")["success"] is False


def test_save_from_local_path(schema: None, as_owner_a: None, tmp_path: Path) -> None:
    p = tmp_path / "src.md"
    p.write_text("# 外部文件", encoding="utf-8")
    result = doc_save(name="导入.md", path=str(p))
    assert result["success"] is True
    assert result["data"]["mime"] == "text/markdown"
    read = doc_read(result["data"]["id"])
    assert read["data"]["content"] == "# 外部文件"


def test_save_corrupted_path_still_stored(
    schema: None, as_owner_a: None, tmp_path: Path
) -> None:
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"%PDF-1.4 broken")
    result = doc_save(name="损坏.pdf", path=str(p))
    # 解析失败不阻断存档，按扩展名推断 mime
    assert result["success"] is True
    assert result["data"]["mime"] == "application/pdf"


def test_read_missing(schema: None, as_owner_a: None) -> None:
    result = doc_read(uuid.uuid4().hex)
    assert result["success"] is False


def test_read_truncated(schema: None, as_owner_a: None) -> None:
    doc_id = _save_a(content="x" * 5000)
    result = doc_read(doc_id, max_chars=100)
    assert result["success"] is True
    assert result["data"]["truncated"] is True
    assert result["data"]["total_chars"] == 5000
    assert len(result["data"]["content"]) == 100
    assert doc_read(doc_id, max_chars=0)["success"] is False


def test_search_by_name_and_mime(schema: None, as_owner_a: None) -> None:
    _save_a(name="需求说明.md")
    _save_a(name="架构设计.pdf", content="pdf 正文占位")
    by_name = doc_search(name="需求")
    assert by_name["success"] is True
    assert len(by_name["data"]["items"]) == 1
    assert by_name["data"]["items"][0]["name"] == "需求说明.md"
    by_mime = doc_search(mime="application/pdf")
    assert len(by_mime["data"]["items"]) == 1
    assert by_mime["data"]["items"][0]["name"] == "架构设计.pdf"


def test_list_paged(schema: None, as_owner_a: None) -> None:
    for i in range(5):
        _save_a(name=f"doc-{i}.md")
    total = doc_list()["data"]["total"]
    assert total == 5
    page = doc_list(limit=2, offset=1)
    assert len(page["data"]["items"]) == 2
    assert doc_list(limit=0)["success"] is False
    assert doc_list(offset=-1)["success"] is False


def test_delete(schema: None, as_owner_a: None) -> None:
    doc_id = _save_a()
    assert doc_delete(doc_id)["success"] is True
    assert doc_read(doc_id)["success"] is False
    assert doc_delete(doc_id)["success"] is False  # 二次删除报不存在
    assert doc_list()["data"]["total"] == 0


def test_owner_isolation_crud(schema: None, monkeypatch: pytest.MonkeyPatch) -> None:
    import littledotmcp.domains.doc.tools as tools

    def set_owner(owner: str) -> None:
        monkeypatch.setattr(tools, "_current_owner", lambda: owner)

    # A 保存
    set_owner(OWNER_A)
    doc_id = _save_a()
    # B 视角：read/search/delete 均不可见
    set_owner(OWNER_B)
    assert doc_read(doc_id)["success"] is False
    assert doc_search(name="笔记")["data"]["count"] == 0
    assert doc_list()["data"]["total"] == 0
    assert doc_delete(doc_id)["success"] is False
    # A 视角仍完整
    set_owner(OWNER_A)
    assert doc_read(doc_id)["success"] is True


def test_default_owner_is_local() -> None:
    # stdio 单人模式下未 monkeypatch 时归属固定 local
    assert _current_owner() == "local"
