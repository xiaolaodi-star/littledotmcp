"""M6-02 HTTP 鉴权/限流中间件测试。

覆盖：无 Token→401、错误 Token→401、共享 Token→放行、用户 Token→放行、
连续超额→429、reset_data 幂等。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _make_app(with_auth: bool = True, with_rate: bool = True):
    """构造带中间件的测试应用。"""
    from littledotmcp.auth_middleware import AuthMiddleware, RateLimitMiddleware

    app = Starlette()
    if with_rate:
        app.add_middleware(RateLimitMiddleware)
    if with_auth:
        app.add_middleware(AuthMiddleware)

    async def echo(request):
        return JSONResponse({"owner_id": request.scope.get("owner_id"), "ok": True})

    async def health(request):
        return JSONResponse({"status": "ok", "ok": True})

    app.add_route("/echo", echo, methods=["GET"])
    app.add_route("/health", health, methods=["GET"])
    return app


@pytest.fixture
def auth_env(isolated_settings, monkeypatch):
    """配置 MCP_AUTH_TOKEN 并清缓存，返回 (settings, token)。"""
    from littledotmcp.config import get_settings

    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-shared-token")
    get_settings.cache_clear()
    s = get_settings()
    return s, "test-shared-token"


def test_no_token_returns_401(auth_env):
    client = TestClient(_make_app())
    resp = client.get("/echo")
    assert resp.status_code == 401


def test_invalid_token_returns_401(auth_env):
    client = TestClient(_make_app())
    resp = client.get("/echo", headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401


def test_malformed_auth_header_returns_401(auth_env):
    client = TestClient(_make_app())
    resp = client.get("/echo", headers={"Authorization": "Basic abc"})
    assert resp.status_code == 401


def test_shared_token_allowed(auth_env):
    _, token = auth_env
    client = TestClient(_make_app())
    resp = client.get("/echo", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["owner_id"] == "local"


def test_health_path_public(auth_env):
    """健康检查路径免鉴权。"""
    client = TestClient(_make_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_user_token_allowed(auth_env, sqlite_tmp_engine):
    """用户 Token（M1-05 令牌体系）同样可放行。"""
    from littledotmcp.auth import login, register
    from littledotmcp.db.models import Base

    Base.metadata.create_all(sqlite_tmp_engine)
    register("alice", "secret-pw", "Alice")
    info = login("alice", "secret-pw")

    client = TestClient(_make_app())
    resp = client.get("/echo", headers={"Authorization": f"Bearer {info['token']}"})
    assert resp.status_code == 200
    assert resp.json()["owner_id"] == info["user_id"]


def test_rate_limit_returns_429(auth_env):
    """低阈值下连续请求超额返回 429。"""
    from littledotmcp.auth_middleware import RateLimitMiddleware

    app = Starlette()

    async def echo(request):
        return JSONResponse({"ok": True})

    app.add_route("/echo", echo, methods=["GET"])
    app.add_middleware(RateLimitMiddleware, rate=3, per_seconds=60)
    client = TestClient(app)
    for _ in range(3):
        assert client.get("/echo").status_code == 200
    assert client.get("/echo").status_code == 429


def test_rate_limit_resets_after_window(auth_env):
    """令牌随时间补充，窗口后恢复放行。"""
    from littledotmcp.auth_middleware import RateLimitMiddleware

    app = Starlette()

    async def echo(request):
        return JSONResponse({"ok": True})

    app.add_route("/echo", echo, methods=["GET"])
    app.add_middleware(RateLimitMiddleware, rate=1, per_seconds=1)
    client = TestClient(app)
    assert client.get("/echo").status_code == 200
    assert client.get("/echo").status_code == 429
    import time

    time.sleep(1.1)
    assert client.get("/echo").status_code == 200


def test_reset_data_idempotent(isolated_settings, tmp_data_dir, monkeypatch):
    """reset_data 幂等：首次清库，二次无待清理，均重建空库。"""
    from sqlalchemy import create_engine

    import littledotmcp.db.engine as engine_mod
    from littledotmcp.config import get_settings

    s = get_settings()
    db_file = Path(str(s.db_url).replace("sqlite:///", "", 1))
    assert not db_file.exists()

    # patch engine 指向隔离 db（与 settings.db_url 一致）
    eng = create_engine(
        s.db_url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        future=True,
    )
    monkeypatch.setattr(engine_mod, "engine", eng)

    # 造一点数据（先建库）
    from littledotmcp.db.models import Base

    Base.metadata.create_all(eng)
    (tmp_data_dir / "vectors" / "dummy.bin").write_bytes(b"x")
    assert db_file.exists()

    # scripts 非包目录，加入 sys.path 后按模块导入
    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    import reset_data as reset_mod

    # 首次重置：删除 db 与向量目录，重建空库
    assert reset_mod.reset_data() == 0
    assert db_file.exists()  # 重建后的空库
    assert not (tmp_data_dir / "vectors").exists()

    # 二次重置：无待清理，依然成功
    assert reset_mod.reset_data() == 0
    assert db_file.exists()
    eng.dispose()
