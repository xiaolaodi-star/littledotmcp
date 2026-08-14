"""M7 golden 测试：真实 Embedder 缓存命中 / kb_ask 引用 / 无 Key 降级 / 维度对齐 / 隔离。"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from littledotmcp.db import Base
from littledotmcp.domains.doc.tools import doc_save
from littledotmcp.domains.kb import tools as kb_tools
from littledotmcp.domains.kb.tools import kb_ask, kb_ingest
from littledotmcp.rag.embedding import (
    EmbeddingCache,
    FakeEmbedder,
    OpenAICompatEmbedder,
    get_embedder,
)
from littledotmcp.config import get_settings

OWNER_A = "owner-a"
OWNER_B = "owner-b"


@pytest.fixture
def schema(sqlite_tmp_engine) -> Iterator[None]:
    Base.metadata.create_all(sqlite_tmp_engine)
    yield
    Base.metadata.drop_all(sqlite_tmp_engine)


def _set_owner(monkeypatch: pytest.MonkeyPatch, owner: str) -> None:
    import littledotmcp.domains.doc.tools as doc_tools

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


# ---------------------------------------------------------------- EmbeddingCache


def test_embedding_cache_persist(tmp_path) -> None:
    p = tmp_path / "c.jsonl"
    c = EmbeddingCache(p, dim=4)
    key = c.cache_key("m", "你好")
    c.put(key, [1.0, 2.0, 3.0, 4.0])
    c2 = EmbeddingCache(p, dim=4)
    assert c2.get(key) == [1.0, 2.0, 3.0, 4.0]
    assert c2.hits == 1
    assert c2.misses == 0


def test_embedding_cache_key_differs_by_dim() -> None:
    c1 = EmbeddingCache("x.jsonl", dim=4)
    c2 = EmbeddingCache("x.jsonl", dim=8)
    assert c1.cache_key("m", "t") != c2.cache_key("m", "t")


def test_openai_embedder_cache_hit(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """首次网络调用（mock），二次命中磁盘缓存不再请求。"""
    cache = EmbeddingCache(tmp_path / "c.jsonl", dim=4)
    emb = OpenAICompatEmbedder(
        model="test-model", api_key="sk-test", base_url="http://127.0.0.1:9/v1", dim=4, cache=cache
    )
    calls = {"n": 0}

    def fake_create(model: str, input: list[str]):  # noqa: A002
        calls["n"] += 1
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3, 0.4]) for _ in input])

    monkeypatch.setattr(emb._client.embeddings, "create", fake_create)
    v1 = emb.embed(["你好"])[0]
    v2 = emb.embed(["你好"])[0]
    assert v1 == [0.1, 0.2, 0.3, 0.4]
    assert v2 == v1
    assert calls["n"] == 1  # 第二次命中缓存，未触发网络


# ---------------------------------------------------------------- get_embedder 工厂


def test_get_embedder_default_fake(isolated_settings) -> None:
    e = get_embedder()
    assert isinstance(e, FakeEmbedder)
    assert e.dim == 32


def test_get_embedder_openai_requires_key(
    isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_API_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="EMBEDDING_API_KEY"):
        get_embedder()


# ---------------------------------------------------------------- 维度对齐


def test_dim_alignment(
    isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """embedding_dim 配置贯通 get_embedder 与 _vector_store。"""
    monkeypatch.setenv("EMBEDDING_DIM", "64")
    get_settings.cache_clear()
    e = get_embedder()
    assert e.dim == 64
    vs = kb_tools._vector_store()
    assert vs.dim == 64


# ---------------------------------------------------------------- kb_ask


def test_kb_ask_with_reference(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _save_and_ingest(OWNER_A, monkeypatch, content="花园的月季春天开花。月季需要充足阳光和水分。")
    monkeypatch.setattr(
        kb_tools,
        "_call_llm_answer",
        lambda q, items: "月季春天开花【来源：知识库.md#0】",
    )
    res = kb_ask("月季")
    assert res["success"] is True
    assert res["data"]["degraded"] is False
    assert "【来源：知识库.md#0】" in res["data"]["answer"]
    assert res["data"]["sources"]
    assert res["data"]["sources"][0]["title"] == "知识库.md"


def test_kb_ask_no_llm_key_degrade(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    _save_and_ingest(OWNER_A, monkeypatch, content="花园的月季春天开花。月季需要充足阳光和水分。")
    res = kb_ask("月季")
    assert res["success"] is True
    assert res["data"]["degraded"] is True  # 降级返回检索片段
    assert res["data"]["sources"]


def test_kb_ask_llm_error_degrade(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _save_and_ingest(OWNER_A, monkeypatch, content="花园的月季春天开花。")

    def boom(q: str, items: list[dict]) -> str:
        raise RuntimeError("network down")

    monkeypatch.setattr(kb_tools, "_call_llm_answer", boom)
    res = kb_ask("月季")
    assert res["success"] is True
    assert res["data"]["degraded"] is True


def test_kb_ask_empty_kb(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_owner(monkeypatch, OWNER_A)
    res = kb_ask("月季")
    assert res["success"] is True
    assert res["data"]["sources"] == []


def test_kb_ask_owner_isolation(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _save_and_ingest(OWNER_A, monkeypatch, content="私人领地的机密方案。")
    _set_owner(monkeypatch, OWNER_B)
    res = kb_ask("机密")
    assert res["success"] is True
    assert res["data"]["sources"] == []  # B 视角无任何片段


def test_kb_ask_unknown_owner_doc_invisible(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _save_and_ingest(OWNER_A, monkeypatch, content="绝密：核弹发射密码。")
    kb_id = kb_tools.kb_list()["data"]["items"][0]["id"]
    _set_owner(monkeypatch, OWNER_B)
    assert kb_tools.kb_delete(kb_id)["success"] is False  # B 不能删 A 的文档


def test_ingest_reports_real_dim(
    schema: None, isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """kb_ingest 返回实际 embedder 维度（fake=32）。"""
    _set_owner(monkeypatch, OWNER_A)
    saved = doc_save(name="知识库.md", content="花园的月季。")
    ing = kb_ingest(str(saved["data"]["id"]))
    assert ing["data"]["dim"] == 32
