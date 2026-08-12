"""数据库层：engine / session / 模型 / Repository 基类（M1）。

注意：不要在此 `from .engine import engine`，否则包属性 db.engine 会遮蔽子模块，
导致后续 `import littledotmcp.db.engine` 取到 Engine 实例而非模块。
"""

from __future__ import annotations

from .engine import SessionLocal, get_engine
from .models import Base
from .repository import OwnerScopedRepository, Repository

__all__ = ["Base", "SessionLocal", "get_engine", "Repository", "OwnerScopedRepository"]
