"""kb 域数据访问（M3-08）：均继承 OwnerScopedRepository 强制 owner 隔离。"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import CursorResult, select
from sqlalchemy import delete as sa_delete

from ...db.models import KbChunk, KbDocument
from ...db.repository import OwnerScopedRepository


class KbDocumentRepository(OwnerScopedRepository[KbDocument]):
    """kb_documents 表隔离仓库。"""

    model = KbDocument

    def get_by_storage_key(self, owner_id: str, storage_key: str) -> KbDocument | None:
        """按来源 storage_key 查询（用于 ingest 幂等重建）。"""
        stmt = select(KbDocument).where(
            KbDocument.owner_id == owner_id,
            KbDocument.storage_key == storage_key,
        )
        return self.session.scalars(stmt).first()


class KbChunkRepository(OwnerScopedRepository[KbChunk]):
    """kb_chunks 表隔离仓库。"""

    model = KbChunk

    def list_by_doc(self, owner_id: str, doc_id: str) -> list[KbChunk]:
        stmt = (
            select(KbChunk)
            .where(KbChunk.owner_id == owner_id, KbChunk.doc_id == doc_id)
            .order_by(KbChunk.seq)
        )
        return list(self.session.scalars(stmt).all())

    def list_all_by_owner(self, owner_id: str) -> list[KbChunk]:
        stmt = (
            select(KbChunk)
            .where(KbChunk.owner_id == owner_id)
            .order_by(KbChunk.seq)
        )
        return list(self.session.scalars(stmt).all())

    def delete_by_doc(self, owner_id: str, doc_id: str) -> int:
        stmt = sa_delete(KbChunk).where(
            KbChunk.owner_id == owner_id,
            KbChunk.doc_id == doc_id,
        )
        result = cast(CursorResult[Any], self.session.execute(stmt))
        self.session.flush()
        return int(result.rowcount or 0)
