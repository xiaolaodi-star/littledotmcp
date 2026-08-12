"""M3-05 中文感知切块器：分句 + token 预算切块 + 10% 重叠 + 来源锚点。

设计：
- token 估算：中文/全角标点按单字 1 token，其余字符按 4 字符 1 token；
- 先按句子切分（保留原分隔符），贪心打包到 max_tokens（默认 800）；
- 相邻块之间保留重叠（默认 max_tokens 的 10%）；
- 单句超预算时按字符窗口硬切，避免超大块；
- 每块携带原文字符偏移锚点（start/end），供来源引用回溯。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..common.errors import ValidationError

# 中文/全角标点（按单字 1 token 估算）
_CJK = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")
# 分句边界：中英文句号/感叹/问号/分号/换行（保留分隔符）
_SENT = re.compile(r"[^。！？；;!?\n]*[。！？；;!?\n]")

DEFAULT_MAX_TOKENS = 800
DEFAULT_OVERLAP_RATIO = 0.1


@dataclass(frozen=True)
class Chunk:
    """切块结果：序号 + 内容 + 原文字符锚点。"""

    seq: int
    content: str
    start: int
    end: int


def _estimate_tokens(text: str) -> int:
    cjk = len(_CJK.findall(text))
    other = len(text) - cjk
    return cjk + other // 4


def _split_sentences(text: str) -> list[tuple[int, str]]:
    """按句切分，返回 (start, sentence) 列表（含分隔符，保留原文偏移）。"""
    sents: list[tuple[int, str]] = []
    pos = 0
    for m in _SENT.finditer(text):
        sents.append((m.start(), m.group(0)))
        pos = m.end()
    if pos < len(text):
        sents.append((pos, text[pos:]))
    return sents


def _tail(sents: list[tuple[int, str]], overlap_tokens: int) -> list[tuple[int, str]]:
    """取句子序列尾部作为下一块重叠起点（累计 token 达到 overlap 即停，至少 1 句）。"""
    tail: list[tuple[int, str]] = []
    total = 0
    for s in reversed(sents):
        total += _estimate_tokens(s[1])
        tail.append(s)
        if total >= overlap_tokens:
            break
    return list(reversed(tail))


def _hard_split(
    text: str, start: int, max_tokens: int, overlap: int
) -> list[list[tuple[int, str]]]:
    """超长句按字符窗口硬切（窗口=max_tokens 字符，步长=窗口-overlap）。"""
    step = max(1, max_tokens - overlap)
    parts: list[list[tuple[int, str]]] = []
    i = 0
    while i < len(text):
        j = min(i + max_tokens, len(text))
        parts.append([(start + i, text[i:j])])
        if j >= len(text):
            break
        i += step
    return parts


def _to_chunk(seq: int, sents: list[tuple[int, str]]) -> Chunk:
    content = "".join(s[1] for s in sents)
    return Chunk(seq=seq, content=content, start=sents[0][0], end=sents[-1][0] + len(sents[-1][1]))


def chunk_text(
    text: str,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int | None = None,
) -> list[Chunk]:
    """将文本切为带重叠的块序列（seq 从 0 起）。

    Args:
        text: 待切分纯文本。
        max_tokens: 单块 token 预算（默认 800）。
        overlap_tokens: 块间重叠 token 数；默认 max_tokens 的 10%。

    Returns:
        按序排列的 Chunk 列表；空白文本返回空列表。

    Raises:
        ValidationError: 参数非法。
    """
    if max_tokens < 1:
        raise ValidationError("max_tokens 必须大于 0")
    if overlap_tokens is not None and overlap_tokens < 0:
        raise ValidationError("overlap_tokens 不能为负")
    text = text.strip()
    if not text:
        return []
    overlap = int(max_tokens * DEFAULT_OVERLAP_RATIO) if overlap_tokens is None else overlap_tokens
    overlap = max(0, overlap)

    sentences = _split_sentences(text)
    chunks: list[list[tuple[int, str]]] = []
    cur: list[tuple[int, str]] = []
    cur_tokens = 0
    for start, sent in sentences:
        sent_tokens = _estimate_tokens(sent)
        if sent_tokens > max_tokens and not cur:
            chunks.extend(_hard_split(sent, start, max_tokens, overlap))
            continue
        if cur and cur_tokens + sent_tokens > max_tokens:
            chunks.append(cur)
            cur = _tail(cur, overlap)
            cur_tokens = sum(_estimate_tokens(s[1]) for s in cur)
        cur.append((start, sent))
        cur_tokens += sent_tokens
    if cur:
        chunks.append(cur)

    return [_to_chunk(i, c) for i, c in enumerate(chunks)]
