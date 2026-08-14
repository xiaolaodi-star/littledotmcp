"""建表与迁移（M1-03）。

可重复执行（幂等）：仅 create_all，新增表/列请走 alembic（后续里程碑）。
设置 STANDARD_TEMPLATES=1 时同时注入 M5 内置规范模板。
"""

from __future__ import annotations

import os

from littledotmcp.db import models  # noqa: F401 确保模型注册
from littledotmcp.db.models import Base


def init_db() -> None:
    # 动态读取 engine，避免模块导入时绑定导致测试 patch 失效（M10 修复）
    from littledotmcp.db import engine as engine_mod

    engine = engine_mod.engine
    Base.metadata.create_all(engine)
    print("数据库已初始化/更新（幂等）：", engine.url)
    if os.environ.get("STANDARD_TEMPLATES") == "1":
        from seed_standards import seed_standards  # 本地脚本，非包内

        n = seed_standards()
        print(f"规范模板注入完成：{n} 条（已存在跳过）")


if __name__ == "__main__":
    init_db()
