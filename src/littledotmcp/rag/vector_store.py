"""M3-07 VectorStore 抽象与 ChromaDB 持久化实现。

- VectorStore：向量库抽象（upsert/search/delete_by_doc），接口可切换
  sqlite-vec / pgvector 等后端；
- ChromaVectorStore：基于 chromadb.PersistentClient 的本地持久化；
  - metadata 强制注入 owner_id/doc_id，调用方不可覆盖（owner 隔离硬约束）；
  - 检索必须带 where={"owner_id": ...}，跨用户不可见；
  - 重启后同一 vector_dir 数据不丢。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol, cast

import chromadb

from ..common.errors import ValidationError

# 关闭 chromadb 遥测，保证离线可用
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

DEFAULT_COLLECTION = "kb_chunks"


class VectorStore(Protocol):
    """向量库抽象。"""

    dim: int

    def upsert(self, owner_id: str, doc_id: str, items: list[tuple[str, list[float]]]) -> None: ...

    def search(self, owner_id: str, vector: list[float], top_k: int) -> list[tuple[str, float]]: ...

    def delete_by_doc(self, owner_id: str, doc_id: str) -> None: ...


class ChromaVectorStore:
    """ChromaDB 本地持久化向量库。

    items 中每个元素为 (chunk_id, vector)；chunk_id 与 KbChunk.id 对齐，
    便于反向回查元数据。
    """

    def __init__(
        self,
        path: Path,
        *,
        dim: int = 32,
        collection: str = DEFAULT_COLLECTION,
    ) -> None:
        if dim < 1:
            raise ValidationError("dim 必须大于 0")
        self.dim = dim
        self._client = chromadb.PersistentClient(path=str(path))
        self._collection = self._client.get_or_create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, owner_id: str, doc_id: str, items: list[tuple[str, list[float]]]) -> None:
        if not owner_id or not doc_id:
            raise ValidationError("owner_id / doc_id 不能为空")
        ids: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict[str, str]] = []
        for chunk_id, vec in items:
            if len(vec) != self.dim:
                raise ValidationError(f"向量维度 {len(vec)} 与库维度 {self.dim} 不一致")
            ids.append(chunk_id)
            embeddings.append(vec)
            # owner_id/doc_id 强制注入，调用方不可覆盖
            metadatas.append({"owner_id": owner_id, "doc_id": doc_id})
        if ids:
            # chromadb 类型签名过宽（期望 numpy/list[Sequence]），运行时接受 list[list[float]]
            self._collection.upsert(
                ids=ids,
                embeddings=cast(Any, embeddings),
                metadatas=cast(Any, metadatas),
            )

    def search(self, owner_id: str, vector: list[float], top_k: int) -> list[tuple[str, float]]:
        if len(vector) != self.dim:
            raise ValidationError(f"查询向量维度 {len(vector)} 与库维度 {self.dim} 不一致")
        if top_k < 1:
            raise ValidationError("top_k 必须大于 0")
        # chromadb 1.5 count() 无 where 参数，用 get(where, limit=1) 快速判空
        if not self._collection.get(where={"owner_id": owner_id}, limit=1)["ids"]:
            return []
        res = self._collection.query(
            query_embeddings=cast(Any, [vector]),
            n_results=top_k,
            where={"owner_id": owner_id},
        )
        ids_raw = res.get("ids")
        dist_raw = res.get("distances")
        if not ids_raw or not dist_raw:
            return []
        ids = ids_raw[0]
        distances = dist_raw[0]
        if distances is None:
            return []
        # cosine space 下 distance ∈ [0,2]，similarity = 1 - distance（截断负数）
        return [(cid, max(0.0, 1.0 - d)) for cid, d in zip(ids, distances, strict=True)]

    def delete_by_doc(self, owner_id: str, doc_id: str) -> None:
        # chromadb 多条件过滤须显式 $and（顶层多键 dict 会被当作操作符表达式）
        self._collection.delete(
            where={"$and": [{"owner_id": owner_id}, {"doc_id": doc_id}]}
        )

    def count(self, owner_id: str) -> int:
        ids = self._collection.get(where={"owner_id": owner_id}, include=[])["ids"]
        return len(ids)
