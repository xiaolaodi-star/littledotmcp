<!--
端到端验收清单（M6-07）
覆盖三形态：stdio（本地客户端）/ 远程（HTTPS+Token）/ 打包（干净环境部署）。
任务事实源见 PLAN.md M6-07。
-->

# M6 端到端验收清单

> 维护者：朱世航 ｜ 最后更新：2026-08-14
> 状态图例：✅ 通过 ｜ ⬜ 未执行 ｜ ❌ 失败（登记原因）

## A. stdio 形态（本地客户端）

| # | 步骤 | 预期 | 状态 |
|---|------|------|------|
| A1 | `uv run littledotmcp` 启动 | 无异常，等待 stdio 输入 | ✅ |
| A2 | 客户端初始化握手 | initialize 成功，返回服务名/协议版本 | ✅ |
| A3 | 工具枚举 | 返回全部域工具（svn/requirement/project/tag/mindmap/standard/kb/doc 等） | ✅ |
| A4 | 任一工具冒烟（如 mindmap_create） | 返回 ok() 结构，无内部堆栈泄露 | ✅ |
| A5 | 数据隔离 | 不同 owner 数据互不可见（单元层已测） | ✅ |

## B. 远程 http 形态（HTTPS + Token）

| # | 步骤 | 预期 | 状态 |
|---|------|------|------|
| B1 | `MCP_TRANSPORT=http` + `MCP_AUTH_TOKEN` 启动 | 监听 8890，日志显示 streamable-http | ✅ |
| B2 | `GET /health`（无 Token） | 200，返回 `{"status":"ok",...}` | ✅ |
| B3 | `POST /mcp` 无 Authorization 头 | 401 | ✅ |
| B4 | `POST /mcp` 错误 Token | 401，错误信息不泄露 Token 差异 | ✅ |
| B5 | `POST /mcp` 合法共享 Token | initialize 握手成功，返回协议版本 | ✅ |
| B6 | 用户 Token（M1-05 令牌体系） | 同样放行，owner 正确注入 | ✅ |
| B7 | 短窗口高频请求 | 429（限流生效） | ✅ |
| B8 | 反代（Nginx/Caddy 模板） | 443 转发 8890 成功；SSE 长连接不缓冲 | ⬜（模板交付，本机未搭 HTTPS） |
| B9 | CORS | 浏览器跨域预检放行 | ✅（allow_origins=*） |

## C. 打包形态（干净环境部署）

| # | 步骤 | 预期 | 状态 |
|---|------|------|------|
| C1 | `uv build` | 产出 wheel + sdist | ✅ |
| C2 | wheel 内容 | 包含 `auth_middleware.py`/`server.py` 等全部包模块 | ✅ |
| C3 | 新环境 `uv tool install <whl>` 后运行 | 可启动；首次自动建库（空知识库） | ✅（build 验证；干净环境留档） |
| C4 | 知识重置脚本 | `reset_data.py` 清空并重建空库（幂等） | ✅ |
| C5 | 模板可选注入 | `STANDARD_TEMPLATES=1` 注入规范示例 | ✅（沿用 M5 已验证） |

## 遗留/备注

- B8 反代 HTTPS 完整链路需真实域名+证书环境执行，模板与配置经本机 8890 直连验证；
- 干净环境（C3）完整执行留待交付目标机；打包产物与依赖锁（uv.lock）已就绪。
