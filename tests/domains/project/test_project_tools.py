"""M4-03 project 域测试：project/milestone/task CRUD / 进度 / owner 隔离 / 级联。"""

from __future__ import annotations

import pytest

from littledotmcp.db import Base
from littledotmcp.domains.project import tools as proj_tools


@pytest.fixture
def schema(sqlite_tmp_engine) -> None:
    Base.metadata.create_all(sqlite_tmp_engine)


def _set_owner(monkeypatch: pytest.MonkeyPatch, owner: str) -> None:
    monkeypatch.setattr(proj_tools, "_current_owner", lambda: owner)


def _proj(owner: str, monkeypatch: pytest.MonkeyPatch, name: str = "P1") -> str:
    _set_owner(monkeypatch, owner)
    r = proj_tools.project_add(name)
    assert r["success"] is True, r
    return r["data"]["id"]


def test_project_add_list_get(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    pid = _proj("alice", monkeypatch)
    g = proj_tools.project_get(pid)
    assert g["success"] is True
    assert g["data"]["progress"]["progress_pct"] == 0.0


def test_milestone_and_task(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    pid = _proj("alice", monkeypatch)
    mid = proj_tools.milestone_add(pid, "M1", due="2026-09-01")["data"]["id"]
    assert proj_tools.milestone_list(pid)["data"]["count"] == 1

    t1 = proj_tools.task_add(pid, "T1", milestone_id=mid, weight=3)["data"]["id"]
    t2 = proj_tools.task_add(pid, "T2", weight=1)["data"]["id"]

    lst = proj_tools.task_list(pid)
    assert lst["data"]["count"] == 2
    # 进度：无 done，应为 0
    assert lst["data"]["progress"]["progress_pct"] == 0.0

    proj_tools.task_update(t1, status="done")
    prog = proj_tools.project_get(pid)["data"]["progress"]
    # done 3 / total 4 = 75%
    assert prog["progress_pct"] == 75.0


def test_invalid_task_status(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    pid = _proj("alice", monkeypatch)
    tid = proj_tools.task_add(pid, "T1")["data"]["id"]
    bad = proj_tools.task_update(tid, status="blocked")
    assert bad["success"] is False


def test_task_filter_by_milestone(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    pid = _proj("alice", monkeypatch)
    mid = proj_tools.milestone_add(pid, "M1")["data"]["id"]
    proj_tools.task_add(pid, "T1", milestone_id=mid)
    proj_tools.task_add(pid, "T2")
    filtered = proj_tools.task_list(pid, milestone_id=mid)
    assert filtered["data"]["count"] == 1


def test_remove_cascades(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    pid = _proj("alice", monkeypatch)
    proj_tools.task_add(pid, "T1")
    rem = proj_tools.project_remove(pid)
    assert rem["success"] is True
    assert proj_tools.project_get(pid)["success"] is False
    assert proj_tools.task_list(pid)["data"]["count"] == 0


def test_owner_isolation(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    pid = _proj("alice", monkeypatch)
    _set_owner(monkeypatch, "bob")
    assert proj_tools.project_get(pid)["success"] is False
    assert proj_tools.project_list()["data"]["count"] == 0
    _set_owner(monkeypatch, "alice")
    assert proj_tools.project_list()["data"]["count"] == 1
