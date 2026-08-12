"""M3-05 golden 测试：中文感知切块器（质量/重叠/锚点/边界）。"""

from __future__ import annotations

from itertools import pairwise

import pytest

from littledotmcp.common.errors import ValidationError
from littledotmcp.rag.chunker import chunk_text


def test_empty_text_returns_empty() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_short_text_single_chunk() -> None:
    chunks = chunk_text("这是一个很短的段落。")
    assert len(chunks) == 1
    assert chunks[0].seq == 0
    assert chunks[0].start == 0
    assert chunks[0].content == "这是一个很短的段落。"


def test_seq_continuous() -> None:
    text = "第一句话。第二句话。第三句话。第四句话。" * 30
    chunks = chunk_text(text, max_tokens=50)
    assert len(chunks) >= 2
    assert [c.seq for c in chunks] == list(range(len(chunks)))


def test_anchors_align_with_source() -> None:
    text = "第一段内容。第二段内容。第三段内容。" * 20
    chunks = chunk_text(text, max_tokens=40)
    assert len(chunks) >= 2
    assert chunks[0].start == 0
    assert chunks[-1].end == len(text)
    for c in chunks:
        assert text[c.start : c.end] == c.content


def test_overlap_between_adjacent_chunks() -> None:
    text = "本段落描述第一项技术细节。" * 100
    chunks = chunk_text(text, max_tokens=50)
    assert len(chunks) >= 2
    for prev, cur in pairwise(chunks):
        # 相邻块重叠：cur 的开头内容应能在 prev 尾部找到
        assert cur.content[:5] in prev.content
        assert cur.start < prev.end


def test_long_sentence_hard_split() -> None:
    text = "字" * 2000  # 无标点超长段落 → 按字符窗口硬切
    chunks = chunk_text(text, max_tokens=100)
    assert len(chunks) >= 10
    for c in chunks:
        assert len(c.content) <= 100
        assert text[c.start : c.end] == c.content


def test_validation() -> None:
    with pytest.raises(ValidationError):
        chunk_text("abc", max_tokens=0)
    with pytest.raises(ValidationError):
        chunk_text("abc", overlap_tokens=-1)
