"""M3-06 golden 测试：FakeEmbedder 确定性 + 缓存命中。"""

from __future__ import annotations

import pytest

from littledotmcp.rag.embedding import FakeEmbedder


def test_dim_and_norm() -> None:
    e = FakeEmbedder(dim=16)
    vecs = e.embed(["a", "b"])
    assert len(vecs) == 2
    assert all(len(v) == 16 for v in vecs)
    for v in vecs:
        norm = sum(x * x for x in v)
        assert abs(norm - 1.0) < 1e-6  # L2 归一化


def test_invalid_dim() -> None:
    with pytest.raises(ValueError):
        FakeEmbedder(dim=0)


def test_deterministic_same_text() -> None:
    e = FakeEmbedder()
    assert e.embed(["你好世界"]) == e.embed(["你好世界"])


def test_different_text_different_vector() -> None:
    e = FakeEmbedder()
    assert e.embed(["你好"])[0] != e.embed(["再见"])[0]


def test_cache_hit_and_miss_count() -> None:
    e = FakeEmbedder()
    e.embed(["a", "b", "a", "c", "b"])
    assert e.misses == 3
    assert e.hits == 2
    e.embed(["a"])
    assert e.hits == 3
    assert e.misses == 3
