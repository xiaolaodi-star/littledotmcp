"""M5-04 seed_standards 测试：模板注入幂等、force 覆盖。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from littledotmcp.db import Base
from littledotmcp.db import engine as db_engine
from littledotmcp.domains.standard.storage import StandardRepository

# scripts 非包目录，手动加入 sys.path 后按模块导入
_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import seed_standards  # noqa: E402


@pytest.fixture
def schema(sqlite_tmp_engine) -> None:
    Base.metadata.create_all(sqlite_tmp_engine)


def test_seed_idempotent(sqlite_tmp_engine, schema) -> None:
    n1 = seed_standards.seed_standards()
    assert n1 == len(seed_standards.TEMPLATES)
    n2 = seed_standards.seed_standards()
    assert n2 == 0  # 已存在跳过

    with db_engine.SessionLocal() as session:
        names = [s.name for s in StandardRepository(session).list_by_owner("local")]
    assert "命名规范" in names
    assert len(names) == len(seed_standards.TEMPLATES)


def test_seed_force_overwrites(sqlite_tmp_engine, schema) -> None:
    from littledotmcp.db.models import Standard

    with db_engine.SessionLocal() as session:
        repo = StandardRepository(session)
        repo.add(
            Standard(
                id="fixed",
                owner_id="local",
                name="命名规范",
                category="naming",
                content="旧内容",
            )
        )
        session.commit()

    n = seed_standards.seed_standards(force=True)
    assert n == len(seed_standards.TEMPLATES)

    with db_engine.SessionLocal() as session:
        std = StandardRepository(session).get_by_name("local", "命名规范")
        assert std is not None and "命名规范" in std.content
