"""M5-01 mindmap 模型测试：树 ↔ mermaid 双向转换与语法校验。"""

from __future__ import annotations

import pytest

from littledotmcp.domains.mindmap.model import (
    MindNode,
    mermaid_to_tree,
    tree_to_mermaid,
    validate_mermaid,
)

SAMPLE = """mindmap
  root((主题))
    分支A
      叶子A1
      叶子A2
    分支B
      ((圆形B1))
"""


def test_parse_roundtrip() -> None:
    root = mermaid_to_tree(SAMPLE)
    assert root.title == "主题"
    assert [c.title for c in root.children] == ["分支A", "分支B"]
    assert [c.title for c in root.children[0].children] == ["叶子A1", "叶子A2"]
    # 形状包裹被剥掉
    assert root.children[1].children[0].title == "圆形B1"


def test_render_roundtrip() -> None:
    root = mermaid_to_tree(SAMPLE)
    rendered = tree_to_mermaid(root)
    reparsed = mermaid_to_tree(rendered)
    assert reparsed == root
    assert rendered.startswith("mindmap\n")


def test_validate_ok() -> None:
    assert validate_mermaid(SAMPLE) is True


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "graph TD\n  a --> b",
        "mindmap",
        "mindmap\n  根\n  另一根",
        "mindmap\n  (( ))",
    ],
)
def test_invalid_mermaid(bad: str) -> None:
    assert validate_mermaid(bad) is False
    with pytest.raises(ValueError):
        mermaid_to_tree(bad)


def test_empty_title_rejected() -> None:
    with pytest.raises(ValueError):
        mermaid_to_tree("mindmap\n  分支A\n    (( ))\n    子X")


def test_to_dict() -> None:
    root = MindNode("主题", [MindNode("子")])
    assert root.to_dict() == {"title": "主题", "children": [{"title": "子", "children": []}]}
