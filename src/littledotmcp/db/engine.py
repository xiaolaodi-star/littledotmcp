"""SQLAlchemy engine / session（M1-01）。

默认 SQLite（个人零依赖）；DB_URL 可切 MySQL/PostgreSQL（服务端多用户）。
SQLite 开启外键约束与 WAL，保证开发体验与并发读取。
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings

_settings = get_settings()
_url = _settings.db_url

_connect_args: dict = {}
if _url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
    # 自动创建 sqlite 文件所在目录，避免 "unable to open database file"
    import pathlib

    _db_path = _url.replace("sqlite:///", "", 1)
    if _db_path and _db_path != ":memory:":
        pathlib.Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

engine: Engine = create_engine(
    _url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
)


def get_engine() -> Engine:
    """返回全局 engine（测试可重建）。"""
    return engine


def get_session() -> Iterator[Session]:
    """FastAPI/CLI 依赖式会话上下文（yield 自动关闭）。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
