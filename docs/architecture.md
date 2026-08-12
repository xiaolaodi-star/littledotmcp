<!--
架构知识库（Architecture Knowledge Base）
维护约定：架构层级的任何新增/修改/废弃，必须先更新本文件对应章节，再改代码；
禁止仅改代码而不回写本文件（防止与实现漂移）。任务事实源见 PLAN.md。
-->

# littledotmcp 架构设计（知识库）

> 维护者：朱世航 ｜ 最后更新：2026-08-12 ｜ 状态：M0 起逐里程碑落地

## 1. 定位

个人 MCP 开发工具箱：通过 MCP 协议向任意 MCP 客户端暴露 10 个开发工作域能力
（sql-er / sql-validate / doc / svn / mindmap / standard / kb / project / tag / requirement）。
三种部署形态：本地 stdio、服务端 streamable-http + Token、打包给别人（空知识库 + 用户隔离）。

## 2. 总体架构

```
客户端层（Claude Desktop / Cursor / CodeBuddy…）
   │ stdio（本地）/ HTTPS streamable-http（远程）
   ▼
接入层（单应用，模块化单体）
   FastMCP：传输适配 + 鉴权（本地信任边界 / 远程 Bearer）+ 工具/资源/提示词注册
   ▼
领域服务层（按域分包，工具域前缀命名）
   sql_er │ sql_validate │ doc │ svn │ mindmap │ standard │ kb │ project │ tag │ requirement
   ▼
基础设施层
   SQLAlchemy(SQLite 默认/MySQL·PG 可选，全表 owner_id) │ VectorStore(ChromaDB 默认，可切)
   │ 本地文件 + 企微 API │ svn CLI（凭据加密）│ LLM/Embedding（OpenAI 兼容 / Ollama）
```

## 3. 关键决策（ADR 式）

- **ADR-1 语言/框架**：Python 3.12 + 官方 `mcp` SDK（FastMCP）。理由：sqlglot 原生支持
  Hive/Doris/Oracle 方言解析；RAG/文档解析生态最全；MCP 官方 Python SDK 双传输齐全；
  uv 打包轻，利于交付。备选：TypeScript/Node（MCP 生态广，但 SQL 方言与 RAG 生态弱）。
- **ADR-2 服务形态**：模块化单体。一个应用一个端口；工具域前缀命名防冲突；
  未来按包边界可拆独立 MCP server（演进路径，不提前做）。
- **ADR-3 多租户隔离**：所有数据表 owner_id；Repository 层强制拼接；
  向量 metadata 强制注入 owner_id；交付 = 空知识库 + 各自数据。
- **ADR-4 存储默认零中间件**：SQLite + 本地文件 + ChromaDB 持久化目录，
  打包给别人不强制装 MySQL/Redis；交付用 uv 可执行/源码包，本地安装即可运行，无需容器化。
- **ADR-5 SQL 域**：sqlglot（hive/doris/oracle/mysql）+ 自研 DDL 子集解析与 L1 语义规则；
  L2 真实库校验走 SqlValidator 适配接口。范围锁定"小型脚本"，复杂特性入已知限制。
- **ADR-6 部署**：同一套代码三形态；远程仅 HTTPS 反代 + Bearer Token（首期），
  多用户阶段升级 MCP OAuth 2.1。

> 本文件随里程碑落地持续回写；详细任务见 [PLAN.md](PLAN.md)。
