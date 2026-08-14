"""规范存储（M5-04）：StandardRepository，强制 owner 隔离。"""

from __future__ import annotations

from sqlalchemy import select

from ...db.models import Standard
from ...db.repository import OwnerScopedRepository


class StandardRepository(OwnerScopedRepository[Standard]):
    """standards 表仓储，全部查询强制 owner_id。"""

    model = Standard

    def get_by_name(self, owner_id: str, name: str) -> Standard | None:
        stmt = select(Standard).where(Standard.owner_id == owner_id, Standard.name == name)
        return self.session.scalars(stmt).one_or_none()
