"""M1 隔离与 Repository 契约测试（M1-04 / M1-08）。

核心验收：A/B 用户互不可见数据；越权注入 owner_id 被 Repository 拒绝。
"""

from __future__ import annotations

import uuid

import pytest

from littledotmcp.auth import authenticate, login, register
from littledotmcp.db import Base
from littledotmcp.db.models import KbDocument, User
from littledotmcp.db.repository import OwnerScopedRepository, Repository


@pytest.fixture
def _schema(sqlite_tmp_engine: object) -> None:
    Base.metadata.create_all(sqlite_tmp_engine)
    yield
    Base.metadata.drop_all(sqlite_tmp_engine)


class _KbRepo(OwnerScopedRepository[KbDocument]):
    model = KbDocument


def _make_doc(owner_id: str) -> KbDocument:
    return KbDocument(
        id=uuid.uuid4().hex,
        owner_id=owner_id,
        title=f"doc-{owner_id[:6]}",
        storage_key="k",
    )


def test_owner_scoped_isolation(_schema: None) -> None:
    from littledotmcp.db.engine import SessionLocal

    a = "owner-a"
    b = "owner-b"
    with SessionLocal() as s:
        repo_a = _KbRepo(s)
        repo_b = _KbRepo(s)
        repo_a.add(_make_doc(a))
        repo_b.add(_make_doc(b))
        s.commit()

        # list_by_owner 严格按 owner_id 过滤（隔离由业务层只传 current_owner 保证）
        a_docs = repo_a.list_by_owner(a)
        assert len(a_docs) == 1
        assert a_docs[0].owner_id == a
        # 查询不存在的 owner 返回空
        assert repo_a.list_by_owner("owner-unknown") == []
        # get_by_owner 越权返回 None：用 a 的 repo 取 b 的文档应拿不到
        b_doc = b_docs_first = repo_b.list_by_owner(b)[0]
        assert repo_a.get_by_owner(a, b_doc.id) is None
        assert repo_b.get_by_owner(b, b_doc.id) is b_doc


def test_owner_scoped_rejects_missing_owner_field(_schema: None) -> None:
    from littledotmcp.db.engine import SessionLocal

    class _UserRepo(Repository[User]):
        model = User

    with SessionLocal() as s:
        # User 无 owner_id，必须拒绝使用 OwnerScopedRepository
        class _BadRepo(OwnerScopedRepository[User]):
            model = User

        with pytest.raises(AttributeError):
            _BadRepo(s).add(User(id="x", username="x", password_hash="y"))


def test_auth_roundtrip(_schema: None) -> None:
    register("alice", "secret123", "Alice")
    tok = login("alice", "secret123")["token"]
    owner = authenticate(tok)
    assert isinstance(owner, str) and len(owner) > 0
    with pytest.raises(Exception):
        login("alice", "wrong")
