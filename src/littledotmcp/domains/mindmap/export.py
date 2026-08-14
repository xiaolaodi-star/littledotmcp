"""思维导图导出（M5-02）：树结构 → OPML XML。

OPML（Outline Processor Markup Language）为 XMind / FreeMind 通用导入格式，
outline 嵌套表示层级，text 属性承载节点标题。
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from .model import MindNode


def _outline_xml(node: MindNode, indent: int) -> list[str]:
    """递归渲染单节点的 <outline> 行。"""
    prefix = "  " * indent
    # XML 属性内的双引号必须转义，escape 默认不处理，需显式补充
    quoted = escape(node.title, {'"': "&quot;"})
    lines = [f'{prefix}<outline text="{quoted}">']
    for child in node.children:
        lines.extend(_outline_xml(child, indent + 1))
    lines.append(f"{prefix}</outline>")
    return lines


def tree_to_opml(root: MindNode, title: str = "mindmap") -> str:
    """将树渲染为 OPML XML 文本（UTF-8，含 XML 声明）。"""
    head = (
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<opml version=\"2.0\">",
        "  <head>",
        f"    <title>{escape(title)}</title>",
        "  </head>",
        "  <body>",
    )
    body = _outline_xml(root, 2)
    tail = ("  </body>", "</opml>")
    return "\n".join((*head, *body, *tail)) + "\n"
