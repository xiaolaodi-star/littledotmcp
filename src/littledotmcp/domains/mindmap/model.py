"""Mermaid mindmap 树模型与双向转换（M5-01）。

- MindNode：思维导图树节点（title + children）
- mermaid_to_tree / tree_to_mermaid：Mermaid mindmap 文本 ↔ 树 双向转换
- validate_mermaid：语法校验（非法输入抛 ValueError，含可读信息）
"""

from __future__ import annotations

import re
from collections.abc import Iterable


class MindNode:
    """思维导图树节点。"""

    def __init__(self, title: str, children: Iterable[MindNode] | None = None) -> None:
        self.title = title
        self.children: list[MindNode] = list(children) if children is not None else []

    def depth_first(self) -> list[MindNode]:
        """先序遍历全部节点（含自身）。"""
        nodes = [self]
        for child in self.children:
            nodes.extend(child.depth_first())
        return nodes

    def to_dict(self) -> dict:
        """转为可 JSON 序列化的字典。"""
        return {
            "title": self.title,
            "children": [c.to_dict() for c in self.children],
        }

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MindNode):
            return False
        return self.title == other.title and self.children == other.children

    def __repr__(self) -> str:
        return f"MindNode({self.title!r}, {len(self.children)} children)"


_ID_PREFIX_RE = re.compile(r"^[A-Za-z0-9_\-]+\(\((.*)\)\)$", re.DOTALL)


def _strip_shape(text: str) -> str:
    """去掉 mermaid 节点形状包裹，仅保留标题文本。

    支持 ((...))、[[...]]、[...]、(...)、{...} 等常见形状，
    以及 mermaid 根节点常见的 id((...)) 写法（如 root((主题))）。
    """
    stripped = text.strip()
    if stripped.startswith("((") and stripped.endswith("))") and len(stripped) >= 4:
        return stripped[2:-2].strip()
    m = _ID_PREFIX_RE.match(stripped)
    if m:
        return m.group(1).strip()
    for open_, close in (("[[", "]]"), ("[", "]"), ("(", ")"), ("{", "}")):
        if (
            stripped.startswith(open_)
            and stripped.endswith(close)
            and len(stripped) >= len(open_) + len(close)
        ):
            return stripped[len(open_):-len(close)].strip()
    return stripped


def mermaid_to_tree(mermaid: str) -> MindNode:
    """解析 Mermaid mindmap 文本为树结构。

    规则：
    - 首行必须为 mindmap 关键字（不参与树）
    - 首个内容节点为根，缩进以其为基准
    - 节点缩进必须严格大于其父节点；只允许一个根

    非法输入抛 ValueError（含可读信息），由调用方转为 fail()。
    """
    lines = [ln for ln in (mermaid or "").splitlines() if ln.strip()]
    if not lines or lines[0].strip().lower() != "mindmap":
        raise ValueError("Mermaid 文本必须以 'mindmap' 关键字开头")
    body = lines[1:]
    if not body:
        raise ValueError("思维导图没有内容节点")

    parsed: list[tuple[int, str]] = []
    for ln in body:
        raw = ln.replace("\t", "  ")
        text = raw.lstrip(" ")
        indent = len(raw) - len(text)
        title = _strip_shape(text)
        if not title:
            raise ValueError(f"存在空标题节点：{ln.strip()!r}")
        parsed.append((indent, title))

    root_indent = parsed[0][0]
    root = MindNode(parsed[0][1])
    stack: list[tuple[int, MindNode]] = [(root_indent, root)]
    for indent, title in parsed[1:]:
        if indent <= root_indent:
            raise ValueError(f"思维导图只允许一个根节点，出现多余根：{title!r}")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if not stack:
            raise ValueError(f"缩进层级异常：{title!r}")
        node = MindNode(title)
        stack[-1][1].children.append(node)
        stack.append((indent, node))
    return root


def tree_to_mermaid(root: MindNode) -> str:
    """将树渲染为 Mermaid mindmap 文本（2 空格/级）。"""
    lines = ["mindmap", f"  {root.title}"]

    def walk(node: MindNode, level: int) -> None:
        for child in node.children:
            lines.append("  " * (level + 1) + child.title)
            walk(child, level + 1)

    walk(root, 1)
    return "\n".join(lines)


def validate_mermaid(mermaid: str) -> bool:
    """校验 Mermaid 文本是否合法（不抛异常）。"""
    try:
        mermaid_to_tree(mermaid)
        return True
    except ValueError:
        return False
