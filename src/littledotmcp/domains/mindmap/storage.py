"""思维导图存储（M5-01）：MindmapRepository，强制 owner 隔离。"""

from __future__ import annotations

from sqlalchemy import select

from ...db.models import Mindmap
from ...db.repository import OwnerScopedRepository


class MindmapRepository(OwnerScopedRepository[Mindmap]):
    """mindmaps 表仓储，全部查询强制 owner_id。"""

    model = Mindmap

    def get_by_title(self, owner_id: str, title: str) -> Mindmap | None:
        stmt = select(Mindmap).where(
            Mindmap.owner_id == owner_id, Mindmap.title == title
        )
        return self.session.scalars(stmt).one_or_none()
