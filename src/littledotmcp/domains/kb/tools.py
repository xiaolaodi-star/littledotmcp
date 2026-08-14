"""kb 域 MCP 工具（M3-08）：kb_ingest / kb_search / kb_list / kb_delete / kb_ask。

- 向量化经 get_embedder() 工厂按 EMBEDDING_PROVIDER 切换（M7）：
  fake（离线确定性）/ openai（OpenAI 兼容端点）/ ollama（本地 Ollama）；
- kb_ask（M7）：检索上下文经 LLM 生成带来源引用的回答，无 LLM Key 时降级；
- 元数据落 kb_documents/kb_chunks（OwnerScopedRepository 强制 owner 隔离），
  向量落 SqliteVecVectorStore（owner_id/doc_id 强制注入，SQL 层 owner 过滤）。
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
from ...rag.embedding import Embedder, get_embedder
from ...rag.parsers import ParseError, parse_document
from ...rag.vector_store import SqliteVecVectorStore
from ...server import mcp
from .ranking import bm25_scores
from .storage import KbChunkRepository, KbDocumentRepository

logger = get_logger(__name__)

# stdio 单人模式固定归属；http 多用户模式（M6）按鉴权上下文解析
_DEFAULT_OWNER = "local"

# 列表分页上限 / 检索上限
_MAX_LIMIT = 100
_MAX_TOP_K = 20

# 融合权重：向量 0.7 + BM25 0.3
_VEC_WEIGHT = 0.7
_BM25_WEIGHT = 0.3

# kb_ask 注入 LLM 的上下文上限（防超长请求）
_ASK_CONTEXT_CHARS = 8000


def _current_owner() -> str:
    """返回当前调用方 owner_id（stdio 单人固定 local）。"""
    return _DEFAULT_OWNER


def _embedder() -> Embedder:
    """延迟创建向量化器（按 EMBEDDING_PROVIDER 工厂返回）。"""
    return get_embedder()


def _vector_store(dim: int | None = None) -> SqliteVecVectorStore:
    """延迟创建向量库（随配置实时，便于测试重定向）。

    dim 不传时用配置 embedding_dim；调用方应尽量传 embedder 的实际维度，
    保证入库/检索与向量库维度一致。
    """
    if dim is None:
        dim = get_settings().embedding_dim
    return SqliteVecVectorStore(get_settings().vector_dir, dim=dim)


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
            emb = _embedder()
            vectors: list[list[float]] = emb.embed([c.content for c in chunks])

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
            _vector_store(dim=emb.dim).upsert(owner, kb_doc.id, vector_items)
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
                "dim": emb.dim,
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
        emb = _embedder()
        query_vec = emb.embed([query])[0]
        vec_hits = _vector_store(dim=emb.dim).search(owner, query_vec, top_k * 2)

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


def _call_llm_answer(query: str, items: list[dict]) -> str | None:
    """调用 OpenAI 兼容 LLM 生成带来源引用的回答；无 Key/失败返回 None。"""
    settings = get_settings()
    if not settings.llm_api_key:
        return None
    from openai import OpenAI

    context = "\n\n".join(
        f"[{i + 1}] 来源：{item['title']}#{item['seq']}\n{item['content']}"
        for i, item in enumerate(items)
    )
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url or None)
    resp = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是知识库问答助手。仅依据提供的参考资料回答问题，"
                    "并用【来源：标题#序号】标注引用出处；资料不足时如实说明，不要编造。"
                ),
            },
            {
                "role": "user",
                "content": f"问题：{query}\n\n参考资料：\n{context[:_ASK_CONTEXT_CHARS]}",
            },
        ],
        temperature=0.2,
    )
    content = resp.choices[0].message.content
    return content.strip() if content else None


@mcp.tool(
    name="kb_ask",
    description=(
        "知识库问答：先混合检索 Top-K 相关片段，再经 LLM 生成带【来源：标题#序号】"
        "引用的回答（未配置 LLM_API_KEY 时降级返回检索片段）。"
    ),
)
def kb_ask(query: str, top_k: int = 5) -> dict:
    """基于知识库的生成式问答（检索 → LLM 引用回答，无 Key 降级片段）。"""
    search_result = kb_search(query=query, top_k=top_k)
    if not search_result["success"]:
        return search_result
    items = search_result["data"]["items"]
    if not items:
        return ok(data={"answer": "", "sources": [], "degraded": False}, message="知识库无相关内容")
    try:
        answer = _call_llm_answer(query, items)
    except Exception as exc:
        logger.warning("kb_ask LLM 调用失败，降级返回检索片段：%s", exc)
        answer = None
    if not answer:
        return ok(
            data={
                "answer": "（未配置 LLM_API_KEY 或调用失败，以下为检索片段，请配置后重试）",
                "sources": items,
                "degraded": True,
            },
            message="LLM 不可用，已降级返回检索片段",
        )
    return ok(
        data={"answer": answer, "sources": items, "degraded": False},
        message="生成回答完成",
    )
