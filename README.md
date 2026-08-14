# littledotmcp — 个人 MCP 开发工具箱

通过 [MCP（Model Context Protocol）](https://modelcontextprotocol.io) 向任意 MCP 客户端（Claude Desktop / Cursor / CodeBuddy 等）暴露个人开发工作能力：

| 域 | 能力 |
|----|------|
| sql-er | 根据 Hive / Doris / Oracle DDL 生成 Mermaid ER 图 |
| sql-validate | 三方言 SQL 脚本静态校验（可选真实库 JDBC 校验） |
| doc | 文档管理：本地文件 / 企业微信，存储后端可切换 |
| svn | SVN 操作：checkout / update / commit / log / diff / blame / status |
| mindmap | Mermaid 思维导图生成、OPML 导出（可导入 XMind） |
| standard | 规范要求（命名 / SQL / 提交 / 上线清单）注册与检索 |
| kb | 个人问答知识库（RAG，按用户隔离） |
| project | 项目 / 里程碑 / 任务三级进度管理 |
| tag | 跨实体（需求 / 文档 / 项目 / 知识库）通用标签 |
| requirement | 需求生命周期：评估 → 开发 → 上线，全程可追溯 |

## 形态

- 个人本地：`stdio` 传输，被 MCP 客户端拉起
- 服务端远程：`streamable-http` + HTTPS + Token 鉴权
- 打包给别人：uv 可执行/源码包 + 空知识库初始化，每人只用自己导入的知识

## 环境要求

- Python 3.12（本仓库 `.python-version` 固定 3.12）
- 可选：svn 客户端（M4）、企业微信凭据（M3）、LLM API Key（M3 起）

## 快速开始

```bash
# 1. 安装依赖（uv 自动按 .python-version 创建 .venv）
uv sync

# 2. 运行测试
uv run pytest

# 3. 配置（可选，默认即可跑通）
copy .env.example .env

# 4. 启动（stdio，供 MCP 客户端配置使用）
uv run littledotmcp
```

MCP 客户端配置示例：

```json
{
  "mcpServers": {
    "littledotmcp": {
      "command": "uv",
      "args": ["run", "littledotmcp"]
    }
  }
}
```

## 服务端远程部署（streamable-http）

```bash
# 1. 配置（http 模式必须设置强随机 Token，否则拒绝启动）
export MCP_TRANSPORT=http
export MCP_AUTH_TOKEN="请设置强随机Token"
export HTTP_HOST=0.0.0.0
export HTTP_PORT=8890

# 2. 启动
uv run littledotmcp
```

远程 MCP 客户端配置：

```json
{
  "mcpServers": {
    "littledotmcp": {
      "type": "http",
      "url": "https://mcp.example.com/mcp",
      "headers": { "Authorization": "Bearer 你的Token" }
    }
  }
}
```

远程部署必须经 HTTPS 反代（禁止直暴露 8890 明文端口），模板见 `deploy/nginx.conf`（Nginx）与 `deploy/caddy.Caddyfile`（Caddy 自动 HTTPS）；`GET /health` 免鉴权供反代探测，其余路径一律要求 Bearer Token 且按 IP 限流。详细步骤见 [部署文档](docs/deploy.md)。

## 重置知识库

```bash
# 清空 data/ 下数据库与向量目录，重建空库（不删 .env/配置）
uv run python scripts/reset_data.py

# 清空并注入规范示例模板
STANDARD_TEMPLATES=1 uv run python scripts/reset_data.py
```

## 打包交付

```bash
uv build   # 产物在 dist/（wheel + sdist）
# 接收方：uv tool install littledotmcp-0.1.0-py3-none-any.whl
# 首次启动自动建库（空知识库），每人只用自己导入的数据
```

## 文档

- [任务计划（WBS）](docs/PLAN.md) — 详细规范化任务清单与进度，**项目唯一任务事实来源**
- [架构设计](docs/architecture.md)（随里程碑回写）
- [已知限制](docs/limitations.md)（随里程碑维护）
- [部署与使用](docs/deploy.md)（M6：三种形态 / 反代 / 配置 / 重置）
- [端到端验收清单](docs/acceptance.md)（M6：stdio / 远程 / 打包三形态）

## 许可

本软件为个人项目，版权归作者所有，禁止商用；未经许可不得擅自使用、复制、修改、分发或二次开发（见 LICENSE）。
