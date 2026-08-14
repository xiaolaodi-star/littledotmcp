"""M11-04 管理 API 测试。

覆盖：知识库列表 owner 隔离（user 仅本人 / admin 跨 owner）、用户管理越权（user 调 admin 403）、
删除他人数据被拒、异常列表/关闭/删除权限、个人改密、运维端点权限。
"""

from __future__ import annotations

from starlette.testclient import TestClient

from littledotmcp.db.models import Base, CallError, Document, KbDocument, User
from littledotmcp.server import build_http_app


def _client(sqlite_tmp_engine, isolated_settings):  # noqa: ANN001
    Base.metadata.create_all(sqlite_tmp_engine)
    return TestClient(build_http_app())


def _setup_admin(client) -> None:
    client.post("/admin/api/setup", json={"username": "root", "password": "secret123"})
    client.post("/admin/api/login", json={"username": "root", "password": "secret123"})


def _create_user(client, username, password, role="user") -> str:
    # 以 admin 身份创建用户
    resp = client.post(
        "/admin/api/users",
        json={"username": username, "password": password, "role": role},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["user_id"]


def _login_as(client, username, password) -> None:
    client.post("/admin/api/login", json={"username": username, "password": password})


def _seed_docs(sqlite_tmp_engine, owner_a, owner_b) -> None:
    """直接落库：两份分属不同 owner 的 Document / KbDocument / CallError。"""
    from littledotmcp.db import engine as db_engine

    with db_engine.SessionLocal() as s:
        s.add(Document(id="dA", owner_id=owner_a, name="A-doc", storage_key="kA", size=10))
        s.add(Document(id="dB", owner_id=owner_b, name="B-doc", storage_key="kB", size=20))
        s.add(KbDocument(id="kA", owner_id=owner_a, title="A-kb", storage_key="sA", chunk_count=3))
        s.add(KbDocument(id="kB", owner_id=owner_b, title="B-kb", storage_key="sB", chunk_count=5))
        s.add(
            CallError(
                id="eA", owner_id=owner_a, tool_name="t", error_type="E", status="open"
            )
        )
        s.add(
            CallError(
                id="eB", owner_id=owner_b, tool_name="t", error_type="E", status="open"
            )
        )
        s.commit()


def test_user_sees_only_own_docs(sqlite_tmp_engine, isolated_settings) -> None:
    """user 角色仅见本人文档，admin 可见全部。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    _setup_admin(client)
    ua = _create_user(client, "alice", "pw1", "user")
    ub = _create_user(client, "bob", "pw2", "user")
    _seed_docs(sqlite_tmp_engine, ua, ub)

    # 以 admin 登录见全部 2 条
    r = client.get("/admin/api/documents")
    assert r.status_code == 200 and r.json()["data"]["total"] == 2

    # 以 alice 登录仅见 1 条（本人）
    _login_as(client, "alice", "pw1")
    r = client.get("/admin/api/documents")
    assert r.json()["data"]["total"] == 1
    assert r.json()["data"]["items"][0]["owner_id"] == ua

    # bob 也仅见 1 条
    _login_as(client, "bob", "pw2")
    assert client.get("/admin/api/documents").json()["data"]["total"] == 1


def test_user_cannot_delete_others_doc(sqlite_tmp_engine, isolated_settings) -> None:
    """user 删除他人文档应被拒（403）。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    _setup_admin(client)
    ua = _create_user(client, "alice", "pw1", "user")
    ub = _create_user(client, "bob", "pw2", "user")
    _seed_docs(sqlite_tmp_engine, ua, ub)

    _login_as(client, "alice", "pw1")
    r = client.delete("/admin/api/documents/dB")  # dB 属于 bob
    assert r.status_code == 403


def test_user_blocked_from_admin_endpoints(sqlite_tmp_engine, isolated_settings) -> None:
    """普通 user 访问用户管理/运维端点返回 403。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    _setup_admin(client)
    _create_user(client, "alice", "pw1", "user")
    _login_as(client, "alice", "pw1")

    assert client.get("/admin/api/users").status_code == 403
    assert client.get("/admin/api/system/config").status_code == 403
    assert client.post("/admin/api/system/reset").status_code == 403


def test_error_close_delete_permissions(sqlite_tmp_engine, isolated_settings) -> None:
    """user 仅能关闭/删除本人异常；admin 可操作全部。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    _setup_admin(client)
    ua = _create_user(client, "alice", "pw1", "user")
    ub = _create_user(client, "bob", "pw2", "user")
    _seed_docs(sqlite_tmp_engine, ua, ub)

    # alice 不能删 bob 的异常
    _login_as(client, "alice", "pw1")
    assert client.delete("/admin/api/errors/eB").status_code == 403
    # alice 能关闭自己异常
    assert client.patch("/admin/api/errors/eA/close").status_code == 200

    # admin 能删除任意
    _login_as(client, "root", "secret123")
    assert client.delete("/admin/api/errors/eB").status_code == 200


def test_me_password_change(sqlite_tmp_engine, isolated_settings) -> None:
    """个人改密：旧密码正确后可用新密码登录。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    _setup_admin(client)
    _create_user(client, "alice", "oldpw", "user")
    _login_as(client, "alice", "oldpw")

    r = client.patch(
        "/admin/api/me/password",
        json={"old_password": "oldpw", "new_password": "newpw"},
    )
    assert r.status_code == 200
    # 旧密码失效
    assert client.post("/admin/api/login", json={"username": "alice", "password": "oldpw"}).status_code == 401
    # 新密码可用
    assert client.post("/admin/api/login", json={"username": "alice", "password": "newpw"}).status_code == 200


def test_admin_create_and_deactivate_user(sqlite_tmp_engine, isolated_settings) -> None:
    """admin 创建用户并可启停/改角色。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    _setup_admin(client)
    uid = _create_user(client, "carol", "pw", "user")

    # 停用
    r = client.patch(f"/admin/api/users/{uid}", json={"is_active": False})
    assert r.status_code == 200 and r.json()["data"]["is_active"] is False
    # 改角色
    r = client.patch(f"/admin/api/users/{uid}", json={"role": "admin"})
    assert r.json()["data"]["role"] == "admin"


def test_admin_page_reachable(sqlite_tmp_engine, isolated_settings) -> None:
    """/admin/ 返回静态单页，且静态资源可访问。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    r = client.get("/admin/")
    assert r.status_code == 200
    assert "管理端" in r.text or "<!doctype html>" in r.text.lower()

    css = client.get("/admin/static/style.css")
    assert css.status_code == 200 and "text/css" in css.headers.get("content-type", "")

    js = client.get("/admin/static/app.js")
    assert js.status_code == 200


def test_admin_static_traversal_blocked(sqlite_tmp_engine, isolated_settings) -> None:
    """静态挂载不允穿越目录（防 ../ 源码泄露）。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    r = client.get("/admin/../server.py")
    # StaticFiles 会拒绝越界路径；任何情况下都不应返回源码内容
    assert "build_http_app" not in r.text
