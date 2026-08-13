"""M3-07 VectorStore 抽象与 SQLite-vec 本地持久化实现。

- VectorStore：向量库抽象（upsert/search/delete_by_doc/count），接口可切换
  sqlite-vec / pgvector 等后端；
- SqliteVecVectorStore：基于标准库 sqlite3 + sqlite-vec 扩展的本地持久化；
  - metadata 强制注入 owner_id/doc_id，调用方不可覆盖（owner 隔离硬约束）；
  - 检索必须带 owner_id 过滤，跨用户不可见；
  - 重启后同一 vector_dir 数据不丢。

注：早期版本使用 chromadb，但其 Rust 绑定在 Windows + Python 3.12 下
upsert 会触发 access violation 崩溃（且无 Python 层 traceback），故替换为
纯 SQLite 的 sqlite-vec 扩展（跨平台有预编译 wheel，无 Rust 绑定依赖）。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Protocol, cast

import sqlite_vec
from sqlite_vec import serialize_float32

from ..common.errors import ValidationError

DEFAULT_COLLECTION = "kb_chunks"


class VectorStore(Protocol):
    """向量库抽象。"""

    dim: int

    def upsert(self, owner_id: str, doc_id: str, items: list[tuple[str, list[float]]]) -> None: ...

    def search(self, owner_id: str, vector: list[float], top_k: int) -> list[tuple[str, float]]: ...

    def delete_by_doc(self, owner_id: str, doc_id: str) -> None: ...

    def count(self, owner_id: str) -> int: ...


def _connect(db_path: Path) -> sqlite3.Connection:
    """连接 SQLite 并加载 sqlite-vec 扩展。"""
    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


class SqliteVecVectorStore:
    """基于 sqlite-vec 的本地持久化向量库。

    items 中每个元素为 (chunk_id, vector)；chunk_id 与 KbChunk.id 对齐，
    便于反向回查元数据。数据持久化到 ``path/kb_vectors.db``，重启不丢。
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
        self._collection = collection
        path.mkdir(parents=True, exist_ok=True)
        self._conn = _connect(path / "kb_vectors.db")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vectors (
                chunk_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                doc_id   TEXT NOT NULL,
                dim      INTEGER NOT NULL,
                vec      BLOB NOT NULL
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_vec_owner ON vectors(owner_id)")
        self._conn.commit()

    def upsert(self, owner_id: str, doc_id: str, items: list[tuple[str, list[float]]]) -> None:
        if not owner_id or not doc_id:
            raise ValidationError("owner_id / doc_id 不能为空")
        rows: list[tuple[str, str, str, int, bytes]] = []
        for chunk_id, vec in items:
            if len(vec) != self.dim:
                raise ValidationError(f"向量维度 {len(vec)} 与库维度 {self.dim} 不一致")
            # owner_id/doc_id 强制注入，调用方不可覆盖
            rows.append((chunk_id, owner_id, doc_id, self.dim, serialize_float32(vec)))
        if rows:
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO vectors (chunk_id, owner_id, doc_id, dim, vec)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )
            self._conn.commit()

    def search(self, owner_id: str, vector: list[float], top_k: int) -> list[tuple[str, float]]:
        if len(vector) != self.dim:
            raise ValidationError(f"查询向量维度 {len(vector)} 与库维度 {self.dim} 不一致")
        if top_k < 1:
            raise ValidationError("top_k 必须大于 0")
        cur = self._conn.execute(
            """
            SELECT chunk_id, vec_distance_cosine(vec, ?) AS distance
            FROM vectors
            WHERE owner_id = ?
            ORDER BY distance ASC
            LIMIT ?
            """,
            (serialize_float32(vector), owner_id, top_k),
        )
        # cosine distance ∈ [0,2]，similarity = 1 - distance（截断负数）
        return [(cast(str, cid), max(0.0, 1.0 - d)) for cid, d in cur.fetchall()]

    def delete_by_doc(self, owner_id: str, doc_id: str) -> None:
        self._conn.execute(
            "DELETE FROM vectors WHERE owner_id = ? AND doc_id = ?",
            (owner_id, doc_id),
        )
        self._conn.commit()

    def count(self, owner_id: str) -> int:
        (n,) = self._conn.execute(
            "SELECT COUNT(*) FROM vectors WHERE owner_id = ?", (owner_id,)
        ).fetchone()
        return int(n)
