"""kb 域本地关键词检索：BM25 零依赖自实现（M3-08）。

个人规模下对全量 chunk 文本线性打分即可；语义召回由向量 Top-K 承担，
两者分数归一融合后输出（见 kb/tools.kb_search）。
"""

from __future__ import annotations

import math
import re

_TOKEN = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]")
_K1 = 1.5
_B = 0.75


def tokenize(text: str) -> list[str]:
    """英文单词 + 中文单字切词（小写）。"""
    return _TOKEN.findall(text.lower())


def bm25_scores(query: str, docs: list[str]) -> list[float]:
    """对每个 doc 计算与 query 的 BM25 分数，返回与 docs 一一对应的列表。"""
    q_tokens = set(tokenize(query))
    if not q_tokens or not docs:
        return [0.0] * len(docs)
    n = len(docs)
    avgdl = sum(len(d) for d in docs) / n
    idf: dict[str, float] = {}
    for term in q_tokens:
        df = sum(1 for d in docs if term in d)
        idf[term] = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
    scores: list[float] = []
    for d in docs:
        dl = len(d)
        score = 0.0
        for term in q_tokens:
            tf = d.count(term)
            if tf == 0:
                continue
            denom = tf + _K1 * (1.0 - _B + _B * dl / avgdl)
            score += idf[term] * (tf * (_K1 + 1.0)) / denom
        scores.append(score)
    return scores
