"""建表与迁移（M1-03）。

可重复执行（幂等）：仅 create_all，新增表/列请走 alembic（后续里程碑）。
空库初始化的规范示例模板由 M5 负责写入。
"""

from __future__ import annotations

from littledotmcp.db import models  # noqa: F401 确保模型注册
from littledotmcp.db.engine import engine
from littledotmcp.db.models import Base


def init_db() -> None:
    Base.metadata.create_all(engine)
    print("数据库已初始化/更新（幂等）：", engine.url)


if __name__ == "__main__":
    init_db()
