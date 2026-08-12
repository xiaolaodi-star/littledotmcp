"""kb 域 MCP 工具（M3-08）：kb_ingest / kb_search / kb_list / kb_delete。

- kb_ask（LLM 生成回答）与真实 Embedding 后端（OpenAI/Ollama）按用户决策
  剥离至 M7 里程碑，本文件不暴露半成品接口；
- 向量化本次用确定性 FakeEmbedder（离线可验收），M7 切换为真实 Embedder 即可热插拔；
- 元数据落 kb_documents/kb_chunks（OwnerScopedRepository 强制 owner 隔离），
  向量落 ChromaVectorStore（metadata 强制注入 owner_id）。
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from ...common.errors import NotFoundError, ValidationError
from ...common.logging import get_logger
from ...common.result import fail, ok
from ...config import get_settings
from ...db import engine as db_engine
from ...db.models import KbChunk, KbDocument
from ...domains.doc.storage import LocalDocStorage
from ...domains.doc.tools import DocumentRepository
from ...rag.chunker import chunk_text
from ...rag.embedding import FakeEmbedder
from ...rag.parsers import ParseError, parse_document
from ...rag.vector_store import ChromaVectorStore
from ...server import mcp
from .ranking import bm25_scores
from .storage import KbChunkRepository, KbDocumentRepository

logger = get_logger(__name__)

# stdio 单人模式固定归属；http 多用户模式（M6）按鉴权上下文解析
_DEFAULT_OWNER = "local"

# 列表分页上限 / 检索上限 / FakeEmbedder 维度
_MAX_LIMIT = 100
_MAX_TOP_K = 20
_DIM = 32

# 融合权重：向量 0.7 + BM25 0.3
_VEC_WEIGHT = 0.7
_BM25_WEIGHT = 0.3


def _current_owner() -> str:
    """返回当前调用方 owner_id（stdio 单人固定 local）。"""
    return _DEFAULT_OWNER


def _embedder() -> FakeEmbedder:
    """延迟创建向量化器（M7 切换真实 Embedder）。"""
    return FakeEmbedder(dim=_DIM)


def _vector_store() -> ChromaVectorStore:
    """延迟创建向量库（随配置实时，便于测试重定向）。"""
    return ChromaVectorStore(get_settings().vector_dir, dim=_DIM)


def _storage() -> LocalDocStorage:
    return LocalDocStorage(get_settings().storage_root)


def _extract_doc_text(owner: str, name: str, storage_key: str) -> str:
    """读取文档原文并解析为纯文本（二进制格式经临时文件桥接）。"""
    raw = _storage().load(owner, storage_key)
    suffix = Path(name).suffix or ".txt"
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / ("kb" + suffix)
        tmp.write_bytes(raw)
        return parse_document(tmp).text


def _kb_doc_dict(doc: KbDocument) -> dict:
    return {
        "id": doc.id,
        "title": doc.title,
        "source_type": doc.source_type,
        "chunk_count": doc.chunk_count,
        "status": doc.status,
        "created_at": doc.created_at.isoformat(),
    }


def _delete_kb_doc(session, owner: str, kb_doc_id: str) -> None:
    """删除知识库文档：chunks（flush）→ 向量 → kb_document，保持事务一致。"""
    KbChunkRepository(session).delete_by_doc(owner, kb_doc_id)
    _vector_store().delete_by_doc(owner, kb_doc_id)
    KbDocumentRepository(session).delete_by_owner(owner, kb_doc_id)
    session.flush()


@mcp.tool(
    name="kb_ingest",
    description=(
        "将已保存文档（doc_id，来自 doc_save）解析、切块、向量化后录入知识库；"
        "同源文档重复录入将幂等重建。返回知识库文档 id 与切块数。"
    ),
)
def kb_ingest(doc_id: str) -> dict:
    """录入文档到知识库（解析→切块→embed→元数据+向量落库）。"""
    owner = _current_owner()
    result_id = ""
    result_title = ""
    result_chunks = 0
    try:
        with db_engine.SessionLocal() as session:
            doc = DocumentRepository(session).get_by_owner(owner, doc_id)
            if doc is None:
                return fail(message="文档不存在")
            text = _extract_doc_text(owner, doc.name, doc.storage_key)
            chunks = chunk_text(text)
            if not chunks:
                return fail(message="文档内容为空，无法切块")
            vectors: list[list[float]] = _embedder().embed([c.content for c in chunks])

            kb_repo = KbDocumentRepository(session)
            old = kb_repo.get_by_storage_key(owner, doc.storage_key)
            if old is not None:
                _delete_kb_doc(session, owner, old.id)

            kb_doc = KbDocument(
                id=uuid.uuid4().hex,
                owner_id=owner,
                title=doc.name,
                source_type="local",
                storage_key=doc.storage_key,
                chunk_count=len(chunks),
                status="ready",
            )
            kb_repo.add(kb_doc)
            vector_items: list[tuple[str, list[float]]] = []
            for seq, (ch, vec) in enumerate(zip(chunks, vectors, strict=True)):
                chunk_id = uuid.uuid4().hex
                session.add(
                    KbChunk(
                        id=chunk_id,
                        owner_id=owner,
                        doc_id=kb_doc.id,
                        seq=seq,
                        content=ch.content,
                        embedding_id=chunk_id,
                    )
                )
                vector_items.append((chunk_id, vec))
            session.flush()
            # 向量为外部存储，独立于 SQLite 事务；失败可整体重跑（幂等）
            _vector_store().upsert(owner, kb_doc.id, vector_items)
            session.commit()
            result_id = kb_doc.id
            result_title = kb_doc.title
            result_chunks = len(chunks)
            logger.info("kb_ingest 完成 doc_id=%s chunks=%d", doc.id, result_chunks)
        return ok(
            data={
                "kb_doc_id": result_id,
                "title": result_title,
                "chunk_count": result_chunks,
                "dim": _DIM,
            },
            message="知识库录入成功",
        )
    except ParseError as exc:
        return fail(message=f"文档解析失败：{exc.message}")
    except NotFoundError as exc:
        return fail(message=exc.message)
    except ValidationError as exc:
        return fail(message=exc.message)
    except Exception as exc:
        logger.exception("kb_ingest 未预期错误")
        return fail(message=f"录入失败：{exc}")


@mcp.tool(
    name="kb_search",
    description=(
        "知识库混合检索：向量 Top-K 与关键词 BM25 融合，返回带来源引用的分块"
        "（doc_id/title/seq/content/score）。仅检索当前用户可见范围。"
    ),
)
def kb_search(query: str, top_k: int = 5) -> dict:
    """混合检索知识库（向量 + BM25，跨用户不可见）。"""
    owner = _current_owner()
    try:
        if not query.strip():
            return fail(message="查询内容必填")
        if not 1 <= top_k <= _MAX_TOP_K:
            return fail(message=f"top_k 需在 1~{_MAX_TOP_K} 之间")
        query_vec = _embedder().embed([query])[0]
        vec_hits = _vector_store().search(owner, query_vec, top_k * 2)

        with db_engine.SessionLocal() as session:
            chunk_repo = KbChunkRepository(session)
            chunks = chunk_repo.list_all_by_owner(owner)
            docs = {d.id: d for d in KbDocumentRepository(session).list_by_owner(owner)}
        if not chunks:
            return ok(data={"items": [], "count": 0}, message="知识库为空")

        idx_of = {c.id: i for i, c in enumerate(chunks)}
        texts = [c.content for c in chunks]
        bm25 = bm25_scores(query, texts)
        # 候选集 = 向量 Top-K ∪ BM25 Top-K
        bm25_top = sorted(range(len(bm25)), key=lambda i: bm25[i], reverse=True)[: top_k * 2]
        candidates = {cid for cid, _ in vec_hits} | {chunks[i].id for i in bm25_top}

        vec_map = dict(vec_hits)
        vec_max = max(vec_map.values(), default=0.0) or 1.0
        bm25_max = max(bm25) or 1.0
        results: list[tuple[float, KbChunk]] = []
        for cid in candidates:
            chunk = chunks[idx_of[cid]]
            norm_vec = vec_map.get(cid, 0.0) / vec_max
            norm_bm25 = bm25[idx_of[cid]] / bm25_max
            score = _VEC_WEIGHT * norm_vec + _BM25_WEIGHT * norm_bm25
            results.append((score, chunk))
        results.sort(key=lambda x: x[0], reverse=True)

        items = []
        for score, chunk in results[:top_k]:
            doc = docs.get(chunk.doc_id)
            items.append(
                {
                    "chunk_id": chunk.id,
                    "doc_id": chunk.doc_id,
                    "title": doc.title if doc else "",
                    "seq": chunk.seq,
                    "content": chunk.content,
                    "score": round(score, 4),
                }
            )
        return ok(data={"items": items, "count": len(items)}, message=f"命中 {len(items)} 条")
    except ValidationError as exc:
        return fail(message=exc.message)
    except Exception as exc:
        logger.exception("kb_search 未预期错误")
        return fail(message=f"检索失败：{exc}")


@mcp.tool(
    name="kb_list",
    description="分页列出当前用户知识库文档（含切块数/状态，时间倒序）。",
)
def kb_list(limit: int = 20, offset: int = 0) -> dict:
    """列出知识库文档。"""
    owner = _current_owner()
    try:
        if not 1 <= limit <= _MAX_LIMIT:
            return fail(message=f"limit 需在 1~{_MAX_LIMIT} 之间")
        if offset < 0:
            return fail(message="offset 不能为负")
        with db_engine.SessionLocal() as session:
            repo = KbDocumentRepository(session)
            docs = repo.list_by_owner(owner)
            total = len(docs)
            docs.sort(key=lambda d: d.created_at, reverse=True)
            page = docs[offset : offset + limit]
        return ok(
            data={"items": [_kb_doc_dict(d) for d in page], "count": len(page), "total": total},
            message=f"共 {total} 条",
        )
    except Exception as exc:
        logger.exception("kb_list 未预期错误")
        return fail(message=f"列出失败：{exc}")


@mcp.tool(
    name="kb_delete",
    description="删除知识库文档（元数据 + 向量同时删除，跨用户越权访问被拒绝）。",
)
def kb_delete(kb_doc_id: str) -> dict:
    """删除知识库文档（元数据 + 向量事务一致）。"""
    owner = _current_owner()
    try:
        with db_engine.SessionLocal() as session:
            doc = KbDocumentRepository(session).get_by_owner(owner, kb_doc_id)
            if doc is None:
                return fail(message="知识库文档不存在")
            _delete_kb_doc(session, owner, kb_doc_id)
            session.commit()
            logger.info("kb_delete 完成 id=%s title=%s", kb_doc_id, doc.title)
        return ok(data={"id": kb_doc_id}, message="删除成功")
    except NotFoundError as exc:
        return fail(message=exc.message)
    except ValidationError as exc:
        return fail(message=exc.message)
    except Exception as exc:
        logger.exception("kb_delete 未预期错误")
        return fail(message=f"删除失败：{exc}")
