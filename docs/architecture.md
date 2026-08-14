<!--
架构知识库（Architecture Knowledge Base）
维护约定：架构层级的任何新增/修改/废弃，必须先更新本文件对应章节，再改代码；
禁止仅改代码而不回写本文件（防止与实现漂移）。任务事实源见 PLAN.md。
-->

# littledotmcp 架构设计（知识库）

> 维护者：朱世航 ｜ 最后更新：2026-08-14 ｜ 状态：M0 起逐里程碑落地

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
   SQLAlchemy(SQLite 默认/MySQL·PG 可选，全表 owner_id) │ VectorStore(sqlite-vec 默认，可切)
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
- **ADR-4 存储默认零中间件**：SQLite + 本地文件 + sqlite-vec 向量库，
  打包给别人不强制装 MySQL/Redis；交付用 uv 可执行/源码包，本地安装即可运行，无需容器化。
- **ADR-5 SQL 域**：sqlglot（hive/doris/oracle/mysql）+ 自研 DDL 子集解析与 L1 语义规则；
  L2 真实库校验走 SqlValidator 适配接口。范围锁定"小型脚本"，复杂特性入已知限制。
- **ADR-6 部署**：同一套代码三形态；远程仅 HTTPS 反代 + Bearer Token（首期），
  多用户阶段升级 MCP OAuth 2.1。
- **ADR-7 doc 域（M3-01~04 落地）**：`DocStorage` 抽象 + `LocalDocStorage`（UUID
  storage_key、防路径穿越、owner 分目录）；元数据落 `documents` 表经
  `OwnerScopedRepository` 强制隔离；provider 恒 LOCAL（企微后端随 M3-03 延后至 M9，见 ADR-14）；
  解析器 `rag/parsers` 按扩展名路由 txt/md/pdf/docx，损坏文件可读报错。
- **ADR-8 kb 域 RAG（M3-05~09 落地，M7 补真实后端）**：RAG 链路
  采用"抽象隔离 + 离线 Fake 验收"：`rag/chunker`（中文分句 + token 预算 +
  10% 重叠 + 锚点）、`rag/embedding.Embedder` 抽象（M7 落地真实 OpenAI/Ollama
  后端，见 ADR-12）、`rag/vector_store` 抽象 + `SqliteVecVectorStore`
  （sqlite-vec 扩展，`VECTOR_DIR` 下 `kb_vectors.db`，**检索强制 owner_id
  过滤**；2026-08-13 因 chromadb 1.5.9 Rust 绑定在 Windows+Py3.12 崩溃，
  经用户决策完全替换 chromadb）；kb 域工具 `kb_ingest`（doc 原文→解析→
  切块→embed→kb_documents/kb_chunks + 向量 upsert，同源幂等）/
  `kb_search`（向量 Top-K + 本地 BM25 自实现融合，返回来源引用）/
  `kb_list` / `kb_delete`（chunks→向量→doc 事务一致）；`kb_ask`（M7）基于
  `kb_search` 检索上下文经 LLM 生成带引用回答。
- **ADR-9 M4 四域（svn/requirement/project/tag，2026-08-13 落地简化版）**：
  svn 域采用 `SvnClient` 抽象 + `LocalFakeSvnClient`（临时目录模拟，无需真实
  svn CLI，凭据加解密用标准库实现）；requirement 域实现状态枚举
  DRAFT/ASSESS/DEV/ONLINE/DONE/CLOSED 与 LLM 降级评估；project 域实现
  项目/里程碑/任务三级仓储，`project_remove` 手动级联删除（SQLite 默认不启用
  外键）；tag 域 tags+entity_tags 多态。M4-08 追溯链路已纳入 M8（见 ADR-13）。
- **ADR-10 mindmap/standard 域（M5，2026-08-13 落地）**：mindmap 域
  `model.py` 维护 `MindNode` 树与 Mermaid mindmap 文本双向转换（支持
  `id((...))` 形状、唯一根、缩进层级校验），`export.py` 树→OPML（XML 转义），
  `from_doc.py` `summarize_outline` 优先调用 OpenAI 兼容 LLM（标准库 urllib，
  复用 `llm_*` 配置），无 Key/异常降级按 Markdown 标题层级解析；standard 域
  规范注册/检索（`OwnerScopedRepository` 隔离），内置模板经
  `scripts/seed_standards.py`（`STANDARD_TEMPLATES=1`）可选注入；
  `resources/standards.py` 注册 Resource 模板 `standard://{name}` + Prompt
  `review_by_standard`。依赖零新增（LLM SDK 留 M7）。
- **ADR-11 远程传输与打包（M6，2026-08-14 落地）**：`MCP_TRANSPORT=http`
  时用 `uvicorn.run(mcp.streamable_http_app())` 起 streamable-http（不再用
  `mcp.run(transport=...)`，以便注入自定义中间件）；`auth_middleware.py`
  提供两层 Starlette 中间件——`AuthMiddleware`（`Authorization: Bearer`，
  先比 `mcp_auth_token` 共享密钥快路径，再走 M1-05 用户 Token，`/health`
  免鉴权）与 `RateLimitMiddleware`（进程内令牌桶按 IP 限流，超限 429，
  符合 ADR-4 零外部中间件）；`server.py` 新增 `init_data()` 启动幂等建库
  与 `build_http_app()` 中间件组装（CORS + 限流 + 鉴权，后加者在外层）；
  反代模板 `deploy/nginx.conf`/`deploy/caddy.Caddyfile`（HTTPS→8890）；
  交付 `uv build`（wheel+sdist），`scripts/reset_data.py` 提供知识重置。
- **ADR-12 真实 Embedding + kb_ask（M7，2026-08-14 落地）**：`rag/embedding.py`
  在 `Embedder` Protocol 下新增两个真实实现——`OpenAICompatEmbedder`（openai
  SDK，`llm_*`/`embedding_*` 配置，覆盖百炼/DeepSeek 等 OpenAI 兼容端点）与
  `OllamaEmbedder`（httpx 直连 `/api/embed`，无需 Key），均支持 `probe_dim()`
  维度探测（真实模型维度覆盖配置）；真实结果经 `EmbeddingCache` 持久化缓存
  （`sha256(model|dim|text)` 为 key 落盘 `data/embedding_cache.jsonl`，追加写 +
  线程锁，命中免网络调用降本）；`get_embedder(settings)` 工厂按
  `embedding_provider`（openai/ollama/fake）切换，默认 fake 保离线；kb 域
  `_embedder()` 改走工厂、`_vector_store(dim=...)` 贯通 embedder 实际维度
  （入库/检索/向量库一致）；`kb_ask`（M7-03）复用 `kb_search` 检索 Top-K
  片段 → `_call_llm_answer`（openai SDK 调 `llm_*`）生成带
  `【来源：标题#seq】` 引用的回答，无 LLM Key 降级返回检索片段并提示。
- **ADR-13 追溯链路（M8，规划中，落地于后续里程碑）**：承接原 M4-08，
  `domains/requirement/trace.py` 的 `build_trace(owner, code)` 聚合需求关联——
  `SvnOpLog.requirement_id`（M8-02 补列 + `svn_commit` 入参，幂等迁移）、
  `Requirement.related_doc/related_commit/related_tag`（M8-03 补）、`EntityTag`
  多态标签（M4-07）；`requirement_trace(code)` 注册为 MCP 工具，owner 隔离经
  `OwnerScopedRepository` 强制。
- **ADR-14 doc 域企微后端（M9，规划中，延后里程碑）**：承接原 M3-03，
  `domains/doc/wecom.py` 的 `WeComDocClient`（corpid/agentid/secret 注入、
  token 获取与缓存、文档读写抽象，httpx）；`documents.provider` 字段已就绪
  （LOCAL/WECOM，默认 LOCAL），M9-02 起 `doc_save/doc_read` 支持 provider
  参数按后端路由；LOCAL 主链不破坏，未配置凭据时降级提示。
- **ADR-15 服务运维管理（M10，规划中，下一里程碑）**：承接 M6 远程部署与 M7
  真实 Embedding 的运维诉求，`server.py` 新增 `custom_route("/metrics")`
  暴露指标（复用 M7 `EmbeddingCache.hits/misses` 缓存计数、M6 限流计数）；
  `domains/admin/tools.py` 提供 `admin_config_check`（配置就绪诊断）、
  `admin_tools`（工具清单）、`admin_stats`（各域数据量，owner 隔离）、
  `admin_reset`（复用 `scripts/reset_data.reset_data()`）；管理权限复用 M6
  共享 Token 快路径，普通用户 Token 拒绝 `admin_*`，避免远程越权运维。

> 本文件随里程碑落地持续回写；详细任务见 [PLAN.md](PLAN.md)。
