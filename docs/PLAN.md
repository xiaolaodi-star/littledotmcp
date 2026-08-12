<!--
littledotmcp 项目任务计划（WBS）
维护约定：本文件是项目唯一的任务事实来源（Single Source of Truth）。
新增/变更/完成任务必须先更新本文件对应条目，再改代码；禁止只改代码不回写本文件。
状态图例：⬜ 未开始 ｜ 🟦 进行中 ｜ ✅ 已完成 ｜ ❌ 已取消
-->

# littledotmcp 项目任务计划（WBS）

> 项目：个人 MCP 开发工具箱 ｜ 语言：Python 3.12 ｜ 框架：官方 mcp SDK（FastMCP）
> 维护者：朱世航 ｜ 最后更新：2026-08-12
> 关联文档：[架构设计](architecture.md) ｜ [已知限制](limitations.md) ｜ [README](../README.md)

---

## 0. 项目概览

通过 MCP 协议接入任意 MCP 客户端（Claude Desktop / Cursor / CodeBuddy），暴露 10 个开发工作域能力：

| 域 | 能力 | 工具前缀 |
|----|------|----------|
| sql-er | Hive/Doris/Oracle DDL → Mermaid ER 图 | `sql_er_*` |
| sql-validate | 三方言脚本静态校验（L1）+ 真实库校验适配（L2） | `sql_validate_*` |
| doc | 文档管理：本地 / 企业微信，存储后端可切换 | `doc_*` |
| svn | checkout/update/commit/log/diff/blame/status | `svn_*` |
| mindmap | Mermaid 思维导图、OPML 导出（可导入 XMind） | `mindmap_*` |
| standard | 规范注册与检索，注册为 MCP Resource 随任务加载 | `standard_*` |
| kb | 个人问答知识库（RAG，按用户隔离） | `kb_*` |
| project | 项目/里程碑/任务三级进度管理 | `project_*` |
| tag | 跨实体（需求/文档/项目/知识库）通用标签 | `tag_*` |
| requirement | 需求生命周期：评估→开发→上线，全程可追溯 | `requirement_*` |

三种部署形态（同一套代码）：
1. 个人本地：`stdio` 传输，被 MCP 客户端拉起；
2. 服务端远程：`streamable-http` + HTTPS + Token 鉴权；
3. 打包给别人：Docker Compose + 空知识库初始化，每人只用自己导入的知识。

---

## 1. 任务编号与状态规范

- 编号规则：`<里程碑>-<序号>`（如 `M2-03`）；横切任务 `XC-<序号>`；工程规约 `规约-<序号>`。
- 状态：⬜ 未开始 / 🟦 进行中 / ✅ 已完成 / ❌ 已取消。本文件是唯一状态事实源，代码提交信息须引用任务编号（如 `feat(sql-er): M2-03 ER 图生成`）。
- 每项任务的验收标准是"完成"的唯一判定依据，未达标准不得标记 ✅。

---

## 2. 全局工程规约（所有任务强制遵守）

| 编号 | 规约 | 要求 |
|------|------|------|
| 规约-01 | 编码规范 | ruff（规则集见 pyproject.toml，行宽 100）；类/函数/变量 lowerCamelCase 或 snake_case 遵循 PEP8；公共 API 必须类型注解与 docstring；禁止裸 `except`；禁止硬编码密钥。 |
| 规约-02 | Git 规范 | 分支模型：`main`（稳定）+ `feature/<域>-<任务号>`；提交信息 Conventional Commits（`feat/fix/docs/refactor/test/chore(域): Mx-xx 描述`）；禁止提交 `.env`、`data/`、`logs/`、`.db`。 |
| 规约-03 | 文档规范 | `docs/` 固定结构：PLAN.md（任务事实源）/ architecture.md（架构知识库）/ limitations.md（已知限制）；文档与代码不得漂移。 |
| 规约-04 | 测试规范 | pytest（tests/ 与 src 同构）；`asyncio_mode=auto`；新增域必须有正向+边界用例；**用户隔离测试为强制项**（M1-08）；覆盖率基线 80% 起。 |
| 规约-05 | 配置规范 | pydantic-settings 分层：默认值 < `.env` < 环境变量；密钥仅存 `.env`/环境变量，代码零硬编码；`.env.example` 与配置组同步维护。 |
| 规约-06 | 安全规范 | 路径穿越防护（本地存储路径规范化+禁 `..`）；凭据加密存储（SVN/企微/LLM Key）；日志脱敏（禁打印密钥/密码）；命令注入防护（svn 参数列表化传参）；SQL 注入防护（ORM/参数绑定）。 |
| 规约-07 | 工具契约规范 | 工具名域前缀；入参用 pydantic 模型/JSON Schema 严格声明；输出统一 `{success, data, message}`（common/result.py 的 `ok()`/`fail()`）；工具实现不直接抛异常给客户端。 |
| 规约-08 | 兼容性规范 | 方言/存储/文档存储/向量存储以抽象接口隔离（sqlglot 解析器、DocStorage、VectorStore、SqlValidator）；依赖经 uv.lock 锁定；SDK 升级前评估破坏性变更；新限制写入 limitations.md。 |

---

## 3. 里程碑与 WBS

### M0 工程骨架（依赖：无）

| 编号 | 任务 | 状态 |
|------|------|------|
| M0-01 | 工程初始化：uv + pyproject + .python-version + .gitignore + 目录结构 + git init | ✅ |
| M0-02 | 配置加载：pydantic-settings `Settings` + `.env.example` + 配置校验 | ✅ |
| M0-03 | FastMCP stdio 起通：`server.py` 组装 + `__main__` 启动 | ✅ |
| M0-04 | hello 示例工具 + 统一返回结构 `common/result.py`（ok/fail）+ 契约装饰器 | ✅ |
| M0-05 | 统一异常与日志：异常映射、结构化日志、脱敏、requestId | ✅ |
| M0-06 | pytest 基座：conftest、asyncio、首个 hello 工具测试 | ✅ |

**M0-01 工程初始化**
- 说明：本任务当前已完成工程文件落地（pyproject/.python-version/.gitignore/.env.example/LICENSE/包骨架）；补齐目录 `src/littledotmcp/{common,db,rag,domains,resources}`、`tests/`、`scripts/`、`docs/`，并 `git init`（main 分支）。
- 验收标准：`uv sync` 成功生成 `.venv` 与 `uv.lock`；`python -m littledotmcp` 可运行；`git status` 干净（忽略规则生效）。
- 依赖：无；规模：S；关键文件：根目录各工程文件。

**M0-02 配置加载**
- 说明：实现 `config.py`：`Settings`（pydantic-settings，`env_file=".env"`），字段含 transport/auth_token/db_url/storage_root/llm*/wecom*/http_*/log_*；启动时校验必填项与枚举合法性。
- 验收标准：缺密钥时报可读错误且不含堆栈泄漏；非法 transport 值被拒绝；`.env.example` 与 Settings 字段一一对应。
- 依赖：M0-01；规模：S；关键文件：`src/littledotmcp/config.py`。

**M0-03 FastMCP stdio 起通**
- 说明：`server.py` 创建 `FastMCP("littledotmcp")`；`__main__.py` 按 `MCP_TRANSPORT` 启动 `mcp.run()`（stdio 默认，http 走 M6）；支持 `python -m littledotmcp` 与 `littledotmcp` 两种入口。
- 验收标准：MCP 客户端（或 `mcp dev` 调试器）可发现并连接；`initialize` 握手成功；工具列表可枚举。
- 依赖：M0-02；规模：M；关键文件：`server.py`、`__main__.py`。

**M0-04 hello 工具 + 统一返回**
- 说明：`common/result.py` 定义 `ok(data)`/`fail(code,message)` 与 `ToolResult` 类型；注册 `hello` 工具（返回版本与能力清单）；建立 `common/tool.py` 契约装饰器（统一入参校验/异常转 fail/日志）。
- 验收标准：调用 `hello` 返回 `{success:true,data:{...},message:""}`；异常路径返回 fail 结构；客户端可稳定解析。
- 依赖：M0-03；规模：M；关键文件：`common/result.py`、`common/tool.py`、`domains/hello.py`。

**M0-05 统一异常与日志**
- 说明：`common/errors.py` 定义 `ToolkitError(code,message)` 与错误码表；`common/logging_.py` 配置 logging（格式含时间/级别/域/requestId）、脱敏过滤器（redact 密钥字段）、`LOG_LEVEL/LOG_DIR` 支持；FastMCP 工具异常统一映射为 fail。
- 验收标准：任意工具抛 ToolkitError → 客户端收到结构化错误；日志无密钥明文；文件日志滚动。
- 依赖：M0-03；规模：M；关键文件：`common/errors.py`、`common/logging_.py`。

**M0-06 pytest 基座**
- 说明：`tests/conftest.py`（临时目录、Settings 注入、FastMCP 测试客户端）、hello 工具与 result 结构测试、异常映射测试。
- 验收标准：`pytest` 全绿；新测试套件跑通 asyncio；覆盖率工具可运行。
- 依赖：M0-03；规模：S；关键文件：`tests/conftest.py`、`tests/test_hello.py`。

### M1 基础设施（依赖：M0）

| 编号 | 任务 | 状态 |
|------|------|------|
| M1-01 | DB 抽象与连接：SQLAlchemy engine/session + SQLite 默认、URL 可配 | ✅ |
| M1-02 | 数据模型 v1：users + 全部域表（全表 owner_id） | ✅ |
| M1-03 | 建表与迁移：init_db 幂等建表 + alembic 起步 | ✅ |
| M1-04 | Repository 隔离基类：OwnerScopedRepository 强制 owner_id | ✅ |
| M1-05 | 用户与 Token 鉴权：注册/登录/签发校验、密码哈希、Bearer 校验 | ✅ |
| M1-06 | 审计日志：工具调用留痕、svn_ops_log、结构化审计 | ✅ |
| M1-07 | 配置组落地：LLM/embedding/企微/存储/Token 配置校验 | ✅ |
| M1-08 | 隔离集成测试：A/B 用户数据互不可见（强制项） | ✅ |

**M1-01 DB 抽象与连接**
- 说明：`db/session.py`：engine（默认 `sqlite:///./data/littledotmcp.db`，`DB_URL` 可切 MySQL/PG）、sessionmaker、`get_session()` 上下文；连接池参数与 SQLite 外键开关。
- 验收标准：CRUD 冒烟通过；URL 可切换；session 正确关闭无泄漏。
- 依赖：M0-06；规模：S；关键文件：`db/session.py`。

**M1-02 数据模型 v1**
- 说明：`db/models.py` 定义全部表：`users`、`kb_documents`、`kb_chunks`、`documents`、`svn_repos`、`svn_ops_log`、`projects`、`milestones`、`tasks`、`requirements`、`tags`、`entity_tags`、`mindmaps`、`standards`；**所有数据表含 owner_id**；requirements 状态枚举 DRAFT/ASSESS/DEV/ONLINE/DONE/CLOSED。
- 验收标准：模型与 [架构设计](architecture.md) §数据模型 一致；外键/索引/唯一约束合理；`owner_id` 无遗漏。
- 依赖：M1-01；规模：L；关键文件：`db/models.py`。

**M1-03 建表与迁移**
- 说明：`scripts/init_db.py` + `db/init_db.py`（create_all 幂等 + 索引）；引入 alembic 生成首版迁移作为演进基线。
- 验收标准：重复执行无副作用；全新空库可一键初始化；迁移可回滚基线。
- 依赖：M1-02；规模：M；关键文件：`scripts/init_db.py`、`alembic/`。

**M1-04 Repository 隔离基类**
- 说明：`db/repository.py`：`OwnerScopedRepository`——构造收 owner_id，所有 query 自动拼接 `owner_id=...`（禁止调用方传入该条件），提供 `list_by_owner/get/insert/update/delete` 与实体类型校验。
- 验收标准：单测证明无 owner 条件调用被拒绝/忽略；A 用户无法读 B 数据（含 update/delete 影响行数为 0）。
- 依赖：M1-02；规模：M；关键文件：`db/repository.py`。

**M1-05 用户与 Token 鉴权**
- 说明：`auth.py`：用户注册（密码 bcrypt/argon2 哈希）、登录签发 Token（HMAC 签名、过期时间）；`get_current_owner_id()` 上下文解析（stdio=当前用户；http=Bearer Token）；Token 校验失败映射统一错误码。
- 验收标准：注册/登录/鉴权链路测试通过；过期/篡改 Token 被拒；密码不明文落库。
- 依赖：M1-01；规模：M；关键文件：`auth.py`、`db/models.py`(users)。

**M1-06 审计日志**
- 说明：工具调用拦截器记录（owner_id、工具名、入参摘要、耗时、结果码）；`svn_ops_log` 记录 SVN 操作；审计日志写入 logs/。
- 验收标准：每次工具调用有留痕；审计不含敏感入参（密钥脱敏）。
- 依赖：M1-04；规模：M；关键文件：`common/audit.py`。

**M1-07 配置组落地**
- 说明：补齐 Settings 各配置组（LLM/embedding/企微/存储根/Token/HTTP）与校验（URL 格式、Key 非空时机、枚举）；同步 `.env.example`。
- 验收标准：配置组与 .env.example 一一对应；非法配置启动即报错。
- 依赖：M0-02；规模：S；关键文件：`config.py`、`.env.example`。

**M1-08 隔离集成测试（强制项）**
- 说明：构造用户 A/B 全量数据，验证 kb/documents/projects/requirements/tags 检索、读取、修改、删除在跨用户场景全部不可见；覆盖 Repository 与后续 VectorStore 隔离。
- 验收标准：测试全绿；该用例集是 M3/M4 域的回归守门员。
- 依赖：M1-04；规模：M；关键文件：`tests/test_isolation.py`。

### M2 SQL 域（依赖：M1）

| 编号 | 任务 | 状态 |
|------|------|------|
| M2-01 | sqlglot 集成与方言检测（hive/doris/oracle/mysql 启发式） | ✅ |
| M2-02 | DDL 解析器：三方言 CREATE TABLE → Table 模型 | ✅ |
| M2-03 | ER 图生成：Table 集合 → Mermaid erDiagram | ✅ |
| M2-04 | L1 静态校验：语法 + 语义规则 | ✅ |
| M2-05 | L2 真实库校验适配：SqlValidator 接口 + 三库适配骨架 | ✅ |
| M2-06 | sql_er_from_ddl 工具注册 | ✅ |
| M2-07 | sql_validate_script 工具注册 | ✅ |
| M2-08 | golden 测试与已知限制清单维护 | ✅ |

**M2-01 sqlglot 集成与方言检测**
- 说明：`domains/sql_er/dialect.py`：方言映射（hive/doris/oracle/mysql）；关键字启发式检测（Hive `PARTITIONED BY`/`STORED AS`、Oracle `VARCHAR2`/`NUMBER`、Doris MySQL 兼容特征），失败可由调用方指定。
- 验收标准：三方言样例各 3 条检测正确；未知方言返回可读提示。
- 依赖：M1-01（db 基建）+ `uv add sqlglot`；规模：M；关键文件：`domains/sql_er/dialect.py`。

**M2-02 DDL 解析器**
- 说明：`domains/sql_er/parser.py`：将 CREATE TABLE 解析为 `Table(name, columns[{name,type,nullable,comment}], pk, fks[], partitions, external)`；支持列注释 `COMMENT`、表注释、`PARTITIONED BY`、复杂类型 `MAP/STRUCT/ARRAY`（Doris/Hive）、`PRIMARY KEY`/`FOREIGN KEY`/`REFERENCES`；解析失败返回带行号错误。
- 验收标准：golden 样例（每方言 5 条 DDL）解析结果与期望一致；错误信息含行号。
- 依赖：M2-01；规模：L；关键文件：`domains/sql_er/parser.py`、`domains/sql_er/model.py`。

**M2-03 ER 图生成**
- 说明：`domains/sql_er/render.py`：Table 集合 → Mermaid `erDiagram` 文本（实体、主键标注、关系 `||--o{`、表/列注释）；对无 FK 的表间关系用命名约定补建议关系（可关闭）。
- 验收标准：输出可被 Mermaid 渲染；多表/无表/含分区表边界正确。
- 依赖：M2-02；规模：M；关键文件：`domains/sql_er/render.py`。

**M2-04 L1 静态校验**
- 说明：`domains/sql_validate/validator.py`：语法（sqlglot parse + 方言）+ 语义规则（重复表、重复列、保留字、类型存在性、FK 目标表/列存在性、分区列重复定义）；分级输出 `[error|warning|info]` 带行号。
- 验收标准：构造 10 条缺陷样例全部命中；无缺陷脚本零误报。
- 依赖：M2-02；规模：L；关键文件：`domains/sql_validate/validator.py`。

**M2-05 L2 真实库校验适配**
- 说明：`domains/sql_validate/adapter.py`：`SqlValidator` 接口（`validate(sql, conn) -> Report`）；Oracle（DBMS 编译/EXPLAIN）/Hive/Doris JDBC 适配骨架；连接信息仅存配置，不落库不打印。
- 验收标准：接口可扩展；未配置连接时 L2 返回明确提示而非崩溃；文档说明连接配置方式。
- 依赖：M2-02；规模：M；关键文件：`domains/sql_validate/adapter.py`。

**M2-06 / M2-07 工具注册**
- 说明：`sql_er_from_ddl(sql, dialect?)`、`sql_validate_script(sql, dialect, level?)` 注册到 FastMCP；入参 pydantic 模型；输出统一结构（ER 文本 / 校验报告）。
- 验收标准：MCP 客户端可调用；非法入参被 Schema 拒绝；返回结构稳定。
- 依赖：M2-03、M2-04；规模：S；关键文件：`domains/sql_er/tools.py`、`domains/sql_validate/tools.py`。

**M2-08 golden 测试与限制清单**
- 说明：`tests/domains/sql_er/`、`tests/domains/sql_validate/` golden 用例（含构造缺陷样例）；`docs/limitations.md` 登记 sqlglot 对复杂 HiveQL 的限制与规避（预规范化）。
- 验收标准：golden 全绿；限制清单覆盖已知解析边界。
- 依赖：M2-02/03/04；规模：M；关键文件：`tests/domains/sql_*`、`docs/limitations.md`。

### M3 文档与知识库（依赖：M1）

| 编号 | 任务 | 状态 |
|------|------|------|
| M3-01 | 文档解析器集合：txt/md/pdf/docx → 纯文本 | ⬜ |
| M3-02 | DocStorage 抽象 + 本地实现（防穿越） | ⬜ |
| M3-03 | 企业微信实现：微盘/文档 API 客户端骨架 | ⬜ |
| M3-04 | doc 域工具：doc_save/read/search/list/delete | ⬜ |
| M3-05 | 切块器：中文感知、500~800 token、10% 重叠 | ⬜ |
| M3-06 | Embedding 抽象：OpenAI 兼容 + Ollama、结果缓存 | ⬜ |
| M3-07 | VectorStore 抽象 + ChromaDB 持久化（metadata 强制 owner_id） | ⬜ |
| M3-08 | RAG 检索问答：向量+BM25 混合、来源引用、kb_* 工具 | ⬜ |
| M3-09 | 用户隔离与成本控制：隔离测试 + embedding 缓存验证 | ⬜ |

**M3-01 文档解析器集合**
- 说明：`rag/parsers.py`：按扩展名路由 txt/md（原生）、pdf（pypdf/pdfplumber）、docx（python-docx）；解析失败记录并跳过；返回文本+元信息（页数/字符数）。
- 验收标准：四种格式样例解析文本正确；损坏文件友好报错。
- 依赖：M1-01 + `uv add pypdf pdfplumber python-docx markdown`；规模：M；关键文件：`rag/parsers.py`。

**M3-02 DocStorage 本地实现**
- 说明：`domains/doc/storage.py`：`DocStorage` 抽象 + `LocalDocStorage`（路径规范化、防 `..`、大小限制、按 owner_id 分目录、storage_key 生成）。
- 验收标准：save/load/delete 测试通过；穿越路径被拒；owner 目录隔离。
- 依赖：M1-04；规模：M；关键文件：`domains/doc/storage.py`。

**M3-03 企业微信实现**
- 说明：`domains/doc/wecom.py`：企微微盘/文档 API 客户端骨架（corpid/agentid/secret 注入、token 缓存、上传/下载/删除）；未配置凭据时返回明确降级提示；备选"仅企微机器人通知"模式。
- 验收标准：凭据缺失时报可读错误；mock API 冒烟通过；失败不崩溃。
- 依赖：M3-02；规模：L；关键文件：`domains/doc/wecom.py`。

**M3-04 doc 域工具**
- 说明：`doc_save/doc_read/doc_search/doc_list/doc_delete`（provider 切换 LOCAL/WECOM）；元数据落 `documents` 表；搜索走 name/type/标签过滤。
- 验收标准：全链路 CRUD 测试；provider 切换生效；搜索过滤正确。
- 依赖：M3-02/03 + M1-04；规模：M；关键文件：`domains/doc/tools.py`。

**M3-05 切块器**
- 说明：`rag/chunker.py`：中文感知分句（按标点/换行）+ 按字符/token 预算切块（500~800 token，10% 重叠），保留块序号与来源锚点。
- 验收标准：中文样例切块质量符合预期；超长段落正确拆分；重叠率可测。
- 依赖：M3-01；规模：M；关键文件：`rag/chunker.py`。

**M3-06 Embedding 抽象**
- 说明：`rag/embedding.py`：`Embedder` 抽象；OpenAI 兼容（httpx/openai SDK，默认百炼/DeepSeek 等）+ Ollama 离线；结果哈希缓存到本地（避免重复计费）；批量接口。
- 验收标准：两种后端可切换；同文本二次调用命中缓存。
- 依赖：M1-07 + `uv add openai httpx`；规模：M；关键文件：`rag/embedding.py`。

**M3-07 VectorStore 抽象 + ChromaDB**
- 说明：`rag/vector_store.py`：`VectorStore` 抽象（upsert/search/delete_by_doc）；ChromaDB 持久化实现（`VECTOR_DIR`）；**所有 metadata 强制注入 owner_id（调用方不可覆盖）**；接口可切 sqlite-vec/Redis/pgvector。
- 验收标准：upsert/search/delete 测试；owner 过滤生效（A 搜不到 B）；持久化重启不丢。
- 依赖：M3-06 + `uv add chromadb`；规模：M；关键文件：`rag/vector_store.py`。

**M3-08 RAG 检索问答**
- 说明：`domains/kb/`：`kb_ingest`（解析→切块→embed→入库，更新 kb_documents/kb_chunks 与向量）、`kb_search`（向量 Top-K + 关键词 BM25 混合，owner/project/标签过滤）、`kb_ask`（检索上下文→LLM 生成，附来源引用）、`kb_delete/kb_list`。
- 验收标准：入库→提问→带引用回答全链路；无 LLM Key 时 kb_search 仍可用。
- 依赖：M3-05/06/07 + M3-04；规模：L；关键文件：`domains/kb/*.py`。

**M3-09 用户隔离与成本控制**
- 说明：kb 域隔离测试（A/B 用户文档互不可见，向量+元数据双层验证）；embedding 缓存命中率验证；RAG 响应 <1s 目标（个人规模）。
- 验收标准：隔离测试全绿；缓存生效；性能目标达成（或记录偏差）。
- 依赖：M3-08；规模：M；关键文件：`tests/test_kb_isolation.py`。

### M4 SVN/需求/项目/标签（依赖：M1）

| 编号 | 任务 | 状态 |
|------|------|------|
| M4-01 | svn CLI 封装：安全调用、超时、输出解析、异常映射 | ⬜ |
| M4-02 | 凭据管理：加密存储、keyring 抽象、脱敏 | ⬜ |
| M4-03 | svn 域工具：checkout/update/commit/log/diff/blame/status | ⬜ |
| M4-04 | 需求状态机：DRAFT/ASSESS/DEV/ONLINE/DONE/CLOSED + 流转规则 | ⬜ |
| M4-05 | 评估与上线流程：影响面报告、上线检查清单 | ⬜ |
| M4-06 | 项目/里程碑/任务：进度自动计算与汇报 | ⬜ |
| M4-07 | 跨实体标签：tags + entity_tags 多态、tag_* 工具 | ⬜ |
| M4-08 | 追溯链路：需求↔SVN 提交↔文档↔标签 | ⬜ |

**M4-01 svn CLI 封装**
- 说明：`domains/svn/client.py`：`SvnClient`（subprocess 参数列表化传参防注入、超时、错误码→异常映射、`--xml` 输出解析）；检测 svn 可执行文件并给出安装提示。
- 验收标准：checkout/update/log 冒烟（本地 svnadmin 临时仓库或 mock）；命令注入尝试被拒；超时正确报错。
- 依赖：M1-01 + `uv add defusedxml`（解析 XML 安全）；规模：M；关键文件：`domains/svn/client.py`。

**M4-02 凭据管理**
- 说明：`domains/svn/credentials.py`：`CredentialStore`（加密存储，密钥取自环境变量/OS keyring 抽象）；读写接口；日志脱敏保证。
- 验收标准：凭据不明文落库/不打印；加解密往返正确。
- 依赖：M4-01；规模：M；关键文件：`domains/svn/credentials.py`。

**M4-03 svn 域工具**
- 说明：注册 `svn_checkout/update/commit/log/diff/blame/status`；仓库元数据落 `svn_repos`；commit 支持关联 requirement_id。
- 验收标准：全部工具注册；操作留痕 svn_ops_log；commit 可带需求关联。
- 依赖：M4-01/02；规模：M；关键文件：`domains/svn/tools.py`。

**M4-04 需求状态机**
- 说明：`domains/requirement/state_machine.py`：状态与合法流转（DRAFT→ASSESS→DEV→ONLINE→DONE→CLOSED，含退回），非法流转拒绝并审计；状态变更时间戳记录。
- 验收标准：非法流转被拒；合法链全通过；变更可追溯。
- 依赖：M1-04；规模：M；关键文件：`domains/requirement/state_machine.py`。

**M4-05 评估与上线流程**
- 说明：`requirement_assess`（LLM 辅助生成影响面报告：涉及表/文档/风险，落库）；`requirement_start_dev`；`requirement_launch`（上线检查清单：关联 SQL 已校验（调 M2）、代码已提交（查 svn_ops_log）、文档已更新；缺项给出阻断提示）。
- 验收标准：评估报告落库可查；上线清单缺项时阻断并列出缺项；全满足可上线。
- 依赖：M4-04 + M2-07 + M4-03；规模：L；关键文件：`domains/requirement/tools.py`。

**M4-06 项目进度**
- 说明：`project_create/update`、`milestone_create`、`task_create/update`（含状态/权重）；进度=完成权重/总权重自动计算；`project_progress_report`（文本，可选 `[skill:xlsx]` 导出 Excel）。
- 验收标准：进度计算正确（含权重、无里程碑边界）；报告生成可用。
- 依赖：M1-04；规模：M；关键文件：`domains/project/*.py`。

**M4-07 跨实体标签**
- 说明：`tags` + `entity_tags`（entity_type/entity_id 多态）；`tag_create/rename/apply/remove/query`（按标签聚合查询，跨 entity_type）；owner 隔离。
- 验收标准：标签增改查、聚合查询正确；隔离测试通过。
- 依赖：M1-04；规模：M；关键文件：`domains/tag/*.py`。

**M4-08 追溯链路**
- 说明：需求详情聚合查询（关联 SVN 提交、文档、标签、项目、评估/上线记录）；提供 `requirement_trace` 工具。
- 验收标准：需求端到端追溯信息完整可查。
- 依赖：M4-03/05/06/07；规模：M；关键文件：`domains/requirement/trace.py`。

### M5 思维导图与规范（依赖：M1）

| 编号 | 任务 | 状态 |
|------|------|------|
| M5-01 | Mermaid mindmap 生成/编辑：mindmap_create/update | ⬜ |
| M5-02 | OPML 导出：mindmap_export（可导入 XMind） | ⬜ |
| M5-03 | 从文档/知识库生成大纲：mindmap_from_doc | ⬜ |
| M5-04 | standard 模型与工具：standard_search/get/add | ⬜ |
| M5-05 | 规范 Resources 注册：standard://{name} + 提示词 | ⬜ |

**M5-01 Mermaid mindmap 生成/编辑**
- 说明：`domains/mindmap/`：树结构 ↔ Mermaid mindmap 文本双向转换；`mindmap_create/update`（持久化 `mindmaps` 表，owner 隔离）；mermaid 语法校验。
- 验收标准：生成合法 mermaid；编辑往返一致；非法输入被拒。
- 依赖：M1-04；规模：M；关键文件：`domains/mindmap/*.py`。

**M5-02 OPML 导出**
- 说明：`mindmap_export(format=opml)`：树 → OPML XML（outline 嵌套，可导入 XMind/FreeMind）；转义与编码正确。
- 验收标准：OPML 校验通过；XMind 可导入（文档验证说明）。
- 依赖：M5-01；规模：S；关键文件：`domains/mindmap/export.py`。

**M5-03 从文档生成大纲**
- 说明：`mindmap_from_doc`：读 kb/doc 文档 → LLM 提炼层级大纲 → 生成思维导图；无 LLM Key 时退回"按标题层级解析"（md 标题/#、docx 标题样式）。
- 验收标准：样例文档出图；无 Key 降级路径可用。
- 依赖：M5-01 + M3；规模：M；关键文件：`domains/mindmap/from_doc.py`。

**M5-04 standard 模型与工具**
- 说明：`standards` 表（owner_id, name, category, version, content_md, is_template）；`standard_add/search/get`（分类/全文检索）；内置模板（命名/SQL/提交/上线清单示例）随空库可选注入。
- 验收标准：增查正确；示例模板可注入与替换。
- 依赖：M1-04；规模：S；关键文件：`domains/standard/*.py`。

**M5-05 规范 Resources 注册**
- 说明：将标准注册为 MCP Resource（URI `standard://{name}`）+ Prompt（如"按 SQL 规范校验"）；模型在相关任务中自动加载。
- 验收标准：客户端可枚举/读取 standard 资源；Prompt 可被调用。
- 依赖：M5-04；规模：S；关键文件：`resources/standards.py`、`server.py`。

### M6 远程传输与打包交付（依赖：M2~M5）

| 编号 | 任务 | 状态 |
|------|------|------|
| M6-01 | Streamable HTTP 传输：uvicorn/Starlette 起 /mcp | ⬜ |
| M6-02 | Token 鉴权 + 限流：Bearer 校验、速率限制、审计 | ⬜ |
| M6-03 | Nginx/Caddy 反代模板：HTTPS 443 → /mcp | ⬜ |
| M6-04 | Dockerfile + docker-compose（app + SQLite 卷，可选 Ollama） | ⬜ |
| M6-05 | 空知识库初始化：首次启动建库、无用户数据 | ⬜ |
| M6-06 | 使用文档与许可：README 部署/配置/知识重置、LICENSE | ⬜ |
| M6-07 | 端到端验收：stdio / 远程 / 打包三形态 | ⬜ |

**M6-01 Streamable HTTP 传输**
- 说明：`MCP_TRANSPORT=http` 时以 uvicorn 启动 streamable-http（FastMCP 内置 Starlette 应用挂载 `/mcp`）；CORS 配置；HTTP_HOST/PORT 生效。
- 验收标准：`curl` 握手（initialize）成功；远程客户端可枚举工具。
- 依赖：M0-03 + `uv add uvicorn`；规模：M；关键文件：`server.py`、`__main__.py`。

**M6-02 Token 鉴权 + 限流**
- 说明：HTTP 中间件：Bearer Token 校验（与 M1-05 令牌体系一致）、简单令牌桶限流（按 IP/Token）、审计；未配置 Token 拒绝远程访问。
- 验收标准：无 Token 拒绝；错误 Token 拒绝；超限 429；合法 Token 通过。
- 依赖：M6-01 + M1-05；规模：M；关键文件：`http_middleware.py`。

**M6-03 反代模板**
- 说明：`deploy/nginx.conf` / `deploy/caddy.Caddyfile` 模板（443 HTTPS → 127.0.0.1:8890/mcp，WebSocket/SSE 支持）。
- 验收标准：模板随仓库交付；注释清晰可改。
- 依赖：M6-02；规模：S；关键文件：`deploy/`。

**M6-04 Docker 打包**
- 说明：`Dockerfile`（python:3.12-slim + uv 安装 + 非 root 运行）+ `docker-compose.yml`（app 挂载 data 卷；可选 Ollama 服务）；镜像内置 chromadb 等原生依赖规避平台问题。
- 验收标准：`docker compose up` 起通；数据持久化；权限最小化。
- 依赖：M1/M2/M3 依赖就绪；规模：M；关键文件：`Dockerfile`、`docker-compose.yml`。

**M6-05 空知识库初始化**
- 说明：容器/新部署首次启动自动建库且无任何用户数据；`STANDARD_TEMPLATES=1` 时注入规范示例（可删除）；提供"知识重置"脚本（清空 data/）。
- 验收标准：全新部署为空；注入模板可选；重置脚本可用。
- 依赖：M6-04 + M1-03；规模：S；关键文件：`scripts/init_db.py`、`scripts/reset_data.py`。

**M6-06 使用文档与许可**
- 说明：README（快速开始/三种形态配置示例/MCP 客户端接入 JSON）、部署文档、配置说明、知识重置说明、LICENSE；文档与代码一致。
- 验收标准：他人按文档可在无本项目源码知识下部署成功。
- 依赖：M6-05；规模：M；关键文件：`README.md`、`docs/deploy.md`。

**M6-07 端到端验收**
- 说明：三形态各跑验收：stdio（本地客户端）、远程（HTTPS+Token 全工具冒烟）、打包（干净环境按文档部署）；覆盖隔离（他人无法看到自己数据之外内容）。
- 验收标准：验收清单全绿；遗留问题登记并纳入下一迭代。
- 依赖：M6-01~06 全部；规模：L；关键文件：`docs/acceptance.md`。

---

## 4. 横切任务（贯穿各里程碑）

| 编号 | 任务 | 说明 |
|------|------|------|
| XC-01 | 测试基座与覆盖维护 | 每域交付即配套测试；覆盖率基线 80% 起；隔离测试为强制回归项。 |
| XC-02 | 文档同步 | architecture.md / limitations.md / README 与代码同步更新，禁止漂移。 |
| XC-03 | 安全巡检 | 依赖漏洞（`uv audit`）、密钥扫描（git 历史/日志）、注入面复查（svn/sql/路径）。 |
| XC-04 | 性能与规模 | RAG 响应 <1s（个人规模）、向量/DB 索引、Embedding 缓存、SQL 校验大脚本性能。 |
| XC-05 | 版本与依赖锁定 | uv.lock 维护；mcp SDK 升级评估（破坏性变更登记）；方言/存储接口演进评估。 |

---

## 5. 任务依赖总览

```
M0-01 → M0-02 → M0-03 → M0-04/M0-05 → M0-06
                    ↘                    ↘
M1: M1-01 → M1-02 → M1-03；M1-04（依赖 01/02）；M1-05（依赖 01）
    M1-06/07/08（依赖 04 及之前）
M2: M2-01 → M2-02 → M2-03、M2-04 → M2-06/M2-07；M2-05（依赖 02）；M2-08（依赖 02/03/04）
M3: M3-01 → M3-05 → M3-06 → M3-07 → M3-08 → M3-09
    M3-02 → M3-03 → M3-04；M3-08 依赖 M3-04
M4: M4-01 → M4-02 → M4-03；M4-04 → M4-05；M4-06（依赖 04）；M4-07（独立）
    M4-08（依赖 03/05/06/07）
M5: M5-01 → M5-02 → M5-03；M5-04 → M5-05
M6: M6-01 → M6-02 → M6-03；M6-04 → M6-05 → M6-06；M6-07（依赖全部）
里程碑建议顺序：M0 → M1 → M2 ‖ M3 ‖ M4 ‖ M5 → M6（M2~M5 可并行）
```

---

## 6. 进度追踪

> 每完成一项：将对应行改为 ✅ 并更新"最后更新"日期。提交信息须带任务编号。

| 编号 | 任务 | 依赖 | 状态 | 完成日期 |
|------|------|------|------|----------|
| M0-01 | 工程初始化 | - | ✅ | 2026-08-12 |
| M0-02 | 配置加载 | M0-01 | ✅ | 2026-08-12 |
| M0-03 | FastMCP stdio 起通 | M0-02 | ✅ | 2026-08-12 |
| M0-04 | hello 工具 + 统一返回 | M0-03 | ✅ | 2026-08-12 |
| M0-05 | 统一异常与日志 | M0-03 | ✅ | 2026-08-12 |
| M0-06 | pytest 基座 | M0-03 | ✅ | 2026-08-12 |
| M1-01 | DB 抽象与连接 | M0-06 | ✅ | 2026-08-12 |
| M1-02 | 数据模型 v1 | M1-01 | ✅ | 2026-08-12 |
| M1-03 | 建表与迁移 | M1-02 | ✅ | 2026-08-12 |
| M1-04 | Repository 隔离基类 | M1-02 | ✅ | 2026-08-12 |
| M1-05 | 用户与 Token 鉴权 | M1-01 | ✅ | 2026-08-12 |
| M1-06 | 审计日志 | M1-04 | ✅ | 2026-08-12 |
| M1-07 | 配置组落地 | M0-02 | ✅ | 2026-08-12 |
| M1-08 | 隔离集成测试 | M1-04 | ✅ | 2026-08-12 |
| M2-01 | sqlglot 集成与方言检测 | M1-01 | ⬜ | |
| M2-02 | DDL 解析器 | M2-01 | ⬜ | |
| M2-03 | ER 图生成 | M2-02 | ⬜ | |
| M2-04 | L1 静态校验 | M2-02 | ⬜ | |
| M2-05 | L2 真实库校验适配 | M2-02 | ⬜ | |
| M2-06 | sql_er_from_ddl 工具 | M2-03 | ⬜ | |
| M2-07 | sql_validate_script 工具 | M2-04 | ⬜ | |
| M2-08 | golden 测试与限制清单 | M2-02/03/04 | ⬜ | |
| M3-01 | 文档解析器集合 | M1-01 | ⬜ | |
| M3-02 | DocStorage 本地实现 | M1-04 | ⬜ | |
| M3-03 | 企业微信实现 | M3-02 | ⬜ | |
| M3-04 | doc 域工具 | M3-02/03 | ⬜ | |
| M3-05 | 切块器 | M3-01 | ⬜ | |
| M3-06 | Embedding 抽象 | M1-07 | ⬜ | |
| M3-07 | VectorStore + ChromaDB | M3-06 | ⬜ | |
| M3-08 | RAG 检索问答 | M3-05/06/07/04 | ⬜ | |
| M3-09 | 用户隔离与成本控制 | M3-08 | ⬜ | |
| M4-01 | svn CLI 封装 | M1-01 | ⬜ | |
| M4-02 | 凭据管理 | M4-01 | ⬜ | |
| M4-03 | svn 域工具 | M4-01/02 | ⬜ | |
| M4-04 | 需求状态机 | M1-04 | ⬜ | |
| M4-05 | 评估与上线流程 | M4-04/M2-07/M4-03 | ⬜ | |
| M4-06 | 项目进度 | M1-04 | ⬜ | |
| M4-07 | 跨实体标签 | M1-04 | ⬜ | |
| M4-08 | 追溯链路 | M4-03/05/06/07 | ⬜ | |
| M5-01 | Mermaid mindmap | M1-04 | ⬜ | |
| M5-02 | OPML 导出 | M5-01 | ⬜ | |
| M5-03 | 从文档生成大纲 | M5-01/M3 | ⬜ | |
| M5-04 | standard 模型与工具 | M1-04 | ⬜ | |
| M5-05 | 规范 Resources 注册 | M5-04 | ⬜ | |
| M6-01 | Streamable HTTP | M0-03 | ⬜ | |
| M6-02 | Token 鉴权 + 限流 | M6-01/M1-05 | ⬜ | |
| M6-03 | 反代模板 | M6-02 | ⬜ | |
| M6-04 | Docker 打包 | M1/M2/M3 | ⬜ | |
| M6-05 | 空知识库初始化 | M6-04/M1-03 | ⬜ | |
| M6-06 | 使用文档与许可 | M6-05 | ⬜ | |
| M6-07 | 端到端验收 | M6-01~06 | ⬜ | |

---

## 7. 风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| Hive/Doris 方言解析边缘用例 | ER/校验准确性 | 只承诺 DDL 子集；维护已知限制清单；必要时预规范化后再解析（M2-08） |
| 企微文档 API 成熟度/权限限制 | 文档管理主链受阻 | DocStorage 抽象隔离影响；备选"本地为主 + 企微机器人通知"（M3-03） |
| chromadb/sqlite-vec 原生依赖兼容 | 打包与平台兼容 | VectorStore 接口抽象可切 Redis/pgvector；Docker 镜像内置依赖（M6-04） |
| 多用户隔离漏洞 | 他人看到自己之外数据 | owner_id 过滤下沉 Repository/VectorStore 强制注入；隔离集成测试守门（M1-08/M3-09） |
| Python 无纯 SVN 库 | svn 能力受限 | subprocess 封装 CLI，文档要求安装 svn client；参数化传参防注入（M4-01） |
| MCP SDK 演进 | 破坏性变更 | uv.lock 锁定；升级评估登记（XC-05） |
| LLM Key 成本/缺失 | kb_ask/mindmap 不可用 | embedding 缓存降本；无 Key 时 kb_search/降级路径可用 |

---

## 8. 里程碑 DoD（Definition of Done）

- **M0**：客户端可连接并调用 hello；`pytest` 绿；配置/日志/异常统一。
- **M1**：建表幂等；owner 隔离基类+鉴权+审计；隔离测试绿。
- **M2**：三方言 ER 图 + 校验报告正确（golden 绿）；限制清单登记。
- **M3**：文档入库→问答带引用；本地/企微可切换；隔离测试绿；RAG <1s。
- **M4**：需求全流程（评估→开发→上线）可走通且可追溯；进度/标签可用。
- **M5**：导图生成/导出/从文档生成；规范资源可被客户端读取。
- **M6**：三形态全部可运行；他人按文档可独立部署空知识库；验收清单绿。
