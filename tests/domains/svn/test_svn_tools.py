"""M4-01 svn 域工具测试：repo CRUD / checkout-commit-log / owner 隔离。"""

from __future__ import annotations

import pytest

from littledotmcp.db import Base
from littledotmcp.domains.svn import tools as svn_tools
from littledotmcp.domains.svn.storage import decrypt, encrypt


@pytest.fixture
def schema(sqlite_tmp_engine) -> None:
    Base.metadata.create_all(sqlite_tmp_engine)


def _set_owner(monkeypatch: pytest.MonkeyPatch, owner: str) -> None:
    monkeypatch.setattr(svn_tools, "_current_owner", lambda: owner)


def test_cred_encrypt_roundtrip() -> None:
    enc = encrypt("secret")
    assert enc != "secret"
    assert decrypt(enc) == "secret"
    assert encrypt("") == ""


def test_repo_add_and_list(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_owner(monkeypatch, "alice")
    add = svn_tools.svn_repo_add("repo1", "https://svn.example.com/repo1", username="u", cred="pw")
    assert add["success"] is True
    rid = add["data"]["id"]

    lst = svn_tools.svn_repo_list()
    assert lst["data"]["count"] == 1
    assert lst["data"]["items"][0]["name"] == "repo1"

    # 凭证不以明文存在于返回
    assert "pw" not in str(lst["data"])


def test_repo_name_conflict(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_owner(monkeypatch, "alice")
    svn_tools.svn_repo_add("repo1", "https://x/1")
    dup = svn_tools.svn_repo_add("repo1", "https://x/2")
    assert dup["success"] is False
    assert "已存在" in dup["message"]


def test_checkout_commit_and_log(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_owner(monkeypatch, "alice")
    rid = svn_tools.svn_repo_add("repo1", "https://x/1")["data"]["id"]

    co = svn_tools.svn_checkout(rid)
    assert co["success"] is True
    assert co["data"]["rev"].startswith("r")

    cm = svn_tools.svn_commit(rid, "initial commit")
    assert cm["success"] is True

    log = svn_tools.svn_log(rid)
    assert log["data"]["count"] >= 2
    ops = [o["op"] for o in log["data"]["items"]]
    assert "checkout" in ops and "commit" in ops


def test_commit_requires_message(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_owner(monkeypatch, "alice")
    rid = svn_tools.svn_repo_add("repo1", "https://x/1")["data"]["id"]
    cm = svn_tools.svn_commit(rid, "   ")
    assert cm["success"] is False


def test_owner_isolation(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_owner(monkeypatch, "alice")
    rid = svn_tools.svn_repo_add("repo1", "https://x/1")["data"]["id"]

    _set_owner(monkeypatch, "bob")
    assert svn_tools.svn_repo_list()["data"]["count"] == 0
    assert svn_tools.svn_checkout(rid)["success"] is False
    assert svn_tools.svn_log(rid)["success"] is False

    _set_owner(monkeypatch, "alice")
    assert svn_tools.svn_repo_list()["data"]["count"] == 1


def test_repo_remove_cascades_log(isolated_settings, schema, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_owner(monkeypatch, "alice")
    rid = svn_tools.svn_repo_add("repo1", "https://x/1")["data"]["id"]
    svn_tools.svn_checkout(rid)
    rem = svn_tools.svn_repo_remove(rid)
    assert rem["success"] is True
    assert svn_tools.svn_log(rid)["success"] is False
