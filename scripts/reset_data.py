"""知识库/数据重置脚本（M6-05）。

清空 data/ 下数据库与向量目录，重建空库（幂等，不删 .env/配置）。
用法：
    uv run python scripts/reset_data.py            # 仅清库
    STANDARD_TEMPLATES=1 uv run python scripts/reset_data.py  # 清库并注入规范模板
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from littledotmcp.config import get_settings


def _sqlite_path(settings) -> Path | None:
    url = settings.db_url
    if not url.startswith("sqlite:///"):
        # 非 SQLite（MySQL/PG）不本地清，提示手工处理
        print(f"当前 DB_URL 非本地 SQLite（{url}），跳过本地文件清理")
        return None
    raw = url.replace("sqlite:///", "", 1)
    if raw == ":memory:":
        return None
    return Path(raw)


def reset_data() -> int:
    from littledotmcp.db.engine import engine  # 函数内取，保证测试可 patch

    settings = get_settings()
    removed: list[str] = []

    db_path = _sqlite_path(settings)
    if db_path is not None and db_path.exists():
        # 先释放连接，避免 Windows 下文件被占用无法删除
        engine.dispose()
        db_path.unlink()
        removed.append(str(db_path))
    # 顺带清理 SQLite 附属文件（WAL/SHM）
    for suffix in ("-wal", "-shm"):
        side = Path(str(db_path) + suffix)
        if side.exists():
            side.unlink()
            removed.append(str(side))

    vector_dir = Path(settings.vector_dir)
    if vector_dir.exists():
        shutil.rmtree(vector_dir)
        removed.append(str(vector_dir))

    # 清理真实 Embedding 结果持久化缓存（M7，按 storage_root 同级定位）
    cache_file = Path(settings.storage_root).parent / "embedding_cache.jsonl"
    if cache_file.exists():
        cache_file.unlink()
        removed.append(str(cache_file))

    if removed:
        for item in removed:
            print("已删除：", item)
    else:
        print("无待清理数据（data/ 已是空库）")

    from init_db import init_db  # 本地脚本，复用幂等建表

    init_db()
    return 0


if __name__ == "__main__":
    sys.exit(reset_data())
