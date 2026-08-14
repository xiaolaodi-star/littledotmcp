"""M8 需求追溯链路测试：聚合 / SVN 关联 / 标签 / 项目里程碑 / owner 隔离。"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from littledotmcp.db import Base, engine as db_engine
from littledotmcp.db.models import Document, Milestone, Project, SvnOpLog, Tag
from littledotmcp.domains.requirement import trace as req_trace
from littledotmcp.domains.requirement import tools as req_tools
from littledotmcp.domains.svn import storage as svn_storage
from littledotmcp.domains.svn import tools as svn_tools


@pytest.fixture
def schema(sqlite_tmp_engine) -> None:
    Base.metadata.create_all(sqlite_tmp_engine)


def _set_owner(monkeypatch: pytest.MonkeyPatch, owner: str) -> None:
    monkeypatch.setattr(req_tools, "_current_owner", lambda: owner)
    monkeypatch.setattr(req_trace, "_current_owner", lambda: owner)
    monkeypatch.setattr(svn_tools, "_current_owner", lambda: owner)


def _add(
    owner: str,
    monkeypatch: pytest.MonkeyPatch,
    code: str = "REQ-1",
    title: str = "t",
    **kw,
) -> None:
    _set_owner(monkeypatch, owner)
    r = req_tools.requirement_add(code, title, **kw)
    assert r["success"] is True, r


def _req_id(code: str) -> str:
    with db_engine.SessionLocal() as s:
        return s.execute(select(__import__("littledotmcp.db.models", fromlist=["Requirement"]).Requirement).where(
            __import__("littledotmcp.db.models", fromlist=["Requirement"]).Requirement.code == code
        )).scalars().first().id


def test_trace_empty(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _add("alice", monkeypatch)
    t = req_trace.requirement_trace("REQ-1")
    assert t["success"] is True
    d = t["data"]
    assert d["found"] is True
    assert d["svn_commits"] == []
    assert d["documents"] == []
    assert d["tags"] == []
    assert d["project"] is None
    assert d["milestone"] is None
    assert len(d["timeline"]) >= 1


def test_trace_not_found(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    t = req_trace.requirement_trace("NOPE")
    assert t["success"] is False


def test_trace_svn_link(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _add("alice", monkeypatch)
    rid = _req_id("REQ-1")
    with db_engine.SessionLocal() as s:
        s.add(
            SvnOpLog(
                id="op-1",
                owner_id="alice",
                repo_id="repo-1",
                op="commit",
                rev="42",
                message="msg",
                requirement_id=rid,
            )
        )
        s.commit()
    t = req_trace.requirement_trace("REQ-1")
    assert t["data"]["svn_commits"][0]["rev"] == "42"


def test_trace_tag_and_project(
    isolated_settings, schema, monkeypatch: pytest.MonkeyPatch
) -> None:
    with db_engine.SessionLocal() as s:
        s.add(Project(id="p1", owner_id="alice", name="P1", status="active"))
        s.add(Milestone(id="m1", owner_id="alice", project_id="p1", name="M1", done=False))
        s.add(Tag(id="tag-1", owner_id="alice", name="urgent"))
        s.commit()
    _add(
        "alice",
        monkeypatch,
        code="REQ-2",
        title="t2",
        project_id="p1",
        milestone_id="m1",
    )
    _set_owner(monkeypatch, "alice")
    r = req_tools.requirement_link("REQ-2", related_tag="tag-1")
    assert r["success"] is True
    t = req_trace.requirement_trace("REQ-2")
    assert t["data"]["project"]["id"] == "p1"
    assert t["data"]["milestone"]["id"] == "m1"
    assert t["data"]["tags"][0]["id"] == "tag-1"


def test_trace_owner_isolation(
    isolated_settings, schema, monkeypatch: pytest.MonkeyPatch
) -> None:
    _add("alice", monkeypatch)
    _set_owner(monkeypatch, "bob")
    t = req_trace.requirement_trace("REQ-1")
    assert t["success"] is False


def test_svn_commit_requirement_id(
    isolated_settings, schema, monkeypatch: pytest.MonkeyPatch
) -> None:
    """svn_commit 透传 requirement_id 落库 SvnOpLog（经回调）。"""
    _add("alice", monkeypatch)
    rid = _req_id("REQ-1")
    # 预建 svn repo，避免仓库不存在
    with db_engine.SessionLocal() as s:
        M = __import__("littledotmcp.db.models", fromlist=["SvnRepo"]).SvnRepo
        s.add(M(id="repo-1", owner_id="alice", name="r", url=""))
        s.commit()

    class _FakeClient:
        def __init__(self, on_op=None):
            self._on_op = on_op

        def commit(self, path, message):
            if self._on_op:
                self._on_op("commit", "99", message)
            return "99"

    monkeypatch.setattr(
        svn_tools,
        "get_svn_client",
        lambda *a, **k: _FakeClient(on_op=k.get("on_op")),
    )
    r = svn_tools.svn_commit("repo-1", "msg", requirement_id=rid)
    assert r["success"] is True
    with db_engine.SessionLocal() as s:
        row = s.execute(select(SvnOpLog).where(SvnOpLog.rev == "99")).scalars().first()
        assert row is not None
        assert row.requirement_id == rid
