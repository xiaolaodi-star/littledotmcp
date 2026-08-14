<!--
部署与使用文档（M6-06 + M11）
覆盖：环境要求、三种启动形态、远程 HTTPS 反代、知识库重置、打包交付、管理端 Web Console。
任务事实源见 PLAN.md M6-01~06 与 M11-01~06。
-->

# 部署与使用文档

> 维护者：朱世航 ｜ 最后更新：2026-08-14（M11 管理端补充）

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

> 注：http 模式同时提供管理端 Web Console（M11），同端口访问 `/admin/`，详见 §8。

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
| `HTTP_HOST` | `0.0.0.0` | http 监听地址；默认全网卡且**明文无证书**，远程暴露务必前置 HTTPS 反代，否则启动会打印安全告警 |
| `HTTP_PORT` | `8890` | http 监听端口 |
| `DB_URL` | `sqlite:///./data/littledotmcp.db` | 业务库 |
| `STORAGE_ROOT` | `./data/files` | 文档/文件存储根目录 |
| `VECTOR_DIR` | `./data/vectors` | 向量库目录 |
| `LOG_DIR` | `./data/logs` | 日志目录 |
| `STANDARD_TEMPLATES` | 空 | 置 `1` 时首次启动注入规范示例模板 |
| `ADMIN_BOOTSTRAP_USER` | 空 | 一次性引导：空库首次启动自动创建的管理员用户名（须与 `ADMIN_BOOTSTRAP_PASSWORD` 配对） |
| `ADMIN_BOOTSTRAP_PASSWORD` | 空 | 一次性引导：与 `ADMIN_BOOTSTRAP_USER` 配对使用，建号后即失效（不设则走 §8.2 浏览器 setup 表单） |
| `ADMIN_SESSION_HOURS` | `12` | 管理端登录会话有效期（小时） |

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
- `GET /admin/` 需登录（未登录 302 至登录页）；`/admin/api/*` 除 `login`/`setup` 外均要求携带管理端 Session Cookie（`littledot_session`）
- 其余路径一律要求 `Authorization: Bearer <token>`

## 8. 管理端 Web Console（M11）

M11 在 http 模式下随进程提供一套内嵌 Web 管理端（同端口、同进程），用于日常管理业务数据，与 MCP 接口并存互不干扰。

### 8.1 访问地址

- 管理端入口：`http://127.0.0.1:8890/admin/`（即 http 监听端口 + `/admin/` 前缀）
- 管理 API：`/admin/api/*`（`login` / `logout` / `me` / `setup` / `documents` / `kb` / `users` / `errors` / `system/*`）
- 静态资源：`/admin/static/*`

### 8.2 首次初始化管理员（二选一）

**方式一：环境变量自动引导（推荐脚本化）**

启动前设置一次性环境变量，空库首次启动时自动创建管理员：

```bash
export ADMIN_BOOTSTRAP_USER=admin
export ADMIN_BOOTSTRAP_PASSWORD="强密码，勿用默认值"
uv run littledotmcp
```

- 仅 `users` 表为空时生效；库非空则跳过并打印日志；
- 建号后环境变量即完成使命，不设任何持久化默认口令；
- 未设置该变量时，可改走方式二。

**方式二：浏览器 setup 表单**

空库启动后直接访问 `http://127.0.0.1:8890/admin/`，页面走 `/admin/api/setup` 创建首个管理员；库非空时该路由自动关闭。

> 两种方式都杜绝"默认口令"：不初始化则无法登录管理端。

### 8.3 登录与会话

- 登录：`POST /admin/api/login`（用户名 + 密码，argon2 校验）；
- 会话：独立 `user_sessions` 表，Cookie 名 `littledot_session`，HttpOnly + SameSite=Strict，默认 12h 过期（`ADMIN_SESSION_HOURS` 可调）；
- 登出：`POST /admin/api/logout` 销毁会话；
- 管理端登录态与 MCP 用户 Token（`users.token`）完全分离，互不影响。

### 8.4 角色与权限边界

| 角色 | 权限 |
|------|------|
| `admin` | 跨 owner 运维视图：管理全部文档 / 知识库 / 用户 / 错误审计 / 系统状态 |
| `user` | 仅本人数据（按 `owner_id` 隔离），越权访问返回 403 |

用户由 admin 通过 `/admin/api/users` 创建（`create_user` 默认 `role=user`），并写入审计日志。

### 8.5 安全提示

- 管理端与 MCP 共用端口，**无独立 TLS**：仅限本机或可信内网使用；
- 远程公网访问必须前置 HTTPS 反代（复用 §3），并配置强密码管理员；
- `HTTP_HOST=0.0.0.0` 启动时会打印明文安全告警，生产环境请收口监听地址或走反代。

## 9. 常见问题

- **http 启动即退出**：未设置 `MCP_AUTH_TOKEN`。远程模式强制要求，见配置表。
- **反代 502**：确认 8890 已监听、`/mcp` 前缀与 `location /mcp` 匹配。
- **权限问题（Linux）**：`data/` 需运行用户可写。
- **管理端打不开**：确认以 `MCP_TRANSPORT=http` 启动（stdio 模式不提供管理端），并访问 `/admin/` 而非 `/mcp`。
- **忘了管理员密码**：库非空时 `ADMIN_BOOTSTRAP` 与 `/admin/api/setup` 均失效。处理方式：备份后清空 `users`/`user_sessions` 表（或重置数据）后重新初始化；日常用户由 admin 在管理端管理。
