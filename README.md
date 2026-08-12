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
- 打包给别人：Docker Compose + 空知识库初始化，每人只用自己导入的知识

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

## 文档

- [任务计划（WBS）](docs/PLAN.md) — 详细规范化任务清单与进度，**项目唯一任务事实来源**
- [架构设计](docs/architecture.md)（随里程碑回写）
- [已知限制](docs/limitations.md)（随里程碑维护）

## 许可

本软件为个人项目，版权归作者所有，禁止商用；未经许可不得擅自使用、复制、修改、分发或二次开发（见 LICENSE）。
