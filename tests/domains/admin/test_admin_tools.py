"""M10 服务运维管理测试：/metrics 路由、admin_* 工具、owner 隔离、管理员权限。

覆盖：
- /metrics 返回 200 + Prometheus 文本格式 + 缓存命中率字段
- admin_config_check 返回降级提示（无 LLM key 时 ready=False）
- admin_tools 返回非空工具清单
- admin_stats 按 owner 隔离统计（A 仅见 A 数据）
- admin_reset 幂等成功；普通 owner 被拒
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

_SRC = Path(__file__).resolve().parents[3] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def _client():
    from littledotmcp.server import mcp

    return TestClient(mcp.streamable_http_app())


# ---------- /metrics 路由 ----------

def test_metrics_endpoint_returns_prometheus_text(isolated_settings):
    client = _client()
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "embedding_cache_hits" in body
    assert "embedding_cache_hit_rate" in body
    assert "process_uptime_seconds" in body


# ---------- admin_config_check ----------

def test_admin_config_check_missing_llm_key_reports_degraded(isolated_settings, sqlite_tmp_engine):
    from littledotmcp.domains.admin import tools

    isolated_settings.llm_api_key = ""
    isolated_settings.embedding_provider = "fake"
    res = tools.admin_config_check()
    assert res["success"] is True
    checks = {c["name"]: c for c in res["data"]["checks"]}
    assert checks["llm"]["ready"] is False
    assert "降级" in checks["llm"]["detail"]


def test_admin_config_check_all_ready_when_configured(isolated_settings, sqlite_tmp_engine, monkeypatch):
    from littledotmcp.domains.admin import tools
    from littledotmcp.config import get_settings

    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_API_KEY", "ek-test")
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")
    get_settings.cache_clear()
    res = tools.admin_config_check()
    assert res["success"] is True
    assert res["data"]["all_ready"] is True


# ---------- admin_tools ----------

def test_admin_tools_returns_nonempty_list(isolated_settings, sqlite_tmp_engine):
    from littledotmcp.domains.admin import tools

    res = tools.admin_tools()
    assert res["success"] is True
    assert res["data"]["count"] > 0
    names = {t["name"] for t in res["data"]["tools"]}
    assert "admin_config_check" in names
    assert "admin_reset" in names


# ---------- admin_stats owner 隔离 ----------

def test_admin_stats_owner_isolation(isolated_settings, sqlite_tmp_engine):
    from littledotmcp.db import engine as db_engine
    from littledotmcp.db.models import Base, Tag
    from littledotmcp.domains.admin import tools

    # 临时引擎建表
    Base.metadata.create_all(db_engine.engine)

    # 插入一条 owner=A 的 Tag
    with db_engine.SessionLocal() as session:
        session.add(Tag(id="tag-a-1", owner_id="user-A", name="t-a"))
        session.commit()

    # 当前 owner 恒为 local（stdio），统计不应包含 user-A 的数据
    res = tools.admin_stats()
    assert res["success"] is True
    assert res["data"]["owner"] == "local"
    assert res["data"]["counts"]["tags"] == 0


# ---------- admin_reset 权限与幂等 ----------

def test_admin_reset_denied_for_non_local_owner(isolated_settings, sqlite_tmp_engine, monkeypatch):
    from littledotmcp.domains.admin import tools

    monkeypatch.setattr(tools, "_current_owner", lambda: "user-B")
    res = tools.admin_reset()
    assert res["success"] is False
    assert "管理员" in res["message"]


def test_admin_reset_succeeds_for_local_owner(isolated_settings, sqlite_tmp_engine, monkeypatch):
    from littledotmcp.domains.admin import tools

    monkeypatch.setattr(tools, "_current_owner", lambda: "local")
    res = tools.admin_reset()
    assert res["success"] is True
    assert "已重置" in res["message"]
