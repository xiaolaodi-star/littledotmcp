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

## 知识库问答（kb_ask）与真实 Embedding

默认 `EMBEDDING_PROVIDER=fake`（离线确定性向量，零成本，无需配置即可体验 kb 域全链路）。接入真实语义能力需在 `.env` 配置：

```bash
# ---- 方式一：OpenAI 兼容端点（百炼 / DeepSeek / 智谱等）----
EMBEDDING_PROVIDER=openai
EMBEDDING_API_KEY=你的Key
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1   # 按服务商调整
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_DIM=1024        # 须与模型一致（v3=1024；Ollama 常见 768）

# ---- 方式二：本地 Ollama（无需 API Key）----
EMBEDDING_PROVIDER=ollama
EMBEDDING_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=bge-m3

# ---- 生成式问答 kb_ask 所需的 LLM ----
LLM_API_KEY=你的Key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
```

- **kb_ask(query, top_k)**：基于知识库检索 Top-K 片段，经 LLM 生成带 `【来源：标题#序号】` 引用的回答；未配置 `LLM_API_KEY` 时自动降级返回检索片段并提示。
- **成本控制**：真实 Embedding 结果按文本哈希持久化缓存到 `data/embedding_cache.jsonl`，重复内容不重复计费；`scripts/reset_data.py` 会一并清理。
- 维度以首次探测结果为准（`probe_dim()`），换模型/维度后建议重置知识库（见下）。

## 重置知识库

```bash
# 清空 data/ 下数据库、向量目录与 Embedding 缓存，重建空库（不删 .env/配置）
uv run python scripts/reset_data.py

# 清空并注入规范示例模板
STANDARD_TEMPLATES=1 uv run python scripts/reset_data.py
```

## 服务运维管理（M10）

为远程部署与真实 Embedding 后的服务提供可观测、可诊断、可统计、可重置的运维能力，严格限定服务运维，不承载业务管理。

### 指标端点 `/metrics`

远程部署（HTTPS 反代后）暴露 Prometheus 文本格式指标，仅含非敏感聚合：

```bash
curl -s https://mcp.example.com/metrics
# 示例：
# process_uptime_seconds 1234.567
# embedding_cache_hits 42
# embedding_cache_misses 8
# embedding_cache_hit_rate 0.8400
# embed_calls 50
# service_info{version="0.1.0"} 1
```

指标在进程内跨调用持续累积（缓存命中率、embed 调用次数等），可用于监控面板与降级告警。

### MCP 运维工具 `admin_*`

以下工具需在本地模式或持有共享 Token（owner 为 `local`）时调用，普通用户 Token 的 owner 非 `local` 会被拒绝：

| 工具 | 说明 |
|------|------|
| `admin_config_check` | 诊断 LLM / Embedding / 鉴权 / 存储配置就绪状态，明确降级原因 |
| `admin_tools` | 返回当前已注册 MCP 工具清单（名称 + 说明） |
| `admin_stats` | 返回当前 owner 各域数据量统计（强制 owner 隔离，普通用户仅见自己数据） |
| `admin_reset` | 一键重置（等价于 CLI `reset_data.py`），复用幂等重建空库，不删 `.env`/配置 |

> 管理权限复用 M6 共享 Token 的 local owner 语义：MCP 工具无法读取 HTTP 头，故以 `_current_owner()=="local"` 作为管理员判定，零新增鉴权模型。多用户 http 场景的细粒度管理员区分将在 M9 OAuth 落地后自然生效（L-015）。

## 管理端 Web Console（M11）

服务启动后（无论 `stdio` 还是 `http` 模式），浏览器访问 **`http://127.0.0.1:8890/admin/`** 即可进入管理端单页（登录 / 初始化、Dashboard、知识库、用户、异常、运维、个人中心六屏，离线静态页无构建/无 CDN）。stdio 模式下管理端由后台线程附带 HTTP 服务，不依赖 `MCP_AUTH_TOKEN`。

### 初始化首个管理员

空库（`users` 表为空）时二选一：

```bash
# 方式一：启动期一次性环境变量（推荐自动化部署）
export ADMIN_BOOTSTRAP_USER=admin
export ADMIN_BOOTSTRAP_PASSWORD="强密码"
uv run littledotmcp

# 方式二：浏览器打开 http://127.0.0.1:8890/admin/ 走 /admin/api/setup 表单创建
```

初始化成功后每次访问都会经 argon2 密码校验 + Session（Cookie `HttpOnly` + `SameSite=Strict`，默认 12h 过期，`ADMIN_SESSION_HOURS` 可调）。

### 角色与能力

| 角色 | 权限 |
|------|------|
| `admin` | 全部管理能力：用户增删改/启停、系统重置、全部异常与审计查看 |
| `user` | 受限视图：仅本人数据（异常等按 owner 强制隔离） |

管理端登录态独立于 MCP 用户 Token（存 `user_sessions` 表，绝不重签 `users.token`，互不干扰，见 L-020）；关键操作（用户变更、系统重置）写 `audit_logs` 审计（L-018）。管理端仅承载运维/管理，业务数据操作仍走 MCP 工具。

### 安全边界（与 L-019 一致）

- 管理端仅支持 HTTP 无证书访问，默认建议绑定 `127.0.0.1`，**仅限本地/可信内网使用**；
- 公网暴露**必须**经 `deploy/nginx.conf` / `deploy/caddy.Caddyfile` 前置 TLS 反代（`/admin` 前缀已全量反代到 127.0.0.1:8890），禁止直暴露 8890 明文端口；
- 绑定 `0.0.0.0` 启动时会输出安全告警日志；
- 会话默认 12h 过期，Cookie 防脚本读取（HttpOnly）且同站限制（SameSite=Strict）。

## 需求追溯链路（M8）

`requirement_trace(code)` 一键聚合需求端到端追溯信息：SVN 提交（经 `requirement_id`）、关联文档、标签（`related_tag` + `EntityTag`）、所属项目/里程碑（扩展 B）、状态流转时间线。强制 owner 隔离，A/B 用户互不可见。

- `svn_commit` 支持 `requirement_id` 入参，将提交关联到需求；
- `requirement_add` 支持 `project_id` / `milestone_id` 入参（扩展 B，关联项目/里程碑）；
- `requirement_link` 支持 `related_tag` / `related_commit` / `related_doc` 关联。

## 企业微信文档后端（M9，骨架 + mock 冒烟）

文档存储后端可切换：`doc_save` / `doc_read` 支持 `provider` 参数（`LOCAL` 默认 / `WECOM`）。

- `provider="LOCAL"`（默认）：原文落本地存储，行为与既有完全一致，不触碰企微；
- `provider="WECOM"`：经 `domains/doc/wecom.py` 的 `WeComDocClient` 写入/读取企微文档，`storage_key` 语义为企微 docid。

可选配置（`config.py` / `.env`）：

```bash
# 企微文档后端（M9 骨架，未接真实网络）
WECOM_CORP_ID=your_corp_id
WECOM_AGENT_ID=your_agent_id
WECOM_SECRET=your_secret
```

> 凭据缺失或企微接口失败时，`WeComDocClient` 返回可读降级结果，不会抛出未捕获异常（L-017）。真实联调前企微侧存取不可用，仅骨架与 mock 冒烟落地。

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
- [部署与使用](docs/deploy.md)（M6/M11：三种形态 / 反代 / 配置 / 重置 / 管理端 Web Console）
- [端到端验收清单](docs/acceptance.md)（M6：stdio / 远程 / 打包三形态）

## 许可

本软件为个人项目，版权归作者所有，禁止商用；未经许可不得擅自使用、复制、修改、分发或二次开发（见 LICENSE）。
