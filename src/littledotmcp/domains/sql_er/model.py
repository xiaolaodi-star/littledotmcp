"""SQL ER 域数据模型（M2-02）。

解析产物统一落为 Table / Column / ForeignKey 结构，与具体方言解耦，
供 ER 图渲染与校验复用。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Column:
    """表字段。"""

    name: str
    dtype: str
    nullable: bool = True
    default: str | None = None
    comment: str | None = None
    # Hive 复杂类型 / 分区列标识
    is_partition: bool = False


@dataclass
class ForeignKey:
    """外键：本表字段 -> 目标表.目标字段。"""

    column: str
    ref_table: str
    ref_column: str


@dataclass
class Table:
    """一张表（含注释、主键、外键、分区列）。"""

    name: str
    columns: list[Column] = field(default_factory=list)
    primary_keys: list[str] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    comment: str | None = None
    # Hive 分区（与 is_partition 列互为冗余，便于渲染/校验）
    partitioned_by: list[str] = field(default_factory=list)
    # 平台特定标记：Hive 外部表 / Doris 模型 / Oracle 同义词等
    extra: dict = field(default_factory=dict)

    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


@dataclass
class Schema:
    """一次解析产出的整库结构。"""

    dialect: str
    tables: list[Table] = field(default_factory=list)

    def table_names(self) -> list[str]:
        return [t.name for t in self.tables]

    def find_table(self, name: str) -> Table | None:
        low = name.lower()
        for t in self.tables:
            if t.name.lower() == low:
                return t
        return None
