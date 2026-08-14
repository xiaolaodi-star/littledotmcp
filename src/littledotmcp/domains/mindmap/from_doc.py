"""从文档/文本生成思维导图大纲（M5-03）。

- summarize_outline：优先调用 LLM（OpenAI 兼容 /chat/completions）提炼层级大纲，
  无 Key 或调用失败时降级按 Markdown 标题层级解析。
- _outline_from_markdown：无 LLM 时按 #/##/### 标题层级构造树。
"""

from __future__ import annotations

import json
import re
import urllib.request

from ...common.logging import get_logger
from ...config import get_settings
from .model import MindNode

logger = get_logger(__name__)

# Markdown 标题（最多 4 级，超出并入第 4 级）
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,4})\s+(.+?)\s*#*\s*$")


def _outline_from_markdown(text: str, title: str) -> MindNode:
    """按 Markdown 标题层级构造树（无 LLM 降级路径）。

    首级标题（#）作为根的直接子节点；若文本没有任何标题，整段作为单一子节点。
    """
    root = MindNode(title)
    stack: list[tuple[int, MindNode]] = [(0, root)]
    for line in (text or "").splitlines():
        m = _HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        node = MindNode(m.group(2).strip())
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1]
        parent.children.append(node)
        stack.append((level, node))
    if not root.children:
        first_line = next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), "")
        if first_line:
            root.children.append(MindNode(first_line[:80]))
    return root


def _call_llm_outline(text: str, title: str) -> str | None:
    """调用 OpenAI 兼容 LLM 提炼大纲，失败返回 None（由调用方降级）。"""
    settings = get_settings()
    if not settings.llm_api_key:
        return None
    payload = {
        "model": settings.llm_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是文档结构分析助手。请把下面的文档整理成思维导图大纲，"
                    "输出格式为 Mermaid mindmap 语法，第一行必须是 mindmap，"
                    "根节点为 ((<title>))，子节点用缩进表达层级。只输出 mindmap 代码。"
                ),
            },
            {"role": "user", "content": f"标题：{title}\n\n文档：\n{text[:12000]}"},
        ],
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        settings.llm_base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.llm_api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    content = (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return content.strip() if content else None


def summarize_outline(text: str, title: str) -> MindNode:
    """生成大纲树：优先 LLM，失败/无 Key 降级 Markdown 标题解析。"""
    try:
        llm_text = _call_llm_outline(text, title)
        if llm_text and llm_text.lower().startswith("mindmap"):
            from .model import mermaid_to_tree

            try:
                return mermaid_to_tree(llm_text)
            except ValueError:
                logger.warning("LLM 大纲非合法 mindmap，降级标题解析")
    except Exception as exc:  # 降级场景，任何 LLM 异常都不阻断
        logger.warning("LLM 大纲调用失败，降级标题解析：%s", exc)
    return _outline_from_markdown(text, title)
