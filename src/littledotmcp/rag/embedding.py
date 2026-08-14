"""M3-06/M7-01 Embedder 抽象、确定性 Fake 与真实后端。

- Embedder：统一向量化接口（批量 embed、维度属性）。
- FakeEmbedder：基于 SHA-256 的确定性向量（同文本同向量），带进程内缓存与
  命中计数，用于离线验收 VectorStore / kb 域，不产生任何网络调用与费用。
- EmbeddingCache：真实后端结果持久化缓存（按 model|dim|text 哈希落盘
  data/embedding_cache.jsonl），命中直接返回，避免重复计费。
- OpenAICompatEmbedder：OpenAI 兼容端点（百炼/DeepSeek/智谱等）。
- OllamaEmbedder：本地 Ollama 原生 /api/embed 端点（无需 API Key）。
- get_embedder：按 EMBEDDING_PROVIDER 返回对应实例的工厂。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import time
from pathlib import Path
from typing import Protocol

import httpx

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_DIM = 32
_DEFAULT_CACHE_FILE = "embedding_cache.jsonl"
_DIM_PROBE_TEXT = "__littledotmcp_dim_probe__"

# M10-01：模块级全局指标收集器。因 get_embedder() 每次重建 EmbeddingCache 实例，
# 实例级 hits/misses 无法跨调用累积，故用进程级 METRICS 持久累积，供 /metrics 读取。
METRICS: dict[str, int] = {
    "embedding_cache_hits": 0,
    "embedding_cache_misses": 0,
    "embed_calls": 0,
}
_METRICS_LOCK = threading.Lock()
_START_TIME = time.monotonic()


def incr(name: str, n: int = 1) -> None:
    """线程安全地累加全局指标（M10-01）。"""
    with _METRICS_LOCK:
        METRICS[name] = METRICS.get(name, 0) + n


def uptime_seconds() -> float:
    """进程已运行秒数（M10-01 /metrics 用）。"""
    return time.monotonic() - _START_TIME


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
        incr("embed_calls")
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


class EmbeddingCache:
    """真实 Embedding 结果的磁盘持久化缓存。

    - key = sha256(model|dim|text)，同文本同模型同维度必然命中；
    - 落盘 data/embedding_cache.jsonl（追加写），启动加载进内存 dict；
    - 命中/未命中有计数，供成本验证（M3-09）。
    """

    def __init__(self, cache_path: str | Path, dim: int) -> None:
        if dim < 1:
            raise ValueError("dim 必须大于 0")
        self._path = Path(cache_path)
        self._dim = dim
        self._lock = threading.Lock()
        self._data: dict[str, list[float]] = {}
        self.hits = 0
        self.misses = 0
        self._load()

    def cache_key(self, model: str, text: str) -> str:
        return hashlib.sha256(f"{model}|{self._dim}|{text}".encode("utf-8")).hexdigest()

    def get(self, key: str) -> list[float] | None:
        with self._lock:
            cached = self._data.get(key)
            if cached is not None:
                self.hits += 1
                incr("embedding_cache_hits")
                return cached
            self.misses += 1
            incr("embedding_cache_misses")
            return None

    def put(self, key: str, vec: list[float]) -> None:
        with self._lock:
            self._data[key] = vec
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"k": key, "v": vec}, ensure_ascii=False) + "\n")
            except OSError as exc:  # 缓存写入失败不应阻断主流程
                logger.warning("embedding 缓存写入失败: %s", exc)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        self._data[rec["k"]] = rec["v"]
                    except (ValueError, KeyError, TypeError):
                        continue
        except OSError as exc:
            logger.warning("embedding 缓存读取失败: %s", exc)


class OpenAICompatEmbedder:
    """OpenAI 兼容端点 Embedder（百炼/DeepSeek/智谱等，含维度探测）。"""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "",
        dim: int = 1024,
        cache: EmbeddingCache | None = None,
        timeout: float = 120.0,
    ) -> None:
        from openai import OpenAI

        self.model = model
        self.dim = dim
        self.cache = cache
        self._client = OpenAI(api_key=api_key or "sk-unset", base_url=base_url or None, timeout=timeout)

    def probe_dim(self) -> int:
        """真实模型返回的向量维度（覆盖配置默认值）。"""
        resp = self._client.embeddings.create(model=self.model, input=_DIM_PROBE_TEXT)
        return len(resp.data[0].embedding)

    def embed(self, texts: list[str]) -> list[list[float]]:
        incr("embed_calls")
        out: list[list[float]] = []
        to_fetch: list[str] = []
        keys: list[str | None] = []
        for text in texts:
            key = self.cache.cache_key(self.model, text) if self.cache else None
            if key is not None and self.cache is not None:
                cached = self.cache.get(key)
                if cached is not None:
                    out.append(cached)
                    continue
            keys.append(key)
            to_fetch.append(text)

        if to_fetch:
            resp = self._client.embeddings.create(model=self.model, input=to_fetch)
            for idx, item in enumerate(resp.data):
                vec = list(item.embedding)
                if len(vec) != self.dim:
                    logger.warning(
                        "模型 %s 实际维度 %d 与配置 %d 不一致，以实际维度为准",
                        self.model,
                        len(vec),
                        self.dim,
                    )
                    self.dim = len(vec)
                key = keys[idx] if idx < len(keys) else None
                if key is not None and self.cache is not None:
                    self.cache.put(key, vec)
                out.append(vec)
        return out


class OllamaEmbedder:
    """本地 Ollama 原生 /api/embed Embedder（无需 API Key，含维度探测）。

    base_url 接受 http://localhost:11434 或 http://localhost:11434/v1 两种写法。
    """

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        dim: int = 768,
        cache: EmbeddingCache | None = None,
        timeout: float = 300.0,
    ) -> None:
        self.model = model
        self.dim = dim
        self.cache = cache
        self._base_url = base_url.rstrip("/")
        if self._base_url.endswith("/v1"):
            self._base_url = self._base_url[: -len("/v1")]
        self._client = httpx.Client(base_url=self._base_url, timeout=timeout)

    def probe_dim(self) -> int:
        resp = self._client.post("/api/embed", json={"model": self.model, "input": _DIM_PROBE_TEXT})
        resp.raise_for_status()
        data = resp.json()
        return len(data["embeddings"][0])

    def embed(self, texts: list[str]) -> list[list[float]]:
        incr("embed_calls")
        out: list[list[float]] = []
        to_fetch: list[str] = []
        keys: list[str | None] = []
        for text in texts:
            key = self.cache.cache_key(self.model, text) if self.cache else None
            if key is not None and self.cache is not None:
                cached = self.cache.get(key)
                if cached is not None:
                    out.append(cached)
                    continue
            keys.append(key)
            to_fetch.append(text)

        if to_fetch:
            resp = self._client.post("/api/embed", json={"model": self.model, "input": to_fetch})
            resp.raise_for_status()
            data = resp.json()
            for idx, vec in enumerate(data["embeddings"]):
                vec = list(vec)
                if len(vec) != self.dim:
                    logger.warning(
                        "模型 %s 实际维度 %d 与配置 %d 不一致，以实际维度为准",
                        self.model,
                        len(vec),
                        self.dim,
                    )
                    self.dim = len(vec)
                key = keys[idx] if idx < len(keys) else None
                if key is not None and self.cache is not None:
                    self.cache.put(key, vec)
                out.append(vec)
        return out


def _cache_path(settings: Settings) -> Path:
    """缓存文件放 storage_root 同级（默认 ./data/embedding_cache.jsonl）。"""
    return settings.storage_root.parent / _DEFAULT_CACHE_FILE


def get_embedder(settings: Settings | None = None) -> Embedder:
    """按 EMBEDDING_PROVIDER 返回 Embedder 实例（默认 fake 保离线可用）。"""
    s = settings or get_settings()
    provider = (s.embedding_provider or "fake").strip().lower()
    if provider == "openai":
        if not s.embedding_api_key:
            raise ValueError("EMBEDDING_PROVIDER=openai 时需配置 EMBEDDING_API_KEY")
        cache = EmbeddingCache(_cache_path(s), s.embedding_dim)
        emb = OpenAICompatEmbedder(
            model=s.embedding_model,
            api_key=s.embedding_api_key,
            base_url=s.embedding_base_url,
            dim=s.embedding_dim,
            cache=cache,
        )
        return _with_probed_dim(emb)
    if provider == "ollama":
        cache = EmbeddingCache(_cache_path(s), s.embedding_dim)
        emb = OllamaEmbedder(
            model=s.embedding_model,
            base_url=s.embedding_base_url or "http://localhost:11434",
            dim=s.embedding_dim,
            cache=cache,
        )
        return _with_probed_dim(emb)
    return FakeEmbedder(dim=s.embedding_dim)


def _with_probed_dim(emb: OpenAICompatEmbedder | OllamaEmbedder) -> OpenAICompatEmbedder | OllamaEmbedder:
    """用真实模型探测维度覆盖配置，探测失败沿用配置（后续 embed 再校准）。"""
    try:
        emb.dim = emb.probe_dim()
        logger.info("embedding 维度探测：%s → %d", emb.model, emb.dim)
    except Exception:
        logger.warning("embedding 维度探测失败，沿用配置维度 %d", emb.dim)
    return emb
