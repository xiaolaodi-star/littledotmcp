"""建表与迁移（M1-03）。

可重复执行（幂等）：仅 create_all，新增表/列请走 alembic（后续里程碑）。
设置 STANDARD_TEMPLATES=1 时同时注入 M5 内置规范模板。
"""

from __future__ import annotations

import os

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from littledotmcp.db import models  # noqa: F401 确保模型注册
from littledotmcp.db.models import Base

# M8 存量库迁移：在 create_all 之外幂等补齐新增列（SQLite 不支持 ADD COLUMN IF NOT EXISTS）
_M8_ALTERS = [
    ("svn_ops_log", "requirement_id", "ALTER TABLE svn_ops_log ADD COLUMN requirement_id VARCHAR(64)"),
    ("requirements", "related_tag", "ALTER TABLE requirements ADD COLUMN related_tag VARCHAR(255)"),
    ("requirements", "project_id", "ALTER TABLE requirements ADD COLUMN project_id VARCHAR(64)"),
    ("requirements", "milestone_id", "ALTER TABLE requirements ADD COLUMN milestone_id VARCHAR(64)"),
]


def _migrate_columns(engine) -> None:
    """对存量 SQLite 库幂等补齐 M8 新增列（列已存在则忽略）。"""
    with engine.begin() as conn:
        for _table, _column, stmt in _M8_ALTERS:
            try:
                conn.execute(text(stmt))
            except OperationalError as exc:
                # 列已存在时 SQLite 报 duplicate column，属幂等预期，忽略
                if "duplicate column" in str(exc).lower():
                    continue
                raise


def init_db() -> None:
    # 动态读取 engine，避免模块导入时绑定导致测试 patch 失效（M10 修复）
    from littledotmcp.db import engine as engine_mod

    engine = engine_mod.engine
    Base.metadata.create_all(engine)
    _migrate_columns(engine)
    print("数据库已初始化/更新（幂等）：", engine.url)
    if os.environ.get("STANDARD_TEMPLATES") == "1":
        from seed_standards import seed_standards  # 本地脚本，非包内

        n = seed_standards()
        print(f"规范模板注入完成：{n} 条（已存在跳过）")


if __name__ == "__main__":
    init_db()
