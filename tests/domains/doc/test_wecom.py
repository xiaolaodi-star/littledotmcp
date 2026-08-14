"""M9 企业微信文档后端测试：mock 冒烟 / 凭据缺失降级 / provider 切换不破 LOCAL。"""

from __future__ import annotations

import pytest

from littledotmcp.db import Base, engine as db_engine
from littledotmcp.domains.doc import tools as doc_tools
from littledotmcp.domains.doc import wecom as wecom_mod


@pytest.fixture
def schema(sqlite_tmp_engine) -> None:
    Base.metadata.create_all(sqlite_tmp_engine)


def _set_owner(monkeypatch: pytest.MonkeyPatch, owner: str) -> None:
    monkeypatch.setattr(doc_tools, "_current_owner", lambda: owner)


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, token_payload, doc_payload) -> None:
    """monkeypatch httpx.get/post 返回可控响应。"""
    captured = {}

    def _get(url, **kwargs):
        captured["get_url"] = url
        return _Resp(token_payload)

    def _post(url, **kwargs):
        captured["post_url"] = url
        captured["post_json"] = kwargs.get("json")
        return _Resp(doc_payload)

    monkeypatch.setattr(wecom_mod.httpx, "get", _get)
    monkeypatch.setattr(wecom_mod.httpx, "post", _post)
    return captured


def test_configured_false_when_missing() -> None:
    c = wecom_mod.WeComDocClient("", "", "")
    assert c.configured is False


def test_degrade_without_credentials() -> None:
    c = wecom_mod.WeComDocClient("", "", "")
    ok_flag, token, msg = c._get_token()
    assert ok_flag is False
    assert "未配置" in msg
    ok_flag, docs, msg = c.list_docs()
    assert ok_flag is False and docs == []
    ok_flag, text, msg = c.read_doc("x")
    assert ok_flag is False and text == ""
    ok_flag, doc_id, msg = c.write_doc("n", "c")
    assert ok_flag is False and doc_id == ""


def test_token_failure_degrades(
    isolated_settings, schema, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = wecom_mod.WeComDocClient("cid", "aid", "sec")
    _patch_httpx(monkeypatch, {"errcode": 1, "errmsg": "bad"}, {})
    ok_flag, token, msg = c._get_token()
    assert ok_flag is False
    assert "bad" in msg


def test_write_read_mock_smoke(
    isolated_settings, schema, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = wecom_mod.WeComDocClient("cid", "aid", "sec")
    captured = _patch_httpx(
        monkeypatch,
        {"errcode": 0, "access_token": "TOK"},
        {"errcode": 0, "docid": "DOC-1", "content": "hello world"},
    )
    ok_flag, doc_id, msg = c.write_doc("name", "hello world")
    assert ok_flag is True and doc_id == "DOC-1"
    ok_flag, text, msg = c.read_doc("DOC-1")
    assert ok_flag is True and text == "hello world"


def test_doc_save_wecom_and_read(
    isolated_settings, schema, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_owner(monkeypatch, "alice")
    c = wecom_mod.WeComDocClient("cid", "aid", "sec")
    captured = _patch_httpx(
        monkeypatch,
        {"errcode": 0, "access_token": "TOK"},
        {"errcode": 0, "docid": "DOC-9", "content": "企微内容"},
    )
    # 注入 client 构造，使 build_wecom_client 返回带 mock 的实例
    monkeypatch.setattr(doc_tools, "build_wecom_client", lambda: c)

    r = doc_tools.doc_save("wecom.md", content="企微内容", provider="WECOM")
    assert r["success"] is True, r
    doc_id = r["data"]["id"]
    # 元数据 provider 应为 WECOM
    with db_engine.SessionLocal() as s:
        from littledotmcp.db.models import Document

        d = s.get(Document, doc_id)
        assert d.provider == "WECOM"
        assert d.storage_key == "DOC-9"

    rr = doc_tools.doc_read(doc_id, provider="WECOM")
    assert rr["success"] is True
    assert rr["data"]["content"] == "企微内容"
    assert rr["data"]["provider"] == "WECOM"


def test_local_unchanged_when_provider_default(
    isolated_settings, schema, monkeypatch: pytest.MonkeyPatch
) -> None:
    """默认 provider=LOCAL 行为不变（不触碰企微）。"""
    _set_owner(monkeypatch, "alice")
    captured = {}
    monkeypatch.setattr(wecom_mod.httpx, "post", lambda *a, **k: captured.setdefault("called", True))
    r = doc_tools.doc_save("local.md", content="local content")
    assert r["success"] is True
    assert r["data"]["id"]
    # 企微未被调用
    assert "called" not in captured
    rr = doc_tools.doc_read(r["data"]["id"])
    assert rr["success"] is True
    assert rr["data"]["content"] == "local content"
    assert "called" not in captured
