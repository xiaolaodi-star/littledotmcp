"""M5-02 OPML 导出测试：结构合法、转义正确、可 XML 解析。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from littledotmcp.domains.mindmap.export import tree_to_opml
from littledotmcp.domains.mindmap.model import MindNode, mermaid_to_tree


def test_opml_structure() -> None:
    root = MindNode("主题", [MindNode("分支A", [MindNode("叶子A1")]), MindNode("分支B")])
    opml = tree_to_opml(root, "我的导图")
    doc = ET.fromstring(opml)  # 可解析即合法
    outlines = doc.findall(".//outline")
    assert len(outlines) == 4
    assert doc.find("./head/title").text == "我的导图"  # type: ignore[union-attr]
    assert outlines[0].attrib["text"] == "主题"
    assert outlines[1].attrib["text"] == "分支A"
    assert outlines[2].attrib["text"] == "叶子A1"


def test_opml_escape() -> None:
    root = MindNode('A&B <tag> "q"', [MindNode("x<y")])
    opml = tree_to_opml(root)
    assert "&amp;" in opml and "&lt;" in opml and "&quot;" in opml
    doc = ET.fromstring(opml)
    assert doc.find(".//outline").attrib["text"] == 'A&B <tag> "q"'  # type: ignore[union-attr]


def test_opml_from_mermaid() -> None:
    mermaid = "mindmap\n  root((主题))\n    子节点"
    root = mermaid_to_tree(mermaid)
    opml = tree_to_opml(root)
    doc = ET.fromstring(opml)
    texts = [o.attrib["text"] for o in doc.findall(".//outline")]
    assert texts == ["主题", "子节点"]
