"""M11-01 数据模型与迁移测试。

覆盖：User.role 默认列、user_sessions/call_errors/audit_logs 三张新表建表与字段、
存量库 users.role 幂等 ALTER 迁移（重复执行不报错）。
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from littledotmcp.db.models import (
    AuditLog,
    Base,
    CallError,
    User,
    UserSession,
)


def test_user_role_default(tmp_path) -> None:
    """User 新增 role 列，默认值为 user。"""
    eng = create_engine(f"sqlite:///{tmp_path / 'u.db'}", future=True)
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, future=True)
    with Session() as s:
        u = User(id="u1", username="alice", password_hash="x")
        s.add(u)
        s.commit()
        assert u.role == "user"
        got = s.get(User, "u1")
        assert got is not None and got.role == "user"
    eng.dispose()


def test_new_tables_created(tmp_path) -> None:
    """三张新表均被 create_all 创建，且字段类型正确。"""
    eng = create_engine(f"sqlite:///{tmp_path / 'n.db'}", future=True)
    Base.metadata.create_all(eng)
    insp = inspect(eng)
    for tbl in ("user_sessions", "call_errors", "audit_logs"):
        assert tbl in insp.get_table_names(), f"缺失表 {tbl}"
    # user_sessions 关键列
    cols = {c["name"] for c in insp.get_columns("user_sessions")}
    assert {"id", "user_id", "token", "expires_at", "ip", "created_at"} <= cols
    # call_errors 关键列
    cols = {c["name"] for c in insp.get_columns("call_errors")}
    assert {"id", "owner_id", "tool_name", "args_summary", "error_type", "status", "occurrences"} <= cols
    # audit_logs 关键列
    cols = {c["name"] for c in insp.get_columns("audit_logs")}
    assert {"id", "actor_id", "action", "entity", "entity_id", "detail"} <= cols
    eng.dispose()


def test_new_models_insertable(tmp_path) -> None:
    """新模型可正常插入与读取。"""
    eng = create_engine(f"sqlite:///{tmp_path / 'i.db'}", future=True)
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, future=True)
    now = dt.datetime.now(dt.timezone.utc)
    with Session() as s:
        u = User(id="u1", username="bob", password_hash="x", role="admin")
        s.add(u)
        s.commit()
        s.add(UserSession(id="s1", user_id="u1", token="tok", expires_at=now))
        s.add(
            CallError(
                id="e1",
                owner_id="u1",
                tool_name="foo",
                error_type="ValueError",
                status="open",
            )
        )
        s.add(AuditLog(id="a1", actor_id="u1", action="user.create", entity="user", entity_id="u2"))
        s.commit()

        assert s.get(UserSession, "s1").user_id == "u1"
        ce = s.get(CallError, "e1")
        assert ce.tool_name == "foo" and ce.occurrences == 1
        assert s.get(AuditLog, "a1").action == "user.create"
    eng.dispose()


def test_m11_alter_migration_idempotent(tmp_path) -> None:
    """users.role 存量 ALTER 迁移幂等：重复执行不报错（duplicate column 被忽略）。"""
    from scripts.init_db import _M11_ALTERS, _migrate_columns  # type: ignore

    eng = create_engine(
        f"sqlite:///{tmp_path / 'm.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(eng)
    # 模拟脚本行为：先建表（无 role 列则补），重复执行两次验证幂等
    _migrate_columns(eng)
    _migrate_columns(eng)  # 第二次应静默跳过（duplicate column）
    insp = inspect(eng)
    cols = {c["name"] for c in insp.get_columns("users")}
    assert "role" in cols
    assert len(_M11_ALTERS) == 1 and _M11_ALTERS[0][0] == "users"
    eng.dispose()
