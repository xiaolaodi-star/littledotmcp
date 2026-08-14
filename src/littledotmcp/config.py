"""应用配置加载（S0.3）。

所有密钥仅经 .env / 环境变量注入，绝不明文入库。
配置读取优先级：默认值 < .env < 环境变量。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。"""

    # ---- 运行模式 ----
    mcp_transport: str = Field(
        default="stdio",
        description="stdio：本地被 MCP 客户端拉起；http：服务端远程（streamable-http）",
    )

    # ---- 鉴权（http 模式必填）----
    mcp_auth_token: str = Field(default="", description="远程调用 Bearer Token，http 模式必填")

    # ---- LLM / Embedding（M3 知识库起需要）----
    llm_base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    llm_api_key: str = Field(default="")
    llm_model: str = Field(default="qwen-plus")
    embedding_base_url: str = Field(default="")
    embedding_api_key: str = Field(default="")
    embedding_model: str = Field(default="text-embedding-v3")
    embedding_provider: str = Field(
        default="fake",
        description="openai：OpenAI 兼容端点；ollama：本地 Ollama；fake：离线确定性向量",
    )
    embedding_dim: int = Field(
        default=32,
        description="向量维度：openai(百炼 v3)=1024、Ollama 常见 768、fake=32",
    )

    # ---- 存储（默认全走本地目录，零外部中间件）----
    db_url: str = Field(default="sqlite:///./data/littledotmcp.db")
    storage_root: Path = Field(default=Path("./data/files"))
    vector_dir: Path = Field(default=Path("./data/vectors"))

    # ---- 企业微信（M3 可选）----
    wecom_corp_id: str = Field(default="")
    wecom_agent_id: str = Field(default="")
    wecom_secret: str = Field(default="")

    # ---- 服务端（M6）----
    http_host: str = Field(default="0.0.0.0")
    http_port: int = Field(default=8890)

    # ---- 日志 ----
    log_level: str = Field(default="INFO")
    log_dir: Path = Field(default=Path("./logs"))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    def require_http_auth(self) -> str:
        """http 模式下返回必填鉴权 Token，缺失即抛错。"""
        if self.mcp_transport == "http" and not self.mcp_auth_token:
            raise ValueError("MCP_TRANSPORT=http 时 MCP_AUTH_TOKEN 为必填项")
        return self.mcp_auth_token


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """进程内单例配置。"""
    return Settings()
