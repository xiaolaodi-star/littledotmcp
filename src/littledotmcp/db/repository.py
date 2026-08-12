"""Repository 基类（M1-04）。

- Repository：通用 CRUD 基类
- OwnerScopedRepository：强制 owner_id 注入的隔离基类，所有用户数据表必须继承，
  禁止调用方自行拼接 owner_id，从数据访问层杜绝越权跨用户可见性。
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Base

M = TypeVar("M", bound=Base)


class Repository(Generic[M]):
    """通用 CRUD 基类。"""

    model: type[M]

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, obj: M) -> M:
        self.session.add(obj)
        self.session.flush()
        return obj

    def get(self, pk: Any) -> M | None:
        return self.session.get(self.model, pk)

    def list_all(self) -> list[M]:
        return list(self.session.scalars(select(self.model)).all())

    def delete(self, obj: M) -> None:
        self.session.delete(obj)
        self.session.flush()


class OwnerScopedRepository(Repository[M], Generic[M]):
    """强制 owner_id 隔离的基类。

    所有查询/插入都自动带 owner_id；若模型无 owner_id 字段则在 add 时抛错，
    从根上保证"只允许使用他们自己的知识"。
    """

    def add(self, obj: M) -> M:  # type: ignore[override]
        # 检查模型「类」是否声明了 owner_id 映射列（用 mapper，排除实例 property 伪装）
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(self.model)
        if "owner_id" not in {c.key for c in mapper.columns}:
            raise AttributeError(
                f"{self.model.__name__} 缺少 owner_id 映射列，无法使用 OwnerScopedRepository"
            )
        return super().add(obj)

    def list_by_owner(self, owner_id: str) -> list[M]:
        stmt = select(self.model).where(self.model.owner_id == owner_id)  # type: ignore[attr-defined]
        return list(self.session.scalars(stmt).all())

    def get_by_owner(self, owner_id: str, pk: Any) -> M | None:
        obj = self.session.get(self.model, pk)
        if obj is None:
            return None
        if getattr(obj, "owner_id", None) != owner_id:
            return None
        return obj

    def delete_by_owner(self, owner_id: str, pk: Any) -> bool:
        obj = self.get_by_owner(owner_id, pk)
        if obj is None:
            return False
        self.session.delete(obj)
        self.session.flush()
        return True

    def delete_all_by_owner(self, owner_id: str) -> int:
        stmt = sa_delete(self.model).where(self.model.owner_id == owner_id)  # type: ignore[attr-defined]
        result = self.session.execute(stmt)
        self.session.flush()
        return int(result.rowcount)
