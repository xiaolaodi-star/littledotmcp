"""M3-08 golden 测试：kb 工具 CRUD / 幂等 / owner 隔离。"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from littledotmcp.db import Base
from littledotmcp.domains.doc.tools import doc_save
from littledotmcp.domains.kb.tools import kb_delete, kb_ingest, kb_list, kb_search

OWNER_A = "owner-a"
OWNER_B = "owner-b"


@pytest.fixture
def schema(sqlite_tmp_engine) -> Iterator[None]:
    Base.metadata.create_all(sqlite_tmp_engine)
    yield
    Base.metadata.drop_all(sqlite_tmp_engine)


def _set_owner(monkeypatch: pytest.MonkeyPatch, owner: str) -> None:
    import littledotmcp.domains.doc.tools as doc_tools
    import littledotmcp.domains.kb.tools as kb_tools

    monkeypatch.setattr(doc_tools, "_current_owner", lambda: owner)
    monkeypatch.setattr(kb_tools, "_current_owner", lambda: owner)


def _save_and_ingest(
    owner: str,
    monkeypatch: pytest.MonkeyPatch,
    *,
    name: str = "知识库.md",
    content: str = "花园的月季春天开花。月季需要充足阳光和水分。",
) -> str:
    _set_owner(monkeypatch, owner)
    saved = doc_save(name=name, content=content)
    assert saved["success"] is True, saved["message"]
    ing = kb_ingest(str(saved["data"]["id"]))
    assert ing["success"] is True, ing["message"]
    return str(ing["data"]["kb_doc_id"])


def test_ingest_roundtrip(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = "花园的月季春天开花。月季需要充足阳光和水分。" * 80
    kb_doc_id = _save_and_ingest(OWNER_A, monkeypatch, content=content)
    listing = kb_list()
    assert listing["success"] is True
    assert listing["data"]["total"] == 1
    item = listing["data"]["items"][0]
    assert item["id"] == kb_doc_id
    assert item["chunk_count"] > 1
    assert item["status"] == "ready"
    assert item["title"] == "知识库.md"


def test_ingest_unknown_doc(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_owner(monkeypatch, OWNER_A)
    assert kb_ingest(uuid.uuid4().hex)["success"] is False


def test_ingest_empty_doc(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_owner(monkeypatch, OWNER_A)
    saved = doc_save(name="空白.txt", content="   ")
    assert saved["success"] is True
    assert kb_ingest(str(saved["data"]["id"]))["success"] is False


def test_ingest_idempotent(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_owner(monkeypatch, OWNER_A)
    saved = doc_save(name="知识库.md", content="内容A。内容B。" * 30)
    doc_id = str(saved["data"]["id"])
    r1 = kb_ingest(doc_id)
    assert r1["success"] is True
    r2 = kb_ingest(doc_id)
    assert r2["success"] is True
    # 同源文档重复录入 → 幂等重建，不新增
    assert kb_list()["data"]["total"] == 1
    assert r1["data"]["chunk_count"] == r2["data"]["chunk_count"]


def test_search_returns_source(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb_doc_id = _save_and_ingest(
        OWNER_A,
        monkeypatch,
        content="花园的月季春天开花。\n月季需要充足阳光和水分。",
    )
    res = kb_search("月季")
    assert res["success"] is True
    assert res["data"]["count"] >= 1
    item = res["data"]["items"][0]
    assert item["doc_id"] == kb_doc_id
    assert item["seq"] >= 0
    assert "月季" in item["content"]
    assert item["title"] == "知识库.md"
    assert item["score"] > 0


def test_search_validation(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _save_and_ingest(OWNER_A, monkeypatch)
    assert kb_search("  ")["success"] is False
    assert kb_search("x", top_k=0)["success"] is False
    assert kb_search("x", top_k=21)["success"] is False


def test_list_paged(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i in range(3):
        _save_and_ingest(OWNER_A, monkeypatch, name=f"知识库{i}.md")
    assert kb_list()["data"]["total"] == 3
    assert len(kb_list(limit=2, offset=1)["data"]["items"]) == 2
    assert kb_list(limit=0)["success"] is False
    assert kb_list(offset=-1)["success"] is False


def test_delete(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb_doc_id = _save_and_ingest(OWNER_A, monkeypatch, content="可删除的知识库内容。")
    assert kb_delete(kb_doc_id)["success"] is True
    assert kb_list()["data"]["total"] == 0
    assert kb_search("知识库")["data"]["count"] == 0
    assert kb_delete(kb_doc_id)["success"] is False  # 二次删除报不存在


def test_owner_isolation(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb_doc_id = _save_and_ingest(OWNER_A, monkeypatch, content="私人领地的机密方案。")
    # B 视角：list/search/delete 均不可见（元数据 + 向量双层隔离）
    _set_owner(monkeypatch, OWNER_B)
    assert kb_list()["data"]["total"] == 0
    assert kb_search("机密")["data"]["count"] == 0
    assert kb_delete(kb_doc_id)["success"] is False
    # A 视角仍完整
    _set_owner(monkeypatch, OWNER_A)
    assert kb_list()["data"]["total"] == 1
