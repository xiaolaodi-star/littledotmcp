"""M5-03 from_doc 测试：无 Key 降级标题解析、LLM 结果解析、异常降级。"""

from __future__ import annotations

import pytest

from littledotmcp.domains.mindmap import from_doc
from littledotmcp.domains.mindmap.from_doc import _outline_from_markdown, summarize_outline

DOC = """# 第一章

## 1.1 背景
## 1.2 目标

# 第二章

## 2.1 方案
"""


def test_outline_from_markdown() -> None:
    root = _outline_from_markdown(DOC, "文档")
    assert [c.title for c in root.children] == ["第一章", "第二章"]
    assert [c.title for c in root.children[0].children] == ["1.1 背景", "1.2 目标"]


def test_outline_from_markdown_no_headings() -> None:
    root = _outline_from_markdown("   \n纯文本段落，没有标题\n  ", "文档")
    assert len(root.children) == 1
    assert root.children[0].title == "纯文本段落，没有标题"


def test_summarize_degrade_without_key(isolated_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    isolated_settings.llm_api_key = ""
    monkeypatch.setattr(from_doc, "get_settings", lambda: isolated_settings)
    root = summarize_outline(DOC, "文档")
    assert root.title == "文档"
    assert len(root.children) == 2


def test_summarize_uses_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_call(text: str, title: str) -> str:
        return "mindmap\n  ((AI大纲))\n    要点1"

    monkeypatch.setattr(from_doc, "_call_llm_outline", fake_call)
    root = summarize_outline("任意文本", "文档")
    assert root.title == "AI大纲"
    assert [c.title for c in root.children] == ["要点1"]


def test_summarize_degrade_on_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(text: str, title: str) -> str:
        raise RuntimeError("api down")

    monkeypatch.setattr(from_doc, "_call_llm_outline", boom)
    root = summarize_outline(DOC, "文档")
    assert root.title == "文档"


def test_summarize_degrade_on_bad_mermaid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        from_doc, "_call_llm_outline", lambda text, title: "mindmap\n  根\n  另一根"
    )
    root = summarize_outline(DOC, "文档")
    assert root.title == "文档"
