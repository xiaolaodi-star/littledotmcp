"""M3-06 Embedder 抽象与确定性 FakeEmbedder。

- Embedder：统一向量化接口（批量 embed、维度属性）；真实 OpenAI 兼容 / Ollama
  后端在 M7 里程碑实现同一接口即可热插拔（用户决策剥离联网调用）。
- FakeEmbedder：基于 SHA-256 的确定性向量（同文本同向量），带进程内缓存与
  命中计数，用于离线验收 VectorStore / kb 域，不产生任何网络调用与费用。
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

DEFAULT_DIM = 32


class Embedder(Protocol):
    """向量化抽象：批量接口 + 维度属性。"""

    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbedder:
    """确定性哈希向量（仅供离线测试/验收，非语义模型）。

    - 同文本必然同向量（可验证 embedding 缓存命中）；
    - 向量已归一化（L2=1），可直接用于余弦相似度。
    """

    def __init__(self, dim: int = DEFAULT_DIM) -> None:
        if dim < 1:
            raise ValueError("dim 必须大于 0")
        self.dim = dim
        self._cache: dict[str, list[float]] = {}
        self.hits = 0
        self.misses = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            cached = self._cache.get(text)
            if cached is not None:
                self.hits += 1
                out.append(cached)
                continue
            self.misses += 1
            vec = self._make(text)
            self._cache[text] = vec
            out.append(vec)
        return out

    def _make(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        raw = [((digest[i % len(digest)] / 255.0) * 2 - 1) for i in range(self.dim)]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]
