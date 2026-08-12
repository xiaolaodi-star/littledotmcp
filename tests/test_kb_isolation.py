"""M3-09 golden 测试：kb 域 A/B 双层隔离（向量 + 元数据）。

强制项：用户隔离测试（规约-04）。验证向量库层与元数据层对跨用户数据
互不可见，且 BM25 关键词增强在隔离范围内正常工作。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from littledotmcp.config import get_settings
from littledotmcp.db import Base
from littledotmcp.db import engine as db_engine
from littledotmcp.domains.doc.tools import doc_save
from littledotmcp.domains.kb.storage import KbChunkRepository, KbDocumentRepository
from littledotmcp.domains.kb.tools import kb_ingest, kb_search
from littledotmcp.rag.vector_store import ChromaVectorStore

OWNER_A = "owner-a"
OWNER_B = "owner-b"
_DIM = 32


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


def _ingest(
    owner: str,
    monkeypatch: pytest.MonkeyPatch,
    *,
    name: str,
    content: str,
) -> str:
    _set_owner(monkeypatch, owner)
    saved = doc_save(name=name, content=content)
    assert saved["success"] is True, saved["message"]
    res = kb_ingest(str(saved["data"]["id"]))
    assert res["success"] is True, res["message"]
    return str(res["data"]["kb_doc_id"])


def _vector_count(owner: str) -> int:
    return ChromaVectorStore(get_settings().vector_dir, dim=_DIM).count(owner)


def test_vector_and_metadata_double_isolation(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    a_id = _ingest(OWNER_A, monkeypatch, name="A方案.md", content="A 的机密方案内容。")
    b_id = _ingest(OWNER_B, monkeypatch, name="B花园.md", content="B 的花园种植笔记。")

    # 向量层：按 owner 物理隔离
    assert _vector_count(OWNER_A) >= 1
    assert _vector_count(OWNER_B) >= 1

    # 检索层：A 搜不到 B 的内容（含 BM25 与向量）
    _set_owner(monkeypatch, OWNER_A)
    res_a = kb_search("花园")
    assert res_a["success"] is True
    assert all(item["doc_id"] == a_id for item in res_a["data"]["items"])

    _set_owner(monkeypatch, OWNER_B)
    res_b = kb_search("机密")
    assert res_b["success"] is True
    assert all(item["doc_id"] == b_id for item in res_b["data"]["items"])


def test_metadata_repository_scope(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    a_id = _ingest(OWNER_A, monkeypatch, name="A.md", content="A 的内容。")
    b_id = _ingest(OWNER_B, monkeypatch, name="B.md", content="B 的内容。")

    with db_engine.SessionLocal() as session:
        docs_a = KbDocumentRepository(session).list_by_owner(OWNER_A)
        chunks_a = KbChunkRepository(session).list_all_by_owner(OWNER_A)
        assert all(d.id == a_id for d in docs_a)
        assert all(c.owner_id == OWNER_A for c in chunks_a)
        assert all(c.doc_id == a_id for c in chunks_a)
        chunks_b = KbChunkRepository(session).list_all_by_owner(OWNER_B)
        assert all(c.doc_id == b_id for c in chunks_b)


def test_bm25_enhances_keyword_match(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    a_id = _ingest(
        OWNER_A,
        monkeypatch,
        name="月季.md",
        content="月季。月季。月季。月季需要充足阳光。",
    )
    _ingest(OWNER_B, monkeypatch, name="牡丹.md", content="牡丹喜肥。牡丹怕涝。")

    _set_owner(monkeypatch, OWNER_A)
    res = kb_search("月季")
    assert res["success"] is True
    assert res["data"]["count"] >= 1
    top = res["data"]["items"][0]
    assert top["doc_id"] == a_id
