"""M3-07 golden 测试：ChromaVectorStore 持久化 / owner 过滤 / 删除。"""

from __future__ import annotations

from pathlib import Path

import pytest

from littledotmcp.common.errors import ValidationError
from littledotmcp.rag.embedding import FakeEmbedder
from littledotmcp.rag.vector_store import ChromaVectorStore


def _vec(text: str) -> list[float]:
    return FakeEmbedder(dim=8).embed([text])[0]


def test_upsert_and_search(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "vectors", dim=8)
    v = _vec("知识库内容")
    store.upsert("alice", "doc-1", [("c1", v)])
    hits = store.search("alice", v, top_k=3)
    assert len(hits) == 1
    assert hits[0][0] == "c1"
    assert hits[0][1] > 0.999  # 相同向量余弦≈1


def test_search_returns_top_k_sorted(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "vectors", dim=8)
    va = _vec("aaa")
    vb = _vec("bbb")
    store.upsert("alice", "doc-1", [("c1", va), ("c2", vb)])
    hits = store.search("alice", va, top_k=2)
    ids = [cid for cid, _ in hits]
    scores = [s for _, s in hits]
    assert ids[0] == "c1"
    assert scores == sorted(scores, reverse=True)


def test_owner_isolation(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "vectors", dim=8)
    v = _vec("私人数据")
    store.upsert("alice", "doc-1", [("c1", v)])
    assert store.search("bob", v, top_k=3) == []
    assert store.count("alice") == 1
    assert store.count("bob") == 0
    # alice 仍可见
    assert len(store.search("alice", v, top_k=3)) == 1


def test_delete_by_doc(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "vectors", dim=8)
    v = _vec("内容")
    store.upsert("alice", "doc-1", [("c1", v), ("c2", v)])
    assert store.count("alice") == 2
    store.delete_by_doc("alice", "doc-1")
    assert store.count("alice") == 0
    assert store.search("alice", v, top_k=3) == []


def test_persistence_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "vectors"
    v = _vec("持久化内容")
    store1 = ChromaVectorStore(path, dim=8)
    store1.upsert("alice", "doc-1", [("c1", v)])
    # 模拟重启：同一目录新建实例
    store2 = ChromaVectorStore(path, dim=8)
    hits = store2.search("alice", v, top_k=3)
    assert len(hits) == 1
    assert hits[0][0] == "c1"


def test_dim_mismatch_validation(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "vectors", dim=8)
    with pytest.raises(ValidationError):
        store.upsert("alice", "doc-1", [("c1", [0.0, 0.0])])  # 维度不符
    with pytest.raises(ValidationError):
        store.search("alice", [0.0, 0.0], top_k=1)
    with pytest.raises(ValidationError):
        store.search("alice", _vec("x"), top_k=0)
