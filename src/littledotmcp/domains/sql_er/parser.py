"""DDL 解析器（M2-02）。

基于 sqlglot 将 CREATE TABLE 解析为 Schema（Table/Column/PK/FK/comment/partition）。
支持 Hive / Doris / Oracle / MySQL 方言。解析失败抛出 ParseError（含行号提示）。

设计要点：
- sqlglot 对复杂 HiveQL 仅承诺 DDL 子集，超限 DDL 由上层预规范化（见 limitations.md）；
- 注释：优先取 sqlglot 的 column comment 属性，缺失时回退正则；Oracle 注释常写在
  表后 `COMMENT ON ...` 或列内 `COMMENT '...'`；Hive/Doris 用 `COMMENT '...'`；
- 分区：Hive `PARTITIONED BY (...)` 解析为 is_partition 列 + table.partitioned_by；
- Doris 模型（UNIQUE/AGGREGATE/DUPLICATE KEY）作为 extra 透传，不影响 ER 渲染。
"""

from __future__ import annotations

import re

import sqlglot
import sqlglot.errors
from sqlglot import exp

from .dialect import detect_dialect, normalize_dialect
from .model import Column, ForeignKey, Schema, Table


class ParseError(ValueError):
    """DDL 解析失败，携带可读原因（含行号若可定位）。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _column_comment(col_expr: exp.ColumnDef) -> str | None:
    """从列定义提取 COMMENT（CommentColumnConstraint 承载）。"""
    for con in col_expr.constraints:
        if isinstance(con.kind, exp.CommentColumnConstraint):
            lit = con.kind.this
            if lit is not None:
                return str(lit.this) if hasattr(lit, "this") else str(lit)
    return None


def _dtype_name(col_expr: exp.ColumnDef) -> str:
    """返回列类型字符串（含精度，如 varchar(255) / decimal(10,2)）。"""
    kind = col_expr.kind
    if kind is None:
        return ""
    return kind.sql(dialect=None).strip()


def _is_nullable(col_expr: exp.ColumnDef) -> bool:
    """列是否可空：存在 NOT NULL 约束则 False。"""
    for con in col_expr.constraints:
        if isinstance(con.kind, exp.NotNullColumnConstraint):
            return False
    return True


def _extract_partitioned_by(create: exp.Create, dialect: str) -> list[str]:
    """提取 Hive PARTITIONED BY 列名（PartitionedByProperty 承载）。"""
    cols: list[str] = []
    if dialect != "hive":
        return cols
    for prop in create.find_all(exp.PartitionedByProperty):
        inner = prop.this
        if isinstance(inner, exp.Schema):
            for cd in inner.expressions:
                if isinstance(cd, exp.ColumnDef):
                    cols.append(cd.name)
    return cols


def _extract_table_comment(create: exp.Create, raw_ddl: str) -> str | None:
    """提取表级 COMMENT（优先 sqlglot SchemaCommentProperty，回退正则）。"""
    comment_prop = create.find(exp.SchemaCommentProperty)
    if comment_prop is not None and comment_prop.this is not None:
        lit = comment_prop.this
        if hasattr(lit, "this"):
            return str(lit.this)
        return str(lit)
    # 兼容部分方言/书写顺序差异：`) COMMENT '...'`
    m = re.search(r"\)\s*comment\s+'((?:[^'\\]|\\.)*)'", raw_ddl, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _parse_one_table(create: exp.Create, dialect: str, raw_ddl: str) -> Table:
    """解析单条 CREATE TABLE 语句。"""
    schema = create.this
    if not isinstance(schema, exp.Schema):
        # 可能没有列定义的 CTAS / 视图，跳过结构细节
        tbl_name = schema.name if hasattr(schema, "name") else str(schema)
        return Table(name=tbl_name)

    table_name = schema.this.name if schema.this is not None else "unknown"

    partition_cols = set(_extract_partitioned_by(create, dialect))
    columns: list[Column] = []
    primary_keys: list[str] = []

    for cd in schema.expressions:
        if isinstance(cd, exp.ColumnDef):
            cname = cd.name
            dtype = _dtype_name(cd)
            nullable = _is_nullable(cd)
            comment = _column_comment(cd)
            default = None
            for con in cd.constraints:
                if isinstance(con.kind, exp.DefaultColumnConstraint):
                    default = con.kind.this.sql() if con.kind.this is not None else None
            is_pk = any(
                isinstance(con.kind, exp.PrimaryKeyColumnConstraint) for con in cd.constraints
            )
            if is_pk:
                primary_keys.append(cname)
            columns.append(
                Column(
                    name=cname,
                    dtype=dtype,
                    nullable=nullable,
                    default=default,
                    comment=comment,
                    is_partition=cname.lower() in partition_cols,
                )
            )
        elif isinstance(cd, exp.PrimaryKey):
            # 表级主键约束
            for col in cd.expressions:
                primary_keys.append(col.name)

    # 补充分区列（Hive PARTITIONED BY 不在主列列表内）
    for pname in partition_cols:
        if pname.lower() not in {c.name.lower() for c in columns}:
            columns.append(
                Column(name=pname, dtype="string", nullable=True, is_partition=True)
            )

    # 外键
    foreign_keys: list[ForeignKey] = []
    for fk in schema.find_all(exp.ForeignKey):
        cols = [c.name for c in fk.expressions]
        ref = fk.args.get("reference")
        if ref is None:
            continue
        ref_schema = ref.this
        ref_table = (
            ref_schema.this.name
            if isinstance(ref_schema, exp.Schema) and ref_schema.this is not None
            else ""
        )
        ref_cols = (
            [c.name for c in ref_schema.expressions]
            if isinstance(ref_schema, exp.Schema)
            else []
        )
        for i, c in enumerate(cols):
            foreign_keys.append(
                ForeignKey(
                    column=c,
                    ref_table=ref_table,
                    ref_column=(
                        ref_cols[i] if i < len(ref_cols) else (ref_cols[0] if ref_cols else "")
                    ),
                )
            )

    table_comment = _extract_table_comment(create, raw_ddl)
    partitioned_col_names = [c.name for c in columns if c.is_partition]

    extra: dict = {}
    # 不调用 create.sql() 生成：doris 部分属性在无 dialect 时无法序列化会抛错；
    # 直接在原始 DDL 文本中匹配 Doris 模型关键字更稳妥。
    for model_kw in ("UNIQUE KEY", "AGGREGATE KEY", "DUPLICATE KEY"):
        if model_kw in raw_ddl.upper():
            extra["doris_model"] = model_kw.title()
            break

    return Table(
        name=table_name,
        columns=columns,
        primary_keys=primary_keys,
        foreign_keys=foreign_keys,
        comment=table_comment,
        partitioned_by=partitioned_col_names,
        extra=extra,
    )


def parse_ddl(ddl: str, dialect: str | None = None) -> Schema:
    """解析一段 DDL（可能含多条 CREATE TABLE）为 Schema。

    Args:
        ddl: DDL 文本（可含多条语句、注释、空行）。
        dialect: 显式方言；为 None 时启发式检测（仍失败则报可读错误）。

    Raises:
        ParseError: 无法解析或方言无法判定。
    """
    if not ddl or not ddl.strip():
        raise ParseError("DDL 为空，请提供 CREATE TABLE 语句")

    resolved = normalize_dialect(dialect) or detect_dialect(ddl)
    if resolved is None:
        raise ParseError(
            "无法自动判定方言。请在调用时显式指定 dialect（hive/doris/oracle/mysql）。"
        )

    try:
        statements = sqlglot.parse(ddl, read=resolved)
    except sqlglot.errors.ParseError as exc:
        raise ParseError(f"[{resolved}] DDL 解析失败：{exc}") from exc

    tables: list[Table] = []
    for stmt in statements:
        if stmt is None:
            continue
        if isinstance(stmt, exp.Create) and stmt.kind == "TABLE":
            tables.append(_parse_one_table(stmt, resolved, ddl))
        # 忽略 COMMENT ON / 其他非建表语句

    if not tables:
        raise ParseError("未解析到任何 CREATE TABLE 语句")

    return Schema(dialect=resolved, tables=tables)
