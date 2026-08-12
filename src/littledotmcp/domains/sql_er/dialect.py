"""方言检测（M2-01）。

关键字启发式优先：根据 Hive / Doris / Oracle / MySQL 各自的标志性语法判定方言。
调用方可显式传入 dialect 跳过检测。无法判定时返回 None，由上层给出可读提示。
"""

from __future__ import annotations

import re

# 方言别名归一
_DIALECT_ALIASES = {
    "hive": "hive",
    "hql": "hive",
    "doris": "doris",
    "mysql": "mysql",
    "oracle": "oracle",
    "plsql": "oracle",
    "ora": "oracle",
}

# 每方言标志性关键字（小写匹配），命中即高置信
_HIVE_HINTS = (
    r"\bpartitioned\s+by\b",
    r"\bstored\s+as\b",
    r"\bclustered\s+by\b",
    r"\bexternal\s+table\b",
    r"\btblproperties\b",
    r"\barray<",
    r"\bmap<",
    r"\bstruct<",
    r"\bstring\b",
)
_ORACLE_HINTS = (
    r"\bvarchar2\s*\(",
    r"\bnumber\s*\(",
    r"\b(date|timestamp)\b.*\bdefault\s+sysdate",
    r"\bclob\b",
    r"\bblob\b",
    r"\bsequence\b",
    r"\btablespace\b",
)
_DORIS_HINTS = (
    r"\bunique\s+key\s*\(",
    r"\baggregate\s+key\s*\(",
    r"\bduplicate\s+key\s*\(",
    r"\bengine\s*=\s*olap\b",
    r"\bproperties\s*\(\s*\"replication_num\"",
    r"\bbitmap\s+index\b",
)


def normalize_dialect(raw: str | None) -> str | None:
    """将用户/检测到的方言名归一为 sqlglot 接受的方言键。"""
    if not raw:
        return None
    return _DIALECT_ALIASES.get(raw.strip().lower())


def detect_dialect(ddl: str) -> str | None:
    """启发式检测 DDL 方言。

    返回 'hive'/'doris'/'oracle'/'mysql' 之一；无法判定返回 None。
    """
    text = ddl.lower()
    scores: dict[str, int] = {"hive": 0, "oracle": 0, "doris": 0, "mysql": 0}

    for pat in _HIVE_HINTS:
        if re.search(pat, text):
            scores["hive"] += 1
    for pat in _ORACLE_HINTS:
        if re.search(pat, text):
            scores["oracle"] += 1
    for pat in _DORIS_HINTS:
        if re.search(pat, text):
            scores["doris"] += 1

    # Doris 兼 MySQL 兼容语法（无 OLAP 特征时按 mysql 兜底）
    if re.search(r"\bengine\s*=\s*innodb\b", text):
        scores["mysql"] += 1

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return None
    return best
