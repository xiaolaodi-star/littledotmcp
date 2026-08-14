# 已知限制（Known Limits）

> 随实现持续维护。每个里程碑在此追加对应域的限制与边界说明。

## M2 SQL 域（当前）

### 解析范围
- 仅解析 `CREATE TABLE` 及其结构（列、类型、主键、外键、注释、Hive 分区）。
- 不解析：`CREATE VIEW`、CTAS（`CREATE TABLE ... AS SELECT`）、`ALTER`、`INSERT`、存储过程、`COMMENT ON TABLE/COLUMN`（Oracle 独立注释语句暂不回填到结构）。
- 多语句 DDL 批量解析：非建表语句（含注释）被忽略，不报错。

### 方言覆盖
- 支持且已 golden 测试：Hive / Doris / Oracle / MySQL。
- 方言自动检测为启发式（关键字命中），不保证 100% 准确；建议调用时显式传 `dialect`。

### 类型校验
- L1 `UNKNOWN_TYPE` 仅为 warning：未知类型不阻断，避免对扩展类型（如 Doris `DECIMALV3`）误报。
- 类型存在性对照 `KNOWN_TYPES` 白名单，非穷举；新增方言私有类型会在 warning 列出。

### Hive 复杂类型
- `ARRAY<...>` / `MAP<...>` / `STRUCT<...>` 仅识别其声明（类型字符串原样保留），不在 ER 图中展开嵌套结构。
- 外部表（`EXTERNAL TABLE`）、`STORED AS`、`TBLPROPERTIES` 仅透传，不影响 ER 渲染。

### Doris 模型
- `UNIQUE KEY` / `AGGREGATE KEY` / `DUPLICATE KEY` 仅作为 `extra.doris_model` 透传，不参与 ER 关系。

### 校验边界
- L1 为静态校验，不连接真实库；`FK_TABLE_MISSING` / `FK_COL_MISSING` 仅在同批解析到的表内核对。
- L2 真实库适配（Oracle 编译 / Hive / Doris JDBC）为可选插件，默认 `NullSqlValidator` 不执行任何外部校验。
- 行号定位：解析错误仅给出可读原因，暂不回写精确行号（sqlglot 异常不含行号）。

### 渲染
- Mermaid `erDiagram` 不支持列内联注释，列注释以行尾 `//` 备注呈现。
- 表名 / 列名含非字母数字下划线字符时，Mermaid 标识符会被归一为下划线（渲染层处理，不影响结构化数据）。

## M11 管理端（Web Console）

### 部署与运行
- 管理端在 stdio 与 http 两种模式下均随进程提供（stdio 模式由后台线程附带 HTTP 服务，http 模式由主进程直接提供），监听 `HTTP_HOST:HTTP_PORT`（默认 `0.0.0.0:8890`）。
- 管理端与 MCP 接口同端口同进程，无独立 TLS；仅限本机或可信内网，公网须前置 HTTPS 反代（见 deploy.md §3）。
- `HTTP_HOST=0.0.0.0` 启动会打印明文安全告警；无证书加密，远程暴露风险高。

### 初始化与账户
- 首个管理员仅两种途径：① 启动前设一次性 `ADMIN_BOOTSTRAP_USER/PASSWORD` 空库自动建；② 空库时浏览器 `/admin/api/setup` 表单。库非空后两种方式均失效，杜绝默认口令。
- 管理端登录态（`user_sessions` + Cookie `littledot_session`）与 MCP 用户 Token（`users.token`）完全分离，互不可代用。
- 普通用户由 admin 在管理端创建，默认 `role=user`，按 `owner_id` 隔离；越权访问返回 403。

### 能力边界
- 管理端面向业务运维视图，不暴露 MCP 工具调用；MCP 客户端能力不受管理端权限影响。
- 会话默认 12h（`ADMIN_SESSION_HOURS` 可调），超时需重新登录。
