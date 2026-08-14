<!--
部署与使用文档（M6-06）
覆盖：环境要求、三种启动形态、远程 HTTPS 反代、知识库重置、打包交付。
任务事实源见 PLAN.md M6-01~06。
-->

# 部署与使用文档

> 维护者：朱世航 ｜ 最后更新：2026-08-14

## 1. 环境要求

- Python 3.12 + [uv](https://docs.astral.sh/uv/)（推荐）
- 操作系统：Windows / Linux / macOS（SVN 域需另装 svn 客户端，见 L-004）
- 可选：OpenAI 兼容 LLM Key（`LLM_API_KEY`），无 Key 时相关能力自动降级

## 2. 三种启动形态

### 2.1 本机 stdio（默认，供本地 MCP 客户端接入）

```bash
uv sync
uv run littledotmcp
```

客户端配置（以 Claude Desktop / 兼容客户端为例）：

```json
{
  "mcpServers": {
    "littledotmcp": {
      "command": "uv",
      "args": ["--directory", "/path/to/littledotmcp", "run", "littledotmcp"]
    }
  }
}
```

### 2.2 远程 streamable-http（服务端常驻）

```bash
export MCP_TRANSPORT=http
export MCP_AUTH_TOKEN="请设置强随机 Token"   # http 模式必填，未配置拒绝启动
export HTTP_HOST=0.0.0.0
export HTTP_PORT=8890
uv run littledotmcp
```

远程客户端接入 JSON：

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

### 2.3 源码运行（开发/调试）

```bash
uv run python -m littledotmcp
```

## 3. HTTPS 反代（远程推荐）

远程部署务必经 HTTPS，禁止直接暴露 8890 明文端口。

### Nginx（`deploy/nginx.conf`）

1. 将 `mcp.example.com` 改为真实域名，证书路径改为实际值；
2. 放入 `/etc/nginx/conf.d/` 后 `nginx -t && nginx -s reload`；
3. 或使用 `certbot --nginx` 自动签发证书。

### Caddy（`deploy/caddy.Caddyfile`，自动 HTTPS）

```bash
caddy run --config deploy/caddy.Caddyfile
```

Caddy 首次访问自动申请 Let's Encrypt 证书，无需手工配置。

## 4. 配置项（`.env` / 环境变量）

| 变量 | 默认 | 说明 |
|------|------|------|
| `MCP_TRANSPORT` | `stdio` | `stdio` 或 `http` |
| `MCP_AUTH_TOKEN` | 空 | http 模式必填；远程 Bearer 共享密钥 |
| `HTTP_HOST` | `0.0.0.0` | http 监听地址 |
| `HTTP_PORT` | `8890` | http 监听端口 |
| `DB_URL` | `sqlite:///./data/littledotmcp.db` | 业务库 |
| `STORAGE_ROOT` | `./data/files` | 文档/文件存储根目录 |
| `VECTOR_DIR` | `./data/vectors` | 向量库目录 |
| `LOG_DIR` | `./data/logs` | 日志目录 |
| `STANDARD_TEMPLATES` | 空 | 置 `1` 时首次启动注入规范示例模板 |

## 5. 知识库重置

```bash
# 仅清空数据（重建空库，不影响 .env 配置）
uv run python scripts/reset_data.py

# 清空并注入规范示例模板
STANDARD_TEMPLATES=1 uv run python scripts/reset_data.py
```

重置会删除 `data/` 下数据库与向量目录，不可恢复；不会删除 `.env`/配置。

## 6. 打包交付（给别人用）

```bash
uv build
# 产物：dist/littledotmcp-0.1.0-py3-none-any.whl
#      dist/littledotmcp-0.1.0.tar.gz
```

接收方安装：

```bash
uvx --from littledotmcp-0.1.0-py3-none-any.whl littledotmcp
# 或
uv tool install littledotmcp-0.1.0-py3-none-any.whl
littledotmcp
```

首次启动自动建库（空知识库，无用户数据）；`STANDARD_TEMPLATES=1` 可选注入模板。

## 7. 健康检查

- `GET /health` → `{"status": "ok", "service": "littledotmcp"}`（免鉴权，供反代探测）
- 其余路径一律要求 `Authorization: Bearer <token>`

## 8. 常见问题

- **http 启动即退出**：未设置 `MCP_AUTH_TOKEN`。远程模式强制要求，见配置表。
- **反代 502**：确认 8890 已监听、`/mcp` 前缀与 `location /mcp` 匹配。
- **权限问题（Linux）**：`data/` 需运行用户可写。
