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
