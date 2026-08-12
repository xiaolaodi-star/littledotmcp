"""pytest 全局 fixture（S0.7）。

- tmp_data_dir：隔离的临时数据目录（DB / 文件 / 向量），避免污染真实 data/
- isolate_settings：将配置重定向到临时目录，保证测试可重复
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 确保 src 在 sys.path（uv 已处理，但独立 pytest 调用兜底）
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """一次性临时数据根目录。"""
    d = tmp_path / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "files").mkdir(exist_ok=True)
    (d / "vectors").mkdir(exist_ok=True)
    return d


@pytest.fixture
def isolated_settings(tmp_data_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """将配置指向临时目录，覆盖 get_settings 单例缓存。"""
    from littledotmcp.config import Settings, get_settings

    s = Settings(
        db_url=f"sqlite:///{tmp_data_dir / 'test.db'}",
        storage_root=tmp_data_dir / "files",
        vector_dir=tmp_data_dir / "vectors",
        log_dir=tmp_data_dir / "logs",
    )
    monkeypatch.setenv("DB_URL", str(s.db_url))
    monkeypatch.setenv("STORAGE_ROOT", str(s.storage_root))
    monkeypatch.setenv("VECTOR_DIR", str(s.vector_dir))
    get_settings.cache_clear()
    return s


@pytest.fixture
def sqlite_tmp_engine(tmp_data_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """重建模块级 SQLAlchemy engine 指向临时 SQLite，避免污染真实 data/。

    返回 (engine, SessionLocal)，并注入到 db.engine / auth 使用的会话工厂。
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import littledotmcp.db.engine as engine_mod

    eng = create_engine(
        f"sqlite:///{tmp_data_dir / 'm1.db'}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        future=True,
    )
    sess_factory = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(engine_mod, "engine", eng)
    monkeypatch.setattr(engine_mod, "SessionLocal", sess_factory)
    yield eng
    eng.dispose()
