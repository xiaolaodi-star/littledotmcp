"""M11-02 管理端认证骨架测试。

覆盖：空库 setup 创建管理员、登录签发 Cookie、/me 鉴权、未登录 401、登出清 Cookie、
过期会话失效、CSRF Origin 拦截。使用 Starlette TestClient 对 build_http_app 做端到端验证。
"""

from __future__ import annotations

import datetime as dt

from starlette.testclient import TestClient


def _client(sqlite_tmp_engine, isolated_settings):  # noqa: ANN001
    from littledotmcp.db.models import Base
    from littledotmcp.server import build_http_app

    Base.metadata.create_all(sqlite_tmp_engine)
    return TestClient(build_http_app())


def test_setup_creates_admin(sqlite_tmp_engine, isolated_settings) -> None:
    """空库 POST /admin/api/setup 创建首个管理员。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    resp = client.post("/admin/api/setup", json={"username": "root", "password": "secret123"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["role"] == "admin"


def test_setup_rejected_when_not_empty(sqlite_tmp_engine, isolated_settings) -> None:
    """非空库禁止重复初始化。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    client.post("/admin/api/setup", json={"username": "root", "password": "secret123"})
    resp = client.post("/admin/api/setup", json={"username": "root2", "password": "secret123"})
    assert resp.status_code == 403


def test_login_and_me(sqlite_tmp_engine, isolated_settings) -> None:
    """登录成功后 Cookie 可用，/me 返回当前用户。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    client.post("/admin/api/setup", json={"username": "root", "password": "secret123"})
    login = client.post("/admin/api/login", json={"username": "root", "password": "secret123"})
    assert login.status_code == 200, login.text
    # 检查 Set-Cookie
    assert "littledot_session" in login.headers.get("set-cookie", "")
    me = client.get("/admin/api/me")
    assert me.status_code == 200
    assert me.json()["data"]["username"] == "root"
    assert me.json()["data"]["role"] == "admin"


def test_login_wrong_password(sqlite_tmp_engine, isolated_settings) -> None:
    """错误密码返回 401。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    client.post("/admin/api/setup", json={"username": "root", "password": "secret123"})
    resp = client.post("/admin/api/login", json={"username": "root", "password": "wrong"})
    assert resp.status_code == 401


def test_me_requires_login(sqlite_tmp_engine, isolated_settings) -> None:
    """未登录访问 /me 返回 401。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    resp = client.get("/admin/api/me")
    assert resp.status_code == 401


def test_logout_clears_session(sqlite_tmp_engine, isolated_settings) -> None:
    """登出后 /me 失效。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    client.post("/admin/api/setup", json={"username": "root", "password": "secret123"})
    client.post("/admin/api/login", json={"username": "root", "password": "secret123"})
    assert client.get("/admin/api/me").status_code == 200
    logout = client.post("/admin/api/logout")
    assert logout.status_code == 200
    assert "littledot_session" in logout.headers.get("set-cookie", "")
    assert client.get("/admin/api/me").status_code == 401


def test_expired_session_rejected(sqlite_tmp_engine, isolated_settings, monkeypatch) -> None:
    """过期会话访问 /me 返回 401。"""
    import littledotmcp.console.auth as ca

    # 让新会话立即过期
    monkeypatch.setattr(ca, "SESSION_EXPIRE_HOURS", -1)
    client = _client(sqlite_tmp_engine, isolated_settings)
    client.post("/admin/api/setup", json={"username": "root", "password": "secret123"})
    client.post("/admin/api/login", json={"username": "root", "password": "secret123"})
    resp = client.get("/admin/api/me")
    assert resp.status_code == 401


def test_csrf_origin_blocked(sqlite_tmp_engine, isolated_settings) -> None:
    """跨站 Origin 的 POST 被 403 拦截。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    client.post("/admin/api/setup", json={"username": "root", "password": "secret123"})
    client.post("/admin/api/login", json={"username": "root", "password": "secret123"})
    # 登录后带跨站 Origin 调 /me（GET 不拦截，改用 logout POST 验证）
    resp = client.post(
        "/admin/api/logout",
        headers={"Origin": "http://evil.example.com"},
    )
    assert resp.status_code == 403


def test_admin_page_reachable(sqlite_tmp_engine, isolated_settings) -> None:
    """/admin/ 页面匿名可访问（返回 200 占位）。"""
    client = _client(sqlite_tmp_engine, isolated_settings)
    resp = client.get("/admin/")
    assert resp.status_code == 200
