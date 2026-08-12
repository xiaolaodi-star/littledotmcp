"""L1 静态校验（M2-04）。

基于解析后的 Schema 做语义规则校验（不连真实库）：
- 重复表名 / 重复列名
- 保留字作标识符
- 类型存在性（方言已知类型）
- FK 目标表 / 列存在性
- 分区列重复定义（既当普通列又当分区列）
- 表无主键（warning，非阻断）

输出分级 [error|warning|info]，每条带行号（如可定位）或表名。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..sql_er.model import Schema, Table

# 常见 SQL 保留字（跨方言最大公约数子集，命中即报 warning）
_RESERVED = {
    "select", "from", "where", "table", "index", "order", "group", "by", "join",
    "insert", "update", "delete", "create", "drop", "alter", "view", "grant",
    "user", "level", "comment", "primary", "foreign", "key", "default", "null",
    "desc", "asc", "session", "date", "timestamp", "column", "constraint",
}

# 方言已知类型（小写），未知类型报 warning（非 error，避免误伤扩展类型）
_KNOWN_TYPES = {
    # 通用
    "int", "integer", "bigint", "smallint", "tinyint", "boolean", "bool",
    "decimal", "numeric", "float", "double", "real",
    "char", "varchar", "varchar2", "text", "string", "clob", "blob",
    "date", "datetime", "timestamp", "time", "json",
    # Hive
    "array", "map", "struct", "binary",
    # Oracle
    "number", "nclob", "nvarchar2", "raw", "long", "bfile",
    # Doris / MySQL
    "bit", "mediumint", "mediumtext", "longtext", "tinytext", "year",
}


@dataclass
class Issue:
    """单条校验问题。"""

    level: str  # error | warning | info
    code: str
    message: str
    table: str | None = None
    column: str | None = None
    line: int | None = None


@dataclass
class ValidationReport:
    """校验报告。"""

    dialect: str
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def passed(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {
            "dialect": self.dialect,
            "passed": self.passed,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [
                {
                    "level": i.level,
                    "code": i.code,
                    "message": i.message,
                    "table": i.table,
                    "column": i.column,
                    "line": i.line,
                }
                for i in self.issues
            ],
        }


def _type_base(dtype: str) -> str:
    """取类型基名（去掉精度括号）。"""
    return dtype.split("(")[0].strip().lower()


def validate(schema: Schema) -> ValidationReport:
    """对 Schema 执行 L1 静态校验，返回报告。"""
    report = ValidationReport(dialect=schema.dialect)
    seen_tables: dict[str, int] = {}

    for t in schema.tables:
        low = t.name.lower()
        if low in seen_tables:
            report.issues.append(
                Issue(
                    "error", "DUP_TABLE",
                    f"重复表名：{t.name}（首次出现于第 {seen_tables[low]} 行附近）",
                    table=t.name,
                )
            )
        else:
            seen_tables[low] = 0

        if t.name.lower() in _RESERVED:
            report.issues.append(
                Issue("warning", "RESERVED_TABLE", f"表名 {t.name} 为保留字", table=t.name)
            )

        _validate_columns(t, report)

        if not t.primary_keys:
            report.issues.append(
                Issue("warning", "NO_PK", f"表 {t.name} 未定义主键", table=t.name)
            )

    _validate_foreign_keys(schema, report)
    return report


def _validate_columns(t: Table, report: ValidationReport) -> None:
    seen_cols: dict[str, int] = {}
    part_set = {c.lower() for c in t.partitioned_by}
    for idx, col in enumerate(t.columns):
        low = col.name.lower()
        if low in seen_cols:
            report.issues.append(
                Issue(
                    "error", "DUP_COLUMN",
                    f"表 {t.name} 重复列名：{col.name}",
                    table=t.name, column=col.name,
                )
            )
        else:
            seen_cols[low] = idx

        if low in _RESERVED:
            report.issues.append(
                Issue("warning", "RESERVED_COLUMN", f"列 {t.name}.{col.name} 为保留字",
                      table=t.name, column=col.name)
            )

        base = _type_base(col.dtype)
        if base and base not in _KNOWN_TYPES:
            report.issues.append(
                Issue("warning", "UNKNOWN_TYPE",
                      f"表 {t.name}.{col.name} 未知类型 {col.dtype!r}（请确认方言支持）",
                      table=t.name, column=col.name)
            )

        if low in part_set and not col.is_partition:
            report.issues.append(
                Issue("error", "PART_COL_DUP",
                      f"表 {t.name} 列 {col.name} 既定义为普通列又出现在 PARTITIONED BY",
                      table=t.name, column=col.name)
            )


def _validate_foreign_keys(schema: Schema, report: ValidationReport) -> None:
    table_index = {t.name.lower(): t for t in schema.tables}
    for t in schema.tables:
        for fk in t.foreign_keys:
            ref = table_index.get(fk.ref_table.lower())
            if ref is None:
                report.issues.append(
                    Issue("error", "FK_TABLE_MISSING",
                          f"表 {t.name} 外键引用不存在的表 {fk.ref_table}",
                          table=t.name, column=fk.column)
                )
                continue
            if fk.ref_column and fk.ref_column.lower() not in {c.name.lower() for c in ref.columns}:
                report.issues.append(
                    Issue("error", "FK_COL_MISSING",
                          f"表 {t.name}.{fk.column} 外键引用 {fk.ref_table}.{fk.ref_column} 不存在",
                          table=t.name, column=fk.column)
                )
